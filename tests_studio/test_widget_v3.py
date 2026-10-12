import base64,copy,json,tempfile,unittest
from pathlib import Path
from studio.customization import preset
from studio.widget_design import WidgetAssets
from studio.widget_fonts import metadata
from studio.settings import Settings
from test_widget_design import image
ROOT=Path(__file__).resolve().parents[1]
def design():return json.loads((ROOT/'docs/Automata-Animated.json').read_text())
class V3Tests(unittest.TestCase):
 def test_motion_layer_and_robot_roundtrip(self):
  p=design();p['elements']['custom']=dict(p['elements']['art'],kind='image',image_data='data:image/png;base64,'+base64.b64encode(image()).decode(),x=-40)
  p['elements']['custom']['motion']={'type':'custom','frames':[{'offset':0,'scale':1},{'offset':.5,'x':50,'rotate':20,'scale':1.2},{'offset':1,'scale':1}]}
  with tempfile.TemporaryDirectory() as tmp:
   a=WidgetAssets(tmp);settings=Settings(Path(tmp)/'settings.json');saved=a.save(settings,p,True);export=a.export(saved)
   self.assertEqual(export['elements']['custom']['image_data'],p['elements']['custom']['image_data']);self.assertEqual(export['elements']['custom']['x'],-40)
   other=WidgetAssets(Path(tmp)/'other');again=other.save(Settings(Path(tmp)/'other.json'),export,True)
   self.assertEqual(again['elements'],saved['elements']);self.assertEqual(again['robot'],saved['robot']);self.assertNotEqual(again['id'],saved['id'])
 def test_arbitrary_layer_and_saved_preset_counts(self):
  p=design()
  for i in range(250):p['elements']['decoration_'+str(i)]={'kind':'shape','x':-100,'y':1200,'w':20,'h':20}
  self.assertEqual(len(preset(p)['elements']),261)
  with tempfile.TemporaryDirectory() as tmp:
   s=Settings(Path(tmp)/'s.json');s.save({'widget_presets':[dict(design(),id=format(i,'016x')) for i in range(35)]});self.assertEqual(len(Settings(Path(tmp)/'s.json').value['widget_presets']),35)
 def test_more_than_four_fonts_allowed(self):
  fonts=[{'id':format(i,'064x'),'name':'Font '+str(i),'format':'woff2'} for i in range(10)]
  self.assertEqual(len(metadata(fonts)),10)
 def test_rejects_malformed_nested_data_and_unsafe_styles(self):
  for key in ['canvas','background','surface','robot']:
   for value in [[],42,'bad',None]:
    p=design();p[key]=value
    with self.subTest(key=key,value=value),self.assertRaises(ValueError):preset(p)
  for prop,value in [('kind','script'),('fill','url(https://evil)'),('x',float('nan')),('font',{}),('asset','../../secret'),('opacity',2)]:
   p=design();p['elements']['art'][prop]=value
   with self.subTest(prop=prop),self.assertRaises(ValueError):preset(p)
  p=design();p['robot']['target']='title'
  with self.assertRaises(ValueError):preset(p)
 def test_rejects_invalid_motion_keyframes(self):
  for frames in [[],[{'offset':0},{'offset':0},{'offset':1}],[{'offset':.2},{'offset':1}],[{'offset':0},{'offset':1,'scale':0}]]:
   p=design();p['elements']['art']['motion']={'type':'custom','frames':frames}
   with self.assertRaises(ValueError):preset(p)
 def test_effects_survive_save_export_restart(self):
  p=json.loads((ROOT/'docs/Halo-Orbit-Glow.json').read_text())
  with tempfile.TemporaryDirectory() as tmp:
   a=WidgetAssets(tmp);settings=Settings(Path(tmp)/'settings.json');saved=a.save(settings,p,True)
   again=Settings(Path(tmp)/'settings.json').value['widget_presets'][0];export=a.export(again)
   self.assertEqual(export['progress_colors'],p['progress_colors']);self.assertEqual(export['border_motion'],p['border_motion'])
   self.assertEqual(len(export['progress_colors']),8)
 def test_rejects_invalid_effects(self):
  for effect,value in [('progress_colors',[]),('progress_colors',['#ffffff']*9),('progress_colors',['#ffffff','url(evil)']),('border_motion',[]),('border_motion',{'enabled':True,'target':'title'}),('border_motion',{'enabled':False,'colors':['#ffffff']}),('border_motion',{'enabled':False,'seconds':float('nan')})]:
   p=design();p[effect]=value
   with self.subTest(effect=effect,value=value),self.assertRaises(ValueError):preset(p)

 def test_legacy_background_effects_roundtrip(self):
  p=design();p['background'].update(clouds=True,stars=True)
  with tempfile.TemporaryDirectory() as tmp:
   a=WidgetAssets(tmp);s=Settings(Path(tmp)/'settings.json');a.save(s,p,True)
   saved=Settings(Path(tmp)/'settings.json').value['widget_presets'][0]
   self.assertTrue(a.export(saved)['background']['clouds']);self.assertTrue(a.export(saved)['background']['stars'])
  for key in ['stars','clouds']:
   p['background'][key]='false'
   with self.assertRaises(ValueError):preset(p)
   p['background'][key]=False
