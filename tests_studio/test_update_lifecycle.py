"""Update retention, failure safety and publisher configuration regressions."""
import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import bootstrap
from studio.updater import Updater
from studio.update_publisher import validate_publisher
from tools import release


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        p = patch.object(bootstrap, 'HOME', self.home)
        p.start(); self.addCleanup(p.stop)
        self.versions = [f'2.0.0-beta.{i}' for i in range(1, 6)]
        for version in self.versions:
            folder = self.home / 'versions' / version
            (folder / 'runtime').mkdir(parents=True)
            (folder / 'runtime/python.exe').write_bytes(b'runtime-fixture')
            (folder / 'entry.py').write_text('# fixture')
        self.mark('current', self.versions[1])
        self.mark('previous', self.versions[0])
        self.data = {
            'userdata/studio.json': b'{"theme":"dark","fallback":"fixture"}',
            'userdata/accounts.json': b'{"fixture_token":"keep"}',
            'userdata/queue.sqlite3': b'queue fixture',
            'userdata/widgets/background.gif': b'GIF fixture',
            'userdata/overlay-key.txt': b'permanent fixture widget key',
            'userdata/moderators.json': b'pairing fixture',
        }
        for name, value in self.data.items():
            path = self.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        spec = importlib.util.spec_from_file_location('install_lifecycle_test',
            Path(__file__).resolve().parents[1] / 'packaging/windows/install_support.py')
        self.support = importlib.util.module_from_spec(spec)
        old_path = sys.path[:]
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))
        spec.loader.exec_module(self.support)
        self.support.root = self.home

    def mark(self, name, version):
        bootstrap.save(self.home / (name + '.json'), {'version': version})

    def assert_data(self):
        for name, value in self.data.items():
            self.assertEqual((self.home / name).read_bytes(), value, name)

    def activate(self, version, code=0):
        result = subprocess.CompletedProcess([], code, '', 'fixture failure' if code else '')
        with patch.object(self.support.subprocess, 'run', return_value=result):
            self.support.activate(version)

    def test_successful_install_cleans_old_versions_and_keeps_rollback_data(self):
        self.activate(self.versions[2])
        self.assertEqual({p.name for p in (self.home / 'versions').iterdir()}, set(self.versions[1:3]))
        self.assertEqual(json.loads((self.home / 'previous.json').read_text())['version'], self.versions[1])
        self.assertTrue((self.home / 'versions' / self.versions[2] / '.ready').exists())
        self.assert_data()

    def test_repeated_installs_keep_exactly_one_previous_and_same_data(self):
        for version in self.versions[2:]:
            folder = self.home / 'versions' / version / 'runtime'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'python.exe').touch()
            self.activate(version)
            self.assertEqual(len(list((self.home / 'versions').iterdir())), 2)
            self.assert_data()

    def test_reinstall_same_version_preserves_rollback(self):
        self.activate(self.versions[1])
        self.assertEqual(json.loads((self.home / 'previous.json').read_text())['version'], self.versions[0])
        self.assert_data()

    def test_failed_installer_preflight_does_not_delete_or_activate(self):
        before = {p.name for p in (self.home / 'versions').iterdir()}
        with self.assertRaisesRegex(RuntimeError, 'Component check failed'):
            self.activate(self.versions[2], code=1)
        self.assertEqual({p.name for p in (self.home / 'versions').iterdir()}, before)
        self.assertEqual(json.loads((self.home / 'current.json').read_text())['version'], self.versions[1])
        self.assert_data()

    def test_pending_version_is_protected(self):
        self.mark('pending', self.versions[2])
        self.assertEqual(set(bootstrap.cleanup_versions()), set(self.versions[3:]))
        self.assert_data()

    def test_bad_or_missing_markers_fail_closed(self):
        for contents in ('bad json', '{"version":"../userdata"}', '{"version":null}', '{}'):
            (self.home / 'current.json').write_text(contents)
            self.assertEqual(bootstrap.cleanup_versions(), [])
        (self.home / 'current.json').unlink()
        self.assertEqual(bootstrap.cleanup_versions(), [])
        self.mark('current', '9.9.9')
        self.assertEqual(bootstrap.cleanup_versions(), [])
        self.assertEqual(len(list((self.home / 'versions').iterdir())), 5)
        self.assert_data()

    def test_unknown_folders_and_external_symlinks_untouched(self):
        extra = self.home / 'versions' / 'my-backup'
        extra.mkdir(); (extra / 'keep').write_text('keep')
        linked = self.home / 'versions' / '9.9.9'
        try:
            linked.symlink_to(self.home / 'userdata', target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation is not available for this account')
        bootstrap.cleanup_versions()
        self.assertTrue(linked.is_symlink())
        self.assertEqual((extra / 'keep').read_text(), 'keep')
        self.assert_data()

    def test_versions_directory_link_is_not_traversed(self):
        original = self.home / 'versions'
        moved = self.home / 'saved-versions'
        original.rename(moved)
        try:
            original.symlink_to(moved, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation is not available for this account')
        self.assertEqual(bootstrap.cleanup_versions(), [])
        self.assertEqual(len(list(moved.iterdir())), 5)

    def test_locked_old_files_retry_without_failing_update(self):
        with patch.object(bootstrap.shutil, 'rmtree', side_effect=PermissionError('locked')):
            self.activate(self.versions[2])
        self.assertEqual(json.loads((self.home / 'current.json').read_text())['version'], self.versions[2])
        self.assertEqual(len(bootstrap.cleanup_versions()), 3)
        self.assert_data()

    def run_launcher(self, args=(), fail=None):
        def runtime(version):
            if version == fail:
                raise RuntimeError('fixture preflight failure')
            return self.home / 'versions' / version, Path(sys.executable)
        with patch.object(sys, 'argv', ['bootstrap.py', *args]), patch.object(sys, 'version_info', (3, 13)), \
                patch.object(bootstrap, 'runtime', side_effect=runtime), \
                patch.object(bootstrap.subprocess, 'call', return_value=0):
            with self.assertRaises(SystemExit) as exit:
                bootstrap.main()
            self.assertEqual(exit.exception.code, 0)

    def test_staged_update_activation_and_rollback_keep_settings(self):
        self.mark('pending', self.versions[2])
        self.run_launcher()
        self.assertEqual({p.name for p in (self.home / 'versions').iterdir()}, set(self.versions[1:3]))
        self.assertFalse((self.home / 'pending.json').exists())
        self.run_launcher(['--rollback'])
        self.assertEqual(json.loads((self.home / 'current.json').read_text())['version'], self.versions[1])
        self.assertEqual(json.loads((self.home / 'previous.json').read_text())['version'], self.versions[2])
        self.assert_data()

    def test_failed_staged_preflight_keeps_all_versions_and_data(self):
        self.mark('pending', self.versions[2])
        self.run_launcher(fail=self.versions[2])
        self.assertEqual(len(list((self.home / 'versions').iterdir())), 5)
        self.assertEqual(json.loads((self.home / 'current.json').read_text())['version'], self.versions[1])
        self.assert_data()


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    def publisher(self):
        return {'repository': 'example/NextUp', 'public_key': base64.b64encode(bytes(range(32))).decode(), 'channel': 'beta'}

    def test_config_validation(self):
        pub = self.publisher()
        validate_publisher(pub, 'example/nextup')
        for changes in ({'repository': ''}, {'repository': 'https://github.com/example/NextUp'},
                        {'public_key': ''}, {'public_key': 'invalid'}, {'public_key': 'YQ=='},
                        {'public_key': None}, {'channel': 'wrong'}):
            with self.assertRaises(ValueError):
                validate_publisher({**pub, **changes})
        with self.assertRaisesRegex(ValueError, 'does not match'):
            validate_publisher(pub, 'another/repo')

    async def test_missing_publisher_reports_setup_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            updater = Updater(Mock(), tmp, tmp)
            updater.get = AsyncMock()
            self.assertIn('docs/PUBLISHING.md', updater.configuration_error)
            with self.assertRaisesRegex(ValueError, 'saved settings'):
                await updater.check()
            updater.get.assert_not_awaited()

    def test_key_generation_will_not_replace_existing_trust_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'publisher.json').write_text(json.dumps(self.publisher()))
            with patch.object(release, 'ROOT', root), patch.object(sys, 'argv', ['release.py', '--generate-key']), \
                    patch.object(release.Path, 'home', return_value=root):
                with self.assertRaisesRegex(SystemExit, 'already pins'):
                    release.main()
            self.assertFalse((root / '.nextup-signing').exists())

    def test_unconfigured_repository_creates_no_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'publisher.json').write_text('{"repository":"","public_key":"","channel":"beta"}')
            with patch.object(release, 'ROOT', root), patch.object(sys, 'argv', ['release.py', '--generate-key']), \
                    patch.object(release.Path, 'home', return_value=root):
                with self.assertRaisesRegex(ValueError, 'not configured'):
                    release.main()
            self.assertFalse((root / '.nextup-signing').exists())

    def test_publisher_preflight_matches_key_and_writes_nothing(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
        key = Ed25519PrivateKey.generate()
        pub = {**self.publisher(), 'public_key': base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()}
        private = base64.b64encode(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'publisher.json').write_text(json.dumps(pub))
            with patch.object(release, 'ROOT', root), patch.object(sys, 'argv', ['release.py', '--check-publisher']), \
                    patch.dict(os.environ, {'NEXTUP_SIGNING_KEY': private, 'GITHUB_REPOSITORY': pub['repository'],
                                           'GITHUB_REF_TYPE': 'tag', 'GITHUB_REF_NAME': 'v' + release.__version__}):
                release.main()
                with patch.dict(os.environ, NEXTUP_SIGNING_KEY=base64.b64encode(bytes(32)).decode()):
                    with self.assertRaisesRegex(SystemExit, 'does not match'):
                        release.main()
            self.assertEqual([p.name for p in root.iterdir()], ['publisher.json'])
