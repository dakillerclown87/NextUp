import json,tempfile,unittest,zipfile
from pathlib import Path
from tools.build_extensions import build
class ExtensionBuildTests(unittest.TestCase):
    def test_both_packages_share_code_with_platform_specific_manifests(self):
        with tempfile.TemporaryDirectory() as t:
            paths=build(t)
            with zipfile.ZipFile(paths[0]) as chromium,zipfile.ZipFile(paths[1]) as firefox:
                a=json.loads(chromium.read('manifest.json'));b=json.loads(firefox.read('manifest.json'))
                self.assertEqual(a['manifest_version'],3);self.assertEqual(b['manifest_version'],2)
                self.assertTrue(b['background']['persistent']);self.assertNotIn('service_worker',b['background'])
                self.assertEqual(a['permissions']+a['host_permissions'],b['permissions'])
                self.assertEqual(a['action'],b['browser_action']);self.assertEqual(b['browser_specific_settings']['gecko']['id'],'nextup-player@nextup.local')
                for name in ['background.js','content.js','popup.js','popup.html']:self.assertEqual(chromium.read(name),firefox.read(name))
                self.assertEqual(chromium.testzip(),None);self.assertEqual(firefox.testzip(),None)
