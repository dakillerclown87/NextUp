import tempfile, unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from studio.playback import Conductor
from studio.queue import Queue
from studio.settings import Settings
from test_core import track, user

class NativeQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.settings=Settings(Path(self.tmp.name)/'settings.json')
        self.settings.save({'provider_mode':'mixed','spotify_native_queue':True})
        self.q=Queue(':memory:',self.settings)
        self.sp=Mock(connected=True,api=AsyncMock(return_value={}),pause=AsyncMock(),play=AsyncMock(),resume=AsyncMock(),advance_queued=AsyncMock(),playback_device=AsyncMock(return_value='pc'))
        self.yt=Mock(last=0,send=AsyncMock())
        self.c=Conductor(self.q,self.sp,self.yt,Mock());self.c.enabled=True
    async def asyncTearDown(self):self.q.db.close();self.tmp.cleanup()
    def add(self,ident,provider='spotify'):
        return self.q.add(track(ident,provider),user(ident),['broadcaster'],owner=True)
    def posts(self):return [x for x in self.sp.api.await_args_list if x.args[0]=='POST']

    async def test_only_next_request_staged_once(self):
        a,b=self.add('a'),self.add('b')
        for _ in range(3):await self.c.native.flush()
        self.assertEqual(len(self.posts()),1);self.assertEqual(a['spotify_delivery'],'sent')
        self.assertNotIn('spotify_delivery',b)
    async def test_never_send_past_youtube(self):
        self.add('y','youtube');a=self.add('a')
        await self.c.native.flush();self.assertFalse(self.posts());self.assertNotIn('spotify_delivery',a)
    async def test_uncertain_append_not_duplicated(self):
        a=self.add('a')
        async def api(method,*args,**kwargs):
            if method=='POST':raise TimeoutError()
            return {}
        self.sp.api.side_effect=api
        await self.c.native.flush();await self.c.native.flush()
        self.assertEqual(a['spotify_delivery'],'uncertain');self.assertEqual(len(self.posts()),1)
    async def test_mixed_queue_consumes_spotify_then_youtube_then_spotify(self):
        a,b,y,d=self.add('a'),self.add('b'),self.add('y','youtube'),self.add('d')
        played=[];self.sp.play.side_effect=lambda t, **kwargs:played.append(t['id']);self.sp.advance_queued.side_effect=lambda t, **kwargs:played.append(t['id'])
        self.yt.send.side_effect=lambda action,t=None:played.append(t['id']) if action=='play' else None
        await self.c.resume() # direct first track
        await self.c.native.flush();self.assertEqual(b['spotify_delivery'],'sent');self.assertNotIn('spotify_delivery',d)
        self.sp.api.return_value={'queue':[{'id':'b'}]}
        await self.c.next(expected=a['id'])
        await self.c.native.flush();self.assertNotIn('spotify_delivery',d)
        await self.c.next(expected=b['id'])
        self.sp.api.return_value={};await self.c.native.flush();self.assertEqual(d['spotify_delivery'],'sent')
        self.sp.api.return_value={'queue':[{'id':'d'}]};await self.c.ended('y')
        self.assertEqual(played,['a','b','y','d'])
        self.assertEqual(self.sp.advance_queued.await_count,2)
    async def test_unrelated_spotify_queue_cannot_replace_requested_track(self):
        a=self.add('a');a['spotify_delivery']='sent'
        self.sp.api.return_value={'queue':[{'id':'unrelated'}]}
        await self.c.resume();self.sp.play.assert_awaited_once_with(a['track'], recover_mismatch=True);self.sp.advance_queued.assert_not_awaited()
    async def test_skip_or_pause_uses_managed_conductor(self):
        a=self.add('a');await self.c.resume();await self.c.pause()
        self.assertFalse(self.c.enabled)
        await self.c.next(expected=a['id']);self.assertEqual(self.q.state['current']['id'],a['id'])
        await self.c.next(manual=True);self.assertIsNone(self.q.state['current'])
    async def test_failed_native_start_retains_request_and_does_not_retry(self):
        a=self.add('a');a['spotify_delivery']='sent';self.sp.api.return_value={'queue':[{'id':'a'}]}
        self.sp.advance_queued.side_effect=ValueError('offline')
        with self.assertRaises(ValueError):await self.c.resume()
        self.assertFalse(self.c.enabled);self.assertIn(a,self.q.state['items']);self.sp.play.assert_not_awaited()
    async def test_rules_rechecked_before_dispatch(self):
        a=self.add('a');a['track']['explicit']=True
        await self.c.native.flush();self.assertFalse(self.posts());self.assertEqual(a['status'],'blocked')
    async def test_sent_items_cannot_be_falsely_removed_or_reordered(self):
        a=self.add('a');await self.c.native.flush()
        with self.assertRaisesRegex(ValueError,'Remove it in Spotify'):self.q.remove(a['id'])
        with self.assertRaisesRegex(ValueError,'Reorder sent'):self.q.reorder([a['id']])
    async def test_native_auto_advance_adopts_only_expected_track(self):
        a,b=self.add('a'),self.add('b');self.q.activate(a);b['spotify_delivery']='sent';self.c.near_end=True
        self.sp.api.return_value={'item':{'id':'b'},'is_playing':True,'progress_ms':500}
        await self.c.poll_spotify();self.assertEqual(self.q.state['current']['id'],b['id']);self.sp.play.assert_not_awaited()

    async def test_already_consumed_native_track_is_not_started_or_skipped_again(self):
        a=self.add('a');a['spotify_delivery']='sent'
        for next_id in ('a','different'):
            self.sp.api.return_value={'item':{'id':'a'},'is_playing':True,
                                      'device':{'id':'pc'},'queue':[{'id':next_id}]}
            await self.c.native.start(a)
        self.sp.play.assert_not_awaited()
        self.sp.advance_queued.assert_not_awaited()

    async def test_wrong_device_is_not_adopted_and_paused_track_is_resumed(self):
        a=self.add('a')
        for playing,device in ((True,'phone'),(False,'pc')):
            self.sp.api.return_value={'item':{'id':'a'},'is_playing':playing,'device':{'id':device}}
            await self.c.native.start(a)
        self.sp.play.assert_awaited_once()
        self.sp.resume.assert_awaited_once_with(a['track'])
        self.sp.advance_queued.assert_not_awaited()

    async def test_natural_handoff_resumes_already_consumed_entry_without_skip(self):
        a,b=self.add('a'),self.add('b');self.q.activate(a);b['spotify_delivery']='sent'
        state={'item':{'id':'b'},'is_playing':True,'device':{'id':'pc'},'queue':[{'id':'b'}]}
        self.sp.api.side_effect=lambda *args,**kwargs:dict(state)
        async def pause(**kwargs): state['is_playing']=False
        self.sp.pause.side_effect=pause
        await self.c.next(expected=a['id'])
        self.sp.resume.assert_awaited_once_with(b['track'])
        self.sp.play.assert_not_awaited()
        self.sp.advance_queued.assert_not_awaited()
        self.assertEqual(self.q.state['current']['id'],b['id'])
