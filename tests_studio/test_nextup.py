import asyncio, tempfile, unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from studio.playback import Conductor
from studio.settings import Settings, validate
from studio.queue import Queue
from studio.providers import Spotify
from studio.customization import preset
from test_core import track, user

class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.settings=Settings(Path(self.tmp.name)/'settings.json');self.q=Queue(':memory:',self.settings)
        self.spotify=Mock(connected=True);self.spotify.api=AsyncMock();self.spotify.pause=AsyncMock();self.spotify.play=AsyncMock();self.spotify.resume=AsyncMock()
        self.c=Conductor(self.q,self.spotify,Mock(),Mock())
    async def asyncTearDown(self):self.q.db.close();self.tmp.cleanup()
    def playback(self, ident='manual', playing=True, seconds=42):
        return {'is_playing':playing,'progress_ms':seconds*1000,'item':{'id':ident,'name':'Manual Spotify song','artists':[{'name':'Artist','id':'art'}],'duration_ms':200000,'album':{'images':[]}}}
    async def test_manual_spotify_play_is_detected_without_a_request(self):
        self.spotify.api.return_value=self.playback()
        await self.c.poll_spotify()
        self.assertEqual(self.c.display_current()['track']['id'],'manual');self.assertEqual(self.c.status,'Playing');self.assertIsNone(self.q.state['current']);self.assertAlmostEqual(self.c.progress,42,delta=.1)
    async def test_last_skip_clears_and_paused_spotify_track_does_not_reappear(self):
        item=self.q.add(track('a'),user(),['broadcaster']);self.q.activate(item)
        self.c.status='Playing';self.c.progress=80;self.c.error='Old error'
        await self.c.next(manual=True)
        self.assertIsNone(self.q.state['current']);self.assertEqual(self.c.status,'Queue empty');self.assertEqual(self.c.progress,0);self.assertEqual(self.c.error,'');self.assertEqual(len(self.q.state['history']),1)
        self.spotify.api.return_value=self.playback('a',False,80)
        await self.c.poll_spotify();self.assertIsNone(self.c.display_current())
        self.spotify.api.return_value=self.playback('a',True,81)
        await self.c.poll_spotify();self.assertEqual(self.c.status,'Playing');self.assertEqual(self.c.display_current()['track']['id'],'a')
    async def test_pause_external_and_resume_does_not_create_queue_entry(self):
        self.spotify.api.return_value=self.playback();await self.c.poll_spotify()
        await self.c.pause();self.spotify.pause.assert_awaited_once();self.assertEqual(self.c.status,'Paused')
        await self.c.resume();self.spotify.resume.assert_awaited_once();self.assertIsNone(self.q.state['current'])
    async def test_progress_moves_between_reports_and_freezes_when_paused(self):
        self.spotify.api.return_value=self.playback();await self.c.poll_spotify()
        self.c._progress_at-=1.2;self.assertGreater(self.c.progress,43)
        await self.c.pause();seconds=self.c.progress;self.c._progress_at-=3;self.assertEqual(self.c.progress,seconds)
    async def test_external_change_does_not_auto_launch_requests(self):
        item=self.q.add(track('a'),user(),['broadcaster']);self.q.activate(item);self.c.enabled=True;self.c.play_started=0
        self.spotify.api.return_value=self.playback('outside');await self.c.poll_spotify()
        self.assertFalse(self.c.enabled);self.assertEqual(self.q.state['current']['id'],item['id']);self.assertEqual(self.c.display_current()['track']['id'],'outside');self.spotify.play.assert_not_awaited()
    async def test_monitor_does_not_race_handoffs(self):
        async with self.c.lock:await self.c.poll_spotify()
        self.spotify.api.assert_not_awaited()
    async def test_last_skip_retains_request_if_pause_fails(self):
        item=self.q.add(track('a'),user(),['broadcaster']);self.q.activate(item);self.spotify.pause.side_effect=ValueError('not confirmed')
        with self.assertRaises(ValueError):await self.c.next(manual=True)
        self.assertEqual(self.q.state['current']['id'],item['id']);self.assertFalse(self.c.enabled)

    async def test_empty_or_paused_poll_does_not_hide_startup_error(self):
        self.c.failed(ValueError('Spotify has no track loaded'))
        for data in ({}, self.playback('stale', False)):
            self.spotify.api.return_value = data
            await self.c.poll_spotify()
            self.assertEqual(self.c.status, 'Needs attention')
            self.assertEqual(self.c.error, 'Spotify has no track loaded')
            self.assertFalse(self.c.enabled)

    async def test_resume_retained_request_clears_external_display_and_old_end_marker(self):
        item=self.q.add(track('a'),user(),['broadcaster']);self.q.activate(item)
        self.spotify.api.return_value=self.playback('outside');await self.c.poll_spotify()
        self.c.near_end=True;self.c.progress=198
        self.spotify.resume.return_value={'progress_ms':1250}
        await self.c.resume()
        self.spotify.resume.assert_awaited_once_with(item['track'])
        self.assertEqual(self.c.display_current()['track']['id'],'a')
        self.assertFalse(self.c.near_end);self.assertTrue(self.c.enabled)
        self.assertAlmostEqual(self.c.progress,1.25,delta=.1)

    async def test_owner_start_allows_bounded_recovery_for_first_request(self):
        item=self.q.add(track('a'),user(),['broadcaster'])
        await self.c.resume()
        self.spotify.play.assert_awaited_once_with(item['track'],recover_mismatch=True)


class CustomizationTests(unittest.TestCase):
    def test_no_recognition_in_nextup(self):self.assertFalse(validate({'recognition_enabled':True})['recognition_enabled'])
    def test_theme_hex_only(self):
        self.assertEqual(validate({'theme_colors':{'accent':'#123abc'}})['theme_colors']['accent'],'#123abc')
        for color in ['red','url(https://evil)','<script>','#123']:
            with self.assertRaises(ValueError):validate({'theme_colors':{'accent':color}})
    def test_custom_variables_and_permissions(self):
        row={'name':'!hello','reply':'Hi {user}, {song} by {artist} on {platform}.','enabled':True,'permission':'everyone','cooldown':15}
        self.assertEqual(validate({'custom_commands':[row]})['custom_commands'][0],row)
        for reply in ['{user.__class__}','{args!r}','{song:>10}','{unknown}']:
            with self.assertRaises(ValueError):validate({'custom_commands':[{**row,'reply':reply}]})
        with self.assertRaises(ValueError):validate({'custom_commands':[{**row,'name':'!sr'}]})
    def test_widget_preset_is_data_only(self):
        p=preset({'format':'nextup-widget-v1','name':'My card','layout':'gradient','equalizer':False,'colors':{'accent':'#abcdef'}})
        self.assertEqual(p['colors']['accent'],'#abcdef')
        with self.assertRaises(ValueError):preset({'format':'nextup-widget-v1','name':'Bad','layout':'<iframe>','equalizer':False})

class CommandDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_custom_command_renders_variables_and_checks_permission(self):
        from aiohttp import ClientSession
        from studio.server import Studio
        with tempfile.TemporaryDirectory() as tmp:
            async with ClientSession() as session:
                s=Studio(session,Path(tmp));s.bot=Mock();s.twitch.roles=AsyncMock(return_value=['viewer'])
                s.settings.save({'custom_commands':[{'name':'!hello','reply':'Hi {user}: {song} ({queue_count})','permission':'everyone','cooldown':15,'enabled':True},{'name':'!staff','reply':'Staff only','permission':'mod','cooldown':0,'enabled':True}]})
                self.assertTrue(await s.chat('12','alice','msg1','!hello',{}));self.assertIn('Hi alice: Nothing playing (0)',s.bot.reply.call_args.args[1])
                await s.chat('13','bob','msg2','!staff',{});self.assertIn('permission',s.bot.reply.call_args.args[1])
                before=s.bot.reply.call_count;await s.chat('12','alice','msg1','!hello',{});self.assertEqual(s.bot.reply.call_count,before)
                s.bot=None;await s.cleanup()
