import base64,io,tempfile,unittest,struct,zlib
from pathlib import Path
from aiohttp import ClientSession
from aiohttp.test_utils import TestServer,TestClient
from studio.server import Studio,admin_app,overlay_app
from studio.settings import Settings
from studio.customization import preset
from studio.widget_design import WidgetAssets,png

def image():
    def chunk(tag,value):return struct.pack('>I',len(value))+tag+value+struct.pack('>I',zlib.crc32(tag+value)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x88\xff\x11\xee\xff\xff'))+chunk(b'IEND',b'')
def design():return {'format':'nextup-widget-v2','name':'Neon test','layout':'spectrum','equalizer':True,'colors':{'accent':'#abcdef'},'canvas':{'width':800,'height':300},'elements':{'title':{'x':200,'y':60,'w':550,'h':48,'size':32,'visible':True}},'background':{'image':'','opacity':.5,'fit':'cover'},'background_data':'data:image/png;base64,'+base64.b64encode(image()).decode()}

class DesignTests(unittest.TestCase):
    def test_save_as_new_keeps_original_and_embeds_background_on_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=Settings(root/'studio.json');assets=WidgetAssets(root)
            first=assets.save(s,design(),True)
            changed={**first,'name':'New copy','colors':{'accent':'#112233'}}
            second=assets.save(s,changed,True)
            self.assertNotEqual(first['id'],second['id']);self.assertEqual(s.value['widget_presets'][0],first)
            portable=assets.export(second);self.assertNotIn('id',portable);self.assertIn('background_data',portable)
            other=WidgetAssets(root/'other');reimported=other.save(Settings(root/'other.json'),portable,True)
            self.assertEqual(other.path(reimported['background']['image']).read_bytes(),image())
            reloaded=Settings(root/'studio.json');self.assertEqual(len(reloaded.value['widget_presets']),2)
    def test_updates_keep_url_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Settings(Path(tmp)/'s.json');assets=WidgetAssets(tmp);p=assets.save(s,design(),True)
            q=assets.save(s,{**p,'colors':{'text':'#123456'}},False)
            self.assertEqual(p['id'],q['id']);self.assertEqual(len(s.value['widget_presets']),1)
    def test_invalid_coordinates_and_unknown_elements_rejected(self):
        for changes in [{'title':{'x':799,'y':10,'w':100,'h':30}}, {'title':{'x':float('nan')}},{'script':{}}]:
            with self.assertRaises(ValueError):preset({**design(),'elements':changes})
    def test_invalid_images_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets=WidgetAssets(tmp)
            for raw in [b'<svg onload="evil()"/>',image()[:-8],image()+b'extra']:
                with self.assertRaises(ValueError):assets.put('data:image/png;base64,'+base64.b64encode(raw).decode())
            with self.assertRaises(ValueError):assets.path('../../secrets')
            self.assertEqual(png(image()),image())
    def test_existing_v1_presets_still_supported(self):
        p=preset({'format':'nextup-widget-v1','name':'Old','layout':'gradient','equalizer':False})
        self.assertEqual(p['format'],'nextup-widget-v1')
    def test_unknown_update_id_does_not_create_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Settings(Path(tmp)/'s.json')
            with self.assertRaisesRegex(ValueError,'new widget'):WidgetAssets(tmp).save(s,design(),False)
            self.assertEqual(s.value['widget_presets'],[])

class WidgetApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.session=ClientSession();self.s=Studio(self.session,Path(self.tmp.name))
        self.admin=TestClient(TestServer(admin_app(self.s)));self.over=TestClient(TestServer(overlay_app(self.s)));await self.admin.start_server();await self.over.start_server()
        self.headers={'Host':'127.0.0.1:8888','X-NextUp-Key':self.s.admin}
    async def asyncTearDown(self):
        await self.admin.close();await self.over.close();await self.s.cleanup();await self.session.close();self.tmp.cleanup()
    async def test_save_export_and_image_routes_with_authorization(self):
        r=await self.admin.post('/api/widget-save',json={'preset':design(),'as_new':True},headers={'Host':'127.0.0.1:8888'});self.assertEqual(r.status,401)
        r=await self.admin.post('/api/widget-save',json={'preset':design(),'as_new':True},headers=self.headers);self.assertEqual(r.status,200);saved=await r.json()
        imagepath='/widget-assets/'+saved['background']['image']+'.png'
        self.assertEqual((await self.over.get(imagepath)).status,401)
        r=await self.over.get(imagepath+'?key='+self.s.overlay_key);self.assertEqual(await r.read(),image())
        r=await self.admin.post('/api/widget-export',json={'id':saved['id']},headers=self.headers);self.assertEqual((await r.json())['background_data'],design()['background_data'])
        r=await self.over.get('/overlay/now?key='+self.s.overlay_key);html=await r.text();self.assertNotIn('__OVERLAY_KEY__',html)
        self.assertEqual((await self.over.post('/api/widget-save?key='+self.s.overlay_key,json={'preset':design()})).status,404)
    async def test_horizon_assets_require_overlay_key(self):
        for route,filename in [('/widget-singularity.js','widget-singularity.js'),('/event-horizon.png','event-horizon.png')]:
            self.assertEqual((await self.over.get(route)).status,401)
            response=await self.over.get(route+'?key='+self.s.overlay_key)
            self.assertEqual(response.status,200)
            self.assertEqual(await response.read(),(Path(__file__).resolve().parents[1]/'studio/static'/filename).read_bytes())
    async def test_bad_presets_do_not_change_settings(self):
        d=design();d['colors']={'text':'red; background:url(x)'}
        r=await self.admin.post('/api/widget-save',json={'preset':d},headers=self.headers);self.assertEqual(r.status,400);self.assertEqual(self.s.settings.value['widget_presets'],[])

class PremiumPresetTests(unittest.TestCase):
    def test_prism_fields_roundtrip_and_validate(self):
        import json
        source=Path(__file__).resolve().parents[1]/'docs/Prism-Afterglow.nextup.json'
        value=json.loads(source.read_text())
        with tempfile.TemporaryDirectory() as t:
            assets=WidgetAssets(t);settings=Settings(Path(t)/'settings.json')
            saved=assets.save(settings,value,True);exported=assets.export(saved)
            self.assertEqual(exported['transition'],'fold')
            self.assertEqual(exported['presentation'],'prism')
            self.assertEqual(assets.save(settings,exported,True)['transition'],'fold')
        for key in ['transition','presentation']:
            with self.assertRaises(ValueError):preset({**value,key:'javascript:invalid'})

class HorizonPresetTests(unittest.TestCase):
    def test_roundtrip_preserves_timing_and_style(self):
        import json
        value=json.loads((Path(__file__).resolve().parents[1]/'docs/Event-Horizon.nextup.json').read_text())
        with tempfile.TemporaryDirectory() as t:
            assets=WidgetAssets(t);settings=Settings(Path(t)/'settings.json')
            saved=assets.save(settings,value,True);exported=assets.export(saved)
            self.assertEqual(exported['transition'],'horizon')
            self.assertEqual(exported['presentation'],'horizon')
            self.assertEqual(assets.save(settings,exported,True)['canvas'],{'width':1120,'height':420})
