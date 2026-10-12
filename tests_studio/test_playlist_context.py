import unittest
from unittest.mock import AsyncMock
from studio.providers import PlaybackStateError
import test_spotify_devices


class PlaylistContextTests(unittest.IsolatedAsyncioTestCase):
    setUp = test_spotify_devices.DeviceTests.setUp

    async def test_playlist_start_confirms_context_and_never_uses_album_recovery(self):
        state = {'is_playing': True, 'device': {'id': 'pc'}, 'item': {'id': 'song'},
                 'repeat_state': 'off', 'shuffle_state': False,
                 'context': {'uri': 'spotify:playlist:' + 'P' * 22}}
        self.spotify.playback_device = AsyncMock(return_value='pc')
        self.spotify.api = AsyncMock(side_effect=[{}, {}, state])
        await self.spotify.play_playlist({'id': 'song'}, 'P' * 22, position_ms=1234)
        call = self.spotify.api.await_args_list[1]
        self.assertEqual(call.args, ('PUT', 'me/player/play'))
        self.assertEqual(call.kwargs['json'], {'context_uri': 'spotify:playlist:' + 'P' * 22,
                         'offset': {'uri': 'spotify:track:song'}, 'position_ms': 1234})
        self.assertEqual(self.spotify.last_start_report['result'], 'confirmed')

    async def test_right_track_in_wrong_playlist_is_not_success(self):
        state = {'is_playing': True, 'device': {'id': 'pc'}, 'item': {'id': 'song'},
                 'repeat_state': 'off', 'context': {'uri': 'spotify:album:' + 'A' * 22}}
        self.spotify.playback_device = AsyncMock(return_value='pc')
        self.spotify.api = AsyncMock(return_value=state)
        with self.assertRaises(PlaybackStateError) as error:
            await self.spotify.play_playlist({'id': 'song'}, 'P' * 22)
        self.assertEqual(error.exception.code, 'spotify_wrong_context')
        writes = [x for x in self.spotify.api.await_args_list if x.args[0] != 'GET']
        self.assertEqual(len(writes), 1)
