import json, tempfile, unittest
from pathlib import Path
from studio.customization import preset
from studio.settings import Settings
from studio.widget_design import WidgetAssets
from tests_studio.test_widget_design import design

class BackgroundPlacementTests(unittest.TestCase):
    def test_old_background_defaults_to_canvas(self):
        p=preset(design());self.assertEqual(p['background']['rect'],{'x':0,'y':0,'w':800,'h':300})
    def test_resized_background_roundtrip_and_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=WidgetAssets(tmp);s=Settings(Path(tmp)/'s.json');original=a.save(s,design(),True)
            draft=json.loads(json.dumps(a.export(original)));rect={'x':-100,'y':20,'w':1000,'h':260};draft['background']['rect']=rect
            saved=a.save(s,draft,True);self.assertEqual(s.value['widget_presets'][0],original)
            self.assertEqual(saved['background']['rect'],rect)
            portable=a.export(saved);other=WidgetAssets(Path(tmp)/'other');p=other.save(Settings(Path(tmp)/'other.json'),portable,True)
            self.assertEqual(p['background']['rect'],rect)
    def test_bad_background_bounds_rejected(self):
        for value in [[],{'w':float('inf')},{'w':True},{'h':0},{'w':3201},{'x':900},{'x':-900}]:
            with self.subTest(rect=value),self.assertRaises(ValueError):
                p=design();p['background']['rect']=value;preset(p)
