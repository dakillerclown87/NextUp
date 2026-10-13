"""Following Spotify never imports or predicts the playlist's track list."""
import unittest
from unittest.mock import AsyncMock
import test_spotify_continuation as fixture
from test_core import track, user


class FollowCurrentPlaylistTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.ActivePlaylistTests.asyncSetUp
    asyncTearDown = fixture.ActivePlaylistTests.asyncTearDown
    setup_player = fixture.ActivePlaylistTests.setup_player
    item = staticmethod(fixture.ActivePlaylistTests.item)
    natural_next = fixture.ActivePlaylistTests.natural_next
    end_native = fixture.ActivePlaylistTests.end_native

    async def enable_follow(self):
        await self.setup_player()
        self.s.settings.save({'spotify_follow_current_playlist': True})
        self.s.spotify.playlist = AsyncMock(side_effect=AssertionError('Must not import a playlist'))
        await self.c.continuation.attach()

    async def test_follows_current_playlist_with_no_requests_or_saved_link(self):
        await self.enable_follow()
        self.assertTrue(self.c.continuation.active)
        self.assertEqual(self.s.settings.value['fallback_playlist'], '')
        self.assertEqual(self.s.queue.state['items'], [])
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p0')
        for i in range(1, 16):
            await self.end_native()
            self.assertEqual(self.s.queue.state['current']['track']['id'], 'p'+str(i))
        self.assertFalse(self.actions)
        self.s.spotify.playlist.assert_not_awaited()

    async def test_switching_playlist_in_spotify_follows_new_context_without_restart(self):
        await self.enable_follow()
        self.state.update(item=self.item('q0'), context={'uri': 'spotify:playlist:'+'Q'*22}, progress_ms=29000)
        self.native = ['q1']
        await self.c.poll_spotify()
        self.assertEqual(self.c.continuation.context['uri'], 'spotify:playlist:'+'Q'*22)
        self.assertEqual(self.c.continuation.context['return_track']['id'], 'q1')
        self.assertEqual(self.c._progress, 29)
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'q0')
        self.assertFalse(self.actions)

    async def test_request_then_youtube_then_return_to_detected_playlist(self):
        await self.enable_follow()
        req = self.s.queue.add(track('request'), user('sr'), ['broadcaster'])
        yt = self.s.queue.add(track('video', 'youtube'), user('yt'), ['broadcaster'])
        await self.c.native.flush()
        await self.end_native()
        self.assertEqual(self.s.queue.state['current']['id'], req['id'])
        self.state['progress_ms'] = 199800
        await self.c.poll_spotify()
        self.assertEqual(self.s.queue.state['current']['id'], yt['id'])
        await self.c.ended('video')
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p1')
        self.assertEqual(self.state['context']['uri'], 'spotify:playlist:'+fixture.PLAYLIST)
        await self.end_native()
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p2')

    async def test_paused_spotify_is_not_started_by_follow_mode(self):
        await self.setup_player()
        self.s.settings.save({'spotify_follow_current_playlist': True})
        self.state['is_playing'] = False
        await self.c.continuation.attach()
        self.assertFalse(self.c.continuation.active)
        self.assertFalse(self.actions)

    async def test_enabling_follow_disables_saved_fallback_without_deleting_link(self):
        await self.setup_player()
        self.s.settings.save({'fallback_enabled': True, 'fallback_playlist': fixture.PLAYLIST})
        response = await self.client.post('/api/settings', headers=self.h,
                                          json={'spotify_follow_current_playlist': True})
        self.assertEqual(response.status, 200, await response.text())
        self.assertFalse(self.s.settings.value['fallback_enabled'])
        self.assertEqual(self.s.settings.value['fallback_playlist'], fixture.PLAYLIST)
        await self.c.continuation.attach()
        self.assertTrue(self.c.continuation.active)
        self.assertFalse(self.actions)

    async def test_album_or_other_device_is_not_attached(self):
        await self.setup_player()
        self.s.settings.save({'spotify_follow_current_playlist': True, 'spotify_device': 'pc'})
        self.state['context'] = {'uri': 'spotify:album:'+'A'*22}
        await self.c.continuation.attach()
        self.assertFalse(self.c.continuation.active)
        self.state.update(context={'uri': 'spotify:playlist:'+fixture.PLAYLIST}, device={'id': 'phone'})
        await self.c.continuation.attach()
        self.assertFalse(self.c.continuation.active)
        self.assertFalse(self.actions)

    async def test_start_before_monitor_prefers_live_playlist_over_old_return_point(self):
        await self.setup_player()
        self.s.settings.save({'spotify_follow_current_playlist': True})
        self.c.continuation.context = {'uri': 'spotify:playlist:'+'O'*22,
                                       'return_track': track('old')}
        await self.c.resume()
        self.assertEqual(self.c.continuation.context['uri'], 'spotify:playlist:'+fixture.PLAYLIST)
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p0')
        self.assertEqual(self.c._progress, 10)
        self.assertFalse(self.actions)

    async def test_start_without_playing_playlist_does_not_load_old_session(self):
        await self.setup_player()
        self.s.settings.save({'spotify_follow_current_playlist': True})
        self.c.continuation.context = {'uri': 'spotify:playlist:'+'O'*22,
                                       'return_track': track('old')}
        self.state['is_playing'] = False
        await self.c.resume()
        self.assertEqual(self.c.status, 'Waiting for Spotify playlist')
        self.assertIsNone(self.s.queue.state['current'])
        self.assertFalse(self.actions)
