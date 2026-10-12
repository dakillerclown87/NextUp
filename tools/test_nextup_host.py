"""Deterministic local fixture for UI regression only; does not use accounts."""
import asyncio,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import AsyncMock
import studio.server as server
original=server.Studio
if '--audio-fixture' in sys.argv:
    original_api=server.api
    async def fixture_api(req):
        if req.match_info['op']=='test-playback':
            from aiohttp import web
            s=req.app[server.STUDIO_KEY];b=await req.json()
            s.conductor.status=b.get('status','Playing')
            s.queue.state['current']['track']['provider']=b.get('provider','spotify')
            return web.json_response({'ok':True})
        return await original_api(req)
    server.api=fixture_api
def create(*a,**k):
    s=original(*a,**k)
    s.settings.save({'block_explicit':False})
    if '--audio-fixture' in sys.argv:
        s.equalizer.helper=Path(__file__).with_name('test_audio_helper.py')
        s.equalizer.unavailable=lambda:''
        s.equalizer.browser_peer=lambda:12345
    if '--redesign-fixture' in sys.argv:
        s.twitch.identity={'user_id':'100'};s.twitch.broadcaster='100';s.twitch.prepare=AsyncMock()
        catalog_rewards=[{'id':'fixture-reward','title':'My Twitch SongRequest','cost':500,'is_user_input_required':True,'is_enabled':True,'is_paused':False}, {'id':'owned-reward','title':'Old NextUp request','cost':1000,'is_user_input_required':True,'is_enabled':True,'is_paused':False}, {'id':'no-text','title':'A reward without text','cost':100,'is_user_input_required':False,'is_enabled':True,'is_paused':False}]
        async def rewards_api(method,path,**kwargs):
            if path!='channel_points/custom_rewards':raise AssertionError(path)
            if method=='POST':
                reward={'id':'new-reward',**kwargs['json'],'is_enabled':True,'is_paused':False}
                catalog_rewards.append(reward);return {'data':[reward]}
            return {'data':[r for r in catalog_rewards if r['id']!='fixture-reward'] if kwargs['params'].get('only_manageable_rewards')=='true' else catalog_rewards}
        s.twitch.api=rewards_api
    tracks=[]
    catalog=[('Midnight Drive','Timecop1983'),('Neon Hearts','The Midnight'),('Electric Dreams','Neon Coast'),('Tokyo Sunset','Night Arcade')]
    if '--redesign-fixture' in sys.argv:catalog += [('After Hours','Night Runner'),('Back to You','Coastal Lights'),('Neon Bloom','Daydream')]
    for i,(title,artist) in enumerate(catalog):
        t={'provider':'spotify','id':str(i)*22,'title':title,'artists':[artist],'artist_ids':['test'],'duration':222+i*15,'explicit':False,'url':'https://open.spotify.com/track/'+str(i)*22,'art':'https://preview.invalid/art'+str(i)+'.svg'}
        tracks.append(t)
        s.queue.add(t,{'id':str(i),'login':['SynthWaveSam','vibez87','synthlover','CyberHawk','nightbot','ellie_day','Skyfall'][i]},['broadcaster'],owner=True)
    s.queue.activate(s.queue.state['items'][0]);s.conductor.status='Playing';s.conductor.progress=88
    s.spotify.pause=AsyncMock();s.spotify.play=AsyncMock();s.spotify.resume=AsyncMock()
    if '--request-fixture' in sys.argv:
        s.settings.save({'block_explicit':True,'review_unknown':True,'require_approval':True})
        def resolved(ident, provider):
            return {**tracks[0], 'id':ident, 'provider':provider,
                    'title':provider.title()+' '+ident, 'artists':['Fixture artist'],
                    'explicit':None if provider=='youtube' else False,
                    'url':('https://open.spotify.com/track/' if provider=='spotify' else 'https://www.youtube.com/watch?v=')+ident}
        s.spotify.resolve=AsyncMock(side_effect=lambda ident:resolved(ident,'spotify'))
        s.youtube.resolve=AsyncMock(side_effect=lambda ident:resolved(ident,'youtube'))
        s.spotify.search=AsyncMock(return_value=[resolved('S'*22,'spotify'),resolved('T'*22,'spotify')])
        s.youtube.search=AsyncMock(return_value=[resolved('SearchTrack','youtube')])
    if '--fallback-fixture' in sys.argv:
        s.vault.put('spotify', {'access_token':'fixture-only'})
        s.spotify.playlist=AsyncMock(return_value=tracks)
        s.spotify.resolve=AsyncMock(return_value={**tracks[3], 'id':'V'*22, 'url':'https://open.spotify.com/track/'+'V'*22})
        async def spotify_api(method,path,**kwargs):
            if path=='me/player':
                current=s.queue.state['current']
                if not current:return {}
                t=current['track']
                return {'is_playing':s.conductor.status=='Playing','progress_ms':s.conductor.progress*1000,
                        'item':{'id':t['id'],'name':t['title'],'duration_ms':t['duration']*1000,
                                'artists':[{'name':t['artists'][0],'id':'test'}]}}
            return {}
        s.spotify.api=spotify_api
    return s
server.Studio=create
asyncio.run(server.run(open_browser=False))
