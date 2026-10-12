"""Pair-code request review on a separate server, with no launcher/admin routes."""
import asyncio
import contextlib
import hashlib
import json
import re
import secrets
import time
from collections import deque
from aiohttp import web
from .storage import write_private
from .settings import ROOT


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Moderation:
    def __init__(self, studio):
        self.studio = studio
        self.path = studio.data / 'moderators.json'
        self.members = json.loads(self.path.read_text()) if self.path.exists() else []
        self.pending = {}
        self.attempts = deque()
        self.runner = self.tunnel = self.reader = None
        self.public_url = ''
        self.tunnel_lock = asyncio.Lock()

    def enabled(self):
        return self.studio.settings.value['moderators_enabled']

    def snapshot(self):
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v['expires'] > now}
        return {'url': self.public_url or 'http://127.0.0.1:8890',
                'online': bool(self.public_url),
                'members': [{k: v for k, v in m.items() if k != 'token_hash'} for m in self.members],
                'pending': [{k: v for k, v in m.items() if k != 'code_hash'} for m in self.pending.values()]}

    def create(self, body):
        if not self.enabled():
            raise ValueError('Enable moderator access first.')
        name = body.get('name', '').strip()
        if not name or len(name) > 60 or any(ord(c) < 32 for c in name):
            raise ValueError('Enter a moderator name, up to 60 characters.')
        permissions = {k: body.get(k, True) for k in ('approve', 'reject')}
        if any(type(v) is not bool for v in permissions.values()) or not any(permissions.values()):
            raise ValueError('Choose Approve, Reject, or both.')
        self.snapshot()
        code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(12))
        member = {'id': secrets.token_hex(12), 'name': name, **permissions,
                  'expires': time.time() + 600, 'code_hash': digest(code)}
        self.pending[member['id']] = member
        return {'code': '-'.join(code[i:i+4] for i in range(0, 12, 4)), 'expires_seconds': 600,
                'id': member['id'], 'url': self.snapshot()['url']}

    def revoke(self, ident):
        self.pending.pop(ident, None)
        self.members = [m for m in self.members if m['id'] != ident]
        write_private(self.path, self.members)

    def pair(self, code):
        if not self.enabled():
            raise web.HTTPForbidden(text='Moderator access is disabled.')
        now = time.time()
        while self.attempts and self.attempts[0] < now - 60:
            self.attempts.popleft()
        if len(self.attempts) >= 12:
            raise web.HTTPTooManyRequests(text='Too many attempts. Try again in one minute.')
        self.attempts.append(now)
        self.snapshot()
        if not isinstance(code, str) or len(code) > 40:
            raise ValueError('Invalid or expired pairing code.')
        hashed = digest(code.upper().replace('-', '').replace(' ', ''))
        match = next((p for p in self.pending.values() if secrets.compare_digest(p['code_hash'], hashed)), None)
        if not match:
            raise ValueError('Invalid or expired pairing code.')
        token = secrets.token_urlsafe(32)
        member = {k: v for k, v in match.items() if k not in ('expires', 'code_hash')}
        member.update(token_hash=digest(token), paired=time.time())
        self.members.append(member)
        try:
            write_private(self.path, self.members)
        except Exception:
            self.members.pop()
            raise
        self.pending.pop(match['id'])
        return {'token': token, 'name': member['name']}

    def authenticate(self, request):
        if not self.enabled():
            raise web.HTTPForbidden(text='Moderator access is disabled.')
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        hashed = digest(token)
        member = next((m for m in self.members if secrets.compare_digest(m['token_hash'], hashed)), None)
        if not member:
            raise web.HTTPUnauthorized(text='Pair this browser again. Access may have been revoked.')
        return member

    def review_state(self, member):
        s = self.studio
        def row(item):
            if not item:
                return None
            return {'id': item.get('id', ''), 'status': item.get('status', 'playing'),
                    'track': {k: item.get('track', {}).get(k) for k in
                              ('title', 'artists', 'provider', 'duration', 'url', 'explicit')},
                    'requester': item.get('user', {}).get('login') or item.get('requester', ''),
                    'reason': item.get('reason', '')}
        playback = s.conductor.snapshot()
        upcoming = [row(x) for x in s.queue.state['items']]
        c = s.settings.value
        fallback = s.conductor.fallback
        provider = c['fallback_provider']
        playlist = c['fallback_playlist'] if provider == 'spotify' else c['fallback_youtube_playlist']
        loaded = bool(fallback.cached_key and fallback.cached_key[:2] == (provider, playlist))
        return {'name': member['name'], 'approve': member['approve'], 'reject': member['reject'],
                'items': [x for x in upcoming if x['status'] == 'review'],
                'queue': upcoming, 'current': row(playback['current']),
                'playback': {'status': playback['status'], 'progress': playback['progress']},
                'require_approval': c['require_approval'], 'updated_at': time.time(),
                'playlist': {'enabled': fallback.enabled, 'provider': provider, 'configured': bool(playlist),
                             'loaded': loaded, 'shuffle': c['fallback_shuffle'],
                             'tracks': [row({'track': t})['track'] for t in fallback.tracks] if loaded else []}}

    def application(self):
        @web.middleware
        async def boundary(req, handler):
            origin = req.headers.get('Origin')
            allowed = {'http://127.0.0.1:8890', 'http://localhost:8890', self.public_url}
            if origin and origin not in allowed:
                raise web.HTTPForbidden(text='Invalid origin.')
            try:
                response = await handler(req)
            except (ValueError, TypeError, KeyError):
                response = web.json_response({'error': 'Invalid request, expired code, or this request can no longer be reviewed.'}, status=400)
            response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                'Referrer-Policy': 'no-referrer', 'Content-Security-Policy':
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
            return response

        async def page(req):
            return web.FileResponse(ROOT / 'studio/static/moderator.html')

        async def asset(req):
            return web.FileResponse(ROOT / ('studio/static/moderator.' + req.match_info['ext']))

        async def pair(req):
            return web.json_response(self.pair((await req.json()).get('code')))

        async def state(req):
            member = self.authenticate(req)
            return web.json_response(self.review_state(member))

        async def review(req):
            member = self.authenticate(req)
            body = await req.json()
            action = body.get('action')
            if action not in ('approve', 'reject') or not member.get(action):
                raise web.HTTPForbidden(text='This access does not allow that action.')
            s = self.studio
            async with s.conductor.lock:
                member = self.authenticate(req)
                if not member.get(action):
                    raise web.HTTPForbidden()
                item = next((x for x in s.queue.state['items'] if x['id'] == body.get('id')), None)
                if not item or item['status'] != 'review':
                    raise ValueError('Already reviewed or removed.')
                if action == 'approve':
                    s.queue.approve(item['id'])
                else:
                    s.queue.remove(item['id'])
            s.diag.add('moderator_review', action + ' by ' + member['name'])
            if action == 'approve':
                if s.conductor.native.enabled:
                    s.background(s.conductor.native.flush())
                elif s.conductor.enabled and not s.queue.state['current']:
                    s.background(s.conductor.next(expected=''))
            return web.json_response({'ok': True})

        app = web.Application(middlewares=[boundary], client_max_size=16384)
        app.router.add_get('/', page)
        app.router.add_get('/moderator.{ext:js|css}', asset)
        app.router.add_post('/pair', pair)
        app.router.add_get('/requests', state)
        app.router.add_post('/review', review)
        return app

    async def start_server(self):
        self.runner = web.AppRunner(self.application(), access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, '127.0.0.1', 8890).start()

    async def start_tunnel(self):
        if not self.enabled():
            raise ValueError('Enable moderator access first.')
        async with self.tunnel_lock:
            if self.tunnel and self.tunnel.returncode is None and self.public_url:
                return self.public_url
            if self.tunnel and self.tunnel.returncode is None:
                self.tunnel.terminate()
                await self.tunnel.wait()
            try:
                self.tunnel = await asyncio.create_subprocess_exec('cloudflared', 'tunnel', '--url',
                    'http://127.0.0.1:8890', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            except FileNotFoundError:
                raise ValueError('Install cloudflared once, then restart NextUp to create a secure moderator link.') from None
            async def consume():
                while line := await self.tunnel.stdout.readline():
                    match = re.search(rb'https://[a-z0-9-]+\.trycloudflare\.com', line)
                    if match:
                        self.public_url = match[0].decode()
                self.public_url = ''
            self.reader = asyncio.create_task(consume())
            for _ in range(100):
                if self.public_url:
                    return self.public_url
                if self.tunnel.returncode is not None:
                    break
                await asyncio.sleep(.2)
            raise ValueError('No secure link yet. Check cloudflared and your network, then retry.')

    async def close(self):
        if self.tunnel and self.tunnel.returncode is None:
            self.tunnel.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.tunnel.wait(), 5)
            if self.tunnel.returncode is None:
                self.tunnel.kill()
        if self.reader:
            self.reader.cancel()
            await asyncio.gather(self.reader, return_exceptions=True)
        if self.runner:
            await self.runner.cleanup()
