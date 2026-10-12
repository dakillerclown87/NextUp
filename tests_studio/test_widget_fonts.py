import base64, copy, hashlib, struct, tempfile, unittest
from pathlib import Path
from studio.widget_fonts import metadata, validate_font
from studio.widget_design import WidgetAssets
from studio.settings import Settings
from studio.customization import preset
from tests_studio import test_widget_design as fixtures


def font_bytes():
    tags=[b'head',b'maxp',b'cmap'];offset=12+16*len(tags)
    return (b'\x00\x01\x00\x00'+struct.pack('>HHHH',3,0,0,0)
        +b''.join(struct.pack('>4sIII',tag,0,offset+i*4,4) for i,tag in enumerate(tags))+b'\0'*12)

def design():
    p=fixtures.design();raw=font_bytes();ident=hashlib.sha256(raw).hexdigest()
    p['fonts']=[{'id':ident,'name':'Test serif','format':'ttf'}]
    p['font_data']={ident:'data:font/ttf;base64,'+base64.b64encode(raw).decode()}
    p['elements']['title'].update(font=ident,weight=600,spacing=1.5)
    return p

class FontTests(unittest.TestCase):
    def test_portable_fonts_and_copy_preserve_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=Settings(root/'s.json');assets=WidgetAssets(root)
            original=assets.save(s,design(),True);portable=assets.export(original)
            self.assertNotIn('font_data',original);self.assertNotIn('id',portable)
            self.assertEqual(portable['font_data'],design()['font_data'])
            changed=copy.deepcopy(portable);changed['elements']['title']['weight']=800
            saved=assets.save(s,changed,True);self.assertNotEqual(original['id'],saved['id'])
            self.assertEqual(s.value['widget_presets'][0],original)
            other=WidgetAssets(root/'other');p=other.save(Settings(root/'other.json'),portable,True)
            self.assertEqual(other.font_path(p['fonts'][0]['id'],'ttf').read_bytes(),font_bytes())
            self.assertEqual(p['elements']['title']['weight'],600)
            self.assertEqual(p['elements']['title']['spacing'],1.5)
    def test_missing_font_and_hash_mismatch_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Settings(Path(tmp)/'s.json');a=WidgetAssets(tmp)
            for missing in [True,False]:
                p=design()
                if missing:p['font_data']={}
                else:
                    f=p['fonts'][0];uri=p['font_data'].pop(f['id']);f['id']='a'*64
                    p['font_data'][f['id']]=uri;p['elements']['title']['font']=f['id']
                with self.assertRaises(ValueError):a.save(s,p,True)
                self.assertEqual(s.value['widget_presets'],[])
    def test_corrupt_font_containers_rejected(self):
        for fmt,raw in [('ttf',font_bytes()[:-1]),('ttf',b'fake'),('woff',b'wOFF'+b'\0'*60),('woff2',b'wOF2'+b'\0'*60)]:
            with self.assertRaises(ValueError):validate_font(raw,fmt)
    def test_typography_bounds(self):
        for key,value in [('font','unknown'),('weight',950),('weight',True),('spacing',float('inf')),('spacing',21)]:
            p=design();p['elements']['title'][key]=value
            with self.assertRaises(ValueError):preset(p)
    def test_metadata_and_asset_paths(self):
        f=design()['fonts'][0]
        for fonts in [[f]*5,[f,f],[{**f,'id':'../x'}],[{**f,'format':'exe'}]]:
            with self.assertRaises(ValueError):metadata(fonts)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):WidgetAssets(tmp).font_path('../x','ttf')
    def test_old_widget_defaults(self):
        p=preset(fixtures.design());self.assertEqual(p['fonts'],[])
        self.assertEqual(p['elements']['title']['font'],'system')
        self.assertEqual(p['elements']['title']['weight'],700)
        self.assertEqual(p['elements']['title']['spacing'],0)

class FontApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.WidgetApiTests.asyncSetUp
    asyncTearDown=fixtures.WidgetApiTests.asyncTearDown
    async def test_font_routes_require_key_and_export_embeds(self):
        r=await self.admin.post('/api/widget-save',json={'preset':design(),'as_new':True},headers=self.headers)
        self.assertEqual(r.status,200);p=await r.json();route='/widget-fonts/'+p['fonts'][0]['id']+'.ttf'
        self.assertEqual((await self.over.get(route)).status,401)
        r=await self.over.get(route+'?key='+self.s.overlay_key)
        self.assertEqual(r.status,200);self.assertEqual(r.content_type,'font/ttf');self.assertEqual(await r.read(),font_bytes())
        r=await self.admin.post('/api/widget-export',json={'id':p['id']},headers=self.headers)
        self.assertEqual((await r.json())['font_data'],design()['font_data'])
