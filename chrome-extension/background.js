'use strict';
const ext=globalThis.browser || globalThis.chrome;
const URL_WS='ws://127.0.0.1:8888/chrome/ws';
let socket=null,authenticated=false,pending=null,managed=null,tabId=null,lastTick=0,busy=false,ended='',status='Not connected',pairCode='',disconnecting=false,scriptFailures=0,reloadedSeq='',lastRepair=0;
const youtube=url=>{try{return new URL(url).origin==='https://www.youtube.com'}catch{return false}};
const send=data=>{if(socket?.readyState===WebSocket.OPEN&&authenticated)socket.send(JSON.stringify(data))};
async function saveStatus(text){status=text;await ext.storage.session.set({status:text})}
async function pauseTab(){if(tabId!=null)try{await ext.tabs.sendMessage(tabId,{type:'stop'},{frameId:0})}catch{}}
async function bounded(operation){
 let timer;
 try{return await Promise.race([operation,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Player response timed out')),2000)})])}finally{clearTimeout(timer)}
}
async function attachPlayer(force=false){
 if(tabId==null)throw Error('Choose a YouTube tab first.');
 const tab=await ext.tabs.get(tabId);
 if(!youtube(tab.url))throw Error('Choose a youtube.com tab first.');
 if(!force&&Date.now()-lastRepair<5000)return false;
 lastRepair=Date.now();
 // The browser enforces the existing YouTube host permission. This only
 // reattaches our packaged script to the selected tab's main frame.
 try{
  await bounded(ext.scripting.executeScript({target:{tabId,frameIds:[0]},files:['content.js'],injectImmediately:true}));
  const result=await bounded(ext.tabs.sendMessage(tabId,{type:'ping'},{frameId:0}));
  if(!result?.ready)throw Error('Player did not respond');
  await saveStatus('YouTube player connected. Retry Play in NextUp if needed.');
  return true;
 }catch{
  await saveStatus('Player connection unavailable. Allow NextUp access to youtube.com in browser extension settings, then refresh this YouTube tab and click Repair player connection.');
  return false;
 }
}
async function openTab(){
 if(tabId!==null){try{const tab=await ext.tabs.get(tabId);if(youtube(tab.url)){await ext.tabs.update(tabId,{active:true});return}}catch{}}
 if(pending||managed)throw Error('Finish the current playback command first.');
 const tab=await ext.tabs.create({url:'https://www.youtube.com/'});tabId=tab.id;await ext.storage.session.set({tabId});await saveStatus('YouTube tab selected. Start the queue in NextUp.');await tick();
}
async function connect(code=''){
 if(socket&&[WebSocket.OPEN,WebSocket.CONNECTING].includes(socket.readyState))throw Error('Already connected. Disconnect before pairing again.');
 const saved=await ext.storage.local.get(['token']);
 if(!code&&!saved.token)return;
 disconnecting=false;pairCode=code;authenticated=false;
 const ws=new WebSocket(URL_WS);socket=ws;
 ws.onopen=()=>ws.send(JSON.stringify(code?{type:'pair',code}:{type:'auth',token:saved.token}));
 ws.onmessage=async event=>{try{
  const m=JSON.parse(event.data);
  if(m.type==='authenticated'){
   authenticated=true;pairCode='';
   if(m.token)await ext.storage.local.set({token:m.token});
   await saveStatus('Connected. Choose a YouTube tab.');
   tick();return;
  }
  if(m.type==='error'){await saveStatus(m.message);disconnecting=true;ws.close();return}
  if(m.type==='open'){await openTab();return}
  if(m.type==='stop'){pending=null;managed=null;await pauseTab();return}
  if(m.type==='cancel'){if(pending?.seq===m.seq||(m.failed&&managed?.generation===m.generation)){pending=null;managed=null;await pauseTab()}return}
  if(m.type!=='command')return;
  if(pending){send({type:'ack',seq:m.seq,ok:false,reason:'busy'});return}
  if(!['play','pause','resume'].includes(m.action)||tabId==null){send({type:'ack',seq:m.seq,ok:false,reason:'tab_closed'});return}
  pending=m;scriptFailures=0;
  if(m.action==='play'){
   if(!/^[\w-]{11}$/.test(m.track?.id||'')){pending=null;send({type:'ack',seq:m.seq,ok:false,reason:'unavailable'});return}
   managed={id:m.track.id,duration:m.track.duration,generation:m.generation};ended='';
   await ext.tabs.update(tabId,{url:'https://www.youtube.com/watch?v='+encodeURIComponent(m.track.id)});
  }
  if(m.action==='resume'&&m.track)managed={id:m.track.id,duration:m.track.duration,generation:m.generation};
  tick();
 }catch{if(pending){send({type:'ack',seq:pending.seq,ok:false,reason:'tab_closed'});pending=null}await saveStatus('Could not control the selected tab. Select it again.')}};
 ws.onclose=async()=>{if(socket!==ws)return;authenticated=false;socket=null;pending=null;managed=null;await pauseTab();if(!disconnecting)await saveStatus('Disconnected. Keep NextUp open; reconnecting automatically.')};
 ws.onerror=()=>saveStatus('Cannot reach NextUp. Open the desktop app.');
}
async function tick(){
 if(busy||!authenticated)return;busy=true;
 try{
  if(tabId==null){send({type:'heartbeat',ready:false});return}
  let tab;
  try{tab=await ext.tabs.get(tabId)}catch{tab=null}
  if(!tab||!youtube(tab.url)){send({type:'heartbeat',ready:false});if(pending)send({type:'ack',seq:pending.seq,ok:false,reason:'tab_closed'});if(managed)send({type:'lost',generation:managed.generation});pending=null;managed=null;tabId=null;await ext.storage.session.remove('tabId');await saveStatus('Choose a YouTube tab.');return}
  let result;
  try{
   let timer;
   try{result=await Promise.race([ext.tabs.sendMessage(tabId,{type:'tick',command:pending,managed},{frameId:0}),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Tab response timed out')),2000)})])}finally{clearTimeout(timer)}
   if(!result||typeof result!=='object')throw Error('Empty player response');
   scriptFailures=0;
   send({type:'heartbeat',ready:true});
  }catch{
   send({type:'heartbeat',ready:false});
   if(await attachPlayer())return;
   if(pending){
    scriptFailures++;send({type:'waiting',seq:pending.seq,reason:'tab_script'});
    if(scriptFailures>=8&&reloadedSeq!==pending.seq&&pending.action==='play'){
     reloadedSeq=pending.seq;await saveStatus('Refreshing the selected YouTube tab to restore its player connection.');
     await ext.tabs.reload(tabId);
    }
   }
   return;
  }
  if(!result)return;
  if(pending&&result.waiting)send({type:'waiting',seq:pending.seq,reason:result.waiting});
  if(pending&&result.seq===pending.seq&&typeof result.ok==='boolean'){
   const command=pending;pending=null;send({type:'ack',seq:command.seq,ok:result.ok,reason:result.reason});
   if(!result.ok){await pauseTab();managed=null;await saveStatus(result.reason==='autoplay'?'Click Play in YouTube, then retry in NextUp.':'Check the selected YouTube tab, then retry.');return}
   await saveStatus(command.action==='pause'?'Connected · YouTube paused':'Connected · YouTube playing');
  }
  if(managed&&result.generation===managed.generation){
   if(result.lost){send({type:'lost',generation:managed.generation});await pauseTab();managed=null;return}
   send({type:'state',generation:managed.generation,seconds:result.seconds,playing:result.playing,ended:result.ended});
   if(!pending&&result.ended&&ended!==managed.generation){ended=managed.generation;send({type:'ended',generation:managed.generation})}
  }
 }finally{busy=false;lastTick=Date.now()}
}
ext.runtime.onMessage.addListener((m,sender,reply)=>{
 // Only our selected tab may report a media end; it cannot issue commands.
 if(m.type==='media-ended'){
  if(sender.id===ext.runtime.id&&sender.tab?.id===tabId&&youtube(sender.url)
     &&managed&&m.generation===managed.generation&&!pending&&ended!==m.generation){
   ended=m.generation;send({type:'ended',generation:m.generation});
  }
  reply({});return;
 }
 // Credentials and browser commands are accepted only from our popup, never a page.
 if(sender.url!==ext.runtime.getURL('popup.html'))return;
 (async()=>{
  if(m.action==='pair'){await connect(String(m.code||'').trim())}
  else if(m.action==='repair'){await attachPlayer(true);await tick()}
  else if(m.action==='connect'){disconnecting=false;await connect()}
  else if(m.action==='open'){await openTab()}
  else if(m.action==='select'){
   if(pending||managed)throw Error('Disconnect first before selecting another tab.');
   const [tab]=await ext.tabs.query({active:true,currentWindow:true});
   if(!tab||!youtube(tab.url))throw Error('Open youtube.com in the current tab first.');
   tabId=tab.id;await ext.storage.session.set({tabId});await saveStatus('YouTube tab selected. Start the queue in NextUp.');await tick();
  }else if(m.action==='disconnect'){
   disconnecting=true;await ext.storage.local.remove('token');await pauseTab();managed=null;pending=null;socket?.close();await saveStatus('Disconnected. Generate a new pairing code to reconnect.');
  }
  return {status,connected:authenticated,selected:tabId!==null};
 })().then(reply,e=>reply({error:e.message}));return true;
});
ext.alarms.onAlarm.addListener(()=>{if(!socket&&!disconnecting)connect().catch(()=>{})});
ext.runtime.onStartup.addListener(()=>connect().catch(()=>{}));
(async()=>{await ext.storage.local.setAccessLevel?.({accessLevel:'TRUSTED_CONTEXTS'});await ext.storage.session.setAccessLevel?.({accessLevel:'TRUSTED_CONTEXTS'});const s=await ext.storage.session.get('tabId');tabId=s.tabId??null;await ext.alarms.create('reconnect',{periodInMinutes:0.5});await connect()})().catch(()=>{});
setInterval(()=>tick().catch(()=>{}),250);
