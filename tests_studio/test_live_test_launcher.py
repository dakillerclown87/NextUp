import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('live_test_launcher', Path(__file__).resolve().parents[1]/'tools/live_playback_test.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LiveTestLauncherTests(unittest.TestCase):
    def test_test_settings_are_isolated_and_no_original_files_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, isolated = Path(tmp)/'installed', Path(tmp)/'test'
            data = original/'userdata'
            data.mkdir(parents=True)
            accounts = b'{"dpapi":"SYNTHETIC-ENCRYPTED-LOGIN"}'
            config = b'{"fallback_enabled":true,"fallback_playlist":"PPPPPPPPPPPPPPPPPPPPPP"}'
            (data/'accounts.json').write_bytes(accounts)
            (data/'studio.json').write_bytes(config)
            (data/'queue.sqlite3').write_bytes(b'ORIGINAL-QUEUE')
            launcher.prepare_data(original, isolated)
            settings = json.loads((isolated/'userdata/studio.json').read_text())
            self.assertTrue(settings['spotify_follow_current_playlist'])
            self.assertFalse(settings['fallback_enabled'])
            self.assertFalse((isolated/'userdata/queue.sqlite3').exists())
            self.assertEqual((data/'studio.json').read_bytes(), config)
            self.assertEqual((data/'accounts.json').read_bytes(), accounts)
            self.assertEqual((data/'queue.sqlite3').read_bytes(), b'ORIGINAL-QUEUE')
            self.assertEqual((isolated/'userdata/accounts.json').read_bytes(), accounts)

    def test_second_launch_keeps_test_settings_and_refreshed_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, isolated = Path(tmp)/'installed', Path(tmp)/'test'
            data = isolated/'userdata'
            data.mkdir(parents=True)
            (data/'accounts.json').write_text('updated-login')
            (data/'studio.json').write_text('updated-test-settings')
            launcher.prepare_data(original, isolated)
            self.assertEqual((data/'accounts.json').read_text(), 'updated-login')
            self.assertEqual((data/'studio.json').read_text(), 'updated-test-settings')

    def test_runtime_lookup_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home/'current.json').write_text(json.dumps({'version':'../../elsewhere'}))
            with self.assertRaises(ValueError): launcher.installed_runtime(home)
