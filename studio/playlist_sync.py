"""Reconcile playlist playback from observations, not a predicted song-end instant."""
import time
from .providers import Spotify


class PlaylistSync:
    def __init__(self, conductor):
        self.c = conductor
        self.candidate = None
        self.timestamp = 0

    def usable(self, data):
        stamp = data.get('timestamp')
        if isinstance(stamp, (int, float)) and stamp > 0:
            if stamp < self.timestamp:
                return False
            self.timestamp = stamp
        # Empty Connect responses during transitions are not owner actions.
        return bool((data.get('item') or {}).get('id'))

    def stable(self, current, data):
        key = (current['id'], (data.get('item') or {}).get('id'),
               (data.get('context') or {}).get('uri'), (data.get('device') or {}).get('id'))
        now = time.monotonic()
        if not self.candidate or self.candidate[0] != key:
            self.candidate = (key, now, 1)
            return False
        self.candidate = (key, self.candidate[1], self.candidate[2] + 1)
        return self.candidate[2] >= 2

    async def adopt(self, row, data):
        c = self.c
        if (c.queue.state['current'] or {}).get('id') != row['id']:
            c.queue.finish()
            c.fallback.commit(row)
            c.queue.activate(row)
        c.observed = None
        c.progress = (data.get('progress_ms') or 0) / 1000
        c.status = 'Playing'
        c.error = ''
        c.near_end = False
        c.spotify_sample = None
        c.play_started = time.monotonic()
        c.recovery = None
        self.candidate = None
        try:
            await c.fallback.replenish()
        except Exception as e:
            c.fallback.note = str(e)

    async def poll(self, current, data):
        c = self.c
        if not current or not current.get('fallback') or not c.enabled or not c.fallback.enabled:
            return False
        device = (data.get('device') or {}).get('id')
        if c.spotify_device and device and device != c.spotify_device:
            c.failed(ValueError('Spotify moved to another device. Select the intended device and resume.'))
            return True
        playing = data.get('is_playing') is True
        if not playing:
            # Pauses stay paused. Normal end detection may still retire a song.
            return False
        raw = data.get('item') or {}
        context = (data.get('context') or {}).get('uri')
        wanted_context = 'spotify:playlist:' + current['fallback_playlist']
        matches = Spotify.matches_track(raw, current['track'])
        if matches and context in (None, wanted_context):
            self.candidate = None
            return False
        if not self.stable(current, data):
            return True
        nxt = c.queue.next_item()
        viewer = nxt and not nxt.get('fallback')
        if not matches and (not viewer or Spotify.matches_track(raw, nxt['track'])):
            # Same-playlist skips, crossfades, shuffle changes and polling gaps
            # can skip more than one row. Reconcile the actual allowed track.
            row = nxt if viewer else next((x for x in c.queue.state['items']
                if x.get('fallback') and x['track']['provider'] == 'spotify'
                and x.get('fallback_playlist') == current['fallback_playlist']
                and Spotify.matches_track(raw, x['track'])), None)
            if row and (viewer or context == wanted_context):
                try:
                    c.queue.check_track(row['track'], reviewed=True)
                except ValueError:
                    row = None
                if row:
                    async with c.lock:
                        if c.queue.state['current'] is current and c.enabled:
                            await self.adopt(row, data)
                            c.diag.add('playlist_reconciled', 'Confirmed playlist transition')
                    return True
        if matches:
            # A competing app changed context, but the song is right. Restore
            # the playlist at the confirmed position, at most once per mismatch.
            async with c.lock:
                try:
                    await c.spotify.play_playlist(current['track'], current['fallback_playlist'],
                                                  position_ms=data.get('progress_ms') or 0)
                    self.candidate = None
                except Exception as e:
                    c.schedule_recovery(current, e)
            return True
        # A viewer request always takes precedence. An outside/blocked song is
        # replaced by the next eligible row, without throwing away the playlist.
        self.candidate = None
        await c.next(expected=current['id'], spotify_state=data)
        return True
