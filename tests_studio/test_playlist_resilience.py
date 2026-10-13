"""Fault-injection and accelerated playback soak tests; no live account required."""
import copy
import json
import os
import random
import time
import unittest
from unittest.mock import AsyncMock, patch
import test_fallback
import test_service
from studio.providers import PlaybackStateError, Spotify
from studio.server import Studio
from test_core import track, user

PL = test_fallback.PLAYLIST

class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_fallback.FallbackTests.asyncSetUp
    asyncTearDown = test_fallback.FallbackTests.asyncTearDown

    def state(self, ident, progress=0, **changes):
        return {**test_fallback.FallbackTests.state(self, ident, True, progress),
                'device': {'id':'pc'}, 'context': {'uri':'spotify:playlist:'+PL},
                'repeat_state':'off', 'shuffle_state':False, **changes}

    async def observe(self, data, twice=True):
        self.sp.api.return_value=data
        await self.c.poll_spotify()
        if twice: await self.c.poll_spotify()

    async def test_crossfade_skip_and_long_gap_reconcile_without_new_start(self):
        self.sp.playlist.return_value=[track('f'+str(i)) for i in range(30)]
        await self.c.resume()
        await self.observe(self.state('f0', 170))
        # Spotify crossfades before the old three-second boundary.
        await self.observe(self.state('f1', 3))
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')
        # A long suspend skips several playlist songs; no end sample is available.
        self.c.spotify_sample=None
        self.c.status='Needs attention'
        await self.observe(self.state('f7', 42))
        self.assertEqual(self.q.state['current']['track']['id'], 'f7')
        self.assertEqual(self.q.next_item()['track']['id'], 'f8')
        self.assertEqual(self.sp.play_playlist.await_count, 1)
        self.assertTrue(self.c.enabled)

    async def test_empty_and_older_reports_do_not_detach_or_advance(self):
        await self.c.resume()
        await self.observe(self.state('f1', 50, timestamp=200))
        await self.observe({})
        await self.observe(self.state('outside', timestamp=100))
        self.assertEqual(self.q.state['current']['track']['id'], 'f1')
        self.assertTrue(self.c.enabled)
        self.assertEqual(self.sp.play_playlist.await_count, 1)
        await self.observe(self.state('outside', timestamp=201), twice=False)
        await self.observe(self.state('f1', 60, timestamp=202))
        self.assertEqual(self.sp.play_playlist.await_count, 1)

    async def test_pending_request_wins_over_native_playlist_skip(self):
        await self.c.resume()
        request=self.q.add(track('viewer'),user('real-viewer'),['viewer'])
        await self.observe(self.state('f2'))
        self.assertEqual(self.q.state['current']['id'],request['id'])
        self.assertEqual(self.q.next_item()['track']['id'],'f2')

    async def test_delayed_start_confirmation_recovers_without_reloading_playlist(self):
        self.sp.play_playlist.side_effect=PlaybackStateError('different track','spotify_wrong_track',{})
        with self.assertRaises(PlaybackStateError):await self.c.resume()
        self.assertIsNotNone(self.c.recovery)
        self.c.recovery['at']=0
        self.sp.api.return_value=self.state('f1',10)
        await self.c.retry_recovery()
        self.assertEqual(self.q.state['current']['track']['id'],'f1')
        self.assertIsNone(self.c.recovery)
        self.assertEqual(self.sp.play_playlist.await_count,1)
        self.assertEqual(self.sp.playlist.await_count,1)

    async def test_start_skips_unavailable_track_in_correct_playlist(self):
        self.sp.play_playlist.side_effect=PlaybackStateError('different track','spotify_wrong_track',{})
        with self.assertRaises(PlaybackStateError):await self.c.resume()
        self.c.recovery['at']=0
        self.sp.api.return_value=self.state('f2',4)
        await self.c.retry_recovery()
        self.assertEqual(self.q.state['current']['track']['id'],'f2')
        self.assertEqual(self.sp.play_playlist.await_count,1)

    async def test_recovery_is_bounded_and_pause_cancels_it(self):
        self.sp.play_playlist.side_effect=PlaybackStateError('different track','spotify_wrong_track',{})
        self.sp.api.return_value=self.state('outside')
        with self.assertRaises(PlaybackStateError):await self.c.resume()
        for _ in range(3):
            self.c.recovery['at']=0
            await self.c.retry_recovery()
        self.assertTrue(self.c.recovery['passive'])
        self.assertTrue(self.c.enabled)
        self.assertEqual(self.sp.play_playlist.await_count,4)
        with self.assertRaises(PlaybackStateError):await self.c.resume()
        await self.c.pause()
        self.assertFalse(await self.c.retry_recovery())
        self.assertFalse(self.c.enabled)

    async def test_500_playlist_rows_do_not_fill_request_slots_or_grow_quadratically(self):
        self.s.save({'queue_limit':1})
        self.sp.playlist.return_value=[track('f'+str(i)) for i in range(501)]
        await self.c.resume()
        self.assertEqual(len(self.q.state['items']),500)
        self.assertEqual(self.q.request_count(),0)
        self.q.add(track('viewer'),user('viewer'),['viewer'])
        self.assertEqual(self.q.request_count(),1)
        self.assertEqual(self.q.next_item()['track']['id'],'viewer')
        self.assertLess(len(json.dumps(self.q.snapshot())),600000)
        with self.assertRaisesRegex(ValueError,'viewer request queue is full'):
            self.q.add(track('another'),user('another'),['viewer'])
        self.s.save({'queue_limit':0})
        self.q.add(track('another'),user('another'),['viewer'])
        self.assertEqual(self.q.request_count(),2)

    async def test_playback_does_not_reload_playlist_every_ten_minutes(self):
        await self.c.resume()
        self.c.fallback.loaded_at-=86400
        self.sp.playlist.side_effect=ValueError('provider temporarily unavailable')
        await self.c.next()
        self.assertEqual(self.sp.playlist.await_count,1)
        self.assertEqual(self.q.state['current']['track']['id'],'f2')
        with self.assertRaisesRegex(ValueError,'temporarily unavailable'):
            await self.c.fallback.load(force=True)

    async def test_seeded_long_run_with_crossfade_skips_gaps_stale_reads_and_requests(self):
        count=int(os.environ.get('NEXTUP_SOAK_TRANSITIONS','300'))
        seeds=int(os.environ.get('NEXTUP_SOAK_SEEDS','3'))
        self.sp.playlist.return_value=[track('f'+str(i)) for i in range(80)]
        await self.c.resume()
        for seed in range(seeds):
            rng=random.Random(seed)
            for step in range(count):
                current=self.q.state['current']
                await self.observe(self.state(current['track']['id'],rng.randint(10,180)))
                # Incomplete and isolated false reports must never stop tracking.
                if rng.random()<.2: await self.observe({})
                if rng.random()<.2:
                    await self.observe(self.state('stale-outside'),twice=False)
                    await self.observe(self.state(current['track']['id'],90))
                if rng.random()<.12:
                    ident='request-'+str(seed)+'-'+str(step)
                    request=self.q.add(track(ident),user(ident),['viewer'])
                    await self.c.next()
                    self.assertEqual(self.q.state['current']['id'],request['id'])
                    await self.c.next()
                else:
                    pending=[x for x in self.q.state['items'] if x.get('fallback')]
                    target=pending[min(len(pending)-1,rng.randrange(3))]
                    self.c.play_started-=rng.randint(1,900)
                    self.c.spotify_sample=None
                    await self.observe(self.state(target['track']['id'],rng.randint(0,20)))
                    self.assertEqual(self.q.state['current']['id'],target['id'])
                self.assertTrue(self.c.enabled,(seed,step,self.c.error))
                self.assertEqual(self.c.error,'')
                self.assertTrue(self.q.state['current'].get('fallback'))
        self.assertEqual(self.sp.playlist.await_count,1)


class ServiceResilienceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_service.ServiceTests.asyncSetUp
    asyncTearDown=test_service.ServiceTests.asyncTearDown

    async def test_real_viewer_request_after_loading_500_tracks_and_hidden_setting_persists(self):
        s=self.s
        s.settings.save({'fallback_enabled':True,'fallback_playlist':PL,'queue_limit':2})
        s.vault.put('spotify',{'access_token':'test-only'})
        s.spotify.playlist=AsyncMock(return_value=[track('f'+str(i)) for i in range(500)])
        s.spotify.resolve=AsyncMock(return_value=track('V'*22))
        await s.conductor.fallback.replenish()
        item=await s.request_song('https://open.spotify.com/track/'+'V'*22,user('viewer'),['viewer'])
        self.assertEqual(item['status'],'queued')
        self.assertEqual(s.queue.next_item()['id'],item['id'])
        r=await self.client.post('/api/settings',headers=self.h,json={'hide_playlist':False})
        self.assertEqual(r.status,200)
        self.assertFalse(s.settings.value['hide_playlist'])

    async def test_widget_links_keep_local_origin_and_same_key_across_restart(self):
        before=self.s.state()['widgets']
        self.s.overlay_public='https://temporary.example.test'
        self.assertEqual(self.s.state()['widgets'],before)
        other=Studio(self.session,self.s.home)
        try:
            self.assertEqual(other.state()['widgets'],before)
            self.assertNotEqual(other.admin,self.s.admin)
        finally:await other.cleanup()

    async def test_spotify_playlist_paginates_beyond_500(self):
        sp=object.__new__(Spotify)
        raw={'id':'f','name':'Title','duration_ms':200000,'artists':[{'id':'a','name':'Artist'}]}
        async def api(method,path,params):
            offset=params['offset']
            return {'items':[{'item':{**raw,'id':str(i)}} for i in range(offset,min(offset+50,1201))],
                    'next':'next' if offset+50<1201 else None}
        sp.api=AsyncMock(side_effect=api)
        songs=await sp.playlist(PL)
        self.assertEqual(len(songs),1201)
        self.assertEqual(songs[-1]['id'],'1200')
        self.assertEqual(sp.api.await_count,25)

import test_spotify_continuation

class AdapterSoakTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_service.ServiceTests.asyncSetUp
    asyncTearDown=test_service.ServiceTests.asyncTearDown
    setup_player=test_spotify_continuation.ActivePlaylistTests.setup_player
    item=staticmethod(test_spotify_continuation.ActivePlaylistTests.item)
    natural_next=test_spotify_continuation.ActivePlaylistTests.natural_next

    async def test_real_spotify_adapter_repeated_native_playlist_transitions(self):
        await self.setup_player()
        s=self.s;c=self.c
        s.settings.save({'fallback_enabled':True,'fallback_playlist':test_spotify_continuation.PLAYLIST,
                         'fallback_shuffle':False,'spotify_native_queue':True})
        s.spotify.playlist=AsyncMock(return_value=[track('p'+str(i)) for i in range(31)])
        await c.resume()
        for step in range(int(os.environ.get('NEXTUP_ADAPTER_SOAK','300'))):
            old=s.queue.state['current']
            self.state['progress_ms']=199800
            await c.poll_spotify()
            if s.queue.state['current'] is old:
                self.natural_next()
                await c.poll_spotify()
                await c.poll_spotify()
            self.assertTrue(c.enabled,(step,c.error))
            self.assertEqual(c.error,'')
            self.assertTrue(s.queue.state['current']['fallback'])
            self.assertEqual(s.queue.state['current']['track']['id'],self.state['item']['id'])
            self.assertEqual(self.state['context']['uri'],'spotify:playlist:'+test_spotify_continuation.PLAYLIST)
        s.spotify.playlist.assert_awaited_once()
