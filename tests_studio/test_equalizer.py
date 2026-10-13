import asyncio, json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
import numpy as np
from studio.equalizer import Spectrum,ApplicationEqualizer,BANDS
from studio.settings import Settings
from tests_studio import test_widget_design as fixtures

def tone(freq=1000,amp=.3,opposite=False):
    s=np.sin(2*np.pi*freq*np.arange(4096)/48000)*amp
    return (np.column_stack([s,-s if opposite else s])*32767).astype('<i2').tobytes()

class SpectrumTests(unittest.TestCase):
    def test_tones_map_to_bands_and_silence_is_zero(self):
        peaks=[]
        for freq in [100,1000,8000]:
            eq=Spectrum();values=eq.feed(tone(freq));self.assertTrue(all(0<=v<=1 for v in values));peaks.append(np.argmax(values));self.assertGreater(max(values),.6)
        self.assertEqual(sorted(peaks),peaks);self.assertEqual(len(set(peaks)),3)
        self.assertEqual(Spectrum().feed(bytes(4096*4)),[0.]*BANDS)
    def test_gain_and_stereo_phase(self):
        a=Spectrum().feed(tone(amp=.02));b=Spectrum().feed(tone(amp=.02),4)
        self.assertGreater(max(b),max(a));self.assertEqual(Spectrum().feed(tone()),Spectrum().feed(tone(opposite=True)))
    def test_bad_pcm_and_settings_rejected(self):
        with self.assertRaises(ValueError):Spectrum().feed(b'one')
        with tempfile.TemporaryDirectory() as t:
            s=Settings(Path(t)/'s.json')
            for patch in [{'widget_audio_pid':True},{'widget_audio_pid':-1},{'widget_audio_started':'-1'},{'widget_audio_started':'9'*21},{'widget_audio_mode':'system'},{'widget_audio_gain':float('nan')},{'widget_audio_gain':9}]:
                with self.assertRaises(ValueError):s.save(patch)

class FakeProcess:
    def __init__(self,ready=True):
        self.stdout=asyncio.StreamReader();self.stderr=asyncio.StreamReader();self.returncode=None;self.done=asyncio.Event()
        if ready:self.stderr.feed_data(b'READY\n')
    async def wait(self):await self.done.wait();return self.returncode
    def terminate(self):self.finish(0)
    def kill(self):self.finish(-9)
    def finish(self,code=0):
        if self.returncode is None:self.returncode=code;self.stdout.feed_eof();self.stderr.feed_eof();self.done.set()

class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(Path(self.tmp.name)/'s.json');self.eq=ApplicationEqualizer(self.s)
        self.s.save({'widget_audio_mode':'application','widget_audio_pid':42,'widget_audio_started':'12345','widget_audio_name':'Spotify'})
    async def asyncTearDown(self):await self.eq.close();self.tmp.cleanup()
    async def until(self,fn):
        for _ in range(100):
            if fn():return
            await asyncio.sleep(.01)
        self.fail('State did not update')
    async def test_pcm_stream_stop_stale_and_no_private_overlay_fields(self):
        proc=FakeProcess()
        with patch.object(self.eq,'unavailable',return_value=''),patch('studio.equalizer.asyncio.create_subprocess_exec',AsyncMock(return_value=proc)) as create:
            await self.eq.configure();await self.until(lambda:self.eq.status=='Listening');proc.stdout.feed_data(tone());await self.until(lambda:max(self.eq.levels)>.5)
            args=create.call_args.args;self.assertEqual(args[-3:],('--capture','42','12345'))
            self.assertGreater(max(self.eq.snapshot(public=True)['levels']),.5);self.assertNotIn('application',self.eq.snapshot(public=True));self.assertNotIn('pid',self.eq.snapshot(public=True))
            self.eq.at=time.monotonic()-1;self.assertEqual(self.eq.snapshot(public=True)['levels'],[0.]*BANDS)
            self.s.save({'widget_audio_mode':'animation'});await self.eq.configure();self.assertEqual(proc.returncode,0);self.assertEqual(self.eq.status,'Animation')
    async def test_app_closed_clears_levels_and_does_not_restart(self):
        proc=FakeProcess()
        with patch.object(self.eq,'unavailable',return_value=''),patch('studio.equalizer.asyncio.create_subprocess_exec',AsyncMock(return_value=proc)) as create:
            await self.eq.configure();await self.until(lambda:self.eq.status=='Listening');proc.stdout.feed_data(tone());await self.until(lambda:max(self.eq.levels)>.5)
            proc.stderr.feed_data(b'APP_CLOSED\n');proc.finish(2);await self.eq.task
            self.assertIn('closed',self.eq.error);self.assertEqual(self.eq.levels,[0.]*BANDS);self.assertEqual(create.await_count,1)
    async def test_startup_error_and_switch_cancel_previous_capture(self):
        bad=FakeProcess(False);bad.stderr.feed_data(b'ERROR Activate 0x80070005\n');bad.finish(1)
        with patch.object(self.eq,'unavailable',return_value=''),patch('studio.equalizer.asyncio.create_subprocess_exec',AsyncMock(return_value=bad)):
            await self.eq.configure();await self.eq.task;self.assertEqual(self.eq.status,'Capture failed');self.assertIn('0x80070005',self.eq.error)
        first,second=FakeProcess(),FakeProcess()
        with patch.object(self.eq,'unavailable',return_value=''),patch('studio.equalizer.asyncio.create_subprocess_exec',AsyncMock(side_effect=[first,second])):
            await self.eq.configure(force=True);await self.until(lambda:self.eq.process is first)
            self.s.save({'widget_audio_pid':43,'widget_audio_started':'67890'});await self.eq.configure();await self.until(lambda:self.eq.process is second);self.assertEqual(first.returncode,0)
    async def test_selection_rejects_stale_process_identity(self):
        with patch.object(self.eq,'applications',AsyncMock(return_value={'applications':[{'pid':42,'started':'new','name':'Spotify'}]})):
            with self.assertRaises(ValueError):await self.eq.choose(42,'12345')
    async def test_application_list_handles_chunked_output(self):
        proc=FakeProcess(False);proc.stdout.feed_data(b'[{"pid":42,');proc.stdout.feed_data(b'"started":"12345","name":"Spotify.exe"}]');proc.finish()
        with patch.object(self.eq,'unavailable',return_value=''),patch('studio.equalizer.asyncio.create_subprocess_exec',AsyncMock(return_value=proc)):
            result=await self.eq.applications();self.assertEqual(result['applications'][0]['pid'],42)

class EqualizerApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.WidgetApiTests.asyncSetUp
    asyncTearDown=fixtures.WidgetApiTests.asyncTearDown
    async def test_audio_stream_auth_and_sanitized_levels(self):
        self.assertEqual((await self.over.get('/audio')).status,401)
        self.s.settings.save({'widget_audio_mode':'application'});self.s.equalizer.levels=[.5]*BANDS;self.s.equalizer.at=time.monotonic()
        ws=await self.over.ws_connect('/audio?key='+self.s.overlay_key);sample=await ws.receive_json(timeout=2)
        self.assertEqual(sample['levels'],[.5]*BANDS);self.assertEqual(set(sample),{'mode','levels','status'});await ws.close()
        self.assertEqual((await self.over.post('/api/audio-source?key='+self.s.overlay_key,json={'pid':1})).status,404)
    async def test_delete_by_id_preserves_other_widget(self):
        one=self.s.widget_assets.save(self.s.settings,fixtures.design(),True);two=self.s.widget_assets.save(self.s.settings,fixtures.design(),True)
        r=await self.admin.post('/api/widget-remove',json={'id':one['id']},headers=self.headers);self.assertEqual(r.status,200)
        self.assertEqual([p['id'] for p in self.s.settings.value['widget_presets']],[two['id']])
        r=await self.admin.post('/api/widget-remove',json={'id':one['id']},headers=self.headers);self.assertEqual(r.status,400)

class FollowTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=CaptureTests.asyncSetUp
    asyncTearDown=CaptureTests.asyncTearDown
    until=CaptureTests.until
    async def test_follow_switch_pause_resume_and_app_restart(self):
        state={'status':'Playing','current':{'track':{'provider':'spotify'}}}
        self.eq.playback=lambda:state;self.eq.browser_peer=lambda:12345
        self.s.save({'widget_audio_mode':'follow','youtube_player_mode':'chrome'})
        rows=[{'pid':111,'started':'1001','name':'Spotify.exe'},{'pid':222,'started':'2002','name':'chrome.exe','peer':True},{'pid':333,'started':'3003','name':'NextUp'}]
        procs=[]
        async def spawn(*args,**kwargs):
            p=FakeProcess();procs.append((args,p));return p
        with patch.object(self.eq,'unavailable',return_value=''),patch.object(self.eq,'applications',AsyncMock(side_effect=lambda **kw:{'applications':rows})),patch('studio.equalizer.asyncio.create_subprocess_exec',side_effect=spawn):
            await self.eq.configure();await self.until(lambda:len(procs)==1)
            self.assertEqual(procs[-1][0][-2:],('111','1001'))
            first=procs[-1][1];first.stdout.feed_data(tone());await self.until(lambda:max(self.eq.levels)>.5)
            self.assertEqual(self.eq.snapshot(public=True)['mode'],'application')
            state['current']['track']['provider']='youtube'
            self.assertEqual(self.eq.snapshot(public=True)['levels'],[0.]*BANDS)
            await self.until(lambda:len(procs)==2);self.assertEqual(first.returncode,0);self.assertEqual(procs[-1][0][-2:],('222','2002'))
            chrome=procs[-1][1];state['status']='Paused';await self.until(lambda:chrome.returncode is not None)
            self.assertEqual(self.eq.snapshot()['levels'],[0.]*BANDS)
            state['status']='Playing';await self.until(lambda:len(procs)==3)
            # App restart changes identity, never reuse the stale PID/creation pair.
            procs[-1][1].finish(2);await self.eq.task
            rows[1]={'pid':444,'started':'4004','name':'chrome.exe','peer':True};self.eq.retry_at=0
            await self.until(lambda:len(procs)==4);self.assertEqual(procs[-1][0][-2:],('444','4004'))
            self.s.save({'youtube_player_mode':'embedded'});await self.eq.configure()
            await self.until(lambda:len(procs)==5);self.assertEqual(procs[-1][0][-2:],('333','3003'))
            self.s.save({'widget_audio_gain':2});await self.eq.configure();self.assertEqual(len(procs),5)
            state['status']='Queue empty';await self.until(lambda:procs[-1][1].returncode is not None)
            await self.eq.close();self.assertIsNone(self.eq.follow_task)
            self.assertEqual(Settings(self.s.path).value['widget_audio_mode'],'follow')
    async def test_follow_missing_ambiguous_retry_and_transition_race(self):
        self.s.save({'widget_audio_mode':'follow'});state={'status':'Playing','current':{'track':{'provider':'spotify'}}};self.eq.playback=lambda:state
        row={'pid':111,'started':'1001','name':'Spotify.exe'}
        with patch.object(self.eq,'applications',AsyncMock(return_value={'applications':[]})) as apps:
            await self.eq._follow_once();self.assertIn('Waiting for Spotify',self.eq.status)
            await self.eq._follow_once();self.assertEqual(apps.await_count,1)
        self.eq.retry_at=0
        with patch.object(self.eq,'applications',AsyncMock(return_value={'applications':[row,dict(row,pid=222)]})):
            await self.eq._follow_once();self.assertIn('Multiple Spotify',self.eq.status);self.assertIsNone(self.eq.task)
        async def delayed(**kwargs):state['status']='Paused';return {'applications':[row]}
        self.eq.retry_at=0
        with patch.object(self.eq,'applications',side_effect=delayed):await self.eq._follow_once()
        self.assertIsNone(self.eq.task)
    async def test_follow_failure_recovers_and_manual_mode_stops_supervisor(self):
        self.s.save({'widget_audio_mode':'follow'});self.eq.playback=lambda:{'status':'Starting Spotify'}
        bad=FakeProcess(False);bad.stderr.feed_data(b'ERROR Start 0x80004005\n');bad.finish(1);good=FakeProcess()
        with patch.object(self.eq,'unavailable',return_value=''),patch.object(self.eq,'applications',AsyncMock(return_value={'applications':[{'pid':111,'started':'1001','name':'Spotify.exe'}]})),patch('studio.equalizer.asyncio.create_subprocess_exec',AsyncMock(side_effect=[bad,good,FakeProcess()])) as create:
            await self.eq.configure();await self.until(lambda:self.eq.status=='Capture failed')
            await asyncio.sleep(.55);self.assertEqual(create.await_count,1)
            self.eq.retry_at=0;await self.until(lambda:self.eq.status=='Listening')
            self.s.save({'widget_audio_mode':'application'});await self.eq.configure();await self.until(lambda:create.await_count==3)
            self.assertIsNone(self.eq.follow_task);self.assertEqual(good.returncode,0);self.assertEqual(create.call_args.args[-2:],('42','12345'))

class BrowserFollowTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=CaptureTests.asyncSetUp
    asyncTearDown=CaptureTests.asyncTearDown
    until=CaptureTests.until
    async def test_only_connected_browser_is_captured_for_each_family(self):
        self.s.save({'widget_audio_mode':'follow','youtube_player_mode':'chrome'})
        self.eq.playback=lambda:{'status':'Playing','current':{'track':{'provider':'youtube'}}}
        self.eq.browser_peer=lambda:40000
        for name in ['chrome.exe','msedge.exe','brave.exe','opera.exe','vivaldi.exe','firefox.exe']:
            rows=[{'pid':11,'started':'11','name':'chrome.exe'}, {'pid':22,'started':'22','name':name,'peer':True}]
            p=FakeProcess();self.eq.retry_at=0;await self.eq._stop()
            with patch.object(self.eq,'applications',AsyncMock(return_value={'applications':rows})) as apps,patch('studio.equalizer.asyncio.create_subprocess_exec',AsyncMock(return_value=p)) as spawn:
                await self.eq._follow_once();await self.until(lambda:self.eq.process is p)
                self.assertEqual(spawn.call_args.args[-2:],('22','22'));apps.assert_awaited_with(follow=True,peer_port=40000)
                await self.eq._stop()
        # An unrelated Chrome is never used if the paired browser can't be resolved.
        with patch.object(self.eq,'applications',AsyncMock(return_value={'applications':[rows[0]]})):
            self.eq.retry_at=0;await self.eq._follow_once();self.assertIsNone(self.eq.task)
        self.eq.browser_peer=lambda:0
        with patch.object(self.eq,'applications',AsyncMock()) as apps:
            await self.eq._follow_once();apps.assert_not_awaited();self.assertIn('Connect the NextUp browser extension',self.eq.status)
    async def test_new_connection_invalidates_old_capture_immediately(self):
        self.s.save({'widget_audio_mode':'follow','youtube_player_mode':'chrome'})
        self.eq.playback=lambda:{'status':'Playing','current':{'track':{'provider':'youtube'}}}
        self.eq.browser_peer=lambda:50001;self.eq.follow_target='browser:50000';self.eq.levels=[.8]*BANDS;self.eq.at=time.monotonic()
        self.assertEqual(self.eq.snapshot(public=True)['levels'],[0.]*BANDS)
