import io,unittest,tempfile
from PIL import Image
from pathlib import Path
from studio.artwork_palette import allowed,extract
from studio.customization import preset,equalizer_style
from studio.widget_design import WidgetAssets
from studio.settings import Settings
from test_widget_v3 import design
class PaletteTests(unittest.TestCase):
 def test_known_hosts_only(self):
  for url in ['https://i.scdn.co/image/abc','https://i.ytimg.com/vi/abc/hqdefault.jpg']:self.assertTrue(allowed(url))
  for url in ['http://i.scdn.co/image/abc','https://i.scdn.co.evil.test/a','https://localhost/a','https://127.0.0.1/a','https://user@i.scdn.co/a','https://i.scdn.co:5000/a','file:///tmp/a']:self.assertFalse(allowed(url))
 def test_palette_and_monochrome(self):
  im=Image.new('RGB',(80,80),'#ed2030');im.paste('#2244ff',(40,0,80,80));b=io.BytesIO();im.save(b,format='PNG');colors=extract(b.getvalue());self.assertIn('#ed2030',colors);self.assertIn('#2244ff',colors)
  b=io.BytesIO();Image.new('RGB',(20,20),'black').save(b,format='PNG');self.assertEqual(len(extract(b.getvalue())),2)
 def test_settings_roundtrip(self):
  p=design();p.update(progress_color_source='artwork',equalizer_style='circle-bars')
  with tempfile.TemporaryDirectory() as tmp:
   a=WidgetAssets(tmp);s=Settings(Path(tmp)/'settings.json');a.save(s,p,True);saved=Settings(Path(tmp)/'settings.json').value['widget_presets'][0];export=a.export(saved);self.assertEqual(export['progress_color_source'],'artwork');self.assertEqual(export['equalizer_style'],'circle-bars')
  p['progress_color_source']='bad'
  with self.assertRaises(ValueError):preset(p)
  for value in ['circle-bars','circle-wave','orb','circle-dots','particle-sphere']:self.assertEqual(equalizer_style(value),value)
