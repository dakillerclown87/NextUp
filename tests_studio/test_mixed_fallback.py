import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
import test_fallback, test_service
from test_core import track, user
from studio.playback import Conductor
from studio.queue import Queue
from studio.providers import YouTube
from studio.settings import validate

class PlaylistTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_fallback.FallbackTests.asyncSetUp
    asyncTearDown=test_fallback.FallbackTests.asyncTearDown
    request=test_fallback.FallbackTests.request
    async def test_youtube_playlist_resume_after_requests_and_provider_switch(self):
        yt=Mock(playlist=AsyncMock(return_value=[{**track('abcdefghijk','youtube'),'explicit':None},track('lmnopqrstuv','youtube')]))
        self.c.fallback.youtube=yt
        self.s.save({'fallback_provider':'youtube','fallback_youtube_playlist':'PLabcdefghijk','fallback_shuffle':False})
        await self.c.resume();self.assertEqual(self.q.state['current']['track']['id'],'abcdefghijk')
        self.request('request','spotify');await self.c.ended('abcdefghijk')
        self.assertEqual(self.q.state['current']['track']['id'],'request')
        await self.c.next();self.assertEqual(self.q.state['current']['track']['id'],'lmnopqrstuv')
        self.s.save({'fallback_provider':'spotify'})
        await self.c.next();self.assertEqual(self.q.state['current']['track']['id'],'f1')
        self.s.save({'fallback_provider':'youtube'})
        await self.c.next();self.assertEqual(self.q.state['current']['track']['id'],'abcdefghijk')
        self.s.save({'fallback_provider':'spotify'})
        await self.c.next();self.assertEqual(self.q.state['current']['track']['id'],'f2')
    async def test_start_with_external_spotify_uses_selected_fallback(self):
        self.c.observed={'id':'external:random','track':track('random'),'user':user()}
        self.c.status='Playing'
        await self.c.resume()
        self.assertEqual(self.q.state['current']['track']['id'],'f1')
        self.sp.resume.assert_not_awaited()
        self.assertEqual(self.calls,['pause:spotify','play:f1'])

    async def test_youtube_cursor_survives_restart(self):
        self.s.save({'fallback_provider':'youtube','fallback_youtube_playlist':'PLabcdefghijk','fallback_shuffle':False})
        yt=Mock(playlist=AsyncMock(return_value=[track('abcdefghijk','youtube'),track('lmnopqrstuv','youtube')]))
        path=Path(self.tmp.name)/'persistent.db';q=Queue(path,self.s)
        c=Conductor(q,self.sp,self.yt,Mock(),yt)
        await c.resume();q.db.close()
        q=Queue(path,self.s)
        try:
            c=Conductor(q,self.sp,self.yt,Mock(),yt);self.assertFalse(c.enabled)
            await c.resume();self.assertEqual(q.state['current']['track']['id'],'lmnopqrstuv')
        finally:q.db.close()
    async def test_failed_youtube_start_does_not_advance_cursor(self):
        self.s.save({'fallback_provider':'youtube','fallback_youtube_playlist':'PLabcdefghijk'})
        self.c.fallback.youtube=Mock(playlist=AsyncMock(return_value=[track('abcdefghijk','youtube')]))
        self.yt.send.side_effect=ValueError('player closed')
        with self.assertRaises(ValueError):await self.c.resume()
        self.assertNotIn('fallback_cursors',self.q.state);self.assertFalse(self.c.enabled)
    async def test_playlist_pagination_batch_metadata_keeps_order_and_skips_unavailable(self):
        youtube=YouTube(Mock(),self.s)
        def video(ident):return {'id':ident,'snippet':{'categoryId':'10','title':ident,'channelTitle':'Artist','channelId':'chan'},'contentDetails':{'duration':'PT3M'},'status':{'embeddable':True}}
        pages=[{'items':[{'contentDetails':{'videoId':'abcdefghijk'}}],'nextPageToken':'two'},
               {'items':[{'contentDetails':{'videoId':'lmnopqrstuv'}},{'contentDetails':{'videoId':'unavailable'}}]},
               {'items':[video('lmnopqrstuv'),video('abcdefghijk')]}]
        youtube.api=AsyncMock(side_effect=pages)
        tracks=await youtube.playlist('PLabcdefghijk')
        self.assertEqual([t['id'] for t in tracks],['abcdefghijk','lmnopqrstuv'])
        self.assertEqual(youtube.api.await_args_list[1].args[1]['pageToken'],'two')
        self.assertEqual(youtube.api.await_count,3)
    def test_youtube_playlist_validation_and_default_order(self):
        self.assertFalse(validate({})['fallback_shuffle'])
        for value in ['PLabcdefghijk','https://www.youtube.com/playlist?list=PLabcdefghijk','https://music.youtube.com/watch?v=abcdefghijk&list=PLabcdefghijk']:
            c=validate({'fallback_provider':'youtube','fallback_enabled':True,'fallback_youtube_playlist':value})
            self.assertEqual(c['fallback_youtube_playlist'],'PLabcdefghijk')
        for value in ['https://evil.test/?list=PLabcdefghijk','https://www.youtube.com/watch?v=abcdefghijk']:
            with self.assertRaises(ValueError):validate({'fallback_youtube_playlist':value})

class MixedSettingsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_service.ServiceTests.asyncSetUp
    asyncTearDown=test_service.ServiceTests.asyncTearDown
    async def test_enabling_spotify_queue_keeps_both_sources_and_playback_intent(self):
        item=self.s.queue.add(track('y','youtube'),user(),['broadcaster'],owner=True);self.s.queue.activate(item);self.s.conductor.enabled=True
        r=await self.client.post('/api/settings',headers=self.h,json={'spotify_native_queue':True})
        self.assertEqual(r.status,200);self.assertEqual(self.s.settings.value['provider_mode'],'mixed');self.assertTrue(self.s.conductor.enabled)
        r=await self.client.post('/api/settings',headers=self.h,json={'provider_mode':'mixed'})
        self.assertEqual(r.status,200);self.assertTrue(self.s.conductor.native.enabled)
    async def test_owner_unknown_video_is_playable_but_viewer_needs_review(self):
        self.s.settings.save({'require_approval':True})
        a=self.s.queue.add({**track('a','youtube'),'explicit':None},user('owner'),['broadcaster'],owner=True)
        b=self.s.queue.add({**track('b','youtube'),'explicit':None},user('viewer'),['viewer'])
        self.assertEqual(a['status'],'queued');self.assertEqual(b['status'],'review')
        self.assertEqual(self.s.queue.next_item()['id'],a['id'])
    async def test_saving_fallback_starts_empty_idle_player_but_not_paused(self):
        import asyncio
        self.s.conductor.resume=AsyncMock()
        r=await self.client.post('/api/settings',headers=self.h,json={'fallback_enabled':True,'fallback_playlist':'A'*22})
        self.assertEqual(r.status,200);await asyncio.sleep(0)
        self.s.conductor.resume.assert_awaited_once()
        self.s.conductor.resume.reset_mock();self.s.conductor.status='Paused'
        r=await self.client.post('/api/settings',headers=self.h,json={'fallback_repeat':True})
        self.assertEqual(r.status,200);await asyncio.sleep(0)
        self.s.conductor.resume.assert_not_awaited()

class SpotifyNativeAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_queued_next_waits_for_track_then_resumes_paused_device(self):
        from studio.providers import Spotify
        sp=object.__new__(Spotify)
        sp.playback_device=AsyncMock(return_value='pc');sp.api=AsyncMock()
        sp.wait_state=AsyncMock(side_effect=[{'is_playing':False,'repeat_state':'off'}, {'is_playing':True,'repeat_state':'off'}])
        await sp.advance_queued(track('a'))
        self.assertEqual([x.args for x in sp.api.await_args_list],[('POST','me/player/next'),('PUT','me/player/play')])
        self.assertEqual([x.args for x in sp.wait_state.await_args_list],[(None,track('a'),'pc'),(True,track('a'),'pc')])
