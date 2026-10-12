import asyncio
import unittest
from unittest.mock import AsyncMock
from studio.providers import Spotify, ServiceError
import test_fallback
import test_service

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_fallback.FallbackTests.asyncSetUp
    asyncTearDown = test_fallback.FallbackTests.asyncTearDown
    request = test_fallback.FallbackTests.request
    activate = test_fallback.FallbackTests.activate

    async def test_failed_load_after_end_retries_playlist_not_finished_song(self):
        self.activate('youtube')
        self.sp.playlist.side_effect = ValueError('Spotify playlist access denied')
        with self.assertRaisesRegex(ValueError, 'access denied'):
            await self.c.ended('original')
        self.assertIsNone(self.q.state['current'])
        self.assertEqual(self.q.state['history'][0]['track']['id'], 'original')
        self.assertIn('access denied', self.c.snapshot()['fallback_note'])
        self.sp.playlist.side_effect = None
        await self.c.resume()
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')
        self.sp.resume.assert_not_awaited()
        self.assertEqual(len(self.q.state['history']), 1)

    async def test_check_load_does_not_consume_cursor_or_play(self):
        tracks = await self.c.fallback.load(force=True)
        self.assertEqual(len(tracks), 2)
        self.assertIn('2 allowed', self.c.fallback.note)
        self.assertNotIn('fallback_cursors', self.q.state)
        self.sp.play.assert_not_awaited()
        await self.c.resume()
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')

class CheckAPITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_service.ServiceTests.asyncSetUp
    asyncTearDown = test_service.ServiceTests.asyncTearDown

    async def test_check_returns_actionable_access_error_and_save_retries_idle_failure(self):
        self.s.settings.save({'fallback_enabled': True, 'fallback_playlist':'A'*22})
        self.s.conductor.fallback.spotify = type('SP', (), {'connected':True, 'playlist':AsyncMock(side_effect=ValueError('Spotify denied access (HTTP 403)'))})()
        r = await self.client.post('/api/fallback-check', headers=self.h, json={})
        self.assertEqual(r.status, 400)
        self.assertIn('HTTP 403', (await r.json())['error'])
        self.assertIn('HTTP 403', self.s.conductor.snapshot()['fallback_note'])
        self.s.conductor.status = 'Needs attention'
        self.s.conductor.resume = AsyncMock()
        r = await self.client.post('/api/settings', headers=self.h, json={'fallback_playlist':'B'*22})
        self.assertEqual(r.status, 200)
        await asyncio.sleep(0)
        self.s.conductor.resume.assert_awaited_once()

class SpotifyPlaylistTests(unittest.IsolatedAsyncioTestCase):
    async def test_403_does_not_suggest_device_and_does_not_try_alternate_endpoint(self):
        sp = object.__new__(Spotify)
        error = ServiceError('forbidden'); error.status = 403
        sp.api = AsyncMock(side_effect=error)
        with self.assertRaisesRegex(ServiceError, 'owned by the connected Spotify account'):
            await sp.playlist('A'*22)
        self.assertEqual(sp.api.await_count, 1)

    async def test_empty_page_with_next_stops_and_reports_no_music(self):
        sp = object.__new__(Spotify)
        sp.api = AsyncMock(return_value={'items': [], 'next':'more'})
        with self.assertRaisesRegex(ValueError, 'no playable music'):
            await sp.playlist('A'*22)
        self.assertEqual(sp.api.await_count, 1)

    async def test_unavailable_entries_count_toward_scan_limit(self):
        sp = object.__new__(Spotify)
        sp.api = AsyncMock(return_value={'items': [None, {'item':None}]*25, 'next':'more'})
        with self.assertRaisesRegex(ValueError, 'no playable music'):
            await sp.playlist('A'*22)
        self.assertEqual(sp.api.await_count, 200)
