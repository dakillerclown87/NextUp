"""Borrow Spotify's active playlist without importing or saving its contents.

Native queue inserts retain Spotify's own context and shuffle order. The saved
return point is only used after a YouTube/direct-start detour loses that context.
"""
import asyncio
import re
import time
from .providers import Spotify


class SpotifyContinuation:
    def __init__(self, conductor):
        self.c = conductor
        self.active = False  # Never auto-resume a previous session on startup.
        self.context = conductor.queue.state.get('spotify_continuation') or {}

    def save(self):
        self.c.queue.state['spotify_continuation'] = self.context
        self.c.queue.save()

    def row(self, track):
        return {'id': 'playlist:' + track['id'], 'track': track,
                'native_playlist': True, 'user': {'id': 'playlist', 'login': 'Spotify playlist'},
                'status': 'playing', 'reviewed': True}

    @property
    def follow_current(self):
        return self.c.queue.settings.value.get('spotify_follow_current_playlist', False)

    async def capture_context(self, data):
        """Remember a return point, without importing the playlist or starting it."""
        c = self.c
        uri = (data.get('context') or {}).get('uri', '')
        if not re.fullmatch(r'spotify:playlist:[A-Za-z0-9]{22}', uri):
            return False
        configured = c.queue.settings.value.get('spotify_device')
        if configured and (data.get('device') or {}).get('id') != configured:
            return False
        track = Spotify.track(data.get('item') or {})
        upcoming = await c.spotify.api('GET', 'me/player/queue')
        entries = upcoming.get('queue') or []
        requests = [x['track'] for x in c.queue.state['items'] if not x.get('fallback')
                    and x['track']['provider'] == 'spotify']
        entry = next((x for x in entries if not any(Spotify.matches_track(x, t) for t in requests)), None)
        if not entry and not self.follow_current:
            return False
        target = Spotify.track(entry) if entry else None
        self.context = {'uri': uri, 'return_track': target,
                        'shuffle': data.get('shuffle_state', False),
                        'repeat': data.get('repeat_state', 'off'),
                        'device': (data.get('device') or {}).get('id')}
        self.active = True
        c.enabled = True
        self.adopt(self.row(track), data)
        self.save()
        return True

    async def attach(self):
        c = self.c
        if (self.active or c.queue.state['current'] or c.fallback.enabled
                or c.status == 'Paused' or c.failed_item
                or c.spotify.connected is not True
                or c.queue.settings.value['provider_mode'] == 'youtube'
                or (not c.queue.next_item() and not self.follow_current)):
            return
        async with asyncio.timeout(12):
            data = await c.spotify.api('GET', 'me/player')
            uri = (data.get('context') or {}).get('uri', '')
            if not data.get('is_playing') or not re.fullmatch(r'spotify:playlist:[A-Za-z0-9]{22}', uri):
                return
            await self.capture_context(data)

    def adopt(self, row, data):
        c = self.c
        if (c.queue.state['current'] or {}).get('id') != row['id']:
            c.queue.finish()
            c.queue.activate(row)
        c.observed = None
        c.status = 'Playing' if data.get('is_playing') else 'Paused'
        c.progress = (data.get('progress_ms') or 0) / 1000
        c.near_end = False
        c.play_started = time.monotonic()
        c.spotify_sample = None
        c.error = ''

    async def remember_next(self):
        # Called before dispatching a viewer request to Spotify, not afterwards.
        if not self.active or not (self.c.queue.state['current'] or {}).get('native_playlist'):
            return
        data = await self.c.spotify.api('GET', 'me/player/queue')
        entries = data.get('queue') or []
        if entries:
            self.context['return_track'] = Spotify.track(entries[0])
            self.save()

    def return_row(self):
        if self.active and self.context.get('return_track'):
            return self.row(self.context['return_track'])
        return None

    async def start(self, row, position_ms=0):
        self.active = True
        state = await self.c.spotify.play_playlist(
            row['track'], self.context['uri'].split(':')[-1], position_ms=position_ms,
            controls={'shuffle': self.context.get('shuffle', False), 'repeat': self.context.get('repeat', 'off')})
        if isinstance(state, dict):
            self.context["device"] = (state.get("device") or {}).get("id") or self.context.get("device")
            self.save()
        return state

    async def poll(self, current, data):
        """True means native playback was handled, without stop/start calls."""
        c = self.c
        if c.fallback.enabled:
            self.active = False
        if not self.active or not c.enabled or not current:
            return False
        device = (data.get('device') or {}).get('id')
        if device and self.context.get('device') and device != self.context['device']:
            self.active = False
            c.enabled = False
            c.error = 'Spotify moved to another device. Resume NextUp when ready.'
            return False
        item = data.get('item') or {}
        same = Spotify.matches_track(item, current['track'])
        nxt = c.queue.next_item()
        uri = (data.get('context') or {}).get('uri')
        playing = data.get('is_playing') is True
        if (self.follow_current and current.get('native_playlist') and playing
                and uri != self.context.get('uri')
                and re.fullmatch(r'spotify:playlist:[A-Za-z0-9]{22}', uri or '')):
            # An owner-selected playlist replaces the borrowed context, even
            # with pending requests. Never reload the old saved playlist here.
            async with c.lock:
                if c.queue.state['current'] is not current or not c.enabled:
                    return True
                async with asyncio.timeout(12):
                    return await self.capture_context(data)
        # A native Spotify request can cross the boundary without any pause,
        # seek, or start request from NextUp. Do not race the Spotify client.
        if same:
            if not playing:
                return False
            if nxt and (nxt['track']['provider'] != 'spotify' or not nxt.get('spotify_delivery')):
                return False
            if uri != self.context['uri'] and not nxt:
                return False
            c.observed = None
            c.status = 'Playing'
            c.progress = (data.get('progress_ms') or 0) / 1000
            return True
        if playing and nxt and nxt['track']['provider'] == 'spotify' and nxt.get('spotify_delivery') and Spotify.matches_track(item, nxt['track']):
            self.adopt(nxt, data)
            return True
        if playing and not nxt and uri == self.context['uri']:
            try:
                self.adopt(self.row(Spotify.track(item)), data)
                await self.remember_next()
            except (ValueError, KeyError, TypeError):
                return False
            return True
        if current.get('native_playlist') and not nxt and uri != self.context['uri']:
            # The owner changed the playlist, or Spotify reached its end.
            # Release it; the next request can attach to the newly chosen list.
            self.active = False
            c.queue.finish()
            c.enabled = False
            return False
        # Unrelated autoplay must not detach the remaining requests/return point.
        if playing and time.monotonic() - c.play_started >= 8:
            await c.next(expected=current['id'], spotify_state=data)
            return True
        return False
