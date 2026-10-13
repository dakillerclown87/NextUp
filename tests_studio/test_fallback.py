import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from studio.playback import Conductor
from studio.queue import Queue
from studio.settings import Settings, validate
from test_core import track, user

PLAYLIST = 'A' * 22

class FallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Settings(Path(self.tmp.name) / 'settings.json')
        self.s.save({'fallback_enabled': True, 'fallback_playlist': PLAYLIST,
                     'fallback_shuffle': False})
        self.q = Queue(':memory:', self.s)
        self.calls = []
        self.sp = Mock(connected=True)
        self.sp.playlist = AsyncMock(return_value=[track('f1'), track('f2')])
        self.sp.api = AsyncMock(return_value={})
        self.sp.verify_track = AsyncMock(return_value=False)
        self.sp.playback_device = AsyncMock(return_value='pc')
        self.sp.play = AsyncMock(side_effect=lambda t, **kwargs:self.calls.append('play:' + t['id']))
        self.sp.pause = AsyncMock(side_effect=lambda **_:self.calls.append('pause:spotify'))
        self.sp.resume = AsyncMock()
        async def playlist_play(t, playlist, position_ms=0):
            if position_ms:
                await self.sp.resume(t)
            else:
                await self.sp.play(t)
        self.sp.play_playlist = AsyncMock(side_effect=playlist_play)
        self.yt = Mock(last=0)
        self.yt.send = AsyncMock(side_effect=lambda a,*_:self.calls.append(a + ':youtube'))
        self.c = Conductor(self.q, self.sp, self.yt, Mock())

    async def asyncTearDown(self):
        self.q.db.close()
        self.tmp.cleanup()

    def request(self, ident='r', provider='spotify'):
        return self.q.add(track(ident, provider), user(ident), ['broadcaster'])

    def activate(self, provider='spotify'):
        item = self.request('original', provider)
        self.q.activate(item)
        self.c.enabled = True
        return item

    def state(self, ident, playing=True, seconds=0):
        return {'is_playing': playing, 'progress_ms': seconds * 1000,
                'item': {'id': ident, 'name': ident, 'artists': [{'id': 'a', 'name': 'Artist'}],
                         'duration_ms': 200000}}

    async def test_youtube_end_starts_spotify_after_pause_and_has_no_viewer_charge(self):
        item = self.activate('youtube')
        counts = dict(self.q.state['counts'])
        await self.c.ended(item['track']['id'])
        self.assertEqual(self.calls, ['pause:youtube', 'play:f1'])
        self.assertTrue(self.c.snapshot()['fallback_active'])
        self.assertEqual(self.q.state['counts'], counts)
        self.assertEqual([x['track']['id'] for x in self.q.state['items']], ['f2'])
        self.assertEqual(self.q.state['settlements'], [])
        self.assertEqual(self.c.display_current()['user']['login'], 'Fallback playlist')

    async def test_spotify_end_holds_before_loading_fallback(self):
        self.activate()
        self.c.near_end = True
        self.sp.api.return_value = self.state('original', False, 200)
        await self.c.poll_spotify()
        self.assertEqual(self.calls, ['pause:spotify', 'play:f1'])
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')

    async def test_requests_take_priority_and_fallback_resumes_at_next_track(self):
        await self.c.resume()
        r = self.request('viewer', 'youtube')
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')
        await self.c.next()
        self.assertEqual(self.q.state['current']['id'], r['id'])
        self.assertEqual(self.calls[-2:], ['pause:spotify', 'play:youtube'])
        await self.c.ended('viewer')
        self.assertEqual(self.q.state['current']['track']['id'], 'f2')
        self.assertEqual(self.sp.playlist.await_count, 1)

    async def test_pause_prevents_automatic_advancement_and_resume_keeps_track(self):
        await self.c.resume()
        item = self.q.state['current']
        await self.c.pause()
        await self.c.next(expected=item['id'])
        self.assertEqual(self.sp.play.await_count, 1)
        await self.c.resume()
        self.sp.resume.assert_awaited_once()
        self.assertEqual(self.q.state['current']['id'], item['id'])

    async def test_repeat_and_single_pass_exhaustion(self):
        await self.c.resume();await self.c.next();await self.c.next()
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')
        self.s.save({'fallback_repeat': False})
        await self.c.next();await self.c.next()
        self.assertEqual(self.c.status, 'Queue empty')
        self.assertIn('finished', self.c.snapshot()['fallback_note'])
        self.assertIsNone(self.q.state['current'])

    async def test_shuffle_does_not_repeat_until_cycle_exhausted(self):
        self.s.save({'fallback_shuffle': True})
        seen = []
        for _ in range(5):
            await self.c.next()
            seen.append(self.q.state['current']['track']['id'])
        self.assertTrue(all(a != b for a,b in zip(seen,seen[1:])))

    async def test_rules_apply_and_rule_changes_are_rechecked(self):
        explicit = {**track('bad'), 'explicit': True}
        long = {**track('long'), 'duration': 400}
        blocked = {**track('blocked'), 'artists': ['Blocked']}
        unknown = {**track('unknown'), 'explicit': None}
        self.sp.playlist.return_value = [explicit, long, blocked, track('ok')]
        self.s.save({'blocked_artists': ['Blocked']})
        await self.c.resume()
        self.assertEqual(self.q.state['current']['track']['id'], 'ok')
        self.s.save({'blocked_tracks': ['ok']})
        with self.assertRaisesRegex(ValueError, 'no playable'):
            await self.c.next()
        self.assertEqual(self.c.status, 'Needs attention')
        self.assertEqual(self.sp.play.await_count, 1)

    async def test_failed_fallback_start_does_not_advance_cursor_or_spam(self):
        self.sp.play.side_effect = ValueError('offline')
        with self.assertRaises(ValueError):await self.c.resume()
        self.assertFalse(self.c.enabled)
        self.assertNotIn('fallback_cursor', self.q.state)
        self.assertEqual([x['track']['id'] for x in self.q.state['items']], ['f1','f2'])
        self.sp.play.side_effect = None
        await self.c.resume()
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')

    async def test_failed_youtube_pause_keeps_source_and_never_starts_spotify(self):
        item = self.activate('youtube')
        self.yt.send.side_effect = ValueError('pause failed')
        with self.assertRaises(ValueError):await self.c.ended('original')
        self.assertEqual(self.q.state['current']['id'], item['id'])
        self.sp.play.assert_not_awaited()

    async def test_disabled_and_youtube_only_do_not_load_or_start_fallback(self):
        for settings in ({'fallback_enabled': False}, {'fallback_enabled': True,'provider_mode':'youtube'}):
            self.s.save(settings)
            await self.c.resume()
            self.assertEqual(self.c.status, 'Queue empty')
        self.sp.playlist.assert_not_awaited()

    async def test_turning_off_allows_current_to_finish_then_stops(self):
        await self.c.resume()
        self.s.save({'fallback_enabled': False})
        await self.c.next()
        self.assertIsNone(self.q.state['current'])
        self.assertEqual(self.sp.play.await_count, 1)

    async def test_unavailable_playlist_does_not_consume_request_or_retry(self):
        self.sp.playlist.side_effect = ValueError('playlist inaccessible')
        with self.assertRaisesRegex(ValueError, 'inaccessible'):await self.c.resume()
        self.assertFalse(self.c.enabled)
        self.assertEqual(self.c.status, 'Needs attention')
        r = self.request()
        await self.c.resume()
        self.assertEqual(self.q.state['current']['id'], r['id'])
        self.assertEqual(self.sp.playlist.await_count, 2)  # bounded prefetch after the request starts
        self.assertTrue(self.c.enabled)

    async def test_cursor_persists_without_restoring_fallback_as_request(self):
        path = Path(self.tmp.name)/'queue.db'
        q = Queue(path, self.s)
        c = Conductor(q, self.sp, self.yt, Mock())
        await c.resume();q.db.close()
        q = Queue(path, self.s)
        try:
            self.assertIsNone(q.state['current'])
            self.assertEqual(q.state['items'], [])
            c = Conductor(q, self.sp, self.yt, Mock())
            self.assertFalse(c.enabled)
            await c.resume()
            self.assertEqual(q.state['current']['track']['id'], 'f2')
        finally:q.db.close()

    async def test_native_empty_start_and_natural_end(self):
        self.s.save({'spotify_native_queue':True,'provider_mode':'spotify'})
        await self.c.resume()
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')
        self.sp.api.return_value = self.state('f1', False, 200)
        await self.c.poll_spotify()
        self.assertEqual(self.q.state['current']['track']['id'], 'f2')

    async def test_native_end_overrides_spotify_autoplay_with_selected_fallback(self):
        self.s.save({'spotify_native_queue':True,'provider_mode':'mixed'})
        await self.c.resume()
        self.c.near_end=True
        self.sp.api.return_value=self.state('unrelated-autoplay',True,1)
        await self.c.poll_spotify()
        await self.c.poll_spotify()
        self.assertEqual(self.q.state['current']['track']['id'],'f2')
        self.assertEqual(self.calls[-2:],['pause:spotify','play:f2'])

    async def test_native_pause_does_not_restart_fallback(self):
        self.s.save({'spotify_native_queue':True,'provider_mode':'mixed'})
        await self.c.resume();await self.c.pause()
        self.sp.api.return_value=self.state('f1',False,200)
        await self.c.poll_spotify()
        self.assertEqual(self.sp.play.await_count,1)
        self.assertFalse(self.c.enabled)

class FallbackSettingsTests(unittest.TestCase):
    def test_playlist_link_normalization_and_settings_validation(self):
        for value in (PLAYLIST,'spotify:playlist:'+PLAYLIST,'https://open.spotify.com/playlist/'+PLAYLIST+'?si=test','https://open.spotify.com/intl-es/playlist/'+PLAYLIST):
            self.assertEqual(validate({'fallback_playlist': value})['fallback_playlist'], PLAYLIST)
        for value in ('bad','https://evil.test/playlist/'+PLAYLIST,'https://open.spotify.com/track/'+PLAYLIST):
            with self.assertRaises(ValueError):validate({'fallback_playlist':value})
        with self.assertRaises(ValueError):validate({'fallback_enabled':True})
        with self.assertRaises(ValueError):validate({'fallback_repeat':'false'})
