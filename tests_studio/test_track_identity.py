"""Permanent catalog-ID mismatches, rather than eventually-correct mock IDs.

The two Stay IDs come from the beta.59 diagnostic. Recording metadata and
Connect responses below are synthetic; these are not live-account tests.
"""
import copy
import unittest
from unittest.mock import AsyncMock, patch
import test_repeated_skips as fixtures
from test_spotify_continuation import PLAYLIST
from test_core import track, user
from studio.providers import Spotify, PlaybackStateError

EXPECTED = '21JvBMXPGJ6rpvHacAFWUO'
OBSERVED = '6kabsWWWUCKCXbBSPt4Cae'


def raw(ident, isrc='GBTEST000001', duration=233000, explicit=False):
    return {'id': ident, 'name': 'Stay', 'duration_ms': duration,
            'artists': [{'id': 'artist', 'name': 'Artist'}],
            'external_ids': {'isrc': isrc}, 'explicit': explicit}


class IdentityTests(unittest.TestCase):
    def test_same_recording_different_catalog_ids(self):
        self.assertTrue(Spotify.matches_track(raw(OBSERVED), Spotify.track(raw(EXPECTED))))

    def test_source_id_is_symmetric(self):
        t = Spotify.track({**raw(OBSERVED), 'linked_from': {'id': EXPECTED}})
        self.assertTrue(Spotify.matches_track({'id': EXPECTED}, t))

    def test_no_title_only_or_different_version_matches(self):
        expected = Spotify.track(raw(EXPECTED))
        for changed in ({'external_ids': {}}, {'external_ids': {'isrc': 'OTHER'}},
                        {'duration_ms': 250000}, {'explicit': True},
                        {'artists': [{'id': 'cover', 'name': 'Artist'}]}):
            with self.subTest(changed=changed):
                self.assertFalse(Spotify.matches_track({**raw(OBSERVED), **changed}, expected))

    def test_empty_ids_never_confirm_a_song(self):
        self.assertFalse(Spotify.matches_track({}, None))


class CatalogPlaybackTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RepeatedSkipTests.asyncSetUp
    asyncTearDown = fixtures.RepeatedSkipTests.asyncTearDown
    setup_player = fixtures.RepeatedSkipTests.setup_player
    setup_saved = fixtures.RepeatedSkipTests.setup_saved
    item = staticmethod(fixtures.RepeatedSkipTests.item)
    natural_next = fixtures.RepeatedSkipTests.natural_next

    async def substituted_player(self):
        await self.setup_saved()
        self.s.settings.save({'fallback_shuffle': True, 'fallback_repeat': False})
        tracks = [Spotify.track(raw(EXPECTED))] + [track('p'+str(i)) for i in range(1, 9)]
        self.s.spotify.playlist = AsyncMock(return_value=tracks)
        base = self.s.spotify.api
        self.metadata_reads = []
        async def api(method, path, **kwargs):
            if path.startswith('tracks/'):
                self.metadata_reads.append(path)
                ident = path.split('/')[-1]
                if ident in (EXPECTED, OBSERVED): return raw(ident)
                return self.item(ident)
            result = await base(method, path, **kwargs)
            if method == 'PUT' and path == 'me/player/play' and self.state['item']['id'] == EXPECTED:
                self.state.update(item=raw(OBSERVED), progress_ms=17500)
            return result
        self.s.spotify.api = api
        # Stable shuffled order for assertions; shuffle remains enabled in settings.
        p = patch('studio.fallback.random.shuffle', lambda values: None)
        p.start(); self.addCleanup(p.stop)

    async def test_permanent_alternate_id_starts_and_survives_more_than_two_skips(self):
        await self.substituted_player()
        await self.c.resume()
        self.assertEqual(self.s.queue.state['current']['track']['id'], EXPECTED)
        self.assertEqual(self.c._progress, 17.5)
        for second in range(18, 28):
            self.state['progress_ms'] = second * 1000
            await self.c.poll_spotify()
            self.assertEqual(self.c._progress, second)
            self.assertEqual(self.c.error, '')
        for _ in range(6):
            response = await self.client.post('/api/playback', headers=self.h, json={'action': 'next'})
            self.assertEqual(response.status, 200, await response.text())
            self.assertIsNone(self.c.recovery)
            self.assertEqual(self.c.error, '')
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p6')
        self.assertTrue(self.c.enabled)
        self.assertLessEqual(len(self.metadata_reads), 20)

    async def test_old_saved_row_without_recording_metadata_recovers_without_restarting(self):
        await self.substituted_player()
        await self.c.fallback.replenish()
        target = self.s.queue.next_item()
        target['track'].pop('isrc', None)
        self.state.update(item=raw(OBSERVED), progress_ms=42000)
        error = PlaybackStateError('Mismatch', 'spotify_wrong_track', self.state)
        error.confirmation_only = True
        self.c.schedule_recovery(target, error)
        writes = len(self.actions)
        await self.c.retry_recovery()
        self.assertIsNone(self.c.recovery)
        self.assertEqual(self.c.error, '')
        self.assertEqual(self.c._progress, 42)
        self.assertEqual(len(self.actions), writes)
        await self.c.poll_spotify()
        self.assertEqual(self.s.queue.state['current']['track']['id'], EXPECTED)

    async def test_unknown_track_times_out_without_marking_request_played_or_restarting(self):
        await self.setup_saved()
        target = self.s.queue.add(track(EXPECTED), user('viewer'), ['broadcaster'])
        self.state.update(item=raw(OBSERVED, 'OTHER'), progress_ms=42000)
        error = PlaybackStateError('Mismatch', 'spotify_wrong_track', self.state)
        error.confirmation_only = True
        self.c.schedule_recovery(target, error)
        self.c.recovery['deadline'] = 0
        writes = len(self.actions)
        await self.c.retry_recovery()
        self.assertIsNone(self.c.recovery)
        self.assertFalse(self.c.enabled)
        self.assertIn(target, self.s.queue.state['items'])
        self.assertIsNone(self.s.queue.state['current'])
        self.assertEqual(self.c.display_current()['track']['id'], OBSERVED)
        self.assertEqual(len(self.actions), writes)

    async def test_equivalent_id_does_not_accept_wrong_device_or_context(self):
        await self.substituted_player()
        await self.c.fallback.replenish()
        target = self.s.queue.next_item()
        self.state.update(item=raw(OBSERVED))
        error = PlaybackStateError('Mismatch', 'spotify_wrong_track', self.state)
        error.confirmation_only = True
        self.c.schedule_recovery(target, error)
        for device, context in [('phone', 'spotify:playlist:'+PLAYLIST), ('pc', 'spotify:album:other')]:
            self.state.update(device={'id': device}, context={'uri': context})
            await self.c.retry_recovery()
            self.assertIsNotNone(self.c.recovery)
            self.assertIsNone(self.s.queue.state['current'])

    async def test_saved_old_id_already_playing_is_not_reset_during_preflight(self):
        await self.substituted_player()
        expected = Spotify.track(raw(EXPECTED))
        expected.pop('isrc')
        self.state.update(item=raw(OBSERVED), progress_ms=57000, repeat_state='off')
        writes = len(self.actions)
        result = await self.s.spotify.play_playlist(expected, PLAYLIST)
        self.assertEqual(result['progress_ms'], 57000)
        self.assertEqual(len(self.actions), writes)
        self.assertEqual(expected['playback_id'], OBSERVED)

    async def test_equivalent_recording_then_youtube_then_request_then_fallback(self):
        await self.substituted_player()
        await self.c.resume()
        youtube = self.s.queue.add(track('abcdefghijk', 'youtube'), user('yt'), ['broadcaster'])
        request = self.s.queue.add(track('requested'), user('sr'), ['broadcaster'])
        await self.c.next(manual=True)
        self.assertEqual(self.s.queue.state['current']['id'], youtube['id'])
        self.assertFalse(self.state['is_playing'])
        await self.c.ended('abcdefghijk')
        self.assertEqual(self.s.queue.state['current']['id'], request['id'])
        await self.c.next(manual=True)
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p1')
        self.assertEqual(self.state['context']['uri'], 'spotify:playlist:'+PLAYLIST)
        self.assertIsNone(self.c.recovery)

    async def test_sparse_player_metadata_verifies_once_then_uses_cached_identity(self):
        await self.substituted_player()
        expected = Spotify.track(raw(EXPECTED))
        expected.pop('isrc')
        observed = {'id': OBSERVED}
        self.assertTrue(await self.s.spotify.verify_track(observed, expected))
        self.assertEqual(len(self.metadata_reads), 2)
        for _ in range(20):
            self.assertTrue(await self.s.spotify.verify_track(observed, expected))
        self.assertEqual(len(self.metadata_reads), 2)

