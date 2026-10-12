(() => {
'use strict';
const ext=globalThis.browser || globalThis.chrome;
if(globalThis.__nextupPlayer12)return;
globalThis.__nextupPlayer12=true;
// This isolated content script never receives pairing codes, tokens or app credentials.
let lastSeq='',lastResult=null,attempted=false,lease=0,owns=false,managed=null,held=false,finished='',lastVideo=null,lastAttempt=0,commandAt=0;
const videos=()=>[...document.querySelectorAll('video')];
function pause(){held=true;for(const v of videos())v.pause();owns=false}
function snapshot(target){
 const video=document.querySelector('video.html5-main-video')||document.querySelector('video');
 const id=new URL(location.href).searchParams.get('v');
 const watch=document.querySelector('ytd-watch-flexy[video-id]');
 const pageId=watch?.getAttribute('video-id');
 const ad=!!document.querySelector('.ad-showing,.ad-interrupting');
 const error=document.querySelector('.ytp-error-content-wrap');
 const unavailable=!!error&&error.getBoundingClientRect().height>0;
 const correct=!!target&&id===target.id&&(!pageId||pageId===target.id);
 const durationMatches=video&&Math.abs(video.duration-(target?.duration||0))<4;
 const ended=!!target&&finished===target.generation;
 return {video,ad,unavailable,correct,generation:target?.generation,
  seconds:ended?target.duration:correct&&!ad?(video?.currentTime||0):0,
  playing:!!(!held&&correct&&!ad&&video&&!video.paused&&!video.ended&&video.readyState>=2),
  ended:ended||!!(correct&&!ad&&video?.ended&&durationMatches),
  lost:!!target&&!ended&&(!correct||unavailable)};
}
function end(){
 const s=snapshot(managed);
 if(!owns||!s.ended||finished===managed?.generation)return;
 finished=managed.generation;pause();
 // Stop locally before waiting for the desktop app or Spotify network calls.
 ext.runtime.sendMessage({type:'media-ended',generation:finished}).catch(()=>{});
}
document.addEventListener('ended',e=>{if(e.target===snapshot(managed).video)end()},true);
document.addEventListener('play',e=>{if(held&&videos().includes(e.target))e.target.pause()},true);
document.addEventListener('playing',e=>{if(held&&videos().includes(e.target))e.target.pause()},true);
ext.runtime.onMessage.addListener((m,sender,reply)=>{
 if(sender.id!==ext.runtime.id)return;
 if(m.type==='ping'){reply({ready:true,version:12});return}
 if(m.type==='stop'){pause();held=false;managed=null;finished='';lastSeq='';lastResult=null;reply({stopped:true});return}
 if(m.type!=='tick')return;
 lease=Date.now();managed=m.managed;
 const cmd=m.command;
 if(cmd&&cmd.seq!==lastSeq){
  lastSeq=cmd.seq;lastResult=null;attempted=false;lastVideo=null;lastAttempt=0;commandAt=Date.now();
  if(['play','resume'].includes(cmd.action)){held=false;finished=''}
 }
 end();
 const s=snapshot(managed);
 if(!cmd){reply({generation:s.generation,seconds:s.seconds,playing:s.playing,ended:s.ended,lost:s.lost});return}
 if(lastResult){reply(lastResult);return}
 const finish=(ok,reason)=>{lastResult={seq:cmd.seq,ok,reason,generation:s.generation,seconds:s.seconds};reply(lastResult)};
 if(cmd.action==='pause'){
  pause();if(videos().every(v=>v.paused))finish(true);else reply({});return;
 }
 if(s.unavailable){pause();finish(false,'unavailable');return}
 if(!s.correct){
  if(Date.now()-commandAt<20000&&['play','resume'].includes(cmd.action)){for(const v of videos())v.pause();reply({waiting:'loading'});return}
  pause();finish(false,'changed');return;
 }
 if(!s.video){reply({waiting:'player_missing'});return}
 owns=true;
 if(!s.video.paused&&!s.video.ended&&!s.ad&&s.video.readyState>=2){finish(true);return}
 if(lastVideo!==s.video){lastVideo=s.video;attempted=false}
 if(!attempted||Date.now()-lastAttempt>1000){
  attempted=true;lastAttempt=Date.now();const sequence=cmd.seq;
  s.video.play().catch(error=>{if(lastSeq!==sequence)return;if(error.name==='NotAllowedError'){lastResult={seq:sequence,ok:false,reason:'autoplay'};pause()}else{attempted=false}});
 }
 reply({waiting:s.ad?'ad':'loading'});
});
// A lost extension/app connection must not leave a second audio source playing.
setInterval(()=>{if(owns&&Date.now()-lease>7000)pause()},1000);

})();
