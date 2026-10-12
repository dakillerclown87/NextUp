"""Recovery must retain requests and bound writes across every Spotify mode."""
import unittest
from unittest.mock import AsyncMock
import test_fallback
from test_core import track, user
from studio.providers import PlaybackStateError

class RecoveryModeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_fallback.FallbackTests.asyncSetUp
    asyncTearDown = test_fallback.FallbackTests.asyncTearDown

    def state(self, ident, **changes):
        return {**test_fallback.FallbackTests.state(self, ident, True, 12),
                'device': {'id':'pc'}, 'context': {'uri':'spotify:playlist:'+test_fallback.PLAYLIST}, **changes}

    def failure(self):
        return PlaybackStateError('different track', 'spotify_wrong_track', self.state('outside'))

    async def retry(self):
        self.c.recovery['at']=0
        await self.c.retry_recovery()

    async def request_failure(self):
        self.s.save({'fallback_enabled':False})
        row=self.q.add(track('request'),user('viewer'),['broadcaster'])
        self.sp.play.side_effect=self.failure()
        with self.assertRaises(PlaybackStateError): await self.c.resume()
        return row

    async def test_request_late_confirmation_is_adopted_without_replaying(self):
        row=await self.request_failure()
        self.sp.api.return_value=self.state('request')
        await self.retry()
        self.assertEqual(self.q.state['current']['id'],row['id'])
        self.assertTrue(self.c.enabled)
        self.assertIsNone(self.c.recovery)
        self.sp.play.assert_awaited_once()
        self.assertIsNone(self.c.failed_item)

    async def test_persistent_request_mismatch_bounds_writes_and_keeps_monitoring(self):
        row=await self.request_failure()
        self.sp.api.return_value=self.state('outside')
        for _ in range(30): await self.retry()
        self.assertEqual(self.sp.play.await_count,4)
        self.assertTrue(self.c.enabled)
        self.assertIn(row,self.q.state['items'])
        self.assertTrue(self.c.recovery['passive'])
        self.sp.api.return_value=self.state('request')
        await self.retry()
        self.assertEqual(self.q.state['current']['id'],row['id'])
        self.assertIsNone(self.c.recovery)

    async def test_native_playlist_late_confirmation_adopts_actual_context_song(self):
        self.s.save({'fallback_enabled':False})
        self.c.continuation.context={'uri':'spotify:playlist:'+test_fallback.PLAYLIST,
                                    'return_track':track('f1'),'device':'pc'}
        self.sp.play_playlist.side_effect=self.failure()
        with self.assertRaises(PlaybackStateError): await self.c.resume()
        self.sp.api.return_value=self.state('f2')
        await self.retry()
        self.assertEqual(self.q.state['current']['track']['id'],'f2')
        self.assertTrue(self.c.continuation.active)
        self.sp.play_playlist.assert_awaited_once()

    async def test_repeatedly_bad_fallback_is_deferred_next_song_starts(self):
        async def start(t,*args,**kwargs):
            if t['id']=='f1': raise self.failure()
            return self.state(t['id'])
        self.sp.play_playlist.side_effect=start
        self.sp.api.return_value=self.state('outside')
        with self.assertRaises(PlaybackStateError): await self.c.resume()
        for _ in range(4): await self.retry()
        self.assertEqual(self.q.state['current']['track']['id'],'f2')
        self.assertTrue(self.c.enabled)
        self.assertIn(('spotify',test_fallback.PLAYLIST,'f1'),self.c.fallback.deferred)
        self.assertIn('skipped',self.c.fallback.note)
        await self.c.fallback.load(force=True)
        self.assertFalse(self.c.fallback.deferred)

    async def test_all_fallback_failures_do_not_loop_control_commands(self):
        self.sp.play_playlist.side_effect=self.failure()
        self.sp.api.return_value=self.state('outside')
        with self.assertRaises(PlaybackStateError): await self.c.resume()
        for _ in range(35): await self.retry()
        self.assertTrue(self.c.enabled)
        self.assertEqual(self.sp.play_playlist.await_count,8)
        self.assertEqual(len(self.c.recovery_skips),2)
        self.assertTrue(self.c.recovery['passive'])

    async def test_resume_recovery_does_not_duplicate_history(self):
        self.s.save({'fallback_enabled':False})
        row=self.q.add(track('request'),user('viewer'),['broadcaster'])
        self.q.activate(row)
        self.sp.resume.side_effect=self.failure()
        with self.assertRaises(PlaybackStateError): await self.c.resume()
        self.sp.api.return_value=self.state('request')
        await self.retry()
        self.assertEqual(self.q.state['history'],[])
        self.assertEqual(self.q.state['current']['id'],row['id'])

    async def test_device_change_does_not_take_over_other_device(self):
        row=await self.request_failure()
        self.sp.api.return_value=self.state('request',device={'id':'phone'})
        for _ in range(5): await self.retry()
        self.sp.play.assert_awaited_once()
        self.assertIn(row,self.q.state['items'])
        self.assertTrue(self.c.recovery['passive'])

    async def test_pause_while_status_pending_cancels_recovery(self):
        row=await self.request_failure()
        async def response(*args,**kwargs):
            await self.c.pause()
            return self.state('request')
        self.sp.api.side_effect=response
        await self.retry()
        self.assertFalse(self.c.enabled)
        self.assertIsNone(self.c.recovery)
        self.assertIn(row,self.q.state['items'])

    async def test_late_success_is_observed_before_retry_deadline(self):
        row=await self.request_failure()
        import time
        self.c.recovery['at']=time.monotonic()+30
        self.sp.api.return_value=self.state('request')
        await self.c.retry_recovery()
        self.assertEqual(self.q.state['current']['id'],row['id'])
        self.assertEqual(self.c.error,'')
        self.assertIsNone(self.c.recovery)
        self.sp.play.assert_awaited_once()

    async def test_status_checks_during_backoff_do_not_send_control_writes(self):
        await self.request_failure()
        import time
        self.c.recovery['at']=time.monotonic()+30
        self.sp.api.return_value=self.state('outside')
        for _ in range(5): await self.c.retry_recovery()
        self.assertEqual(self.sp.api.await_count,5)
        self.sp.play.assert_awaited_once()
        self.assertEqual(self.c.recovery['attempts'],1)

    async def test_passive_recovery_also_observes_success_before_deadline(self):
        row=await self.request_failure()
        import time
        self.c.recovery.update(passive=True,at=time.monotonic()+30)
        self.sp.api.return_value=self.state('request')
        await self.c.retry_recovery()
        self.assertEqual(self.q.state['current']['id'],row['id'])
        self.assertIsNone(self.c.recovery)
        self.sp.play.assert_awaited_once()

    async def test_saved_fallback_late_success_clears_warning_before_retry(self):
        self.sp.play_playlist.side_effect=self.failure()
        with self.assertRaises(PlaybackStateError): await self.c.resume()
        self.sp.api.return_value=self.state('f1')
        await self.c.retry_recovery()
        self.assertEqual(self.c.status,'Playing')
        self.assertEqual(self.c.error,'')
        self.sp.play_playlist.assert_awaited_once()

    async def test_pending_title_is_available_while_provider_is_still_starting(self):
        import asyncio
        self.s.save({'fallback_enabled':False})
        row=self.q.add(track('new-request'),user('viewer'),['broadcaster'])
        entered,release=asyncio.Event(),asyncio.Event()
        async def slow_start(*args,**kwargs):
            entered.set()
            await release.wait()
        self.sp.play.side_effect=slow_start
        task=asyncio.create_task(self.c.resume())
        try:
            await asyncio.wait_for(entered.wait(),1)
            snapshot=self.c.snapshot()
            self.assertEqual(snapshot['starting']['id'],row['id'])
            self.assertEqual(snapshot['status'],'Starting Spotify')
            self.assertIsNone(snapshot['current'])
            self.assertTrue(snapshot['busy'])
        finally:
            release.set()
            await task
        self.assertIsNone(self.c.snapshot()['starting'])
        self.assertEqual(self.c.snapshot()['current']['id'],row['id'])
