import base64,struct,tempfile,unittest
from pathlib import Path
from studio.widget_gif import gif, MAX_GIF
from studio.widget_design import WidgetAssets
from studio.settings import Settings
from test_widget_design import design

# Two independent 1px images; preserved, not normalized to a single PNG frame.
HEADER=b'GIF89a'+struct.pack('<HHBBB',1,1,128,0,0)+b'\x00\x00\x00\xff\xff\xff'
FRAME=b'\x21\xf9\x04\x00\x32\x00\x00\x00\x2c'+struct.pack('<HHHHB',0,0,1,1,0)+b'\x02\x02\x44\x01\x00'
GIF=HEADER+FRAME+FRAME+b'\x3b'
class GifTests(unittest.TestCase):
    def test_preserves_all_frames_on_save_export_reimport(self):
        self.assertEqual(gif(GIF),GIF)
        with tempfile.TemporaryDirectory() as t:
            assets=WidgetAssets(Path(t)/'first');settings=Settings(Path(t)/'s.json')
            p=design();p['background_data']='data:image/gif;base64,'+base64.b64encode(GIF).decode();p['background']['stars']=True;p['background']['clouds']=True
            saved=assets.save(settings,p,True)
            self.assertEqual(assets.path(saved['background']['image']).suffix,'.gif')
            exported=assets.export(saved)
            self.assertEqual(exported['background_data'],p['background_data'])
            self.assertTrue(exported['background']['stars']);self.assertTrue(exported['background']['clouds'])
            other=WidgetAssets(Path(t)/'other');again=other.save(settings,exported,True)
            self.assertEqual(other.path(again['background']['image']).read_bytes(),GIF)
    def test_rejects_invalid_truncated_and_oversize_gifs(self):
        for bad in (b'no',GIF[:-1],GIF+b'junk',HEADER+FRAME*301+b'\x3b',b'GIF89a'+struct.pack('<HHBBB',1601,1,128,0,0)+GIF[13:]):
            with self.assertRaises(ValueError):gif(bad)
    def test_rejects_image_data_that_disagrees_with_mime(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):WidgetAssets(t).put('data:image/png;base64,'+base64.b64encode(GIF).decode())

    def test_twenty_mib_gif_boundary_and_oversize_rejection(self):
        left=MAX_GIF-len(GIF)-3;blocks=bytearray()
        while left:
            n=min(255,left-1)
            if left-n-1==1:n-=1
            blocks.extend(bytes([n])+b'x'*n);left-=n+1
        large=GIF[:-1]+b'\x21\xfe'+blocks+b'\0;'
        self.assertEqual(len(large),MAX_GIF)
        self.assertEqual(gif(large),large)
        with tempfile.TemporaryDirectory() as t:
            assets=WidgetAssets(t)
            uri='data:image/gif;base64,'+base64.b64encode(large).decode()
            ident=assets.put(uri)
            self.assertEqual(assets.path(ident).read_bytes(),large)
            self.assertEqual(assets.export({'background':{'image':ident}})['background_data'],uri)
        with self.assertRaisesRegex(ValueError,'20 MB'):gif(large+b'x')
