"""Actual conductor + Spotify adapter with deterministic service responses."""
import unittest
from unittest.mock import AsyncMock, Mock
import test_service
from test_core import track, user

class OrderedPlaybackTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_service.ServiceTests.asyncSetUp
    asyncTearDown=test_service.ServiceTests.asyncTearDown

    async def exercise(self, fallback_provider):
        s=self.s;c=s.conductor
        s.settings.save({'spotify_native_queue':True,'provider_mode':'mixed','fallback_enabled':True,
                        'fallback_provider':fallback_provider,'fallback_playlist':'F'*22,
                        'fallback_youtube_playlist':'PLabcdefghijk','fallback_shuffle':False})
        s.vault.put('spotify',{'access_token':'test-only'})
        state={'device':{'id':'pc'},'item':None,'is_playing':False,'progress_ms':0,'repeat_state':'off'}
        native=[];played=[];appended=[]
        def item(ident):return {'id':ident,'name':ident,'duration_ms':200000,'artists':[{'id':'artist','name':'Artist'}]}
        async def api(method,path,**kwargs):
            if path=='me/player/devices':return {'devices':[{'id':'pc','is_active':True}]}
            if method=='GET' and path=='me/player/queue':return {'queue':[item(x) for x in native]}
            if method=='POST' and path=='me/player/queue':
                ident=kwargs['params']['uri'].split(':')[-1];native.append(ident);appended.append(ident)
            elif method=='POST' and path=='me/player/next':state.update(item=item(native.pop(0)),progress_ms=0)
            elif method=='PUT' and path=='me/player/pause':state['is_playing']=False
            elif method=='PUT' and path=='me/player/play':
                if kwargs.get('json',{}).get('uris'):state.update(item=item(kwargs['json']['uris'][0].split(':')[-1]),progress_ms=0)
                if kwargs.get('json',{}).get('context_uri'):
                    state.update(item=item(kwargs['json']['offset']['uri'].split(':')[-1]), progress_ms=0,context={'uri':kwargs['json']['context_uri']})
                state['is_playing']=True;played.append(state['item']['id'])
            return dict(state) if method=='GET' else {}
        s.spotify.api=api
        s.spotify.playlist=AsyncMock(return_value=[track('f1'),track('f2')])
        s.youtube.playlist=AsyncMock(return_value=[track('yf1','youtube'),track('yf2','youtube')])
        async def youtube(action,t=None):
            if action=='play':played.append(t['id'])
        c.bridge=Mock(last=0,send=AsyncMock(side_effect=youtube))
        for ident,provider in [('a','spotify'),('b','spotify'),('y','youtube'),('d','spotify')]:
            s.queue.add(track(ident,provider),user(ident),['broadcaster'],owner=True)
        async def end_spotify():
            before=s.queue.state['current']
            state['progress_ms']=199800
            await c.poll_spotify()
            if s.queue.state['current'] is before and native:
                state.update(item=item(native.pop(0)),progress_ms=0)
                played.append(state['item']['id'])
                await c.poll_spotify()
                await c.poll_spotify()
        await c.resume();await c.native.flush()
        await end_spotify();await c.native.flush()
        await end_spotify();await c.native.flush()
        self.assertEqual(s.queue.state['current']['track']['id'],'y')
        self.assertFalse(state['is_playing'])
        await c.ended('y');await end_spotify()
        first='f1' if fallback_provider=='spotify' else 'yf1'
        self.assertEqual(played,['a','b','y','d',first])
        self.assertEqual(appended,['b','d'])
        self.assertTrue(s.queue.state['current']['fallback'])
        s.queue.add(track('request'),user('request'),['broadcaster'],owner=True)
        await c.native.flush()
        if fallback_provider=='spotify':await end_spotify()
        else:await c.ended('yf1')
        self.assertEqual(s.queue.state['current']['track']['id'],'request')
        await end_spotify()
        self.assertEqual(s.queue.state['current']['track']['id'],'f2' if fallback_provider=='spotify' else 'yf2')

    async def test_mixed_order_then_spotify_fallback_and_resume(self):await self.exercise('spotify')
    async def test_mixed_order_then_youtube_fallback_and_resume(self):await self.exercise('youtube')
