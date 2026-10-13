"""Small, cached palettes from provider artwork; no arbitrary URL proxy."""
import asyncio,io,time
from urllib.parse import urlsplit
from aiohttp import ClientTimeout

HOSTS={'i.scdn.co','mosaic.scdn.co','i.ytimg.com','img.youtube.com'}
def allowed(url):
 try:
  u=urlsplit(url)
  return u.scheme=='https' and u.hostname in HOSTS and not u.username and not u.password and u.port in (None,443)
 except (ValueError,TypeError):return False

def extract(data):
 from PIL import Image
 with Image.open(io.BytesIO(data)) as image:
  if image.width*image.height>16000000:raise ValueError('Artwork too large')
  image.thumbnail((80,80));rgb=image.convert('RGB');small=rgb.quantize(colors=16)
  palette=small.getpalette();ranked=sorted(small.getcolors() or [],reverse=True);chosen=[]
  for count,index in ranked:
   c=tuple(palette[index*3:index*3+3])
   if max(c)<25 or min(c)>240:continue
   if all(sum((a-b)**2 for a,b in zip(c,old))>1800 for old in chosen):chosen.append(c)
   if len(chosen)==8:break
  if not chosen:chosen=[tuple(round(v) for v in rgb.resize((1,1)).getpixel((0,0)))]
  if len(chosen)==1:chosen.append(tuple(min(255,round(v*.7+55)) for v in chosen[0]))
  return ['#%02x%02x%02x'%c for c in chosen]

class ArtworkPalette:
 def __init__(self,session):self.session=session;self.cache={};self.lock=asyncio.Lock()
 async def get(self,url):
  if not allowed(url):return []
  async with self.lock:
   now=time.monotonic();cached=self.cache.get(url)
   if cached and cached[0]>now:return cached[1]
   result=[]
   try:
    async with self.session.get(url,allow_redirects=False,timeout=ClientTimeout(total=5)) as response:
     if response.status==200 and response.headers.get('Content-Type','').split(';')[0] in ('image/jpeg','image/png','image/webp','image/gif'):
      data=bytearray()
      async for block in response.content.iter_chunked(65536):
       data.extend(block)
       if len(data)>4*1024*1024:raise ValueError('Artwork too large')
      result=await asyncio.to_thread(extract,bytes(data))
   except Exception:pass
   if len(self.cache)>=64:self.cache.pop(next(iter(self.cache)))
   self.cache[url]=(now+(600 if result else 30),result)
   return result
