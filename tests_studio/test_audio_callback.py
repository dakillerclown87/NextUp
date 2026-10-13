"""Compile and exercise the production callback; no Windows/audio claim."""
import os,shutil,subprocess,tempfile,unittest
from pathlib import Path
class CallbackContractTests(unittest.TestCase):
    def test_production_callback_agility_identity_and_lifetime(self):
        compiler=shutil.which('cc') or shutil.which('gcc')
        if not compiler:self.skipTest('A native C compiler is required for the callback contract test.')
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as t:
            exe=Path(t)/('callback.exe' if os.name=='nt' else 'callback')
            subprocess.run([compiler,'-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',str(root/'tests_native/audio_completion_test.c'),'-o',str(exe)],check=True,capture_output=True)
            result=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
            self.assertIn('supports IAgileObject',result.stdout)
