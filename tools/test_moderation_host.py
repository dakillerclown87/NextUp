"""Local moderator browser fixture; mutations are controlled by stdin only."""
import asyncio,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aiohttp import ClientSession,web
from studio.server import Studio
async def main():
 with tempfile.TemporaryDirectory() as tmp:
  async with ClientSession() as session:
   s=Studio(session,Path(tmp));s.settings.save({'moderators_enabled':True,'require_approval':True,'fallback_playlist':'A'*22})
   def add(name,owner=False):
    t={'id':name,'title':name,'artists':['Fixture artist'],'artist_ids':[],'provider':'spotify','duration':200,'explicit':False,'url':'https://open.spotify.com/track/'+name}
    return s.queue.add(t,{'id':name,'login':name},['broadcaster'] if owner else ['viewer'],owner=owner)
   current=add('Current song',True);s.queue.activate(current);add('Already queued',True)
   s.conductor.fallback.cached_key=('spotify','A'*22,'');s.conductor.fallback.tracks=[current['track']]
   first=s.moderation.create({'name':'Moderator One'});second=s.moderation.create({'name':'Storage blocked'})
   runner=web.AppRunner(s.moderation.application());await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
   port=site._server.sockets[0].getsockname()[1];url=f'http://127.0.0.1:{port}';s.moderation.public_url=url
   print(json.dumps({'url':url,'code':first['code'],'second':second['code']}),flush=True)
   try:
    while line:=await asyncio.to_thread(sys.stdin.readline):
     command=line.strip()
     if command=='add':add('New viewer request')
     elif command=='revoke':s.moderation.revoke(first['id'])
     elif command=='stop':break
     print(json.dumps({'done':command}),flush=True)
   finally:await runner.cleanup();await s.cleanup()
asyncio.run(main())
