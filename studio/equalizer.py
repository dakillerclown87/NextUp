"""Application-only Windows audio capture; transmit levels, never raw audio."""
import asyncio, contextlib, json, math, os, sys, time
from pathlib import Path

BANDS=32
class Spectrum:
    def __init__(self,rate=48000,size=4096):
        import numpy as np
        self.np=np
        self.size=size;self.samples=np.zeros((size,2),dtype=np.float32)
        self.window=np.hanning(size).astype(np.float32);self.scale=self.window.sum()/2
        frequencies=np.fft.rfftfreq(size,1/rate);edges=np.geomspace(40,18000,BANDS+1)
        self.ranges=[np.flatnonzero((frequencies>=lo)&(frequencies<hi)) for lo,hi in zip(edges[:-1],edges[1:])]
    def feed(self,pcm,gain=1):
        np=self.np
        if len(pcm)%4:raise ValueError('PCM must contain complete stereo frames.')
        values=np.frombuffer(pcm,dtype='<i2').astype(np.float32).reshape(-1,2)/32768
        n=min(len(values),self.size)
        if n:
            self.samples[:-n]=self.samples[n:];self.samples[-n:]=values[-n:]
        # Analyze channels separately so opposite-phase stereo does not cancel.
        power=np.abs(np.fft.rfft(self.samples*self.window[:,None],axis=0))/self.scale
        levels=[]
        for indices in self.ranges:
            peak=float(power[indices].max())*gain if len(indices) else 0
            db=20*math.log10(max(peak,1e-9))
            levels.append(round(max(0,min(1,(db+72)/72)),4))
        return levels

class ApplicationEqualizer:
    def __init__(self,settings,helper=None,playback=None,browser_peer=None):
        self.settings=settings;self.helper=Path(helper) if helper else Path(__file__).parent/'native/NextUpAudio.exe'
        self.task=None;self.process=None;self.lock=asyncio.Lock();self.levels=[0.]*BANDS;self.at=0.;self.status='Animation';self.error=''
        self.apps=[];self._signature=None
        self.browser_peer=browser_peer or (lambda:0);self.playback=playback;self.follow_task=None;self.follow_target=None;self.retry_at=0.;self.active_name=''
    def unavailable(self):
        if sys.platform!='win32':return 'Application audio capture requires Windows 11 (or Windows build 20348+).'
        if sys.getwindowsversion().build<20348:return 'This Windows version does not support application audio capture.'
        if not self.helper.is_file():return 'The audio capture component is missing. Install the latest NextUp EXE.'
        return ''
    def snapshot(self,public=False):
        reactive=self.settings.value['widget_audio_mode']!='animation';fresh=reactive and time.monotonic()-self.at<.35
        if self.settings.value['widget_audio_mode']=='follow' and self._desired_source()!=self.follow_target:fresh=False
        status=self.status
        if reactive and status=='Listening' and (not fresh or max(self.levels)<.01):status='Waiting for audio from the selected application'
        result={'mode':'application' if reactive else 'animation','levels':self.levels.copy() if fresh else [0.]*BANDS,'status':status}
        if not public:result.update(supported=not bool(self.unavailable()),reason=self.unavailable(),error=self.error,application=self.active_name if self.settings.value['widget_audio_mode']=='follow' else self.settings.value['widget_audio_name'])
        return result
    async def applications(self,follow=False,peer_port=0):
        reason=self.unavailable()
        if reason:return {'supported':False,'reason':reason,'applications':[]}
        args=['--follow-list',str(peer_port)] if follow else ['--list']
        proc=await asyncio.create_subprocess_exec(str(self.helper),*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0),limit=65536)
        try:
            async def read_list():
                chunks=[];size=0
                while chunk:=await proc.stdout.read(16384):
                    size+=len(chunk)
                    if size>262144:raise ValueError('Application list is too large.')
                    chunks.append(chunk)
                return b''.join(chunks)
            raw=await asyncio.wait_for(read_list(),5);await asyncio.wait_for(proc.wait(),2)
            if proc.returncode or len(raw)>262144:raise ValueError('Could not list applications. Open the app window and refresh.')
            rows=json.loads(raw)
            if not isinstance(rows,list) or len(rows)>128:raise ValueError('Invalid application list.')
            self.apps=[]
            for p in rows:
                if type(p.get('pid')) is int and 0<p['pid']<=0xffffffff and isinstance(p.get('started'),str) and p['started'].isdigit() and len(p['started'])<=20 and isinstance(p.get('name'),str):
                    row={'pid':p['pid'],'started':p['started'],'name':'NextUp' if p['pid']==os.getpid() else p['name'][:100]}
                    if p.get('peer') is True:row['peer']=True
                    self.apps.append(row)
            return {'supported':True,'reason':'','applications':sorted(self.apps,key=lambda p:(p['name'].casefold(),p['pid']))}
        finally:
            if proc.returncode is None:proc.kill()
            await proc.wait()
    async def choose(self,pid,started):
        rows=(await self.applications())['applications']
        selected=next((p for p in rows if p['pid']==pid and p['started']==started),None)
        if not selected:raise ValueError('That application is no longer available. Refresh applications and select it again.')
        self.settings.save({'widget_audio_pid':selected['pid'],'widget_audio_started':selected['started'],'widget_audio_name':selected['name'],'widget_audio_mode':'application'})
        await self.configure(force=True)
    async def configure(self,force=False):
        async with self.lock:
            c=self.settings.value;signature=(c['widget_audio_mode'],c['widget_audio_pid'],c['widget_audio_started'],c['youtube_player_mode'] if c['widget_audio_mode']=='follow' else '')
            if signature==self._signature and not force:return
            await self._stop_follow();await self._stop();self.follow_target=None;self.retry_at=0.;self.active_name='';self._signature=signature;self.error='';self.levels=[0.]*BANDS;self.at=0
            if c['widget_audio_mode']=='animation':self.status='Animation';return
            reason=self.unavailable()
            if reason:self.status='Unavailable';self.error=reason;return
            if c['widget_audio_mode']=='follow':
                self.status='Following NextUp playback';self.follow_task=asyncio.create_task(self._follow_loop());return
            if not c['widget_audio_pid'] or not c['widget_audio_started']:self.status='Choose an application';return
            self.status='Starting capture';self.task=asyncio.create_task(self._capture(c['widget_audio_pid'],c['widget_audio_started']))
    def _desired_source(self):
        if not self.playback:return None
        state=self.playback();status=state.get('status')
        if status=='Starting Spotify':provider='spotify'
        elif status=='Starting YouTube':provider='youtube'
        elif status=='Playing':provider=((state.get('current') or {}).get('track') or {}).get('provider')
        else:return None
        if provider=='spotify':return 'spotify'
        if provider=='youtube':
            if self.settings.value['youtube_player_mode']!='chrome':return 'embedded'
            port=self.browser_peer()
            return 'browser:'+str(port if type(port) is int and 0<port<65536 else 0)
        return None
    async def _follow_once(self):
        """Reconcile only audio capture; never control or delay music playback."""
        target=self._desired_source()
        if target!=self.follow_target:
            await self._stop();self.follow_target=target;self.retry_at=0.;self.error='';self.active_name=''
        if not target:
            self.status='Following NextUp — waiting for playback';return
        if self.task and not self.task.done():return
        if time.monotonic()<self.retry_at:return
        self.retry_at=time.monotonic()+5
        browser=target.startswith('browser:');port=int(target.split(':')[1]) if browser else 0
        if browser and not port:
            self.status='Connect the NextUp browser extension to follow YouTube audio';return
        rows=(await self.applications(follow=True,peer_port=port))['applications']
        names={'chrome.exe':'Chrome','msedge.exe':'Microsoft Edge','brave.exe':'Brave','opera.exe':'Opera / Opera GX','vivaldi.exe':'Vivaldi','firefox.exe':'Firefox'}
        if browser:
            matches=[p for p in rows if p.get('peer') is True and p['name'].casefold() in names]
            label=names[matches[0]['name'].casefold()] if len(matches)==1 else 'the connected browser'
        else:
            name={'spotify':'spotify.exe','embedded':'nextup'}[target]
            matches=[p for p in rows if p['name'].casefold()==name]
            label={'spotify':'Spotify','embedded':'NextUp YouTube player'}[target]
        if len(matches)!=1:
            self.active_name='';self.error=''
            self.status=('Waiting for '+label+' — reconnecting automatically') if not matches else ('Multiple '+label+' processes found — close extra instances or use manual selection')
            return
        # Discovery can take time. Re-check playback and mode before opening a pipe.
        if self.settings.value['widget_audio_mode']!='follow' or self._desired_source()!=target:return
        p=matches[0];await self._stop();self.active_name=label;self.error='';self.status='Starting capture'
        self.task=asyncio.create_task(self._capture(p['pid'],p['started']))
    async def _follow_loop(self):
        while True:
            try:
                async with self.lock:
                    if self.settings.value['widget_audio_mode']!='follow':return
                    await self._follow_once()
            except asyncio.CancelledError:raise
            except Exception:
                self.status='Automatic audio discovery unavailable';self.error='Retrying automatically. Check that Spotify or the YouTube player is open.'
                self.retry_at=time.monotonic()+5
            await asyncio.sleep(.5)
    async def _stop_follow(self):
        if self.follow_task:
            self.follow_task.cancel();await asyncio.gather(self.follow_task,return_exceptions=True);self.follow_task=None
    async def _capture(self,pid,started):
        proc=None;stderr_task=None;ready=asyncio.get_running_loop().create_future()
        try:
            proc=await asyncio.create_subprocess_exec(str(self.helper),'--capture',str(pid),started,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0),limit=65536)
            self.process=proc
            async def messages():
                while raw:=await proc.stderr.readline():
                    line=raw.decode('utf-8','replace').strip()
                    if line=='READY':
                        if not ready.done():ready.set_result(True)
                    elif line=='APP_CLOSED':self.error=('Application closed or restarted. Reconnecting automatically.' if self.settings.value['widget_audio_mode']=='follow' else 'Application closed or restarted. Refresh applications and select it again.')
                    elif line.startswith('ERROR '):
                        detail=line[6:180]
                        self.error=('Windows rejected audio callback initialization ('+detail+'). Update NextUp, then retry capture.' if '0x8000000e' in detail.lower() else 'Audio capture failed: '+detail)
                if not ready.done():ready.set_exception(ValueError(self.error or 'The audio capture component stopped before it was ready.'))
            stderr_task=asyncio.create_task(messages())
            await asyncio.wait_for(ready,10);self.status='Listening';analyzer=await asyncio.to_thread(Spectrum)
            while True:
                pcm=await proc.stdout.readexactly(4096)
                self.levels=analyzer.feed(pcm,self.settings.value['widget_audio_gain']);self.at=time.monotonic()
        except asyncio.CancelledError:raise
        except asyncio.IncompleteReadError:
            if stderr_task:
                with contextlib.suppress(asyncio.TimeoutError):await asyncio.wait_for(asyncio.shield(stderr_task),1)
            self.status='Capture stopped';self.error=self.error or 'Audio capture stopped. Refresh applications and select the app again.'
        except asyncio.TimeoutError:self.status='Capture failed';self.error='Audio capture did not start in time. Select the application again.'
        except Exception as exc:
            self.status='Capture failed';self.error=str(exc)[:200]
        finally:
            if proc:
                if proc.returncode is None:proc.terminate()
                try:await asyncio.wait_for(proc.wait(),2)
                except asyncio.TimeoutError:proc.kill();await proc.wait()
            if stderr_task:
                stderr_task.cancel();await asyncio.gather(stderr_task,return_exceptions=True)
            if not ready.done():ready.cancel()
            elif not ready.cancelled():ready.exception() # consume startup errors during cancellation
            self.process=None;self.levels=[0.]*BANDS;self.at=0
    async def _stop(self):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
    async def close(self):
        async with self.lock:
            await self._stop_follow();await self._stop()
