import unittest,tempfile,json
from pathlib import Path
from studio.customization import equalizer_response,preset
from studio.widget_design import WidgetAssets
from studio.settings import Settings
class EqualizerResponseTests(unittest.TestCase):
 def test_defaults_and_bad_values(self):
  self.assertEqual(equalizer_response({}),dict(sensitivity=1,attack_ms=45,release_ms=220,bass=0))
  for value in [None,[],{'sensitivity':True},{'sensitivity':float('nan')},{'attack_ms':0},{'release_ms':1001},{'bass':-1}]:
   with self.assertRaises(ValueError):equalizer_response(value)
 def test_roundtrip_saved_exported_imported(self):
  p=json.loads((Path(__file__).resolve().parents[1]/'docs/Album-Aura.json').read_text())
  tuning=dict(sensitivity=2.5,attack_ms=10,release_ms=120,bass=80);p['equalizer_response']=tuning;p['equalizer_color_source']='artwork'
  with tempfile.TemporaryDirectory() as tmp:
   a=WidgetAssets(tmp);s=Settings(Path(tmp)/'settings.json');a.save(s,p,True)
   saved=Settings(Path(tmp)/'settings.json').value['widget_presets'][0]
   self.assertEqual(preset(a.export(saved))['equalizer_response'],tuning)
   self.assertEqual(preset(a.export(saved))['equalizer_color_source'],'artwork')
  p.update(format='nextup-widget-v1');self.assertEqual(preset(p)['equalizer_response'],tuning)

 def test_color_source_default_and_validation(self):
  p=dict(format='nextup-widget-v1',name='Colors',layout='spectrum',equalizer=True,colors={})
  self.assertEqual(preset(p)['equalizer_color_source'],'custom')
  for v in [None,True,'bad',{},[]]:
   p['equalizer_color_source']=v
   with self.assertRaises(ValueError):preset(p)
