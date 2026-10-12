"""Real user-provided catalog metadata; playback state is still simulated."""
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
import test_track_identity as fixture
from studio.providers import Spotify, PlaybackStateError
from test_spotify_continuation import PLAYLIST

RECORDINGS = json.loads((Path(__file__).parent/'fixtures/spotify_stay_relink.json').read_text())['recordings']


def metadata(ident):
    row = RECORDINGS[ident]
    return {'id': row['id'], 'name': row['name'], 'duration_ms': row['duration_ms'],
            'explicit': row['explicit'], 'is_playable': row['is_playable'],
            'linked_from': {'id': row['linked_from']} if row['linked_from'] else None,
            'external_ids': {'isrc': row['isrc']},
            'artists': [{'id': ident, 'name': name} for ident, name in zip(row['artist_ids'], row['artist_names'])]}


class RecordedRelinkTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.CatalogPlaybackTests.asyncSetUp
    asyncTearDown = fixture.CatalogPlaybackTests.asyncTearDown
    setup_player = fixture.CatalogPlaybackTests.setup_player
    setup_saved = fixture.CatalogPlaybackTests.setup_saved
    item = staticmethod(fixture.CatalogPlaybackTests.item)
    natural_next = fixture.CatalogPlaybackTests.natural_next

    async def setup_recording(self):
        await self.setup_saved()
        original = metadata(fixture.EXPECTED)
        original.update(id=fixture.EXPECTED, linked_from=None)
        old = Spotify.track(original)
        old.pop('isrc') # Actual beta.59 saved rows never stored the recording ID.
        self.s.spotify.playlist = AsyncMock(return_value=[old])
        base = self.s.spotify.api
        async def api(method, path, **kwargs):
            if path.startswith('tracks/'):
                self.assertEqual(method, 'GET')
                self.assertEqual(kwargs['params'], {'market': 'from_token'})
                return metadata(path.split('/')[-1])
            return await base(method, path, **kwargs)
        self.s.spotify.api = api
        self.state.update(item=metadata(fixture.OBSERVED), progress_ms=41000, repeat_state='off')
        return old

    async def test_real_metadata_confirms_relink_without_restarting_active_song(self):
        old = await self.setup_recording()
        writes = len(self.actions)
        state = await self.s.spotify.play_playlist(old, PLAYLIST)
        self.assertEqual(old['playback_id'], fixture.OBSERVED)
        self.assertEqual(state['progress_ms'], 41000)
        self.assertEqual(len(self.actions), writes)
        self.assertEqual(self.s.spotify.last_start_report['result'], 'confirmed')

    async def test_real_metadata_releases_pending_recovery_and_stays_synchronized(self):
        await self.setup_recording()
        await self.c.fallback.replenish()
        row = self.s.queue.next_item()
        failure = PlaybackStateError('different track', 'spotify_wrong_track', self.state)
        failure.confirmation_only = True
        self.c.schedule_recovery(row, failure)
        writes = len(self.actions)
        await self.c.retry_recovery()
        for seconds in range(42, 62):
            self.state['progress_ms'] = seconds * 1000
            await self.c.poll_spotify()
            self.assertEqual(self.c._progress, seconds)
            self.assertEqual(self.c.error, '')
            self.assertIsNone(self.c.recovery)
        self.assertEqual(len(self.actions), writes)

    async def test_real_metadata_matches_without_names_being_identical(self):
        old = await self.setup_recording()
        old['isrc'] = RECORDINGS[fixture.EXPECTED]['isrc']
        self.assertNotEqual(old['title'], metadata(fixture.OBSERVED)['name'])
        self.assertTrue(Spotify.matches_track(metadata(fixture.OBSERVED), old))
