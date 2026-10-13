"""Overlay delivery on ANSI-default Windows and portable heading preferences."""
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from studio.customization import preset
from studio.settings import Settings
from studio.widget_design import WidgetAssets
from tests_studio import test_widget_design as fixtures

class HeadingTests(unittest.TestCase):
    def test_heading_roundtrip_and_save_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings=Settings(Path(tmp)/'s.json');assets=WidgetAssets(tmp)
            original=assets.save(settings,fixtures.design(),True)
            changed=assets.save(settings,{**original,'label':'Now Playing'},True)
            self.assertEqual(settings.value['widget_presets'][0],original)
            exported=assets.export(changed)
            self.assertEqual(exported['label'],'Now Playing')
            other=assets.save(settings,exported,True)
            self.assertEqual(other['label'],'Now Playing')
            self.assertEqual(Settings(settings.path).value['widget_presets'][-1]['label'],'Now Playing')
    def test_heading_validation_and_legacy_defaults(self):
        for bad in [None,1,False,'x'*81,'one\ntwo','\0','\x7f']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):preset({**fixtures.design(),'label':bad})
        for text in ['', 'Now Playing','Música 🎵','<b>Now Playing</b>']:
            self.assertEqual(preset({**fixtures.design(),'label':text})['label'],text)
        self.assertNotIn('label',preset(fixtures.design()))
        old={'format':'nextup-widget-v1','name':'Old','layout':'spectrum','equalizer':True,'label':'Now Playing'}
        self.assertEqual(preset(old)['label'],'Now Playing')
    def test_builtin_branding_setting_persists_and_rejects_non_boolean(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Settings(Path(tmp)/'s.json');self.assertTrue(s.value['widget_branding'])
            s.save({'widget_branding':False});self.assertFalse(Settings(s.path).value['widget_branding'])
            with self.assertRaises(ValueError):s.save({'widget_branding':'false'})

class WindowsOverlayTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.WidgetApiTests.asyncSetUp
    asyncTearDown=fixtures.WidgetApiTests.asyncTearDown
    async def test_all_overlay_pages_work_with_windows_ansi_default(self):
        original=Path.read_text
        def windows_read(path,encoding=None,errors=None):
            return original(path,encoding=encoding or ('cp1252' if path.name=='overlay.html' else 'utf-8'),errors=errors)
        with patch.object(Path,'read_text',windows_read):
            for kind in ('now','gradient','queue'):
                for suffix in ('','&preset=0','&preset_id=0123456789abcdef'):
                    r=await self.over.get('/overlay/'+kind+'?key='+self.s.overlay_key+suffix)
                    self.assertEqual(r.status,200,kind+suffix);self.assertEqual(r.charset,'utf-8')
                    html=await r.text();self.assertIn('Waiting for NextUp…',html);self.assertNotIn('__OVERLAY_KEY__',html)
    async def test_overlay_exposes_saved_branding(self):
        r=await self.admin.post('/api/settings',json={'widget_branding':False},headers=self.headers)
        self.assertEqual(r.status,200)
        r=await self.over.get('/state?key='+self.s.overlay_key)
        self.assertIs((await r.json())['branding'],False)
