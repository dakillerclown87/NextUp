const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
test('embedded player holds an ended video until the next authorized start',async()=>{
 let poll,events,command=null,state=-1;const reports=[],elements={status:{},enable:{}};
 const player={pauseVideo(){state=2},playVideo(){state=1;events.onStateChange({data:1})},loadVideoById(){this.playVideo()},getPlayerState:()=>state,getCurrentTime:()=>10};
 const context={location:{hash:'#local',pathname:'/player',origin:'http://127.0.0.1:8888'},sessionStorage:{getItem(){},setItem(){}},history:{replaceState(){}},crypto:{randomUUID:()=> 'client'},document:{getElementById:id=>elements[id],createElement:()=>({}),head:{appendChild(){}}},setInterval:f=>poll=f,fetch:async(url,options)=>{const body=JSON.parse(options.body);if(url.endsWith('player-event'))reports.push(body);return {ok:true,json:async()=>url.endsWith('player-poll')?command||{}:{}}},YT:{PlayerState:{PLAYING:1,PAUSED:2,ENDED:0,CUED:5},Player:function(_,config){events=config.events;return player}}};context.window=context;
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../studio/static/player.js'),'utf8'),context);
 elements.enable.onclick();context.onYouTubeIframeAPIReady();events.onReady();
 command={seq:'start',action:'play',track:{id:'first',title:'First'}};await poll();
 assert.equal(state,1);assert.equal(reports.filter(x=>x.event==='ack').length,1);
 command=null;state=0;events.onStateChange({data:0});
 assert.equal(state,2);assert.equal(reports.filter(x=>x.event==='ended').length,1);
 state=1;events.onStateChange({data:1});assert.equal(state,2);
 events.onStateChange({data:0});assert.equal(reports.filter(x=>x.event==='ended').length,1);
 command={seq:'second',action:'play',track:{id:'second',title:'Second'}};await poll();assert.equal(state,1);
 command={seq:'pause',action:'pause'};await poll();state=1;events.onStateChange({data:1});assert.equal(state,2);
});
