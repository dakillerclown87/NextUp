const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function fixture(){
 let listener,now=10000;const timers=[],events={},messages=[];
 const video={paused:true,ended:false,readyState:4,currentTime:10,duration:180,pause(){this.paused=true},play(){this.paused=false;return Promise.resolve()}};
 const flags={ad:false,error:false,id:'abcdefghijk'};
 const context={URL,Date:{now:()=>now},location:{href:'https://www.youtube.com/watch?v=abcdefghijk'},setInterval:f=>timers.push(f),chrome:{runtime:{id:'own-extension',onMessage:{addListener:f=>listener=f},sendMessage:async m=>messages.push(m)}},document:{addEventListener:(name,fn)=>events[name]=fn,querySelectorAll:()=>[video],querySelector:q=>q.startsWith('video')?video:q.startsWith('ytd-watch')?{getAttribute:()=>flags.id}:q.startsWith('.ad-')?(flags.ad?{}:null):flags.error?{getBoundingClientRect:()=>({height:10})}:null}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../chrome-extension/content.js'),'utf8'),context);
 const managed={id:'abcdefghijk',generation:'generation',duration:180};
 const send=(command=null)=>{let out;listener({type:'tick',command,managed},{id:'own-extension'},r=>out=r);return out};
 return {send,video,flags,context,managed,messages,emit:name=>events[name]({target:video}),advance:ms=>{now+=ms},leaseExpire:()=>{now+=8000;timers.forEach(f=>f())}};
}
test('pause is acknowledged only after the media is paused',()=>{const f=fixture();f.video.paused=false;assert.equal(f.send({seq:'1',action:'pause'}).ok,true);assert.equal(f.video.paused,true)});
test('start confirms real playback, not simply a play invocation',()=>{const f=fixture();assert.equal(f.send({seq:'1',action:'play'}).ok,undefined);assert.equal(f.send({seq:'1',action:'play'}).ok,true)});
test('ads neither acknowledge song start nor finish a queue item',()=>{const f=fixture();f.flags.ad=true;f.video.paused=false;assert.equal(f.send({seq:'1',action:'play'}).ok,undefined);f.video.ended=true;assert.equal(f.send().ended,false);f.flags.ad=false;f.video.ended=false;assert.equal(f.send({seq:'1',action:'play'}).ok,true)});
test('autoplay rejection is surfaced, not reported as playing',async()=>{const f=fixture();f.video.play=()=>Promise.reject(Object.assign(Error('blocked'),{name:'NotAllowedError'}));f.send({seq:'1',action:'play'});await Promise.resolve();assert.equal(f.send({seq:'1',action:'play'}).reason,'autoplay')});
test('navigated and unavailable pages fail without playing another video',()=>{for(const flag of ['id','error']){const f=fixture();f.flags[flag]=flag==='id'?'different':true;if(flag==='id'){assert.equal(f.send({seq:'1',action:'play'}).waiting,'loading');f.advance(21000)}assert.equal(f.send({seq:'1',action:'play'}).ok,false);assert.equal(f.video.paused,true)}});
test('lost connection pauses owned playback after the lease expires',()=>{const f=fixture();f.video.paused=false;f.send({seq:'1',action:'play'});f.leaseExpire();assert.equal(f.video.paused,true)});
test('end reporting verifies video duration to avoid treating an ad as the song',()=>{const f=fixture();f.video.ended=true;f.video.duration=15;assert.equal(f.send().ended,false);f.video.duration=180;assert.equal(f.send().ended,true)});

test('natural end pauses and reports immediately, then blocks autoplay until a new command',()=>{
 const f=fixture();f.video.paused=false;f.send({seq:'1',action:'play'});
 f.video.ended=true;f.video.currentTime=180;f.emit('ended');
 assert.equal(f.video.paused,true);assert.equal(f.messages.length,1);
 f.flags.id='nextautoplay';f.video.ended=false;f.video.paused=false;f.emit('play');
 assert.equal(f.video.paused,true);assert.equal(f.send().ended,true);assert.equal(f.send().lost,false);
 f.flags.id='abcdefghijk';f.video.ended=false;f.video.currentTime=0;
 f.send({seq:'2',action:'resume'});assert.equal(f.video.paused,false);
});
test('ad end does not hold the requested music or report an end',()=>{
 const f=fixture();f.video.paused=false;f.send({seq:'1',action:'play'});
 f.flags.ad=true;f.video.ended=true;f.emit('ended');
 assert.equal(f.messages.length,0);assert.equal(f.video.paused,false);
});
test('pause holds subsequent autoplay but an explicit resume releases it',()=>{
 const f=fixture();f.send({seq:'1',action:'pause'});f.video.paused=false;f.emit('playing');
 assert.equal(f.video.paused,true);f.send({seq:'2',action:'resume'});assert.equal(f.video.paused,false);
});

test('transient play interruption retries instead of becoming an autoplay denial',async()=>{const f=fixture();let count=0;f.video.play=()=>{if(++count===1)return Promise.reject(Object.assign(Error('interrupted'),{name:'AbortError'}));f.video.paused=false;return Promise.resolve()};f.send({seq:'r',action:'play'});await Promise.resolve();f.send({seq:'r',action:'play'});assert.equal(f.send({seq:'r',action:'play'}).ok,true)});
test('paused media is retried after a page/ad transition',()=>{const f=fixture();f.flags.ad=true;f.send({seq:'r',action:'play'});f.video.paused=true;f.flags.ad=false;f.advance(1500);f.send({seq:'r',action:'play'});assert.equal(f.send({seq:'r',action:'play'}).ok,true)});

test('reattaching packaged content script does not duplicate playback listeners',()=>{
 const f=fixture();let added=0;f.context.chrome.runtime.onMessage.addListener=()=>added++;
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../chrome-extension/content.js'),'utf8'),f.context);
 assert.equal(added,0);assert.equal(f.send({seq:'1',action:'pause'}).ok,true);
});
