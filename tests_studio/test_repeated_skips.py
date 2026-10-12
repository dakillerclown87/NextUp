"""Manual-skip regression using the real conductor and Spotify adapter.

The simulated Connect client can reject repeated context reloads and delay
status independently of audio. No live Spotify account is implied.
"""
import copy
import os
import unittest
from unittest.mock import AsyncMock, patch
import test_spotify_continuation as fixture
from test_core import track
from studio.providers import PlaybackStateError

class RepeatedSkipTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixture.ActivePlaylistTests.asyncSetUp
    asyncTearDown=fixture.ActivePlaylistTests.asyncTearDown
    setup_player=fixture.ActivePlaylistTests.setup_player
    item=staticmethod(fixture.ActivePlaylistTests.item)
    natural_next=fixture.ActivePlaylistTests.natural_next

    async def setup_saved(self):
        await self.setup_player()
        self.s.settings.save({'fallback_enabled':True,'fallback_playlist':fixture.PLAYLIST,
                              'fallback_shuffle':False,'spotify_native_queue':True})
        self.s.spotify.playlist=AsyncMock(return_value=[track('p'+str(i)) for i in range(1001)])
        self.sleep=patch('studio.providers.asyncio.sleep',new=AsyncMock())
        self.sleep.start();self.addCleanup(self.sleep.stop)

    async def test_two_then_many_skips_do_not_reload_playlist(self):
        await self.setup_saved()
        raw=self.s.spotify.api
        reloads=0
        async def api(method,path,**kwargs):
            nonlocal reloads
            if method=='PUT' and path=='me/player/play' and kwargs.get('json',{}).get('context_uri'):
                reloads+=1
                if reloads>=3: return {} # Connect accepts but keeps the old song.
            return await raw(method,path,**kwargs)
        self.s.spotify.api=api
        await self.c.resume()
        for step in range(int(os.environ.get('NEXTUP_SKIP_SOAK','50'))):
            response=await self.client.post('/api/playback',headers=self.h,json={'action':'next'})
            self.assertEqual(response.status,200,await response.text())
            self.assertEqual(self.s.queue.state['current']['track']['id'],'p'+str(step+1))
            self.assertEqual(self.c.error,'')
            self.assertTrue(self.c.enabled)
        self.assertLessEqual(reloads,1)
        self.s.spotify.playlist.assert_awaited_once()

    async def test_delayed_second_skip_confirmation_does_not_repeat_skip_or_restart(self):
        await self.setup_saved()
        raw=self.s.spotify.api
        remaining=0;stale=None;skips=0
        async def api(method,path,**kwargs):
            nonlocal remaining,stale,skips
            if method=='POST' and path=='me/player/next':
                skips+=1
                if skips==2: stale=copy.deepcopy(self.state);remaining=26
            if method=='GET' and path=='me/player' and remaining:
                remaining-=1
                return copy.deepcopy(stale)
            return await raw(method,path,**kwargs)
        self.s.spotify.api=api
        await self.c.resume();await self.c.next(manual=True)
        with self.assertRaises(PlaybackStateError):await self.c.next(manual=True)
        # Audio already advanced; the reporting endpoint is still behind.
        self.assertEqual(self.state['item']['id'],'p2')
        self.state['progress_ms']=12000
        writes=len(self.actions)
        for _ in range(8):
            if self.c.recovery:
                self.c.recovery['at']=0
                await self.c.retry_recovery()
        self.assertEqual(len(self.actions),writes)
        self.assertEqual(skips,2)
        self.assertEqual(self.s.queue.state['current']['track']['id'],'p2')
        self.assertEqual(self.c._progress,12)
        self.assertEqual(self.state['progress_ms'],12000)
        self.assertEqual(self.c.error,'')
        self.assertEqual(self.s.spotify.last_start_report['result'],'confirmed_late')

    async def test_already_started_playlist_song_is_not_restarted_on_retry(self):
        await self.setup_saved();await self.c.resume()
        self.state.update(item=self.item('p1'),progress_ms=23000)
        writes=len(self.actions)
        data=await self.s.spotify.play_playlist(track('p1'),fixture.PLAYLIST)
        self.assertEqual(len(self.actions),writes)
        self.assertEqual(data['progress_ms'],23000)

    async def test_late_context_start_is_observed_without_position_zero_retry(self):
        await self.setup_saved();await self.c.resume()
        raw=self.s.spotify.api
        stale=copy.deepcopy(self.state);remaining=26
        async def api(method,path,**kwargs):
            nonlocal remaining
            if method=='GET' and path=='me/player' and remaining:
                remaining-=1
                return copy.deepcopy(stale)
            return await raw(method,path,**kwargs)
        # An unrelated native head forces the explicit context-offset path.
        self.native=['outside']
        self.s.spotify.api=api
        with self.assertRaises(PlaybackStateError):await self.c.next(manual=True)
        self.assertTrue(self.c.recovery['confirmation_only'])
        self.assertEqual(self.state['item']['id'],'p1')
        self.state['progress_ms']=17500
        writes=len(self.actions)
        for _ in range(8):
            if self.c.recovery:
                self.c.recovery['at']=0
                await self.c.retry_recovery()
        self.assertEqual(len(self.actions),writes)
        self.assertEqual(self.state['progress_ms'],17500)
        self.assertEqual(self.c._progress,17.5)
        self.assertEqual(self.c.error,'')

    async def test_two_skips_then_youtube_and_viewer_request_keep_queue_order(self):
        from test_core import user
        await self.setup_saved();await self.c.resume()
        await self.c.next(manual=True);await self.c.next(manual=True)
        yt=self.s.queue.add(track('video','youtube'),user('a'),['broadcaster'])
        song=self.s.queue.add(track('viewer'),user('b'),['broadcaster'])
        await self.c.next(manual=True)
        self.assertEqual(self.s.queue.state['current']['id'],yt['id'])
        self.assertFalse(self.state['is_playing'])
        await self.c.ended('video')
        self.assertEqual(self.s.queue.state['current']['id'],song['id'])
        await self.c.next(manual=True)
        self.assertEqual(self.s.queue.state['current']['track']['id'],'p3')
        for i in range(4,14):
            await self.c.next(manual=True)
            self.assertEqual(self.state['item']['id'],'p'+str(i))
            self.assertEqual(self.state['context']['uri'],'spotify:playlist:'+fixture.PLAYLIST)
        self.assertEqual(self.c.error,'')
        self.assertTrue(self.s.spotify.connected)
        self.s.spotify.playlist.assert_awaited_once()

    async def test_overlapping_skips_do_not_queue_duplicate_commands(self):
        import asyncio
        await self.setup_saved();await self.c.resume()
        raw=self.s.spotify.api
        entered,release=asyncio.Event(),asyncio.Event()
        async def api(method,path,**kwargs):
            if method=='POST' and path=='me/player/next':
                entered.set();await release.wait()
            return await raw(method,path,**kwargs)
        self.s.spotify.api=api
        task=asyncio.create_task(self.c.next(manual=True))
        try:
            await asyncio.wait_for(entered.wait(),1)
            for _ in range(5):
                with self.assertRaisesRegex(ValueError,'already running'):await self.c.next(manual=True)
        finally:
            release.set();await task
        self.assertEqual(sum(p=='me/player/next' for m,p,k in self.actions),1)
        self.assertEqual(self.s.queue.state['current']['track']['id'],'p1')

    async def pending_skip(self):
        await self.setup_saved();await self.c.resume()
        raw=self.s.spotify.api
        stale=copy.deepcopy(self.state);lag=False
        async def api(method,path,**kwargs):
            nonlocal lag
            if method=='POST' and path=='me/player/next':lag=True
            if method=='GET' and path=='me/player' and lag:return copy.deepcopy(stale)
            return await raw(method,path,**kwargs)
        self.s.spotify.api=api
        with self.assertRaises(PlaybackStateError):await self.c.next(manual=True)
        return raw

    async def test_pause_stops_audio_while_accepted_skip_is_unconfirmed(self):
        raw=await self.pending_skip()
        self.s.spotify.api=raw
        await self.c.pause()
        self.assertFalse(self.state['is_playing'])
        self.assertFalse(self.c.enabled)
        self.assertIsNone(self.c.recovery)

    async def test_explicit_skip_abandons_pending_background_track(self):
        raw=await self.pending_skip()
        self.s.spotify.api=raw
        await self.c.next(manual=True)
        self.assertEqual(self.s.queue.state['current']['track']['id'],'p2')
        self.assertEqual(self.state['item']['id'],'p2')
        self.assertIsNone(self.c.recovery)
        self.assertEqual(self.c.error,'')

    async def test_observation_does_not_adopt_wrong_context_or_other_device(self):
        raw=await self.pending_skip()
        self.s.spotify.api=raw
        writes=len(self.actions)
        for context,device in [('spotify:album:'+'A'*22,'pc'),('spotify:playlist:'+fixture.PLAYLIST,'phone')]:
            self.state.update(context={'uri':context},device={'id':device})
            for _ in range(3):
                self.c.recovery['at']=0
                await self.c.retry_recovery()
            self.assertIsNotNone(self.c.recovery)
            self.assertEqual(len(self.actions),writes)
        self.state.update(context={'uri':'spotify:playlist:'+fixture.PLAYLIST},device={'id':'pc'},progress_ms=26000)
        await self.c.retry_recovery()
        self.assertIsNone(self.c.recovery)
        self.assertEqual(self.state['progress_ms'],26000)
        self.assertEqual(len(self.actions),writes)

    async def test_restoring_lost_context_preserves_live_song_position(self):
        await self.setup_saved();await self.c.resume()
        self.state.update(context={'uri':'spotify:album:'+'A'*22},progress_ms=42000)
        await self.s.spotify.play_playlist(track('p0'),fixture.PLAYLIST)
        self.assertEqual(self.state['progress_ms'],42000)
        self.assertEqual(self.state['context']['uri'],'spotify:playlist:'+fixture.PLAYLIST)
        starts=[k for m,p,k in self.actions if p=='me/player/play']
        self.assertEqual(starts[-1]['json']['position_ms'],42000)

    async def test_launcher_skip_route_abandons_pending_background_track(self):
        raw=await self.pending_skip()
        self.s.spotify.api=raw
        response=await self.client.post('/api/playback',headers=self.h,json={'action':'next'})
        self.assertEqual(response.status,200,await response.text())
        self.assertEqual(self.s.queue.state['current']['track']['id'],'p2')
        self.assertEqual(self.state['item']['id'],'p2')
