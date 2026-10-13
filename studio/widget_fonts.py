"""Bounded portable font containers; fonts are not installed into the OS."""
import base64,hashlib,re,struct
FORMATS={'ttf':b'\x00\x01\x00\x00','otf':b'OTTO','woff':b'wOFF','woff2':b'wOF2'}
MAX_FONT=2*1024*1024
SYSTEM_FONTS={'system','sans','serif','mono'}
def metadata(value):
    if not isinstance(value,list):raise ValueError('Fonts must be a list.')
    rows=[];seen=set()
    for f in value:
        if not isinstance(f,dict):raise ValueError('Invalid widget font.')
        ident,name,fmt=f.get('id'),f.get('name'),f.get('format')
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{64}',ident) or ident in seen:raise ValueError('Invalid or duplicate font identity.')
        if not isinstance(name,str) or not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name):raise ValueError('Font names must be 1–80 characters.')
        if not isinstance(fmt,str) or fmt not in FORMATS:raise ValueError('Use TTF, OTF, WOFF or WOFF2 fonts.')
        seen.add(ident);rows.append(dict(id=ident,name=name.strip(),format=fmt))
    return rows

def validate_font(data,fmt):
    if not 12<=len(data)<=MAX_FONT or data[:4]!=FORMATS.get(fmt):raise ValueError('Invalid font file. Use TTF, OTF, WOFF or WOFF2 under 2 MB.')
    if fmt in ('ttf','otf'):
        n=struct.unpack_from('>H',data,4)[0]
        if not 1<=n<=256 or len(data)<12+16*n:raise ValueError('Damaged font directory.')
        tags=set()
        for i in range(n):
            tag,_,offset,size=struct.unpack_from('>4sIII',data,12+i*16)
            if tag in tags or offset<12+16*n or offset+size>len(data):raise ValueError('Damaged font table.')
            tags.add(tag)
        if not {b'head',b'maxp',b'cmap'}.issubset(tags):raise ValueError('Font is missing required tables.')
    else:
        minimum=44 if fmt=='woff' else 48
        if len(data)<minimum:raise ValueError('Incomplete web font.')
        length,n,reserved,decoded=struct.unpack_from('>IHHI',data,8)
        if length!=len(data) or reserved or not 1<=n<=256 or not 12<=decoded<=16*1024*1024:raise ValueError('Invalid web font header.')
        if fmt=='woff':
            if len(data)<44+20*n:raise ValueError('Incomplete web font directory.')
            for i in range(n):
                _,offset,compressed,original,_=struct.unpack_from('>4sIIII',data,44+20*i)
                if offset<44+20*n or offset+compressed>len(data) or compressed>original or original>decoded:raise ValueError('Invalid web font table.')
        elif not 1<=struct.unpack_from('>I',data,20)[0]<=len(data)-48:raise ValueError('Invalid WOFF2 data length.')
    return data

def decode_font(uri,info):
    prefix='data:font/'+info['format']+';base64,'
    if not isinstance(uri,str) or len(uri)>MAX_FONT*4//3+100 or not uri.startswith(prefix):raise ValueError('Invalid embedded font data.')
    try:data=base64.b64decode(uri[len(prefix):],validate=True)
    except ValueError:raise ValueError('Invalid font encoding.') from None
    validate_font(data,info['format'])
    if hashlib.sha256(data).hexdigest()!=info['id']:raise ValueError('Embedded font does not match its identity.')
    return data
