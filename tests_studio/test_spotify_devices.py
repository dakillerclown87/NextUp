"""Regression coverage for saved devices and asynchronous Spotify Connect handoff."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from studio.providers import Spotify, PlaybackStateError, ServiceError
from studio.settings import Settings


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / 'settings.json')
        self.settings.save({'spotify_device': 'pc', 'spotify_device_name': 'My PC'})
        self.spotify = Spotify(Mock(), self.settings, Mock())
        self.sleep = patch('studio.providers.asyncio.sleep', new=AsyncMock())
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def test_device_survives_restart_and_partial_settings_save(self):
        self.settings.save({'theme': 'light'})
        reloaded = Settings(self.settings.path)
        self.assertEqual(reloaded.value['spotify_device'], 'pc')
        self.assertEqual(reloaded.value['spotify_device_name'], 'My PC')

    def test_failed_disk_write_does_not_change_active_settings(self):
        with patch('studio.settings.write_private', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.settings.save({'spotify_device': 'phone'})
        self.assertEqual(self.settings.value['spotify_device'], 'pc')

    async def test_slow_state_accepts_relinked_track_only_on_selected_device(self):
        wrong = {'is_playing': True, 'device': {'id': 'phone'}, 'item': {'id': 'song'}}
        right = {'is_playing': True, 'device': {'id': 'pc'},
                 'item': {'id': 'local-market-song', 'linked_from': {'id': 'song'}}}
        self.spotify.api = AsyncMock(side_effect=[wrong] * 14 + [{}, right])
        self.assertEqual(await self.spotify.wait_state(True, 'song', 'pc'), right)
        self.assertEqual(self.spotify.api.await_count, 16)

    async def test_empty_state_cannot_confirm_pause(self):
        self.spotify.api = AsyncMock(return_value={})
        with self.assertRaisesRegex(ValueError, 'no playback state'):
            await self.spotify.wait_state(False)

    async def test_wrong_device_never_confirms_play(self):
        self.spotify.api = AsyncMock(return_value={'is_playing': True, 'device': {'id': 'phone'}, 'item': {'id': 'song'}})
        with self.assertRaisesRegex(ValueError, 'different device'):
            await self.spotify.wait_state(True, 'song', 'pc')

    async def test_pause_targets_actual_device_not_saved_next_device(self):
        self.spotify.api = AsyncMock(side_effect=[{'is_playing': True, 'device': {'id': 'phone'}}, {}, {}, {'is_playing': False}])
        await self.spotify.pause()
        self.assertEqual(self.spotify.api.await_args_list[1].kwargs['params'], {'device_id': 'phone'})
        self.assertEqual(self.spotify.api.await_count, 4)

    async def test_direct_start_precedes_settings_and_needs_no_transfer(self):
        calls = []
        repeat = "context"
        async def api(method, path, **kwargs):
            nonlocal repeat
            calls.append((method, path, kwargs))
            if path == 'me/player/devices':
                return {'devices': [{'id': 'pc', 'is_active': False}]}
            if method == 'GET':
                return {'is_playing': True, 'device': {'id': 'pc'}, 'item': {'id': 'song'}, 'repeat_state': repeat}
            if path == 'me/player/repeat':
                repeat = "off"
            return {}
        self.spotify.api = AsyncMock(side_effect=api)
        await self.spotify.play({'id': 'song'})
        self.assertEqual(calls[1], ('PUT', 'me/player/play', {'params': {'device_id': 'pc'}, 'json': {'uris': ['spotify:track:song'], 'position_ms': 0}}))
        self.assertEqual(calls[2][:2], ('GET', 'me/player'))
        self.assertEqual(calls[3][:2], ('PUT', 'me/player/repeat'))
        self.assertEqual(calls[-1][:2], ('GET', 'me/player'))
        self.assertFalse(any(method == 'PUT' and path in ('me/player', 'me/player/shuffle') for method, path, _ in calls))

    async def test_missing_saved_device_does_not_fall_back_to_other_device(self):
        self.spotify.api = AsyncMock(return_value={'devices': [{'id': 'phone', 'is_active': True}]})
        with self.assertRaisesRegex(ValueError, 'saved Spotify device is unavailable'):
            await self.spotify.play({'id': 'song'})
        self.assertEqual(self.spotify.api.await_count, 1)

    async def test_restricted_device_rejected_before_commands(self):
        self.spotify.api = AsyncMock(return_value={'devices': [{'id': 'pc', 'is_restricted': True}]})
        with self.assertRaisesRegex(ValueError, 'does not allow'):
            await self.spotify.playback_device()
        self.assertEqual(self.spotify.api.await_count, 1)

    async def test_active_device_mode_resolves_current_target(self):
        self.settings.save({'spotify_device': '', 'spotify_device_name': ''})
        self.spotify.api = AsyncMock(return_value={'devices': [{'id': 'phone', 'is_active': True}, {'id': 'pc', 'is_active': False}]})
        self.assertEqual(await self.spotify.playback_device(), 'phone')

    async def test_idle_device_is_reused_after_youtube_without_transfer(self):
        self.settings.save({'spotify_device': '', 'spotify_device_name': ''})
        self.spotify.api = AsyncMock(return_value={'device': {'id': 'pc'}, 'is_playing': False})
        await self.spotify.pause()  # Remember the device before YouTube takes over.
        self.fake_player()
        await self.spotify.play({'id': 'song'})
        self.assertEqual(self.commands, [('me/player/play', {
            'params': {'device_id': 'pc'},
            'json': {'uris': ['spotify:track:song'], 'position_ms': 0}})])

    async def test_idle_fallback_never_selects_an_unknown_device(self):
        self.settings.save({'spotify_device': '', 'spotify_device_name': ''})
        self.spotify.remember_device({'device': {'id': 'gone'}})
        self.spotify.api = AsyncMock(return_value={'devices': [{'id': 'pc', 'is_active': False}]})
        with self.assertRaisesRegex(ValueError, 'No active Spotify device'):
            await self.spotify.playback_device()

    async def test_new_active_or_saved_choice_overrides_remembered_device(self):
        self.settings.save({'spotify_device': '', 'spotify_device_name': ''})
        self.spotify.remember_device({'device': {'id': 'pc'}})
        self.spotify.api = AsyncMock(return_value={'devices': [
            {'id': 'pc', 'is_active': False}, {'id': 'phone', 'is_active': True}]})
        self.assertEqual(await self.spotify.playback_device(), 'phone')
        self.settings.save({'spotify_device': 'pc'})
        self.assertEqual(await self.spotify.playback_device(), 'pc')

    async def test_slow_provider_has_an_overall_deadline_and_no_late_retry(self):
        blocked, cancelled = asyncio.Event(), asyncio.Event()
        async def api(*args, **kwargs):
            try:
                await blocked.wait()
            finally:
                cancelled.set()
        self.spotify.api = AsyncMock(side_effect=api)
        self.spotify.START_TIMEOUT = .02
        with self.assertRaises(PlaybackStateError) as raised:
            await self.spotify.play({'id': 'song'})
        self.assertEqual(raised.exception.code, 'spotify_start_timeout')
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.spotify.api.await_count, 1)

    async def test_resume_confirms_relinked_track_on_saved_device(self):
        state = {'is_playing': True, 'device': {'id': 'pc'}, 'item': {'id': 'regional', 'linked_from': {'id': 'song'}}}
        self.spotify.api = AsyncMock(side_effect=[{'devices': [{'id': 'pc', 'is_active': True}]}, state, {}, state])
        await self.spotify.resume({'id': 'song'})
        self.assertEqual(self.spotify.api.await_args_list[2].kwargs, {'params': {'device_id': 'pc'}})

    def fake_player(self, *, fail_first=False, stalled=None, late=False, error_status=None):
        self.starts = 0
        self.reads = 0
        self.commands = []
        ready = {'is_playing': True, 'device': {'id': 'pc'}, 'item': {'id': 'song'}, 'repeat_state': 'off'}
        empty = {'is_playing': False, 'device': {'id': 'pc'}, 'item': None}
        async def api(method, path, **kwargs):
            if method == 'PUT':
                self.commands.append((path, kwargs))
                if path == 'me/player/play':
                    self.starts += 1
                    if error_status and self.starts == 1:
                        e = ServiceError('Mock HTTP failure')
                        e.status = error_status
                        raise e
                return {}
            if path == 'me/player/devices':
                return {'devices': [{'id': 'pc', 'is_active': False}]}
            if path == 'tracks/song':
                return {'id': 'song', 'is_playable': True, 'album': {'uri': 'spotify:album:' + 'a' * 22}}
            self.reads += 1
            if stalled is not None:
                return stalled
            if late and self.reads > 21:
                return ready
            return empty if fail_first and self.starts == 1 else ready
        self.spotify.api = AsyncMock(side_effect=api)

    async def test_stalled_empty_player_retries_once_and_recovers(self):
        self.fake_player(fail_first=True)
        await self.spotify.play({'id': 'song'})
        self.assertEqual(self.starts, 2)
        self.assertEqual([path for path, _ in self.commands], ['me/player/play', 'me/player/play'])
        self.assertEqual(self.commands[1][1]['json'], {
            'context_uri': 'spotify:album:' + 'a' * 22,
            'offset': {'uri': 'spotify:track:song'}, 'position_ms': 0})
        self.assertEqual(self.spotify.last_start_report['method'], 'album_offset')
        self.assertTrue(self.spotify.last_start_report['track_matches'])
        self.assertNotIn('pc', str(self.spotify.last_start_report))

    async def test_successful_alternate_is_reused_for_this_device(self):
        self.fake_player(fail_first=True)
        await self.spotify.play({'id': 'song'})
        self.fake_player()
        await self.spotify.play({'id': 'song'})
        self.assertEqual(self.starts, 1)
        self.assertIn('context_uri', self.commands[0][1]['json'])

    async def test_unavailable_album_never_repeats_broken_start(self):
        self.fake_player(fail_first=True)
        original = self.spotify.api
        async def api(method, path, **kwargs):
            if path == 'tracks/song':
                return {'id': 'song', 'is_playable': False, 'album': {'uri': 'spotify:album:' + 'a' * 22}}
            return await original(method, path, **kwargs)
        self.spotify.api = AsyncMock(side_effect=api)
        with self.assertRaises(PlaybackStateError):
            await self.spotify.play({'id': 'song'})
        self.assertEqual(self.starts, 1)

    async def test_late_success_during_metadata_lookup_is_not_restarted(self):
        self.fake_player(fail_first=True)
        original = self.spotify.api
        metadata_loaded = False
        async def api(method, path, **kwargs):
            nonlocal metadata_loaded
            result = await original(method, path, **kwargs)
            if path == 'tracks/song':
                metadata_loaded = True
            elif method == 'GET' and path == 'me/player' and metadata_loaded:
                return {'device': {'id': 'pc'}, 'item': {'id': 'song'}, 'is_playing': True, 'repeat_state': 'off'}
            return result
        self.spotify.api = AsyncMock(side_effect=api)
        await self.spotify.play({'id': 'song'})
        self.assertEqual(self.starts, 1)

    async def test_resume_and_pause_have_deadlines_too(self):
        self.spotify.START_TIMEOUT = .01
        async def blocked(*args, **kwargs):
            await asyncio.Event().wait()
        self.spotify.api = AsyncMock(side_effect=blocked)
        for operation in (self.spotify.pause, self.spotify.resume):
            with self.assertRaises(PlaybackStateError):
                await operation()

    async def test_persistently_blank_client_stops_after_two_starts(self):
        self.fake_player(stalled={'device': {'id': 'pc'}, 'is_playing': False, 'item': None})
        with self.assertRaisesRegex(PlaybackStateError, 'no track loaded') as raised:
            await self.spotify.play({'id': 'song'})
        self.assertEqual(raised.exception.code, 'spotify_empty_player')
        self.assertEqual(self.starts, 2)
        self.assertEqual(len(self.commands), 2)

    async def test_late_success_does_not_restart_the_song(self):
        self.fake_player(fail_first=True, late=True)
        await self.spotify.play({'id': 'song'})
        self.assertEqual(self.starts, 1)
        self.assertEqual(len(self.commands), 1)

    async def test_different_device_does_not_trigger_recovery(self):
        self.fake_player(stalled={'device': {'id': 'phone'}, 'is_playing': True, 'item': {'id': 'song'}})
        with self.assertRaisesRegex(PlaybackStateError, 'different device'):
            await self.spotify.play({'id': 'song'})
        self.assertEqual(self.starts, 1)

    async def test_different_playing_song_does_not_trigger_recovery(self):
        self.fake_player(stalled={'device': {'id': 'pc'}, 'is_playing': True, 'item': {'id': 'other'}})
        with self.assertRaisesRegex(PlaybackStateError, 'different track'):
            await self.spotify.play({'id': 'song'})
        self.assertEqual(self.starts, 1)

    async def test_only_explicit_404_uses_transfer_fallback(self):
        self.fake_player(error_status=404)
        await self.spotify.play({'id': 'song'})
        self.assertEqual([path for path, _ in self.commands], ['me/player/play', 'me/player', 'me/player/play'])
        self.assertEqual(self.commands[1][1]['json'], {'device_ids': ['pc'], 'play': False})

    async def test_auth_permission_and_rate_limit_failures_do_not_retry(self):
        for status in (401, 403, 429):
            with self.subTest(status=status):
                self.fake_player(error_status=status)
                with self.assertRaises(ServiceError):
                    await self.spotify.play({'id': 'song'})
                self.assertEqual(self.starts, 1)
                self.assertEqual(len(self.commands), 1)

    async def test_repeat_confirmation_failure_is_distinct(self):
        self.spotify.api = AsyncMock(return_value={'is_playing': True, 'device': {'id': 'pc'}, 'item': {'id': 'song'}, 'repeat_state': 'track'})
        with self.assertRaisesRegex(PlaybackStateError, 'Repeat off') as raised:
            await self.spotify.wait_state(True, 'song', 'pc', repeat_off=True)
        self.assertEqual(raised.exception.code, 'spotify_repeat_unconfirmed')

    async def test_owner_resume_replaces_wrong_playing_song_with_one_alternate(self):
        self.fake_player(fail_first=True)
        original = self.spotify.api
        async def api(method, path, **kwargs):
            if method == 'GET' and path == 'me/player' and self.starts < 2:
                return {'device': {'id': 'pc'}, 'is_playing': True, 'item': {'id': 'other'}}
            return await original(method, path, **kwargs)
        self.spotify.api = AsyncMock(side_effect=api)
        state = await self.spotify.resume({'id': 'song'})
        self.assertEqual(state['item']['id'], 'song')
        self.assertEqual(self.starts, 2)
        self.assertIn('context_uri', self.commands[1][1]['json'])
        self.assertNotIn('me/player/next', [c[0] for c in self.commands])

    async def test_owner_retry_never_chases_playback_on_another_device(self):
        self.fake_player(stalled={'device': {'id': 'phone'}, 'is_playing': True, 'item': {'id': 'other'}})
        with self.assertRaisesRegex(PlaybackStateError, 'different device'):
            await self.spotify.play({'id': 'song'}, recover_mismatch=True)
        self.assertEqual(self.starts, 1)

    async def test_owner_retry_stops_after_two_attempts_when_wrong_track_persists(self):
        self.fake_player(stalled={'device': {'id': 'pc'}, 'is_playing': True, 'item': {'id': 'other'}})
        with self.assertRaisesRegex(PlaybackStateError, 'different track'):
            await self.spotify.play({'id': 'song'}, recover_mismatch=True)
        self.assertEqual(self.starts, 2)

    async def test_owner_retry_rechecks_late_success_before_restarting(self):
        self.fake_player(fail_first=True)
        original = self.spotify.api
        reads = 0
        async def api(method, path, **kwargs):
            nonlocal reads
            if method == 'GET' and path == 'me/player':
                reads += 1
                if reads > 7:
                    return {'device': {'id': 'pc'}, 'is_playing': True, 'item': {'id': 'song'}, 'repeat_state': 'off'}
            return await original(method, path, **kwargs)
        self.spotify.api = AsyncMock(side_effect=api)
        await self.spotify.play({'id': 'song'}, recover_mismatch=True)
        self.assertEqual(self.starts, 1)
