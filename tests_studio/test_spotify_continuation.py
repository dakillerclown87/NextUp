"""Real conductor/provider adapter, simulated Spotify Connect state transitions."""
import copy
import unittest
from unittest.mock import AsyncMock, Mock
import test_service
from test_core import track, user

PLAYLIST = 'P' * 22


class ActivePlaylistTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_service.ServiceTests.asyncSetUp
    asyncTearDown = test_service.ServiceTests.asyncTearDown

    async def setup_player(self):
        s = self.s
        s.settings.save({'fallback_enabled': False, 'spotify_native_queue': False,
                         'provider_mode': 'mixed'})
        s.vault.put('spotify', {'access_token': 'test-only'})
        self.native = []
        self.next_index = 1
        self.actions = []
        self.state = {'item': self.item('p0'), 'is_playing': True, 'progress_ms': 10000,
                      'context': {'uri': 'spotify:playlist:' + PLAYLIST},
                      'device': {'id': 'pc'}, 'shuffle_state': False, 'repeat_state': 'context'}
        async def api(method, path, **kwargs):
            if method != 'GET': self.actions.append((method, path, copy.deepcopy(kwargs)))
            if path == 'me/player/devices': return {'devices': [{'id': 'pc', 'is_active': True}]}
            if path == 'me/player/queue':
                if method == 'POST': self.native.append(kwargs['params']['uri'].split(':')[-1]); return {}
                return {'queue': [self.item(x) for x in self.native + ['p' + str(self.next_index)]]}
            if path == 'me/player/play' and method == 'PUT':
                body = kwargs.get('json', {})
                if body.get('context_uri'):
                    self.state['context'] = {'uri': body['context_uri']}
                    ident = body['offset']['uri'].split(':')[-1]
                    self.state['item'] = self.item(ident)
                    self.state['progress_ms'] = body.get('position_ms', 0)
                    if ident.startswith('p'): self.next_index = int(ident[1:]) + 1
                elif body.get('uris'):
                    self.state.update(item=self.item(body['uris'][0].split(':')[-1]), context=None, progress_ms=0)
                self.state['is_playing'] = True
            if path == 'me/player/next' and method == 'POST': self.natural_next()
            if path == 'me/player/pause': self.state['is_playing'] = False
            if path == 'me/player/repeat': self.state['repeat_state'] = kwargs['params']['state']
            if path == 'me/player/shuffle': self.state['shuffle_state'] = kwargs['params']['state'] == 'true'
            return copy.deepcopy(self.state) if method == 'GET' else {}
        s.spotify.api = api
        s.spotify.resolve = AsyncMock(side_effect=lambda ident: track(ident))
        s.youtube.resolve = AsyncMock(side_effect=lambda ident: track(ident, 'youtube'))
        s.conductor.bridge = Mock(last=0, send=AsyncMock())
        self.c = s.conductor

    @staticmethod
    def item(ident):
        return {'id': ident, 'name': ident, 'duration_ms': 200000,
                'artists': [{'id': 'artist', 'name': 'Artist'}], 'explicit': False}

    def natural_next(self):
        if self.native: ident = self.native.pop(0)
        else:
            ident = 'p' + str(self.next_index)
            self.next_index += 1
        self.state.update(item=self.item(ident), is_playing=True, progress_ms=0)

    async def request(self, ident='R' * 22, provider='spotify'):
        url = 'https://open.spotify.com/track/' + ident if provider == 'spotify' else 'https://youtube.com/watch?v=' + ident
        return await self.s.request_song(url, user(ident), ['broadcaster'], owner=True)

    async def end_native(self):
        self.state['progress_ms'] = 199800
        await self.c.poll_spotify()
        self.natural_next()
        await self.c.poll_spotify()
        await self.c.native.flush()

    async def test_no_saved_playlist_requests_join_native_playback_and_continue_twenty_songs(self):
        await self.setup_player()
        request = await self.request()
        self.assertEqual(self.s.settings.value['fallback_playlist'], '')
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p0')
        self.assertEqual(request['spotify_delivery'], 'sent')
        await self.end_native()
        self.assertEqual(self.s.queue.state['current']['id'], request['id'])
        for n in range(1, 21):
            await self.end_native()
            self.assertEqual(self.s.queue.state['current']['track']['id'], 'p' + str(n))
            self.assertEqual(self.state['context']['uri'], 'spotify:playlist:' + PLAYLIST)
        # No interruption of playback; the only write is adding the request.
        self.assertEqual([(m,p) for m,p,k in self.actions], [('POST','me/player/queue')])
        self.assertEqual(self.s.queue.state['counts'][request['user']['id']], 1)

    async def test_two_requests_ahead_of_playlist_without_duplicate_appends(self):
        await self.setup_player()
        a = await self.request('A' * 22)
        b = await self.request('B' * 22)
        self.assertEqual(self.native, [a['track']['id']])
        await self.end_native()
        self.assertEqual(self.native, [b['track']['id']])
        await self.end_native()
        self.assertEqual(self.s.queue.state['current']['id'], b['id'])
        await self.end_native()
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p1')
        self.assertEqual(len(self.actions), 2)

    async def test_youtube_handoff_returns_to_original_next_song_and_context(self):
        await self.setup_player()
        self.state.update(shuffle_state=True, repeat_state='context')
        y = await self.request('abcdefghijk', 'youtube')
        self.state['progress_ms'] = 199800
        await self.c.poll_spotify()
        self.assertEqual(self.s.queue.state['current']['id'], y['id'])
        self.assertFalse(self.state['is_playing'])
        await self.c.ended('abcdefghijk')
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p1')
        self.assertEqual(self.state['context']['uri'], 'spotify:playlist:' + PLAYLIST)
        self.assertTrue(self.state['shuffle_state'])
        self.assertEqual(self.state['repeat_state'], 'context')
        await self.end_native()
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p2')

    async def test_mixed_requests_respect_youtube_barrier_then_restore_playlist(self):
        await self.setup_player()
        a = await self.request('A' * 22)
        y = await self.request('abcdefghijk', 'youtube')
        b = await self.request('B' * 22)
        await self.end_native()
        self.assertEqual(self.s.queue.state['current']['id'], a['id'])
        self.assertEqual(self.native, [])
        self.state['progress_ms'] = 199800
        await self.c.poll_spotify()
        self.assertEqual(self.s.queue.state['current']['id'], y['id'])
        await self.c.native.flush()
        await self.c.ended('abcdefghijk')
        self.assertEqual(self.s.queue.state['current']['id'], b['id'])
        self.assertEqual(self.state['repeat_state'], 'context')
        await self.end_native()
        self.assertEqual(self.s.queue.state['current']['track']['id'], 'p1')

    async def test_pause_is_not_overridden_by_another_request(self):
        await self.setup_player()
        await self.request()
        await self.c.pause()
        await self.request('B' * 22)
        await self.c.poll_spotify()
        self.assertFalse(self.state['is_playing'])
        self.assertFalse(self.c.enabled)
        self.assertEqual(self.c.status, 'Paused')

    async def test_approval_required_does_not_append_before_approval(self):
        await self.setup_player()
        self.s.settings.save({'require_approval': True})
        r = self.s.queue.add(track('A' * 22), user('v'), ['viewer'])
        async with self.c.lock: await self.c.continuation.attach()
        self.assertFalse(self.c.continuation.active)
        self.assertFalse(self.actions)
        self.s.queue.approve(r['id'])
        async with self.c.lock: await self.c.continuation.attach()
        await self.c.native.flush()
        self.assertEqual(self.native, ['A' * 22])

    async def test_saved_fallback_takes_precedence(self):
        await self.setup_player()
        self.s.settings.save({'fallback_enabled': True, 'fallback_playlist': 'F' * 22})
        await self.request()
        self.assertFalse(self.c.continuation.active)
        self.assertFalse(self.actions)

    async def test_stopped_or_nonplaylist_spotify_is_not_adopted(self):
        await self.setup_player()
        self.state['is_playing'] = False
        await self.request()
        self.assertFalse(self.c.continuation.active)
        self.state.update(is_playing=True, context={'uri': 'spotify:album:' + PLAYLIST})
        await self.c.continuation.attach()
        self.assertFalse(self.c.continuation.active)
