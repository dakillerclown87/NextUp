"""App links submit directly; name searches remain non-mutating."""
import unittest
from unittest.mock import AsyncMock
import test_service
from test_core import track

class SongInputTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_service.ServiceTests.asyncSetUp
    asyncTearDown = test_service.ServiceTests.asyncTearDown

    async def send(self, text, provider='spotify'):
        r = await self.client.post('/api/song-input', headers=self.h, json={'text':text,'provider':provider})
        return r.status, await r.json()

    async def test_spotify_then_youtube_links_ignore_search_picker(self):
        self.s.settings.save({'block_explicit':False})
        self.s.spotify.resolve = AsyncMock(return_value=track('a'*22))
        self.s.youtube.resolve = AsyncMock(return_value=track('abcdefghijk','youtube'))
        self.s.spotify.search = AsyncMock()
        self.s.youtube.search = AsyncMock()
        status,first = await self.send('https://open.spotify.com/track/'+'a'*22, 'youtube')
        self.assertEqual(status,200)
        status,second = await self.send(' https://youtu.be/abcdefghijk?si=shared ', 'spotify')
        self.assertEqual(status,200)
        self.assertEqual([x['track']['provider'] for x in self.s.queue.state['items']],['spotify','youtube'])
        self.assertEqual(second['item']['track']['provider'],'youtube')
        self.s.youtube.resolve.assert_awaited_once_with('abcdefghijk')
        self.s.spotify.search.assert_not_awaited();self.s.youtube.search.assert_not_awaited()

    async def test_name_search_uses_selected_source_without_queuing(self):
        self.s.youtube.search=AsyncMock(return_value=[track('abcdefghijk','youtube')])
        status,data=await self.send('Artist Song','youtube')
        self.assertEqual(status,200);self.assertEqual(len(data['tracks']),1)
        self.assertFalse(self.s.queue.state['items'])
        self.s.youtube.search.assert_awaited_once_with('Artist Song')

    async def test_bad_links_are_errors_not_silent_empty_searches(self):
        self.s.youtube.search=AsyncMock()
        status,data=await self.send('https://www.youtube.com/playlist?list=123','youtube')
        self.assertEqual(status,400);self.assertIn('video link',data['error'])
        self.s.youtube.search.assert_not_awaited()

    async def test_direct_links_still_obey_blocks_and_review_rules(self):
        self.s.youtube.resolve=AsyncMock(return_value={**track('abcdefghijk','youtube'),'explicit':None})
        status,data=await self.send('https://youtu.be/abcdefghijk')
        self.assertEqual(status,200);self.assertEqual(data['item']['status'],'queued')
        self.assertTrue(data['item']['reviewed'])
        self.assertEqual(self.s.queue.next_item()['id'],data['item']['id'])
        self.s.settings.save({'blocked_tracks':['lmnopqrstuv']})
        self.s.youtube.resolve.return_value=track('lmnopqrstuv','youtube')
        status,data=await self.send('https://youtu.be/lmnopqrstuv')
        self.assertEqual(status,400);self.assertIn('blocked',data['error'])
