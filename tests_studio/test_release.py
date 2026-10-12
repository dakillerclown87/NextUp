from studio import __version__
NEXT_VERSION = __version__.rsplit(".", 1)[0] + "." + str(int(__version__.rsplit(".", 1)[1]) + 1)
import base64, hashlib, io, json, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from studio.updater import Updater
from studio.instance import InstanceLock
import bootstrap


class ReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_staging_keeps_userdata_and_pins_publisher(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "userdata").mkdir()
            (home / "userdata/config.json").write_text('{"keep":true}')
            key = Ed25519PrivateKey.generate()
            public = base64.b64encode(
                key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode()
            pub = {"repository": "owner/repo", "public_key": public, "channel": "beta"}
            (home / "publisher.json").write_text(json.dumps(pub))
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                for name in [
                    "studio/__init__.py",
                    "studio/server.py",
                    "requirements.txt",
                ]:
                    z.writestr(name, "")
                z.writestr("publisher.json", '{"repository":"malicious/new","cloud_url":"https://nextup.test"}')
            archive = buf.getvalue()
            manifest = json.dumps(
                {
                    "version": NEXT_VERSION,
                    "sha256": hashlib.sha256(archive).hexdigest(),
                    "size": len(archive),
                }
            ).encode()
            sig = base64.b64encode(key.sign(manifest))
            payload = {"zip": archive, "manifest": manifest, "signature": sig}
            u = Updater(Mock(), home, home)
            u.release = {
                "tag": NEXT_VERSION,
                "assets": {
                    "nextup-app.zip": "zip",
                    "manifest.json": "manifest",
                    "manifest.sig": "signature",
                },
            }

            async def get(url, limit):
                return payload[url]

            u.get = get
            await u.stage()
            self.assertTrue((home / "pending.json").exists())
            self.assertEqual(
                json.loads((home / "versions" / NEXT_VERSION / "publisher.json").read_text()),
                pub,
            )
            self.assertEqual(
                (home / "userdata/config.json").read_text(), '{"keep":true}'
            )

    async def test_pkce_refresh_and_playlist_new_item_schema(self):
        from studio.settings import Settings
        from studio.providers import Spotify, Vault

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            s = Settings(path / "s.json")
            s.save({"spotify_client_id": "a" * 32})
            v = Vault(path / "v.json")
            p = Spotify(Mock(), s, v)
            p.connect()
            state = p.pending["state"]
            verifier = p.pending["verifier"]
            with patch(
                "studio.providers.request",
                new=AsyncMock(
                    return_value={
                        "access_token": "fake",
                        "refresh_token": "fake-refresh",
                        "expires_in": 3600,
                    }
                ),
            ) as req:
                await p.callback("fake-code", state)
                self.assertEqual(
                    req.await_args.kwargs["data"]["code_verifier"], verifier
                )
            with self.assertRaises(ValueError):
                await p.callback("fake-code", state)
            t = {
                "id": "a" * 22,
                "name": "Song",
                "artists": [{"name": "Artist", "id": "b" * 22}],
                "duration_ms": 120000,
                "explicit": False,
                "album": {"images": []},
            }
            p.api = AsyncMock(return_value={"items": [{"item": t}], "next": None})
            items = await p.playlist("c" * 22)
            self.assertEqual(items[0]["duration"], 120)
            self.assertTrue(p.api.await_args.args[1].endswith("/items"))


class BootstrapTests(unittest.TestCase):
    def test_instance_lock_blocks_second_process(self):
        import subprocess, sys

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with InstanceLock(home):
                code = ("import sys; sys.path.insert(0, "
                        + repr(str(Path(__file__).resolve().parents[1]))
                        + "); from pathlib import Path; from studio.instance import InstanceLock\ntry:\n with InstanceLock(Path(sys.argv[1])): pass\nexcept ValueError: sys.exit(42)")
                r = subprocess.run(
                    [sys.executable, "-c", code, tmp], capture_output=True
                )
                self.assertEqual(r.returncode, 42)

    def test_failed_preflight_preserves_current(self):
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "current.json").write_text('{"version":"2.0.0-beta.1"}')
            (home / "pending.json").write_text('{"version":"2.0.0-beta.2"}')

            def runtime(v):
                if v.endswith(".2"):
                    raise RuntimeError("dependency failure")
                return home, Path(sys.executable)

            with (
                patch.object(bootstrap, "HOME", home),
                patch.object(bootstrap, "runtime", side_effect=runtime),
                patch.object(sys, "argv", ["bootstrap.py"]),
                patch.object(sys, "version_info", (3, 13)),
                patch("bootstrap.subprocess.call", return_value=0),
            ):
                with self.assertRaises(SystemExit):
                    bootstrap.main()
            self.assertEqual(
                json.loads((home / "current.json").read_text())["version"],
                "2.0.0-beta.1",
            )
            self.assertFalse((home / "pending.json").exists())


class PlaybackConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def test_spotify_pause_waits_for_actual_state(self):
        from studio.providers import Spotify
        from studio.settings import Settings

        with tempfile.TemporaryDirectory() as tmp:
            p = Spotify(Mock(), Settings(Path(tmp) / "s.json"), Mock())
            p.api = AsyncMock(
                side_effect=[
                    {"is_playing": True},
                    {},
                    {"is_playing": True},
                    {"is_playing": False},
                ]
            )
            with patch("studio.providers.asyncio.sleep", new=AsyncMock()):
                await p.pause()
            self.assertEqual(p.api.await_count, 4)

    async def test_refuses_unconfirmed_spotify_pause(self):
        from studio.providers import Spotify
        from studio.settings import Settings

        with tempfile.TemporaryDirectory() as tmp:
            p = Spotify(Mock(), Settings(Path(tmp) / "s.json"), Mock())
            p.api = AsyncMock(return_value={"is_playing": True})
            with patch("studio.providers.asyncio.sleep", new=AsyncMock()):
                with self.assertRaisesRegex(ValueError, "confirm"):
                    await p.pause()
