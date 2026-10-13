"""Scoped, origin-bound Chrome player connection; no admin credentials reach Chrome."""
import asyncio
import contextlib
import re
import secrets
import time
from aiohttp import web, WSMsgType


def extension_origin(origin):
    """Accept extension origins only; pairing tokens remain bound to exact origin."""
    return isinstance(origin,str) and bool(re.fullmatch(
        r'(?:chrome-extension://[a-p]{32}|moz-extension://[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})',origin))


class PlayerChoice:
    def __init__(self, settings, embedded, chrome):
        self.settings, self.embedded, self.chrome = settings, embedded, chrome

    @property
    def selected(self):
        return self.chrome if self.settings.value['youtube_player_mode'] == 'chrome' else self.embedded

    @property
    def last(self):
        return self.selected.last

    async def send(self, action, track=None):
        return await self.selected.send(action, track)


class ChromePlayer:
    def __init__(self, studio):
        self.studio = studio
        self.ws = None
        self.last = 0
        self.code = ''
        self.expires = 0
        self.command = None
        self.waiter = None
        self.generation = ''
        self.track = ''
        self.details = None
        self.started = False
        self.peer_port = 0
        self.wait_reason = ''

    def audio_peer(self):
        return self.peer_port if self.connected else 0

    @property
    def connected(self):
        return self.ws is not None and not self.ws.closed

    def pairing_code(self):
        self.code = secrets.token_hex(16)
        self.expires = time.monotonic() + 180
        return self.code

    def authenticate(self, origin, message):
        if not isinstance(message, dict):
            raise ValueError('Invalid handshake.')
        if not extension_origin(origin):
            raise ValueError('Open the NextUp extension to pair.')
        if message.get('type') == 'pair':
            if not self.code or time.monotonic() > self.expires or not secrets.compare_digest(str(message.get('code', '')), self.code):
                raise ValueError('Pairing code is invalid or expired. Generate a new code in NextUp.')
            self.code = ''
            token = secrets.token_urlsafe(32)
            self.studio.vault.put('chrome', {'origin': origin, 'token': token})
            return token
        saved = self.studio.vault.read().get('chrome', {})
        if (message.get('type') != 'auth' or saved.get('origin') != origin
                or not saved.get('token') or not secrets.compare_digest(str(message.get('token', '')), saved['token'])):
            raise ValueError('Pair this extension with NextUp again.')
        return None

    async def close(self):
        ws = self.ws
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.send_json({'type': 'stop'})
                await ws.close()
        self.last = 0

    async def revoke(self):
        self.code = ''
        self.studio.vault.put('chrome', None)
        await self.close()

    async def send(self, action, track=None):
        if not self.connected or time.monotonic() - self.last > 8:
            raise ValueError('Connect the browser extension and choose a YouTube tab first.')
        if self.waiter is not None:
            raise ValueError('A Browser playback command is still pending.')
        seq = secrets.token_hex(16)
        if action == 'play':
            self.generation = seq
            self.track = track['id']
            self.details = track
            self.started = False
        if action == 'resume':
            current = self.studio.queue.state['current']
            self.details = self.details or (current['track'] if current else None)
            if not self.details:
                raise ValueError('No browser track to resume. Start the queue again.')
            self.track = self.details['id']
            self.generation = self.generation or seq
            track = self.details
        command = {'type': 'command', 'action': action, 'seq': seq,
                   'generation': self.generation, 'track': track}
        self.command = command
        self.wait_reason = ''
        self.waiter = asyncio.get_running_loop().create_future()
        confirmed = False
        try:
            await self.ws.send_json(command)
            # Ads and initial page loading may take time. Never acknowledge early.
            await asyncio.wait_for(self.waiter, 120 if action == 'play' else 15)
            confirmed = True
        except asyncio.TimeoutError:
            reasons = {'tab_script': 'The extension cannot reach the YouTube player. Reload the NextUp extension, refresh the selected YouTube tab, then retry.', 'ad': 'YouTube is still showing an advertisement. Let it finish in the selected tab, then retry.', 'player_missing': 'The selected YouTube page has no playable video yet. Finish any sign-in or consent in that tab, then retry.', 'loading': 'YouTube has not started the requested video. Check the selected tab for buffering or a Play button, then retry.'}
            raise ValueError(reasons.get(self.wait_reason, 'The browser did not confirm playback. Refresh the selected YouTube tab and check its player, then retry.')) from None
        finally:
            self.command = None
            self.waiter = None
            if self.connected:
                with contextlib.suppress(Exception):
                    await self.ws.send_json({'type': 'cancel', 'seq': seq, 'generation': self.generation, 'failed': not confirmed})

    def receive(self, message):
        kind = message.get('type')
        if kind == 'heartbeat':
            self.last = time.monotonic() if message.get('ready') is True else 0
            return
        if self.studio.settings.value['youtube_player_mode'] != 'chrome':
            return
        if kind == 'waiting':
            if self.command and message.get('seq') == self.command['seq'] and message.get('reason') in ('tab_script', 'ad', 'player_missing', 'loading'):
                self.wait_reason = message['reason']
            return
        if kind == 'ack':
            if not self.command or message.get('seq') != self.command['seq'] or self.waiter.done():
                return
            if message.get('ok') is True:
                if self.command['action'] in ('play', 'resume'):
                    self.started = True
                self.waiter.set_result(True)
            else:
                # Only fixed messages, not arbitrary page text or credentials.
                reason = message.get('reason')
                messages = {'autoplay': 'Click Play in the selected YouTube tab, then retry.',
                            'unavailable': 'YouTube cannot play this video in this browser. Check the tab for the reason.',
                            'tab_closed': 'The selected YouTube tab was closed or navigated away.',
                            'changed': 'The selected YouTube tab changed videos. Retry the queue.'}
                self.waiter.set_exception(ValueError(messages.get(reason, 'The browser could not confirm the playback command. Check its YouTube tab.')))
            return
        if message.get('generation') != self.generation or not self.started:
            return
        c = self.studio.queue.state['current']
        if not c or c['track']['provider'] != 'youtube' or c['track']['id'] != self.track:
            return
        if kind == 'state':
            value = message.get('seconds')
            if type(value) in (int, float) and 0 <= value <= 7200:
                if (type(message.get('playing')) is bool and not message.get('ended')
                        and not self.command and not self.studio.conductor.lock.locked()
                        and not self.studio.conductor.error):
                    self.studio.conductor.status = 'Playing' if message['playing'] else 'Paused'
                self.studio.conductor.progress = value
        elif kind == 'ended' and not self.command and self.studio.conductor.enabled:
            # A final paused/buffering report can arrive before ended. Display
            # status is not queue intent; explicit Pause disables the conductor.
            self.started = False
            async def advance():
                with contextlib.suppress(Exception):
                    await self.studio.conductor.next(expected=c['id'])
            self.studio.background(advance())
        elif kind == 'lost':
            self.started = False
            self.studio.conductor.failed(ValueError('The browser player lost its selected YouTube video. Check the tab and retry.'))

    async def handle(self, req):
        ws = web.WebSocketResponse(max_msg_size=8192, heartbeat=5)
        await ws.prepare(req)
        owns = False
        try:
            first = await asyncio.wait_for(ws.receive_json(), 5)
            if self.connected:
                raise ValueError('Another browser connection is active. Disconnect it before pairing a different browser.')
            token = self.authenticate(req.headers.get('Origin', ''), first)
            self.ws = ws
            peer=req.transport.get_extra_info('peername') if req.transport else None
            self.peer_port=peer[1] if peer and peer[0]=='127.0.0.1' else 0
            owns = True
            await ws.send_json({'type': 'authenticated', 'token': token})
            async for item in ws:
                if item.type != WSMsgType.TEXT:
                    continue
                data = item.json()
                if isinstance(data, dict):
                    self.receive(data)
        except (ValueError, TypeError, asyncio.TimeoutError):
            with contextlib.suppress(Exception):
                await ws.send_json({'type': 'error', 'message': 'Connection rejected. Close other NextUp extension connections, then generate a fresh pairing code.'})
        finally:
            if owns and self.ws is ws:
                self.ws = None
                self.peer_port = 0
                self.last = 0
                if self.waiter and not self.waiter.done():
                    self.waiter.set_exception(ValueError('The browser disconnected before confirming playback.'))
                c = self.studio.queue.state['current']
                if c and c['track']['provider'] == 'youtube' and self.studio.settings.value['youtube_player_mode'] == 'chrome':
                    self.studio.conductor.failed(ValueError('The browser disconnected. Reconnect its extension before resuming.'))
            await ws.close()
        return ws
