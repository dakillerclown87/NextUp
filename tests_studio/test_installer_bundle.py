import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.repack_windows_ui import missing_requirements

class InstallerBundleTests(unittest.TestCase):
    def test_repack_rescans_when_directory_timestamp_does_not_change(self):
        import os
        from importlib.metadata import distributions
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);site=root/'site';site.mkdir();lock=root/'lock.txt'
            lock.write_text('Pillow==12.3.0 --hash=sha256:fixture\n')
            stamp=site.stat()
            self.assertEqual(list(distributions(path=[str(site)])),[])
            self.assertEqual(len(missing_requirements(site,lock)),1)
            info=site/'pillow-12.3.0.dist-info';info.mkdir()
            (info/'METADATA').write_text('Name: Pillow\nVersion: 12.3.0\n')
            os.utime(site,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            self.assertEqual(missing_requirements(site,lock),[])
            (info/'METADATA').write_text('Name: Pillow\nVersion: 12.2.0\n')
            self.assertEqual(len(missing_requirements(site,lock)),1)

    def test_repack_detects_missing_and_outdated_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);site=root/'site';site.mkdir();lock=root/'lock.txt'
            lock.write_text('Pillow==12.3.0 --hash=sha256:fixture\n')
            self.assertEqual(len(missing_requirements(site,lock)),1)
            info=site/'pillow-12.2.0.dist-info';info.mkdir()
            (info/'METADATA').write_text('Name: Pillow\nVersion: 12.2.0\n')
            self.assertEqual(len(missing_requirements(site,lock)),1)
            (info/'METADATA').write_text('Name: Pillow\nVersion: 12.3.0\n')
            self.assertEqual(missing_requirements(site,lock),[])

    def test_failed_preflight_retains_active_version_and_records_cause(self):
        import bootstrap
        spec=importlib.util.spec_from_file_location('installer_failure_test',Path(__file__).resolve().parents[1]/'packaging/windows/install_support.py')
        support=importlib.util.module_from_spec(spec);old_path=list(sys.path)
        try:
            spec.loader.exec_module(support)
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);version='2.0.0-beta.47'
                (root/'versions'/version).mkdir(parents=True)
                original=json.dumps({'version':'2.0.0-beta.44'})
                (root/'current.json').write_text(original)
                (root/'userdata').mkdir();(root/'userdata/accounts.json').write_text('keep')
                result=subprocess.CompletedProcess([],1,'',"ModuleNotFoundError: No module named 'PIL'")
                with patch.object(support,'root',root),patch.object(bootstrap,'HOME',root),patch.object(support.subprocess,'run',return_value=result):
                    with self.assertRaisesRegex(RuntimeError,'Component check failed'):support.activate(version)
                self.assertEqual((root/'current.json').read_text(),original)
                self.assertEqual((root/'userdata/accounts.json').read_text(),'keep')
                self.assertIn("No module named 'PIL'",(root/'install-diagnostics.txt').read_text())
                self.assertFalse((root/'versions'/version/'.ready').exists())
        finally:sys.path[:]=old_path

    def test_repack_replaces_corrupt_runtime_and_keeps_dependencies(self):
        import io,zipfile
        from tools.repack_windows_ui import refresh_runtime
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('python313.dll',b'verified runtime bytes')
        with tempfile.TemporaryDirectory() as tmp:
            build=Path(tmp);app=build/'app';runtime=app/'runtime'
            runtime.mkdir(parents=True);(runtime/'python313.dll').write_bytes(b'broken')
            dep=runtime/'Lib/site-packages/fixture.txt';dep.parent.mkdir(parents=True);dep.write_text('keep')
            archive=build/'source.zip';archive.write_bytes(stream.getvalue())
            with patch('tools.build_windows.check_runtime') as verify:
                refresh_runtime(build,app,archive)
                verify.assert_called_once_with(stream.getvalue())
            for root in (build/'runtime',runtime):
                self.assertEqual((root/'python313.dll').read_bytes(),b'verified runtime bytes')
            self.assertEqual(dep.read_text(),'keep')

    def test_truncated_native_binary_is_rejected(self):
        import struct
        from tools.repack_windows_ui import check_pe
        data=bytearray(512);data[:2]=b'MZ';struct.pack_into('<I',data,60,128)
        data[128:132]=b'PE\0\0';struct.pack_into('<H',data,134,1)
        struct.pack_into('<H',data,148,0);struct.pack_into('<II',data,168,1024,512)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'broken.dll';path.write_bytes(data)
            with self.assertRaisesRegex(ValueError,'Truncated section'):check_pe(path)
