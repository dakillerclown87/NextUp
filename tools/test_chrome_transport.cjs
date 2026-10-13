/* Run with Node 22+, npm package ws and NEXTUP_TEST_PYTHON. Browser APIs and
   YouTube DOM are simulated; the service-worker/content scripts and server are real. */
const fs=require('fs'),vm=require('vm'),path=require('path'),os=require('os'),assert=require('assert/strict'),{spawn}=require('child_process'),WS=require('ws');
const firefox=process.env.NEXTUP_TEST_BROWSER==='firefox',apiName=firefox?'browser':'chrome';
const root=path.resolve(__dirname,'..'),extensionId=firefox?'nextup-player@nextup.local':'a'.repeat(32),origin=firefox?'moz-extension://12345678-1234-1234-1234-123456789abc':'chrome-extension://'+extensionId;
(async()=>{const home=fs.mkdtempSync(path.join(os.tmpdir(),'nextup-transport-')),timers=[];let proc,worker;
try{
 proc=spawn(process.env.NEXTUP_TEST_PYTHON||'python',['-u','-m','tools.test_chrome_host'],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});let err='';proc.stderr.on('data',d=>err+=d);
 const url=await new Promise((resolve,reject)=>{let out='';const t=setTimeout(()=>reject(Error(err||'Server timeout')),10000);proc.stdout.on('data',d=>{out+=d;const m=out.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(t);resolve(new URL(m[1]))}});proc.on('exit',c=>{clearTimeout(t);reject(Error('Server exit '+c+err))})});
 const api=async(op,body)=>{const r=await fetch(url.origin+'/api/'+op,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-NextUp-Key':url.hash.slice(1)},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error);return data};
 const every=(fn,ms)=>{const t=setInterval(fn,ms);timers.push(t);return t};
 const wait=async(fn)=>{for(let i=0;i<100;i++){if(await fn())return;await new Promise(r=>setTimeout(r,100))}throw Error('Condition timed out')};
 let listener,tab=null,content=null,nextId=1;
 const area=()=>{const data={};return {get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,data[k]])),set:async o=>Object.assign(data,o),remove:async k=>delete data[k],setAccessLevel:async()=>{}}};
 function page(){
  let receive;const events={};const video={paused:true,ended:false,duration:30,currentTime:0,readyState:4,pause(){this.paused=true},play(){this.paused=false;return Promise.resolve()}};
  const doc={addEventListener:(name,fn)=>events[name]=fn,querySelectorAll:()=>[video],querySelector:q=>q.startsWith('video')?video:q.startsWith('ytd-watch')?{getAttribute:()=>new URL(tab.url).searchParams.get('v')}:null};
  vm.runInNewContext(fs.readFileSync(path.join(root,'chrome-extension/content.js'),'utf8'),{URL,Date,location:{href:tab.url},document:doc,setInterval:every,[apiName]:{runtime:{id:extensionId,onMessage:{addListener:f=>receive=f},sendMessage:async m=>listener(m,{id:extensionId,tab:{id:tab.id},url:tab.url},()=>{})}}});
  content={video,receive,emit:name=>events[name]({target:video})};
 }
 const chrome={storage:{local:area(),session:area()},runtime:{id:extensionId,getURL:p=>origin+'/'+p,onMessage:{addListener:f=>listener=f},onStartup:{addListener(){}}},alarms:{create:async()=>{},onAlarm:{addListener(){}}},tabs:{get:async id=>{if(!tab||tab.id!==id)throw Error('closed');return tab},query:async()=>tab?[tab]:[],create:async o=>{tab={id:nextId++,url:o.url,status:'complete'};page();return tab},update:async(id,o)=>{if(!tab||tab.id!==id)throw Error('closed');if(o.url){tab.url=o.url;page()}return tab},sendMessage:async(id,m)=>{if(!tab||tab.id!==id)throw Error('closed');let reply;content.receive(m,{id:extensionId},r=>reply=r);return reply}}};
 class BrowserSocket extends WS{constructor(url){super(url,{origin})}}
 if(firefox){delete chrome.storage.local.setAccessLevel;delete chrome.storage.session.setAccessLevel}
 worker=vm.createContext({[apiName]:chrome,WebSocket:BrowserSocket,URL,Date,JSON,setInterval:every,console});
 vm.runInContext(fs.readFileSync(path.join(root,'chrome-extension/background.js'),'utf8'),worker);
 const popup=m=>new Promise(resolve=>listener(m,{url:origin+'/popup.html'},resolve));
 await popup({action:'pair',code:(await api('chrome-pair',{})).code});await wait(()=>vm.runInContext('authenticated',worker));
 await popup({action:'open'});await wait(async()=>(await api('state')).connections.youtube_player);
 await api('request',{url:'https://www.youtube.com/watch?v=abcdefghijk'});await api('playback',{action:'resume'});assert.equal(content.video.paused,false);
 await api('playback',{action:'pause'});assert.equal(content.video.paused,true);
 await api('playback',{action:'resume'});assert.equal(content.video.paused,false);
 await api('request',{url:'https://open.spotify.com/track/1234567890123456789012'});
 // A final paused report may reach NextUp before YouTube's ended signal.
 content.video.paused=true;content.video.currentTime=29;
 await wait(async()=>(await api('state')).playback.status==='Paused');
 content.video.currentTime=30;content.video.ended=true;content.emit('ended');
 assert.equal(content.video.paused,true);
 // YouTube tries to autoplay while Spotify is starting; the local hold wins.
 content.video.ended=false;content.video.paused=false;content.emit('play');
 assert.equal(content.video.paused,true);
 await wait(async()=>(await api('state')).queue.current?.track.provider==='spotify');
 let state=await api('state');assert.equal(state.playback.status,'Playing');assert.equal(state.queue.items.length,0);
 await api('playback',{action:'next'});assert.equal((await api('state')).queue.current,null);
 await api('request',{url:'https://www.youtube.com/watch?v=lmnopqrstuv'});await wait(async()=>{const s=await api('state');return !s.playback.busy&&s.queue.current?.track.id==='lmnopqrstuv'});await api('chrome-revoke',{});await wait(()=>content.video.paused);
 console.log('PASS ('+apiName+'): actual extension scripts + live app: pairing, open/select, navigation, play, pause, resume, final paused report, natural YouTube end → inactive Spotify device, final skip and revocation. Browser/media/Spotify responses simulated.');
}finally{for(const t of timers)clearInterval(t);if(worker)vm.runInContext('socket?.close()',worker);if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,3000)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
