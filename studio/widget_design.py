"""Portable data-only widget designs and bounded, local PNG backgrounds."""
import base64, hashlib, math, re, secrets, struct, zlib
from pathlib import Path
from .widget_gif import gif, MAX_GIF
from .widget_fonts import metadata, SYSTEM_FONTS, FORMATS, decode_font

PARTS = ('art', 'brand', 'title', 'artist', 'requester', 'progress', 'time', 'equalizer', 'queue')
MAX_IMAGE = 2 * 1024 * 1024

def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Widget positions, sizes and opacity must be within the displayed limits.')
    return value

def design(value):
    canvas = value.get('canvas', {})
    if not isinstance(canvas,dict):raise ValueError('Invalid widget canvas.')
    w, h = number(canvas.get('width', 800), 300, 1600), number(canvas.get('height', 300), 150, 1000)
    parts = value.get('elements', {})
    if not isinstance(parts, dict) or set(parts) - set(PARTS): raise ValueError('Unknown widget element.')
    fonts=metadata(value.get('fonts',[]))
    allowed=SYSTEM_FONTS|{f['id'] for f in fonts}
    elements = {}
    for name, p in parts.items():
        if not isinstance(p, dict): raise ValueError('Invalid widget element.')
        x, y = number(p.get('x', 0), 0, w), number(p.get('y', 0), 0, h)
        width, height = number(p.get('w', 100), 8, w), number(p.get('h', 30), 4, h)
        if x + width > w + .01 or y + height > h + .01: raise ValueError('Keep widget elements inside the canvas.')
        if type(p.get('visible', True)) is not bool: raise ValueError('Invalid visibility toggle.')
        font=p.get('font','system')
        if not isinstance(font,str) or font not in allowed:raise ValueError('Select a font included in this widget.')
        weight=number(p.get('weight',700 if name=='title' else 400),100,900)
        if type(weight) is not int or weight%100:raise ValueError('Font weight must be 100, 200, … 900.')
        elements[name] = dict(font=font,weight=weight,spacing=number(p.get('spacing',3 if name=='brand' else 0),-5,20),x=x,y=y,w=width,h=height,size=number(p.get('size', 20), 8, 96),visible=p.get('visible',True))
    background = value.get('background', {})
    if not isinstance(background, dict): raise ValueError('Invalid widget background.')
    asset = background.get('image', '')
    if not isinstance(asset, str) or (asset and not re.fullmatch('[a-f0-9]{64}', asset)): raise ValueError('Invalid widget image.')
    if background.get('fit', 'cover') not in ('cover','contain','stretch'): raise ValueError('Invalid image fit.')
    rect = background.get('rect', {'x':0,'y':0,'w':w,'h':h})
    if not isinstance(rect,dict):raise ValueError('Invalid background placement.')
    rw,rh = number(rect.get('w',w),8,w*4),number(rect.get('h',h),4,h*4)
    rect = dict(x=number(rect.get('x',0),8-rw,w-8),y=number(rect.get('y',0),4-rh,h-4),w=rw,h=rh)
    for motion in ('stars', 'clouds'):
        if type(background.get(motion,False)) is not bool:raise ValueError('Invalid animated '+motion+' toggle.')
    appearance={}
    for key, choices in [('transition',('none','fold','horizon')),('presentation',('standard','prism','horizon'))]:
        if key in value:
            if value[key] not in choices:raise ValueError('Invalid widget '+key+'.')
            appearance[key]=value[key]
    return {**appearance,'fonts':fonts,'canvas': {'width':w,'height':h}, 'elements':elements,
            'background':{'stars':background.get('stars',False),'clouds':background.get('clouds',False),'rect':rect,'image':asset,'opacity':number(background.get('opacity',.5),0,1),'fit':background.get('fit','cover')}}

def png(data):
    """Accept normalized RGB/RGBA PNGs only; verify chunks and bounded pixel data."""
    if len(data)>MAX_IMAGE or not data.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('Use a PNG background under 2 MB, or upload an image through the editor.')
    pos=8; compressed=bytearray(); header=None; ended=False
    while pos+12<=len(data):
        n=struct.unpack('>I',data[pos:pos+4])[0];tag=data[pos+4:pos+8];chunk=data[pos+8:pos+8+n]
        if pos+12+n>len(data) or zlib.crc32(tag+chunk)&0xffffffff != struct.unpack('>I',data[pos+8+n:pos+12+n])[0]: raise ValueError('Damaged PNG background.')
        if tag==b'IHDR':
            if header is not None or pos!=8 or n!=13:raise ValueError('Invalid PNG header.')
            width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',chunk)
            if not (1<=width<=2048 and 1<=height<=2048 and width*height<=2_000_000) or (depth,color,compression,filtering,interlace) not in [(8,2,0,0,0),(8,6,0,0,0)]:raise ValueError('Upload this image through the editor to resize/convert it.')
            header=(width,height,3 if color==2 else 4)
        elif tag==b'IDAT':compressed.extend(chunk)
        elif tag==b'IEND':ended=True;pos+=12+n;break
        elif tag==b'acTL':raise ValueError('Animated backgrounds are not supported.')
        pos+=12+n
    if not header or not ended or pos!=len(data):raise ValueError('Incomplete PNG background.')
    width,height,channels=header;expected=height*(width*channels+1)
    try:
        decoder=zlib.decompressobj(); pixels=decoder.decompress(compressed,expected+1)
        if len(pixels)!=expected or not decoder.eof or decoder.unused_data:raise ValueError('Invalid PNG pixels.')
    except zlib.error:raise ValueError('Invalid PNG pixels.') from None
    return data

class WidgetAssets:
    def __init__(self, data):self.folder=Path(data)/'widget-assets'
    def path(self, ident):
        if not re.fullmatch('[a-f0-9]{64}',ident):raise ValueError('Invalid widget image.')
        animated=self.folder/(ident+'.gif')
        return animated if animated.is_file() else self.folder/(ident+'.png')
    def font_path(self,ident,fmt):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{64}',ident) or not isinstance(fmt,str) or fmt not in FORMATS:raise ValueError('Invalid widget font.')
        return self.folder/(ident+'.'+fmt)
    def put(self, uri):
        if not isinstance(uri,str) or not uri.startswith(('data:image/png;base64,','data:image/gif;base64,')):raise ValueError('Choose a PNG (2 MB) or GIF (20 MB) background.')
        limit = MAX_GIF if uri.startswith('data:image/gif;') else MAX_IMAGE
        if len(uri)>4*((limit+2)//3)+100:raise ValueError('Background exceeds the '+str(limit//(1024*1024))+' MB limit.')
        try:data=base64.b64decode(uri.split(',',1)[1],validate=True)
        except ValueError:raise ValueError('Invalid background image encoding.') from None
        fmt='gif' if uri.startswith('data:image/gif;') else 'png'
        (gif if fmt=='gif' else png)(data); ident=hashlib.sha256(data).hexdigest();self.folder.mkdir(parents=True,exist_ok=True)
        path=self.folder/(ident+'.'+fmt)
        if not path.exists():path.write_bytes(data)
        return ident
    def export(self,p):
        result=dict(p);ident=p.get('background',{}).get('image')
        if ident:
            path=self.path(ident)
            if not path.exists():raise ValueError('Background image is missing; upload it again.')
            result['background_data']='data:image/'+path.suffix[1:]+';base64,'+base64.b64encode(path.read_bytes()).decode()
        result['font_data']={}
        for font in p.get('fonts',[]):
            path=self.font_path(font['id'],font['format'])
            if not path.is_file():raise ValueError('Font file is missing; upload it again.')
            result['font_data'][font['id']]='data:font/'+font['format']+';base64,'+base64.b64encode(path.read_bytes()).decode()
        if p.get('format')=='nextup-widget-v3':
            result['elements']={k:dict(v) for k,v in p['elements'].items()}
            for part in result['elements'].values():
                if part.get('asset'):
                    path=self.path(part['asset'])
                    if not path.exists():raise ValueError('Layer image is missing.')
                    part['image_data']='data:image/'+path.suffix[1:]+';base64,'+base64.b64encode(path.read_bytes()).decode()
        result.pop('id',None)
        return result
    def save(self,settings,value,as_new):
        from .customization import preset
        if not isinstance(value,dict):raise ValueError('Invalid widget preset.')
        value=dict(value);rows=settings.value['widget_presets']
        if as_new:value['id']=secrets.token_hex(8)
        elif not any(p['id']==value.get('id') for p in rows):raise ValueError('Save this design as a new widget first.')
        uri=value.pop('background_data',None)
        embedded=value.pop('font_data',{})
        if not isinstance(embedded,dict):raise ValueError('Invalid embedded fonts.')
        # Validate coordinates and names before writing image bytes.
        validated=preset(value)
        fonts=validated.get('fonts',[])
        if set(embedded)-{f['id'] for f in fonts}:raise ValueError('Unexpected embedded font.')
        pending=[]
        for font in fonts:
            path=self.font_path(font['id'],font['format'])
            if font['id'] in embedded:pending.append((path,decode_font(embedded[font['id']],font)))
            elif not path.is_file():raise ValueError('Font file is missing. Import the exported widget or upload the font again.')
        if uri is not None:
            if validated['format'] not in ('nextup-widget-v2','nextup-widget-v3'):raise ValueError('Background images need widget format v2.')
            validated['background']['image']=self.put(uri)
        if validated['format']=='nextup-widget-v3':
            for key,part in validated['elements'].items():
                uri=value['elements'][key].get('image_data')
                if uri is not None:part['asset']=self.put(uri)
                if part['asset'] and not self.path(part['asset']).is_file():raise ValueError('Layer image is missing. Import the complete exported widget.')
        ident=validated.get('background',{}).get('image')
        if ident and not self.path(ident).is_file():raise ValueError('Background image is missing. Import the exported widget file or upload the image again.')
        for path,data in pending:
            self.folder.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix('.tmp');temp.write_bytes(data);temp.replace(path)
        updated=[*rows,validated] if as_new else [validated if p['id']==validated['id'] else p for p in rows]
        settings.save({'widget_presets':updated})
        return validated
