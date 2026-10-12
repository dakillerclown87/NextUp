/* Real saved overlay; playback snapshots are controlled without external accounts. */
const {chromium}=require('playwright'),{spawn}=require('child_process'),fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
(async()=>{const root=path.resolve(__dirname,'..'),home=fs.mkdtempSync(path.join(os.tmpdir(),'prism-test-'));let proc,browser;
try{
 proc=spawn('python3',['-u','tools/test_nextup_host.py','--fallback-fixture'],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});let err='';proc.stderr.on('data',d=>err+=d);
 const url=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error(err||'startup timeout')),15000);proc.stdout.on('data',d=>{out+=d;const m=out.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});proc.on('exit',c=>{clearTimeout(timer);reject(Error('server exit '+c))})});
 browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote']});
 const context=await browser.newContext({viewport:{width:1120,height:420}}),errors=[];
 await context.route('https://preview.invalid/**',r=>r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"><defs><radialGradient id="g"><stop stop-color="#a387ef"/><stop offset=".45" stop-color="#543d94"/><stop offset="1" stop-color="#0a1630"/></radialGradient><linearGradient id="p" x2="1" y2="1"><stop stop-color="#42e6f0"/><stop offset="1" stop-color="#e58bdf"/></linearGradient></defs><rect width="400" height="400" fill="url(#g)"/><circle cx="200" cy="185" r="93" fill="url(#p)"/><ellipse cx="200" cy="198" rx="156" ry="42" fill="none" stroke="#e6cdff" stroke-width="12" transform="rotate(-25 200 198)"/><path d="M0 385L80 260 162 335 228 273 400 400H0" fill="#111e3a"/><circle cx="61" cy="80" r="3" fill="white"/><circle cx="336" cy="64" r="2" fill="white"/></svg>'}));
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.setViewportSize({width:1000,height:800});await page.goto(url);await page.locator('[data-nav=widgets]').click();await page.locator('#import-widget').setInputFiles(path.join(root,'docs/Event-Horizon.nextup.json'));await page.waitForFunction(()=>widgetDraft?.name==='Event Horizon');await page.locator('#we-save-new').click();await page.waitForFunction(()=>state.settings.widget_presets.length===1);
 const exported=await page.evaluate(()=>api('widget-export',{id:widgetDraft.id}));assert.equal(exported.transition,'horizon');assert.equal(exported.presentation,'horizon');
 const overlayURL=await page.evaluate(()=>state.widgets.now+'&preset_id='+widgetDraft.id),overlay=await context.newPage();overlay.on('pageerror',e=>errors.push(e.message));let scenario=null,outage=false;
 await overlay.route('**/state?*',async r=>{if(outage){await r.abort();return}const response=await r.fetch(),d=await response.json();if(scenario){d.current=scenario.id?{...d.current,id:scenario.id,requester:'MoonWatcher',track:{...d.current.track,id:scenario.id,title:scenario.title,duration:scenario.duration??222}}:null;d.playback.status=scenario.status;d.playback.progress=scenario.progress??0;}if(scenario?.remove)d.presets=[];await r.fulfill({json:d})});
 await overlay.goto(overlayURL);await overlay.waitForFunction(()=>document.querySelector('#widget').dataset.horizonPhase==='open');await overlay.waitForFunction(()=>[...document.images].every(im=>im.complete));
 await overlay.screenshot({path:path.join(root,'build/Event-Horizon-preview.png')});
 const change=async s=>{scenario=s;await overlay.evaluate(()=>refresh());await overlay.waitForTimeout(40)};
 const phase=async v=>overlay.waitForFunction(v=>document.querySelector('#widget').dataset.horizonPhase===v,v);
 await change({id:'first',title:'Event Horizon',status:'Playing',progress:10});await phase('open');
 await change({id:'first',title:'Event Horizon',status:'Playing',progress:219});await phase('absorbing');
 assert.equal(await overlay.locator('[data-part=title]').textContent(),'Event Horizon');
 await overlay.waitForTimeout(500);await overlay.screenshot({path:path.join(root,'build/Event-Horizon-suction.png')});
 await change({id:'first',title:'Event Horizon',status:'Paused',progress:219});await overlay.waitForTimeout(650);
 const paused=await overlay.locator('.wd-horizon-card').evaluate(e=>e.style.transform);await overlay.waitForTimeout(400);
 const still=await overlay.locator('.wd-horizon-card').evaluate(e=>e.style.transform);
 const numbers=s=>s.match(/-?[0-9.]+/g).map(Number);assert(numbers(paused).every((n,i)=>Math.abs(n-numbers(still)[i])<.04),'paused suction must settle and hold');
 assert.equal(await overlay.locator('#widget').getAttribute('data-horizon-phase'),'absorbing');
 // Seek back restores the full card without waiting for a song change.
 await change({id:'first',title:'Event Horizon',status:'Playing',progress:100});await phase('open');
 await change({id:'first',title:'Event Horizon',status:'Playing',progress:222});await phase('absorbed');
 await overlay.screenshot({path:path.join(root,'build/Event-Horizon-blackhole.png')});
 await change({id:'second',title:'Into the Unknown',status:'Starting Spotify',progress:0});await phase('idle');
 assert.equal(await overlay.locator('[data-part=title]').textContent(),'Event Horizon');
 await change({id:'second',title:'Into the Unknown',status:'Playing',progress:0});await phase('burst');await phase('open');
 await change({id:'third',title:'Skipped Quickly',status:'Playing',progress:0});
 await change({id:'fourth',title:'Final Destination',status:'Playing',progress:0});await phase('open');
 assert.equal(await overlay.locator('[data-part=title]').textContent(),'Final Destination');
 await change({id:'fourth',title:'Final Destination',status:'Playing',progress:900,duration:0});await overlay.waitForTimeout(400);await phase('open');
 outage=true;await overlay.evaluate(()=>refresh());await phase('idle');outage=false;await change({id:'fifth',title:'Recovered',status:'Playing',progress:1});await phase('open');
 await overlay.emulateMedia({reducedMotion:'reduce'});await change({id:'sixth',title:'Quiet Orbit',status:'Playing',progress:220});await phase('open');assert.equal(await overlay.locator('.wd-horizon-card').evaluate(e=>e.style.opacity),'1');
 await overlay.emulateMedia({reducedMotion:'no-preference'});
 if(process.env.NEXTUP_HORIZON_VIDEO){
  // Browser virtual time makes a frame-accurate 30 fps preview of the real renderer.
  const folder=path.join(root,'build/horizon-frames');fs.mkdirSync(folder,{recursive:true});
  await overlay.clock.install({time:new Date('2030-01-01T00:00:00Z')});await overlay.clock.pauseAt(new Date('2030-01-01T00:01:00Z'));
  scenario={id:'demo-a',title:'Event Horizon',status:'Playing',progress:216};await overlay.evaluate(()=>refresh());
  await overlay.clock.runFor(4000);
  await change({id:'demo-a',title:'Event Horizon',status:'Paused',progress:216});await overlay.clock.runFor(1000);
  for(let i=0;i<330;i++){
   const sec=i/30;
   scenario=sec<6?{id:'demo-a',title:'Event Horizon',status:'Playing',progress:216+sec}:sec<6.7?{id:'demo-b',title:'Into the Unknown',status:'Starting Spotify',progress:0}:{id:'demo-b',title:'Into the Unknown',status:'Playing',progress:sec-6.7};
   if(i%15===0||i===201)await overlay.evaluate(()=>refresh());
   await overlay.clock.runFor(1000/30);
   await overlay.screenshot({path:path.join(folder,String(i).padStart(3,'0')+'.png'),omitBackground:true});
  }
  await overlay.clock.resume();
 }
 await change({id:'remove',title:'Removing',status:'Playing'});await change({id:null,status:'Queue empty',remove:true});
 await overlay.waitForFunction(()=>document.querySelector('#widget').textContent==='This widget has been removed.');await overlay.waitForTimeout(1200);
 assert.equal(await overlay.locator('.wd-horizon-card').count(),0);assert.equal(await overlay.locator('.wd-horizon-fx').count(),0);
 assert.deepEqual(errors,[]);
 console.log('PASS: saved import/export, playback end anticipation, pause, seek back, absorption, delayed start, burst, rapid skips, unknown duration, offline recovery, reduced motion, disposal.');

}finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
