import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from aiohttp import ClientSession, WSServerHandshakeError
from aiohttp.test_utils import TestServer, TestClient
from studio.server import Studio, admin_app
from test_core import track

ORIGIN = 'chrome-extension://' + 'a' * 32


class ChromeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.session = ClientSession()
        self.s = Studio(self.session, Path(self.temp.name))
        self.s.settings.save({'youtube_player_mode':'chrome'})
        self.client = TestClient(TestServer(admin_app(self.s)))
        await self.client.start_server()
        self.h = {'Host':'127.0.0.1:8888','X-NextUp-Key':self.s.admin}
        self.sockets = []

    async def asyncTearDown(self):
        for ws in self.sockets:
            await ws.close()
        await self.client.close()
        await self.s.cleanup()
        await self.session.close()
        self.temp.cleanup()

    async def pair(self):
        response = await self.client.post('/api/chrome-pair',headers=self.h,json={})
        code = (await response.json())['code']
        ws = await self.client.ws_connect('/chrome/ws',headers={'Host':'127.0.0.1:8888','Origin':ORIGIN})
        self.sockets.append(ws)
        await ws.send_json({'type':'pair','code':code})
        auth = await ws.receive_json()
        self.assertEqual(auth['type'],'authenticated')
        self.assertTrue(auth['token'])
        await ws.send_json({'type':'heartbeat','ready':True})
        for _ in range(100):
            if self.s.chrome.last:break
            await asyncio.sleep(.001)
        return ws, auth['token']

    async def test_youtube_status_uses_selected_player_and_fresh_heartbeat(self):
        from unittest.mock import patch, PropertyMock
        self.assertFalse(self.s.state()['connections']['youtube_player'])
        await self.pair()
        self.assertTrue(self.s.state()['connections']['youtube_player'])
        self.s.chrome.last = time.monotonic()-9
        self.assertFalse(self.s.state()['connections']['youtube_player'])
        self.s.chrome.last = time.monotonic()
        with patch('studio.chrome.ChromePlayer.connected', new_callable=PropertyMock, return_value=False):
            self.assertFalse(self.s.state()['connections']['youtube_player'])
        self.s.settings.save({'youtube_player_mode':'embedded'})
        self.assertFalse(self.s.state()['connections']['youtube_player'])
        self.s.bridge.poll('fixture')
        self.assertTrue(self.s.state()['connections']['youtube_player'])
        self.s.bridge.last = 0
        self.assertFalse(self.s.state()['connections']['youtube_player'])

    async def test_saving_theme_refreshes_native_titlebars(self):
        from unittest.mock import Mock
        self.s.desktop = Mock()
        response = await self.client.post('/api/settings', headers=self.h,
                                         json={'theme':'light','theme_colors':{'bg':'#123456'}})
        self.assertEqual(response.status,200)
        self.s.desktop.refresh_window_theme.assert_called_once_with()

    async def test_origin_code_scope_expiry_and_replay(self):
        with self.assertRaises(WSServerHandshakeError):
            await self.client.ws_connect('/chrome/ws',headers={'Host':'127.0.0.1:8888','Origin':'https://www.youtube.com'})
        code = self.s.chrome.pairing_code()
        self.s.chrome.expires = time.monotonic()-1
        with self.assertRaises(ValueError):
            self.s.chrome.authenticate(ORIGIN,{'type':'pair','code':code})
        ws, token = await self.pair()
        with self.assertRaises(ValueError):
            self.s.chrome.authenticate('chrome-extension://'+'b'*32,{'type':'auth','token':token})
        with self.assertRaises(ValueError):
            self.s.chrome.authenticate(ORIGIN,{'type':'pair','code':code})
        response = await self.client.get('/api/state',headers=self.h)
        self.assertNotIn(token,json.dumps(await response.json()))
        response = await self.client.post('/api/settings',headers={'Host':'127.0.0.1:8888','Origin':ORIGIN,'X-NextUp-Key':token},json={'theme':'light'})
        self.assertEqual(response.status,403)

    async def test_pause_ack_required_before_spotify_starts(self):
        ws, _ = await self.pair()
        current = self.s.queue.add(track('abcdefghijk','youtube'),{'id':'1','login':'v'},['broadcaster'])
        self.s.queue.activate(current)
        self.s.queue.add(track('spotify'),{'id':'1','login':'v'},['broadcaster'])
        self.s.spotify.play = AsyncMock()
        task = asyncio.create_task(self.s.conductor.next())
        cmd = await ws.receive_json()
        self.assertEqual(cmd['action'],'pause')
        self.s.spotify.play.assert_not_awaited()
        await ws.send_json({'type':'ack','seq':'wrong','ok':True})
        await asyncio.sleep(.01)
        self.s.spotify.play.assert_not_awaited()
        await ws.send_json({'type':'ack','seq':cmd['seq'],'ok':True})
        await task
        self.s.spotify.play.assert_awaited_once()
        self.s.spotify.pause = AsyncMock()

    async def test_chrome_play_waits_for_ack_after_spotify_pause(self):
        ws, _ = await self.pair()
        current = self.s.queue.add(track('sp'),{'id':'1','login':'v'},['broadcaster'])
        self.s.queue.activate(current)
        self.s.queue.add(track('abcdefghijk','youtube'),{'id':'1','login':'v'},['broadcaster'])
        self.s.spotify.pause = AsyncMock()
        task = asyncio.create_task(self.s.conductor.next())
        cmd = await ws.receive_json()
        self.s.spotify.pause.assert_awaited_once()
        self.assertEqual(cmd['action'],'play')
        self.assertIsNone(self.s.queue.state['current'])
        await ws.send_json({'type':'ack','seq':cmd['seq'],'ok':True})
        await task
        self.assertEqual(self.s.queue.state['current']['track']['id'],'abcdefghijk')
        self.assertEqual(self.s.conductor.status,'Playing')
        self.s.queue.finish()

    async def test_natural_end_after_paused_report_advances_to_spotify(self):
        ws, _ = await self.pair()
        c = self.s.queue.add(track('abcdefghijk','youtube'),{'id':'1','login':'v'},['broadcaster'])
        self.s.queue.activate(c)
        nxt = self.s.queue.add(track('sp'),{'id':'1','login':'v'},['broadcaster'])
        self.s.chrome.generation = 'current'
        self.s.chrome.track = 'abcdefghijk'
        self.s.chrome.started = True
        self.s.conductor.enabled = True
        self.s.conductor.status = 'Playing'
        started, release = asyncio.Event(), asyncio.Event()
        async def play(track):
            started.set()
            await release.wait()
        self.s.spotify.play = AsyncMock(side_effect=play)
        await ws.send_json({'type':'state','generation':'current','seconds':119,'playing':False,'ended':False})
        for _ in range(100):
            if self.s.conductor.status == 'Paused': break
            await asyncio.sleep(.001)
        self.assertEqual(self.s.conductor.status, 'Paused')
        await ws.send_json({'type':'ended','generation':'current'})
        cmd = await asyncio.wait_for(ws.receive_json(), 2)
        self.assertEqual(cmd['action'], 'pause')
        self.s.spotify.play.assert_not_awaited()
        await ws.send_json({'type':'ack','seq':cmd['seq'],'ok':True})
        await asyncio.wait_for(started.wait(), 2)
        self.assertEqual(self.s.conductor.status, 'Starting Spotify')
        # Duplicate completion cannot consume another request.
        await ws.send_json({'type':'ended','generation':'current'})
        release.set()
        for _ in range(100):
            if self.s.queue.state['current']: break
            await asyncio.sleep(.001)
        self.assertEqual(self.s.queue.state['current']['id'], nxt['id'])
        self.assertEqual(self.s.conductor.status, 'Playing')
        self.s.spotify.play.assert_awaited_once()
        self.s.queue.finish()

    async def test_paused_queue_does_not_consume_chrome_end(self):
        c = self.s.queue.add(track('abcdefghijk','youtube'),{'id':'1','login':'v'},['broadcaster'])
        self.s.queue.activate(c)
        self.s.chrome.generation = 'current'
        self.s.chrome.track = 'abcdefghijk'
        self.s.chrome.started = True
        self.s.conductor.status = 'Paused'
        self.s.conductor.enabled = False
        self.s.conductor.next = AsyncMock()
        self.s.chrome.receive({'type':'ended','generation':'current'})
        await asyncio.sleep(0)
        self.s.conductor.next.assert_not_awaited()
        self.s.queue.finish()

    async def test_disconnect_never_starts_next_source(self):
        ws, _ = await self.pair()
        c = self.s.queue.add(track('abcdefghijk','youtube'),{'id':'1','login':'v'},['broadcaster'])
        self.s.queue.activate(c)
        self.s.queue.add(track('sp'),{'id':'1','login':'v'},['broadcaster'])
        self.s.spotify.play = AsyncMock()
        task = asyncio.create_task(self.s.conductor.next())
        await ws.receive_json()
        await ws.close()
        with self.assertRaisesRegex(ValueError,'disconnected'):
            await task
        self.s.spotify.play.assert_not_awaited()
        self.assertFalse(self.s.conductor.enabled)

    async def test_error_ack_keeps_request_and_stops_queue(self):
        ws, _ = await self.pair()
        self.s.queue.add(track('abcdefghijk','youtube'),{'id':'1','login':'v'},['broadcaster'])
        task = asyncio.create_task(self.s.conductor.next())
        cmd = await ws.receive_json()
        await ws.send_json({'type':'ack','seq':cmd['seq'],'ok':False,'reason':'unavailable'})
        with self.assertRaisesRegex(ValueError,'cannot play'):
            await task
        self.assertIsNone(self.s.queue.state['current'])
        self.assertEqual(len(self.s.queue.state['items']),1)
        self.assertFalse(self.s.conductor.enabled)

    async def test_mode_switch_cannot_race_handoff_and_embedded_is_disabled(self):
        await self.s.conductor.lock.acquire()
        try:
            response = await self.client.post('/api/settings',headers=self.h,json={'youtube_player_mode':'embedded'})
            self.assertEqual(response.status,400)
        finally:self.s.conductor.lock.release()
        response = await self.client.post('/api/player-poll',headers=self.h,json={'client':'embedded'})
        self.assertEqual(response.status,400)

    async def test_stale_end_cannot_advance_current_video(self):
        c = self.s.queue.add(track('abcdefghijk','youtube'),{'id':'1','login':'v'},['broadcaster'])
        self.s.queue.activate(c)
        self.s.chrome.generation = 'new'
        self.s.chrome.track = 'abcdefghijk'
        self.s.chrome.started = True
        self.s.conductor.status = 'Playing'
        self.s.conductor.next = AsyncMock()
        self.s.chrome.receive({'type':'ended','generation':'old'})
        await asyncio.sleep(0)
        self.s.conductor.next.assert_not_awaited()
        self.s.queue.finish()

    async def test_browser_mode_accepts_non_embeddable_video(self):
        v={'snippet':{'categoryId':'10','title':'Song','channelTitle':'Artist','channelId':'artist'},'status':{'embeddable':False},'contentDetails':{'duration':'PT3M'}}
        self.s.youtube.api=AsyncMock(return_value={'items':[v]})
        self.assertEqual((await self.s.youtube.resolve('abcdefghijk'))['duration'],180)
        self.s.settings.save({'youtube_player_mode':'embedded'})
        with self.assertRaisesRegex(ValueError,'non-embeddable'):
            await self.s.youtube.resolve('abcdefghijk')

class FirefoxTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=ChromeTests.asyncSetUp
    asyncTearDown=ChromeTests.asyncTearDown
    async def test_firefox_pair_origin_binding_and_real_peer_port(self):
        origin='moz-extension://12345678-1234-1234-1234-123456789abc'
        from studio.chrome import extension_origin
        for bad in ['null','https://www.youtube.com','moz-extension://example.com',origin+'/path',origin+':80','chrome-extension://'+('z'*32)]:
            self.assertFalse(extension_origin(bad))
            with self.assertRaises(WSServerHandshakeError):await self.client.ws_connect('/chrome/ws',headers={'Host':'127.0.0.1:8888','Origin':bad})
        code=self.s.chrome.pairing_code();ws=await self.client.ws_connect('/chrome/ws',headers={'Host':'127.0.0.1:8888','Origin':origin});self.sockets.append(ws)
        await ws.send_json({'type':'pair','code':code,'pid':999,'peer_port':999})
        msg=await ws.receive_json();self.assertEqual(msg['type'],'authenticated')
        self.assertTrue(0<self.s.chrome.audio_peer()<65536);self.assertNotEqual(self.s.chrome.audio_peer(),999)
        with self.assertRaises(ValueError):self.s.chrome.authenticate(ORIGIN,{'type':'auth','token':msg['token']})
        self.assertIsNone(self.s.chrome.authenticate(origin,{'type':'auth','token':msg['token']}))
        self.assertEqual((await self.client.post('/api/settings',headers={'Host':'127.0.0.1:8888','Origin':origin},json={})).status,403)
        await ws.close()
        for _ in range(100):
            if self.s.chrome.audio_peer()==0:break
            await asyncio.sleep(.01)
        self.assertEqual(self.s.chrome.audio_peer(),0)
