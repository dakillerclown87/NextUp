import asyncio, base64, hashlib, io, json, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from studio.settings import Settings, validate
from studio.queue import Queue
from studio.playback import Conductor, PlayerBridge
from studio.providers import parse_link, Vault
from studio.updater import verify, unpack
from studio.diagnostics import Diagnostics


def track(ident="a", provider="spotify", explicit=False, duration=200):
    return {
        "id": ident,
        "provider": provider,
        **({"youtube_category_id": "10"} if provider == "youtube" else {}),
        "title": "Test song",
        "artists": ["Test Artist"],
        "artist_ids": ["artist-id"],
        "url": "https://example.invalid/" + ident,
        "duration": duration,
        "explicit": explicit,
        "art": "",
    }


def user(i="1"):
    return {"id": i, "login": "viewer" + i}


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.s = Settings(self.root / "settings.json")
        self.q = Queue(self.root / "queue.db", self.s)

    def tearDown(self):
        self.q.db.close()
        self.tmp.cleanup()

    def test_constraints_and_roles(self):
        self.q.add(track(), user(), ["viewer"])
        with self.assertRaisesRegex(ValueError, "cooldown"):
            self.q.add(track("b"), user(), ["viewer"])
        self.q.add(track("c"), user("2"), ["tier3"])
        self.assertEqual(self.q.state["items"][0]["track"]["id"], "a")
        self.assertEqual(self.q.rule(["viewer", "mod", "tier3"])["pending"], 10)

    def test_limit_counts_current(self):
        self.s.value["roles"]["viewer"]["cooldown"] = 0
        a = self.q.add(track("a"), user(), ["viewer"])
        self.q.activate(a)
        self.q.add(track("b"), user(), ["viewer"])
        with self.assertRaisesRegex(ValueError, "active-request"):
            self.q.add(track("c"), user(), ["viewer"])

    def test_length_boundary_and_blocklist_normalization(self):
        self.q.check_track(track(duration=360))
        with self.assertRaises(ValueError):
            self.q.check_track(track(duration=361))
        self.s.value["blocked_artists"] = [" test ARTIST "]
        with self.assertRaisesRegex(ValueError, "artist"):
            self.q.check_track(track())

    def test_explicit_and_review(self):
        with self.assertRaises(ValueError):
            self.q.add(track(explicit=True), user(), ["broadcaster"])
        a = self.q.add(track(provider="youtube", explicit=None), user(), ["viewer"])
        self.assertEqual(a["status"], "review")
        self.assertIsNone(self.q.next_item())
        self.q.approve(a["id"])
        self.assertEqual(self.q.next_item()["id"], a["id"])

    def test_policy_rechecked_before_play(self):
        self.q.add(track(), user(), ["viewer"])
        self.s.value["max_seconds"] = 30
        self.assertIsNone(self.q.next_item())
        self.assertEqual(self.q.state["items"][0]["status"], "blocked")

    def test_source_mode_holds_other_songs(self):
        self.q.add(track("yt", "youtube"), user("1"), ["viewer"])
        self.q.add(track("sp"), user("2"), ["viewer"])
        self.s.value["provider_mode"] = "spotify"
        self.assertEqual(self.q.next_item()["track"]["id"], "sp")
        self.assertEqual(len(self.q.state["items"]), 2)

    def test_removal_ownership_and_refund(self):
        a = self.q.add(
            track(),
            user(),
            ["viewer"],
            redemption={"id": "red", "reward": "r", "broadcaster": "b"},
        )
        with self.assertRaises(ValueError):
            self.q.remove(a["id"], "2")
        self.q.remove(a["id"], "1")
        self.assertEqual(self.q.state["settlements"][0]["status"], "CANCELED")

    def test_dedup_persist_and_recover(self):
        a = self.q.add(track(), user(), ["viewer"], event_id="points:123")
        self.q.activate(a)
        self.q.db.close()
        self.q = Queue(self.root / "queue.db", self.s)
        self.assertIsNone(self.q.state["current"])
        self.assertEqual(len(self.q.state["items"]), 1)
        self.assertIsNone(
            self.q.add(track(), user(), ["viewer"], event_id="points:123")
        )

    def test_votes_and_toggle(self):
        a = self.q.add(track(), user(), ["viewer"])
        self.q.activate(a)
        self.assertFalse(self.q.vote("1"))
        with self.assertRaises(ValueError):
            self.q.vote("1")
        self.assertFalse(self.q.vote("2"))
        self.assertTrue(self.q.vote("3"))
        self.s.value["vote_skip_enabled"] = False
        with self.assertRaises(ValueError):
            self.q.vote("4")

    def test_reorder_rejects_missing_duplicate(self):
        a = self.q.add(track(), user(), ["viewer"])
        b = self.q.add(track("b"), user("2"), ["viewer"])
        with self.assertRaises(ValueError):
            self.q.reorder([a["id"], a["id"]])
        self.q.reorder([b["id"], a["id"]])
        self.assertEqual(self.q.state["items"][0], b)

    def test_custom_commands_and_validation(self):
        with self.assertRaises(ValueError):
            validate(
                {
                    "commands": {
                        "request": "!queue",
                        **{
                            k: v
                            for k, v in self.s.value["commands"].items()
                            if k != "request"
                        },
                    }
                }
            )
        with self.assertRaises(ValueError):
            validate({"max_seconds": True})
        self.s.save({"theme": "light"})
        self.assertEqual(Settings(self.root / "settings.json").value["theme"], "light")


class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Settings(Path(self.tmp.name) / "s.json")
        self.q = Queue(":memory:", self.s)
        self.calls = []
        self.sp = Mock()
        self.yt = Mock()

        async def pause():
            self.calls.append("spotify pause")

        async def play(t, **kwargs):
            self.calls.append("spotify play")

        async def send(action, t=None):
            self.calls.append("youtube " + action)

        self.sp.pause = AsyncMock(side_effect=pause)
        self.sp.play = AsyncMock(side_effect=play)
        self.yt.send = AsyncMock(side_effect=send)
        self.c = Conductor(self.q, self.sp, self.yt, Mock())

    async def asyncTearDown(self):
        self.q.db.close()
        self.tmp.cleanup()

    async def test_both_handoff_directions(self):
        a = self.q.add(track("a", "youtube"), user(), ["viewer"])
        self.q.activate(a)
        self.q.add(track("b"), user("2"), ["viewer"])
        await self.c.next()
        self.assertEqual(self.calls, ["youtube pause", "spotify play"])
        self.calls.clear()
        self.q.add(track("c", "youtube"), user("3"), ["viewer"])
        await self.c.next()
        self.assertEqual(self.calls, ["spotify pause", "youtube play"])

    async def test_pause_failure_does_not_start_next(self):
        a = self.q.add(track("a", "youtube"), user(), ["viewer"])
        self.q.activate(a)
        self.q.add(track("b"), user("2"), ["viewer"])
        self.yt.send.side_effect = ValueError("pause failed")
        with self.assertRaises(ValueError):
            await self.c.next()
        self.sp.play.assert_not_called()
        self.assertEqual(self.q.state["current"], a)

    async def test_start_failure_retains_request(self):
        a = self.q.add(track(), user(), ["viewer"])
        self.sp.play.side_effect = ValueError("offline")
        with self.assertRaises(ValueError):
            await self.c.next()
        self.assertIn(a, self.q.state["items"])
        self.assertIsNone(self.q.state["current"])

    async def test_stale_end_cannot_skip_new_song(self):
        a = self.q.add(track(), user(), ["viewer"])
        self.q.activate(a)
        self.q.add(track("b"), user("2"), ["viewer"])
        self.c.enabled = True
        await self.c.next(expected=a["id"])
        await self.c.next(expected=a["id"])
        self.assertEqual(self.q.state["current"]["track"]["id"], "b")
        self.sp.play.assert_awaited_once()

    async def test_manual_skip_toggle(self):
        self.s.value["skip_enabled"] = False
        with self.assertRaises(ValueError):
            await self.c.next(manual=True)

    async def test_busy_controls_do_not_stack(self):
        self.q.add(track(), user(), ['viewer'])
        started, release = asyncio.Event(), asyncio.Event()
        async def stalled(t, **kwargs):
            started.set()
            await release.wait()
        self.sp.play.side_effect = stalled
        task = asyncio.create_task(self.c.resume())
        await asyncio.wait_for(started.wait(), 2)
        self.assertTrue(self.c.snapshot()['busy'])
        for operation in (self.c.resume, self.c.pause, self.c.next):
            with self.assertRaisesRegex(ValueError, 'already running'):
                await asyncio.wait_for(operation(), .1)
        release.set()
        await task
        self.sp.play.assert_awaited_once()
        self.assertFalse(self.c.snapshot()['busy'])

    async def test_skip_failed_request_does_not_retry_it(self):
        a = self.q.add(track('broken'), user(), ['viewer'])
        b = self.q.add(track('working'), user('2'), ['viewer'])
        self.sp.play.side_effect = ValueError('empty player')
        with self.assertRaises(ValueError):
            await self.c.resume()
        self.assertEqual(self.c.failed_item, a['id'])
        self.sp.play.side_effect = None
        await self.c.next(manual=True)
        self.assertEqual(self.q.state['current']['id'], b['id'])
        self.assertEqual(self.sp.play.await_args.args[0]['id'], 'working')
        self.assertNotIn(a, self.q.state['items'])
        self.assertIsNone(self.c.failed_item)

    async def test_failed_skip_pause_retains_request(self):
        a = self.q.add(track(), user(), ['viewer'])
        self.sp.play.side_effect = ValueError('empty player')
        with self.assertRaises(ValueError):
            await self.c.resume()
        self.sp.pause.side_effect = ValueError('unconfirmed pause')
        with self.assertRaises(ValueError):
            await self.c.next(manual=True)
        self.assertIn(a, self.q.state['items'])
        self.assertFalse(self.c.enabled)

    async def test_ended_after_final_pause_report_starts_spotify_once(self):
        a = self.q.add(track("a", "youtube"), user(), ["viewer"])
        self.q.activate(a)
        b = self.q.add(track("b"), user("2"), ["viewer"])
        self.c.enabled = True
        self.c.status = "Paused"  # Browser's final state, not a user pause.
        await self.c.ended("a")
        await self.c.ended("a")
        self.assertEqual(self.q.state["current"]["id"], b["id"])
        self.assertEqual(self.calls, ["youtube pause", "spotify play"])

    async def test_explicit_pause_blocks_late_end(self):
        a = self.q.add(track("a", "youtube"), user(), ["viewer"])
        self.q.activate(a)
        self.q.add(track("b"), user("2"), ["viewer"])
        self.c.enabled = True
        await self.c.pause()
        await self.c.ended("a")
        self.sp.play.assert_not_awaited()
        self.assertEqual(self.q.state["current"]["id"], a["id"])

    async def test_auto_advance_rechecks_pause_after_waiting_for_lock(self):
        a = self.q.add(track("a", "youtube"), user(), ["viewer"])
        self.q.activate(a)
        self.q.add(track("b"), user("2"), ["viewer"])
        self.c.enabled = True
        async with self.c.lock:
            task = asyncio.create_task(self.c.ended("a"))
            await asyncio.sleep(0)
            self.c.enabled = False
        await task
        self.sp.play.assert_not_awaited()
        self.assertEqual(self.q.state["current"]["id"], a["id"])

    async def test_player_lease_and_ack(self):
        b = PlayerBridge()
        b.poll("one")
        with self.assertRaises(ValueError):
            b.poll("two")
        t = asyncio.create_task(b.send("pause"))
        await asyncio.sleep(0)
        b.ack("two", b.command["seq"])
        self.assertFalse(t.done())
        b.ack("one", b.command["seq"])
        await t


class SecurityTests(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(
            parse_link("https://youtu.be/abcdefghijk?t=3"), ("youtube", "abcdefghijk")
        )
        self.assertEqual(
            parse_link("https://open.spotify.com/track/" + "a" * 22),
            ("spotify", "a" * 22),
        )
        for u in [
            "https://youtube.com.evil.com/watch?v=abcdefghijk",
            "http://localhost/admin",
            "https://evil@youtube.com/watch?v=abcdefghijk",
        ]:
            self.assertIsNone(parse_link(u))

    def test_signed_update_and_tamper(self):
        k = Ed25519PrivateKey.generate()
        public = base64.b64encode(
            k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode()
        raw = b"archive"
        m = json.dumps(
            {
                "version": "2.0.1",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
            }
        ).encode()
        sig = base64.b64encode(k.sign(m))
        self.assertEqual(verify(m, sig, raw, public)["version"], "2.0.1")
        with self.assertRaises(ValueError):
            verify(m, sig, b"tampered", public)
        with self.assertRaises(Exception):
            verify(m + b" ", sig, raw, public)

    def test_archive_rejects_traversal_windows_paths_symlinks(self):
        for path in [
            "../outside.py",
            "C:/bad.py",
            "studio/CON.py",
            "studio/bad.",
            "studio\\bad.py",
        ]:
            b = io.BytesIO()
            with zipfile.ZipFile(b, "w") as z:
                z.writestr(path, "x")
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    unpack(b.getvalue(), tmp)

    def test_valid_archive(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            for name in ["studio/__init__.py", "studio/server.py", "requirements.txt"]:
                z.writestr(name, "")
        with tempfile.TemporaryDirectory() as tmp:
            unpack(b.getvalue(), tmp)
            self.assertTrue((Path(tmp) / "studio/server.py").exists())

    def test_vault_roundtrip_and_disconnect(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = Vault(Path(tmp) / "v.json")
            v.put("spotify", {"access_token": "secret"})
            self.assertEqual(v.read()["spotify"]["access_token"], "secret")
            v.put("spotify", None)
            self.assertEqual(v.read(), {})

    def test_log_analyzer_does_not_echo_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Diagnostics(Path(tmp) / "log")
            result = d.analyze("HTTP 401 Bearer private-secret")
            self.assertNotIn("private-secret", json.dumps(result))
            self.assertIn("reconnect", json.dumps(result))
