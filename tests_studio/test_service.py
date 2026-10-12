import asyncio, json, tempfile, unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from aiohttp import ClientSession
from aiohttp.test_utils import TestServer, TestClient
from studio.server import Studio, admin_app, overlay_app
from test_core import track


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = ClientSession()
        self.s = Studio(self.session, Path(self.tmp.name))
        self.client = TestClient(TestServer(admin_app(self.s)))
        self.overlay = TestClient(TestServer(overlay_app(self.s)))
        await self.client.start_server()
        await self.overlay.start_server()
        self.h = {"Host": "127.0.0.1:8888", "X-NextUp-Key": self.s.admin}

    async def asyncTearDown(self):
        await self.client.close()
        await self.overlay.close()
        await self.s.cleanup()
        await self.session.close()
        self.tmp.cleanup()

    async def test_auth_origin_host_and_no_get_mutation(self):
        r = await self.client.get("/api/state", headers={"Host": "127.0.0.1:8888"})
        self.assertEqual(r.status, 401)
        r = await self.client.post(
            "/api/settings",
            headers={**self.h, "Origin": "https://evil.example"},
            json={"theme": "light"},
        )
        self.assertEqual(r.status, 403)
        r = await self.client.get(
            "/api/state", headers={**self.h, "Host": "evil.example"}
        )
        self.assertEqual(r.status, 403)
        r = await self.client.get("/api/exit", headers=self.h)
        self.assertEqual(r.status, 405)

    async def test_settings_roundtrip_hides_credentials(self):
        r = await self.client.post(
            "/api/settings",
            headers=self.h,
            json={"theme": "light", "youtube_api_key": "secret-key"},
        )
        self.assertEqual(r.status, 200)
        r = await self.client.get("/api/state", headers=self.h)
        self.assertEqual(r.status, 200)
        d = await r.json()
        self.assertEqual(d["settings"]["theme"], "light")
        self.assertNotIn("secret-key", json.dumps(d))

    async def test_native_player_requires_admin_and_uses_desktop_host(self):
        self.s.desktop = Mock()
        r = await self.client.post('/api/desktop-player', headers={'Host': '127.0.0.1:8888'}, json={})
        self.assertEqual(r.status, 401)
        self.s.desktop.open_player.assert_not_called()
        r = await self.client.post('/api/desktop-player', headers=self.h, json={})
        self.assertEqual(r.status, 200)
        self.s.desktop.open_player.assert_called_once_with()

    async def test_desktop_oauth_opens_only_provider_login(self):
        self.s.desktop = Mock()
        url = 'https://accounts.spotify.com/authorize?state=test'
        self.s.spotify.connect = Mock(return_value=url)
        with patch('studio.server.webbrowser.open', return_value=True) as browser:
            r = await self.client.post('/api/spotify-connect', headers=self.h, json={})
        self.assertEqual(r.status, 200)
        browser.assert_called_once_with(url)

    async def test_overlay_is_separate_and_read_only(self):
        r = await self.overlay.get("/state")
        self.assertEqual(r.status, 401)
        r = await self.overlay.get("/state?key=" + self.s.overlay_key)
        self.assertEqual(r.status, 200)
        self.assertEqual(set(await r.json()), {"current", "items", "playback", "colors", "equalizer", "equalizer_style", "presets", "branding"})
        r = await self.overlay.post("/api/settings?key=" + self.s.overlay_key, json={})
        self.assertEqual(r.status, 404)

    async def test_request_api_does_not_trust_supplied_metadata(self):
        self.s.spotify.resolve = AsyncMock(return_value=track("x", duration=1000))
        r = await self.client.post(
            "/api/request",
            headers=self.h,
            json={"url": "https://open.spotify.com/track/" + "a" * 22, "duration": 1},
        )
        self.assertEqual(r.status, 400)
        self.assertEqual(self.s.queue.state["items"], [])

    async def test_point_dedup_and_refund(self):
        self.s.twitch.broadcaster = "100"
        self.s.twitch.roles = AsyncMock(return_value=["viewer"])
        self.s.spotify.resolve = AsyncMock(return_value=track())
        e = {
            "id": "red",
            "reward": {"id": ""},
            "user_id": "1",
            "user_login": "viewer",
            "user_input": "https://open.spotify.com/track/" + "a" * 22,
        }
        await asyncio.gather(self.s.redemption(e), self.s.redemption(e))
        self.assertEqual(len(self.s.queue.state["items"]), 1)
        bad = {**e, "id": "bad", "user_input": "not a song link"}
        await self.s.redemption(bad)
        await self.s.redemption(bad)
        self.assertEqual(len(self.s.queue.state["settlements"]), 1)
        self.assertEqual(self.s.queue.state["settlements"][0]["status"], "CANCELED")

    async def test_pkce_random_state_and_callback_rejection(self):
        self.s.settings.save({"spotify_client_id": "a" * 32})
        url = self.s.spotify.connect()
        self.assertIn("code_challenge_method=S256", url)
        self.assertNotIn("client_secret", url)
        with self.assertRaises(ValueError):
            await self.s.spotify.callback("fake", "wrong-state")

    async def test_tier_roles_from_server_not_user_text(self):
        t = self.s.twitch
        t.broadcaster = "100"
        t.identity = {"user_id": "100"}

        async def api(method, path, **kw):
            return (
                {"data": [{"tier": "3000"}]}
                if path == "subscriptions"
                else {"data": []}
            )

        t.api = AsyncMock(side_effect=api)
        self.assertIn("tier3", await t.roles("22"))
        self.assertEqual(await t.roles("100"), ["broadcaster"])

    async def test_limited_role_fallback_outside_own_channel(self):
        t = self.s.twitch
        t.broadcaster = "100"
        t.identity = {"user_id": "200"}
        roles = await t.roles("22", {"badges": "subscriber/36,vip/1"})
        self.assertIn("tier1", roles)
        self.assertIn("vip", roles)
        self.assertNotIn("tier3", roles)

    async def test_request_replies_include_artist_and_platform_without_internal_id(self):
        self.s.bot = Mock()
        self.s.twitch.roles = AsyncMock(return_value=['viewer'])
        for i, (provider, label, review) in enumerate([('spotify', 'Spotify', False), ('youtube', 'YouTube', False), ('youtube', 'YouTube', True)]):
            song = track(str(i), provider=provider)
            song.update(title='Turn The Tide', artists=['Test Artist', 'Guest Artist'])
            self.s.request_song = AsyncMock(return_value={'id': 'dc782469e6a020b7', 'status': 'review' if review else 'queued', 'track': song})
            handled = await self.s.chat(str(i), 'viewer', 'message'+str(i), '!sr https://example.com/request', {})
            self.assertTrue(handled)
            expected = f"@viewer {'Awaiting review' if review else 'Queued'}: Turn The Tide — Test Artist, Guest Artist ({label})."
            self.s.bot.reply.assert_called_with('message'+str(i), expected)
        # No external chat/network calls are used by this regression.
        self.s.bot = None

    async def test_blank_player_diagnostic_is_exported_without_account_data(self):
        from studio.providers import PlaybackStateError
        item = self.s.queue.add(track(), {'id': 'viewer', 'login': 'viewer'}, ['broadcaster'])
        self.s.spotify.play = AsyncMock(side_effect=PlaybackStateError('Spotify has no track loaded.', 'spotify_empty_player', {'access_token': 'must-not-export'}))
        with self.assertRaises(PlaybackStateError):
            await self.s.conductor.next()
        self.assertIsNone(self.s.queue.state['current'])
        self.assertFalse(self.s.conductor.enabled)
        self.assertEqual(self.s.queue.state['items'][0]['id'], item['id'])
        r = await self.client.get('/api/diagnostics', headers=self.h)
        data = await r.json()
        self.assertEqual(data['events'][-1]['code'], 'spotify_empty_player')
        self.assertIn('no track loaded', data['findings'][0]['suggestion'])
        self.assertNotIn('must-not-export', json.dumps(data))

    async def test_new_request_does_not_restart_failed_player(self):
        self.s.conductor.failed(ValueError('Playback failed'))
        self.s.spotify.resolve = AsyncMock(return_value=track())
        self.s.conductor.next = AsyncMock()
        await self.s.request_song('https://open.spotify.com/track/' + 'a' * 22,
                                  {'id': 'viewer', 'login': 'viewer'}, ['broadcaster'])
        await asyncio.sleep(0)
        self.s.conductor.next.assert_not_awaited()
