const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
async function fixture(){const sent=[],control={broken:false,reloads:0,injections:0,repair:false};const store={get:async()=>({}),set:async()=>{},remove:async()=>{}};const context={URL,Date,setTimeout,clearTimeout,setInterval:()=>{},WebSocket:{OPEN:1,CONNECTING:0},chrome:{scripting:{executeScript:async args=>{control.injections++;control.target=args;if(!control.repair)throw Error('Site access denied');control.broken=false}},storage:{local:store,session:store},tabs:{get:async()=>({id:7,url:'https://www.youtube.com/watch?v=abcdefghijk',status:'loading'}),sendMessage:async(id,m)=>{if(control.broken)throw Error('No receiving end');return m.type==='ping'?{ready:true}:{seq:m.command?.seq,ok:true}},reload:async()=>control.reloads++},runtime:{onMessage:{addListener(){}},onStartup:{addListener(){}},getURL:s=>'chrome-extension://own/'+s},alarms:{onAlarm:{addListener(){}},create:async()=>{}}},output:sent};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../chrome-extension/background.js'),'utf8'),context);await new Promise(r=>setImmediate(r));vm.runInContext(`authenticated=true;tabId=7;socket={readyState:1,send:s=>output.push(JSON.parse(s))};pending={seq:'one',action:'play'};managed={id:'abcdefghijk',generation:'g'};`,context);return {context,sent,control,tick:()=>vm.runInContext('tick()',context)}}
test('loading page can confirm actual video playback without waiting for tab completion',async()=>{const f=await fixture();await f.tick();assert(f.sent.some(x=>x.type==='ack'&&x.ok===true))});
test('unresponsive player is refreshed once and never falsely acknowledged',async()=>{const f=await fixture();f.control.broken=true;for(let i=0;i<20;i++)await f.tick();assert.equal(f.control.reloads,1);assert(f.sent.some(x=>x.type==='waiting'&&x.reason==='tab_script'));assert(!f.sent.some(x=>x.type==='ack'&&x.ok));});

test('missing content script is reattached only to the selected main frame',async()=>{
 const f=await fixture();f.control.broken=true;f.control.repair=true;
 await f.tick();assert.equal(f.control.injections,1);assert.equal(f.control.target.target.tabId,7);
 assert.equal(JSON.stringify(f.control.target.target.frameIds),'[0]');
 assert(!f.sent.some(x=>x.type==='ack'&&x.ok));
 assert(f.sent.some(x=>x.type==='heartbeat'&&x.ready===false));
 await f.tick();assert(f.sent.some(x=>x.type==='ack'&&x.ok));assert.equal(f.control.reloads,0);
});
test('denied site access never reports ready and does not spin injections',async()=>{
 const f=await fixture();f.control.broken=true;for(let i=0;i<5;i++)await f.tick();
 assert.equal(f.control.injections,1);assert(!f.sent.some(x=>x.type==='heartbeat'&&x.ready));
});
