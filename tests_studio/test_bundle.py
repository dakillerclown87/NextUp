from studio import __version__
NEXT_VERSION = __version__.rsplit(".", 1)[0] + "." + str(int(__version__.rsplit(".", 1)[1]) + 1)
import base64
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import bootstrap
from studio.updater import Updater, unpack, WINDOWS_ASSETS
from tools.build_windows import check_runtime


class BundledBootstrapTests(unittest.TestCase):
    def test_bundled_runtime_never_installs_python_or_pip(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            folder = home / 'versions/2.0.0-beta.2'
            (folder / 'runtime').mkdir(parents=True)
            (folder / 'runtime/python.exe').touch()
            with patch.object(bootstrap, 'HOME', home), patch('bootstrap.subprocess.run') as run:
                _, exe = bootstrap.runtime('2.0.0-beta.2')
                self.assertEqual(exe, folder / 'runtime/python.exe')
                self.assertEqual(run.call_args.args[0][-1], '--preflight')
                self.assertTrue((folder / '.ready').exists())
                bootstrap.runtime('2.0.0-beta.2')
                self.assertEqual(run.call_count, 1)

    def test_bundle_refuses_source_only_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(bootstrap, 'HOME', Path(tmp)), patch.dict(os.environ, NEXTUP_BUNDLED='1'):
                with self.assertRaisesRegex(ValueError, 'no bundled runtime'):
                    bootstrap.runtime(NEXT_VERSION)

    def test_runtime_download_tamper(self):
        with self.assertRaisesRegex(ValueError, 'checksum'):
            check_runtime(b'not the official runtime')

    def test_reject_source_archive_as_bundle(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            for name in ['studio/__init__.py', 'studio/server.py', 'requirements.txt']:
                z.writestr(name, '')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'Incomplete Windows'):
                unpack(b.getvalue(), tmp, bundled=True)
            self.assertEqual(list(Path(tmp).iterdir()), [])


class BundledUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_signed_bundle_preserves_userdata_and_stages_private_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'userdata').mkdir()
            (home / 'userdata/sentinel').write_text('keep')
            key = Ed25519PrivateKey.generate()
            public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
            pub = {'repository': 'owner/repo', 'public_key': public, 'channel': 'beta'}
            (home / 'publisher.json').write_text(json.dumps(pub))
            b = io.BytesIO()
            with zipfile.ZipFile(b, 'w') as z:
                for name in ['studio/__init__.py', 'studio/server.py', 'requirements.txt',
                             'runtime/python.exe', 'runtime/python313.dll', 'entry.py', 'bundle.json']:
                    z.writestr(name, '{}' if name == 'bundle.json' else '')
            archive = b.getvalue()
            manifest = json.dumps({'version':NEXT_VERSION,'platform':'windows-x64','format':1,
                                  'size':len(archive),'sha256':hashlib.sha256(archive).hexdigest()}).encode()
            payload = dict(zip(WINDOWS_ASSETS, [archive, manifest, base64.b64encode(key.sign(manifest))]))
            with patch.dict(os.environ, NEXTUP_BUNDLED='1'):
                u = Updater(Mock(), home, home)
            u.release = {'tag':NEXT_VERSION,'assets':dict(zip(WINDOWS_ASSETS, WINDOWS_ASSETS))}
            async def get(url, limit):
                return payload[url]
            u.get = get
            await u.stage()
            self.assertEqual((home/'userdata/sentinel').read_text(), 'keep')
            self.assertTrue((home/'versions'/NEXT_VERSION/'runtime/python.exe').exists())
            self.assertEqual(json.loads((home/'pending.json').read_text())['version'], NEXT_VERSION)

