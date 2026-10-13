"""Regression checks for provider autoplay leaking into a managed handoff."""
from unittest.mock import AsyncMock, Mock
import unittest
import test_nextup
import test_fallback
from studio.providers import Spotify


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_nextup.PlaybackTests.asyncSetUp
    asyncTearDown = test_nextup.PlaybackTests.asyncTearDown
    playback = test_nextup.PlaybackTests.playback

    def activate(self):
        from test_core import track, user
        item = self.q.add(track('a'), user(), ['broadcaster'])
        self.q.activate(item)
        self.c.enabled = True
        self.c.status = 'Playing'
        self.c.bridge = Mock(last=0, send=AsyncMock())
        return item

    async def test_verified_boundary_pauses_before_starting_youtube(self):
        from test_core import track, user
        self.activate()
        requested = self.q.add(track('b', 'youtube'), user('other'), ['broadcaster'])
        calls = []
        self.spotify.pause.side_effect = lambda **kw: calls.append(('pause', kw['state']))
        self.c.bridge.send.side_effect = lambda *args: calls.append(('youtube', args))
        self.spotify.api.return_value = self.playback('a', seconds=199.7)
        await self.c.poll_spotify()
        self.assertEqual([x[0] for x in calls], ['pause', 'youtube'])
        self.assertIs(calls[0][1], self.spotify.api.return_value)
        self.assertEqual(self.q.state['current']['id'], requested['id'])

    async def test_pausing_near_end_does_not_start_next_song(self):
        self.activate()
        self.c.near_end = True
        self.spotify.api.return_value = self.playback('a', playing=False, seconds=198)
        await self.c.poll_spotify()
        self.spotify.pause.assert_not_awaited()
        self.c.bridge.send.assert_not_awaited()
        self.assertEqual(self.c.status, 'Paused')

    async def test_timer_does_not_advance_without_verified_boundary(self):
        self.activate()
        self.c.progress = 199
        self.c._progress_at -= 10
        self.spotify.api.return_value = self.playback('a', seconds=195)
        await self.c.poll_spotify()
        self.spotify.pause.assert_not_awaited()
        self.assertEqual(self.q.state['current']['track']['id'], 'a')

    async def test_adaptive_poll_only_near_managed_boundary(self):
        self.activate()
        self.c.progress = 100
        self.assertEqual(self.c.poll_delay(), 2)
        self.c.progress = 199.8
        self.assertEqual(self.c.poll_delay(), .1)
        self.c.enabled = False
        self.assertEqual(self.c.poll_delay(), 2)

    async def test_pause_failure_retains_current_and_does_not_start_youtube(self):
        from test_core import track, user
        current = self.activate()
        self.q.add(track('b', 'youtube'), user('other'), ['broadcaster'])
        self.spotify.pause.side_effect = ValueError('unconfirmed')
        self.spotify.api.return_value = self.playback('a', seconds=199.8)
        with self.assertRaises(ValueError):
            await self.c.poll_spotify()
        self.assertEqual(self.q.state['current']['id'], current['id'])
        self.c.bridge.send.assert_not_awaited()

    async def test_fresh_pause_state_avoids_extra_read_but_confirms_pause(self):
        spotify = object.__new__(Spotify)
        spotify.api = AsyncMock()
        spotify.remember_device = Mock()
        spotify.wait_state = AsyncMock()
        await spotify._pause({'is_playing': True, 'device': {'id': 'actual-device'}})
        spotify.api.assert_awaited_once_with('PUT', 'me/player/pause', params={'device_id': 'actual-device'})
        spotify.wait_state.assert_awaited_once_with(False)


class FallbackOrderTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_fallback.FallbackTests.asyncSetUp
    asyncTearDown = test_fallback.FallbackTests.asyncTearDown
    request = test_fallback.FallbackTests.request
    activate = test_fallback.FallbackTests.activate

    async def test_pause_precedes_slow_fallback_lookup(self):
        self.activate('youtube')
        async def lookup(*args, **kwargs):
            self.assertEqual(self.calls, ['pause:youtube'])
            from test_core import track
            return [track('f1')]
        self.sp.playlist.side_effect = lookup
        await self.c.ended('original')
        self.assertEqual(self.calls, ['pause:youtube', 'play:f1'])
