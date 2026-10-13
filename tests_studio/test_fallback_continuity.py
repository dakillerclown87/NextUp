"""Fallback remains on its chosen playlist when Spotify advances between polls."""
import unittest
import time
from unittest.mock import patch
import test_fallback
from test_core import track, user


class ContinuityTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_fallback.FallbackTests.asyncSetUp
    asyncTearDown = test_fallback.FallbackTests.asyncTearDown
    def state(self, ident, playing=True, seconds=0):
        return {**test_fallback.FallbackTests.state(self, ident, playing, seconds),
                "device": {"id": "pc"}}

    async def miss_boundary(self, ident, *, after='outside-autoplay', elapsed=6):
        self.sp.api.return_value = self.state(ident, True, 195)
        await self.c.poll_spotify()
        self.assertFalse(self.c.near_end)
        now = time.monotonic()
        self.sp.api.return_value = self.state(after, True, 1)
        with patch('studio.playback.time.monotonic', return_value=now + elapsed):
            await self.c.poll_spotify()
            await self.c.poll_spotify()

    async def test_queue_then_multiple_fallback_tracks_stay_in_saved_playlist(self):
        self.sp.playlist.return_value = [track('f1'), track('f2'), track('f3')]
        requested = self.q.add(track('requested'), user(), ['broadcaster'], owner=True)
        await self.c.resume()
        for previous, expected in [('requested', 'f1'), ('f1', 'f2'), ('f2', 'f3'), ('f3', 'f1'), ('f1', 'f2')]:
            await self.miss_boundary(previous)
            self.assertTrue(self.c.enabled)
            self.assertEqual(self.q.state['current']['track']['id'], expected)
            self.assertTrue(self.q.state['current']['fallback'])
        self.assertEqual([x for x in self.calls if x.startswith('play:')],
                         ['play:requested','play:f1','play:f2','play:f3','play:f1','play:f2'])
        self.sp.playlist.assert_awaited_once_with(test_fallback.PLAYLIST)

    async def test_request_interrupts_fallback_then_resumes_its_cursor(self):
        self.s.save({'spotify_native_queue':True})
        await self.c.resume()
        self.q.add(track('viewer-request'), user(), ['broadcaster'], owner=True)
        await self.miss_boundary('f1')
        self.assertEqual(self.q.state['current']['track']['id'], 'viewer-request')
        await self.miss_boundary('viewer-request')
        self.assertEqual(self.q.state['current']['track']['id'], 'f2')

    async def test_repeat_off_stops_without_adopting_external_song(self):
        self.s.save({'fallback_repeat':False})
        await self.c.resume()
        await self.miss_boundary('f1')
        await self.miss_boundary('f2')
        self.assertIsNone(self.q.state['current'])
        self.assertIsNone(self.c.observed)
        self.assertEqual(self.c.status, 'Queue empty')
        self.assertEqual(self.calls[-1], 'pause:spotify')

    async def test_confirmed_outside_song_restores_saved_fallback(self):
        await self.c.resume()
        self.c.play_started -= 20
        await self.miss_boundary('f1', elapsed=1)
        self.assertTrue(self.c.enabled)
        self.assertEqual(self.q.state['current']['track']['id'], 'f2')
        self.assertEqual(self.sp.play.await_count, 2)

    async def test_explicit_pause_does_not_auto_resume_fallback(self):
        await self.c.resume()
        self.sp.api.return_value = self.state('f1', True, 195)
        await self.c.poll_spotify()
        await self.c.pause()
        now = time.monotonic()
        self.sp.api.return_value = self.state('outside', True, 1)
        with patch('studio.playback.time.monotonic', return_value=now+6):
            await self.c.poll_spotify()
        self.assertFalse(self.c.enabled)
        self.assertEqual(self.sp.play.await_count, 1)

    async def test_saved_fallback_survives_long_observation_gap(self):
        await self.c.resume()
        await self.miss_boundary('f1', elapsed=90)
        self.assertTrue(self.c.enabled)
        self.assertEqual(self.q.state['current']['track']['id'], 'f2')

    async def test_different_device_does_not_trigger_missed_end_recovery(self):
        await self.c.resume()
        self.sp.api.return_value = self.state('f1', True, 195)
        await self.c.poll_spotify()
        now = time.monotonic()
        self.c.play_started -= 20
        self.sp.api.return_value = {**self.state('outside'), 'device': {'id': 'phone'}}
        with patch('studio.playback.time.monotonic', return_value=now+6):
            await self.c.poll_spotify()
        self.assertFalse(self.c.enabled)
        self.assertEqual(self.sp.play.await_count, 1)

    async def test_failed_refresh_stops_outside_music_and_reports_error(self):
        await self.c.resume()
        self.c.fallback.invalidate()
        self.sp.playlist.side_effect = ValueError('playlist unavailable')
        with self.assertRaisesRegex(ValueError, 'playlist unavailable'):
            await self.miss_boundary('f1')
        self.assertFalse(self.c.enabled)
        self.assertEqual(self.calls[-1], 'pause:spotify')
        self.assertIsNone(self.q.state['current'])
        self.assertIn('playlist unavailable', self.c.error)

    async def test_twenty_five_tracks_refill_and_remain_ahead_of_repeat_cycle(self):
        self.sp.playlist.return_value = [track('f' + str(i)) for i in range(25)]
        await self.c.resume()
        self.assertEqual(len(self.q.state['items']), 24)
        for i in range(1, 28):
            await self.miss_boundary('f' + str((i - 1) % 25))
            self.assertEqual(self.q.state['current']['track']['id'], 'f' + str(i % 25))
            self.assertEqual(self.q.state['current']['fallback_playlist'], test_fallback.PLAYLIST)
        self.assertTrue(self.c.enabled)
        self.assertEqual(self.sp.playlist.await_count, 1)
        self.assertEqual(self.sp.play_playlist.await_count, 28)

    async def test_natural_next_in_same_playlist_is_adopted_without_restart(self):
        await self.c.resume()
        self.c.play_started -= 200
        self.sp.api.return_value = self.state('f1', True, 199)
        await self.c.poll_spotify()
        self.sp.api.return_value = {**self.state('f2', True, 0),
                                   'context': {'uri': 'spotify:playlist:' + test_fallback.PLAYLIST}}
        # Recreate a natural transition missed by a status poll.
        self.c.near_end = True
        await self.c.poll_spotify()
        await self.c.poll_spotify()
        self.assertEqual(self.q.state['current']['track']['id'], 'f2')
        self.assertEqual(self.sp.play_playlist.await_count, 1)

    async def test_requests_are_inserted_ahead_of_entire_fallback_backlog(self):
        self.s.save({'queue_limit': 5})
        self.sp.playlist.return_value = [track('f' + str(i)) for i in range(20)]
        await self.c.resume()
        r = self.q.add(track('request'), user('owner'), ['broadcaster'], owner=True)
        self.assertEqual(self.q.state['items'][0]['id'], r['id'])
        self.assertEqual(self.q.next_item()['id'], r['id'])
        self.assertEqual(len(self.q.state['items']), 20)
        await self.c.next()
        await self.c.next()
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')
