const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const code=fs.readFileSync(__dirname+'/../studio/static/app.js','utf8');
function setup(){
 const banner={textContent:'',classList:{toggle(_,value){banner.error=value;}}};
 const c={state:{playback:{status:'Recovering Spotify playback',error:'Retrying',busy:false}},playbackPending:false,
  $:()=>banner,syncPlaybackButtons(){},api:async()=>{throw Error('Spotify is reporting a different track.');},banner};
 vm.createContext(c);
 vm.runInContext("let noticeSource='';",c);
 for(const name of ['notice','syncPlaybackNotice'])vm.runInContext(code.split('\n').find(l=>l.startsWith('function '+name+'(')),c);
 const start=code.indexOf('async function runPlayback('),end=code.indexOf('\n}',start)+2;
 vm.runInContext(code.slice(start,end),c);
 c.refresh=async()=>c.syncPlaybackNotice();
 return c;
}
test('successful playback clears only the playback error banner',()=>{
 const c=setup();c.notice('wrong track',true,'playback');c.syncPlaybackNotice();assert.equal(c.banner.textContent,'Retrying');
 c.state.playback={status:'Playing',error:'',busy:false,failed_item:null};c.syncPlaybackNotice();assert.equal(c.banner.textContent,'');assert.equal(c.banner.error,false);
 c.notice('Widget upload failed',true);c.syncPlaybackNotice();assert.equal(c.banner.textContent,'Widget upload failed');
});
test('late failed response cannot restore a warning after a fresh successful state',async()=>{
 const c=setup();c.refresh=async()=>{c.state.playback={status:'Playing',error:'',busy:false};c.syncPlaybackNotice();};
 await c.runPlayback('resume');assert.equal(c.banner.textContent,'');assert.equal(c.playbackPending,false);
});
test('unconfirmed or still-busy playback does not falsely clear a warning',()=>{
 const c=setup();c.notice('wrong track',true,'playback');c.state.playback={status:'Starting Spotify',error:'',busy:true};c.syncPlaybackNotice();assert.equal(c.banner.textContent,'wrong track');
 c.state.playback={status:'Needs attention',error:'Wrong device',busy:false};c.syncPlaybackNotice();assert.equal(c.banner.textContent,'Wrong device');
});
test('fresh recovery status replaces original action error and later clears',async()=>{
 const c=setup();await c.runPlayback('resume');assert.equal(c.banner.textContent,'Retrying');
 c.state.playback={status:'Playing',error:'',busy:false};c.syncPlaybackNotice();assert.equal(c.banner.textContent,'');
});
test('successful playback does not insert a temporary banner before state refresh',async()=>{
 const c=setup();c.api=async()=>({ok:true});let release;
 c.refresh=()=>new Promise(r=>release=r);
 const task=c.runPlayback('next');await new Promise(r=>setImmediate(r));
 assert.equal(c.banner.textContent,'');release();await task;
});
test('starting track renders before playback action completes, with accurate status',()=>{
 const c={state:{playback:{starting:{id:'new',track:{title:'Incoming song',artists:['New artist'],duration:120,provider:'spotify'}},current:{track:{title:'Old song'}},status:'Starting Spotify'},queue:{current:null},settings:{skip_enabled:true}},esc:s=>s||'',art:()=>'',badge:()=>'',uiIcon:()=>'',playbackIcon:()=>'',time:()=>''};
 vm.createContext(c);vm.runInContext(code.split('\n').find(l=>l.startsWith('function playerCard(')),c);
 const html=c.playerCard();assert.match(html,/Incoming song/);assert.match(html,/Starting Spotify/);assert.doesNotMatch(html,/Old song/);
});
