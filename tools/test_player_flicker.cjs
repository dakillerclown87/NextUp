/* Actual launcher DOM with delayed/failed artwork and simulated transitions. */
const {chromium}=require('playwright');
const {spawn}=require('child_process');
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),home=fs.mkdtempSync(path.join(os.tmpdir(),'nextup-player-ui-'));
 let proc,browser;
 try{
  proc=spawn(process.env.NEXTUP_TEST_PYTHON||'python3',['-u','tools/test_nextup_host.py'],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});
  const url=await new Promise((resolve,reject)=>{
   let out='',err='';const timer=setTimeout(()=>reject(Error(err||'Startup timeout')),15000);
   proc.stderr.on('data',d=>err+=d);proc.stdout.on('data',d=>{out+=d;const m=out.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
   proc.on('exit',code=>{clearTimeout(timer);reject(Error('Server exit '+code+' '+err));});
  });
  browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote']});
  const page=await browser.newPage({viewport:{width:1182,height:702}}),errors=[],pending=new Map();
  page.on('pageerror',e=>errors.push(e.message));
  // Drive state deterministically; leave the real animation-frame loop running.
  await page.addInitScript(()=>{const interval=window.setInterval;window.setInterval=(fn,ms,...args)=>ms===1000?0:interval(fn,ms,...args);});
  const cover=route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#29bacd"/></svg>'});
  await page.route('https://preview.invalid/**',async route=>{
   if(/slow|late/.test(route.request().url())){pending.set(route.request().url(),route);return;}
   if(route.request().url().includes('broken'))return route.fulfill({status:404,body:''});
   await cover(route);
  });
  await page.goto(url);await page.waitForSelector('.player-art img');
  await page.evaluate(()=>{
   window.nodes={card:document.querySelector('.listening-card'),image:document.querySelector('.player-art img'),button:document.querySelector('[data-player-toggle]'),fill:document.querySelector('[data-progress-fill]')};
   window.applyPlayer=(status,art,busy=false)=>{state.playback.status=status;state.playback.busy=busy;state.playback.starting=null;playbackPending=false;if(art)state.playback.current.track={...state.playback.current.track,art,title:art.split('/').pop()};syncLive();};
  });
  // Exercise the real click handler BEFORE a polling response. Directly setting
  // a busy state missed this interval in beta.61: buttons dimmed until syncLive.
  let heldPlayback=null;
  await page.route('**/api/playback',route=>{heldPlayback=route;});
  for(let i=0;i<3;i++){
   const layout=await page.locator('#upcoming-panel').boundingBox();
   await page.locator('[data-play=next]').click();
   await page.waitForFunction(()=>playbackPending);
   const frames=await page.evaluate(()=>new Promise(resolve=>{
    const samples=[];const sample=()=>{const b=document.querySelector('[data-player-toggle]');samples.push({opacity:getComputedStyle(b).opacity,disabled:b.disabled,busy:b.closest('.listening-card').getAttribute('aria-busy'),title:document.querySelector('[data-play=next]').title});if(samples.length===12)resolve(samples);else requestAnimationFrame(sample);};sample();
   }));
   for(const frame of frames){assert.equal(frame.opacity,'1','Click must not dim controls before polling');assert.equal(frame.disabled,true);assert.equal(frame.busy,'true');assert.doesNotMatch(frame.title,/Waiting for/);}
   // Hold the follow-up GET after POST success: beta.62 inserted a banner in
   // this gap and moved the WHOLE page until the fresh state cleared it.
   let heldState=null;await page.route('**/api/state',route=>{heldState=route;});
   assert.ok(heldPlayback);await heldPlayback.fulfill({json:{ok:true}});heldPlayback=null;
   await page.waitForFunction(()=>!playbackPending);
   const positions=await page.evaluate(()=>new Promise(resolve=>{
    const samples=[];const sample=()=>{samples.push(document.querySelector('#upcoming-panel').getBoundingClientRect().y);if(samples.length===12)resolve(samples);else requestAnimationFrame(sample);};sample();
   }));
   for(const y of positions)assert.equal(y,layout.y,'Successful playback must not move the whole page before the state refresh');
   assert.equal(await page.locator('#notice').textContent(),'');
   assert.ok(heldState);await heldState.fulfill({response:await heldState.fetch()});await page.unroute('**/api/state');
   await page.waitForFunction(()=>!playbackPending&&!document.querySelector('[data-play=next]').disabled);
   assert.equal(await page.locator('.listening-card').getAttribute('aria-busy'),'false');
  }
  // Genuine notifications/errors remain readable without shifting either column.
  const layoutBeforeNotice=await page.locator('#upcoming-panel').boundingBox();
  for(const error of [false,true]){
   await page.evaluate(error=>notice('A message that must remain readable.',error),error);
   assert.equal(await page.locator('#notice').isVisible(),true);
   assert.deepEqual(await page.locator('#upcoming-panel').boundingBox(),layoutBeforeNotice);
   await page.evaluate(()=>notice(''));
   assert.deepEqual(await page.locator('#upcoming-panel').boundingBox(),layoutBeforeNotice);
  }
  // Repeated skips must not recreate the card, image, progress bar or button.
  for(let i=0;i<10;i++)for(const status of ['Switching songs','Starting Spotify','Playing']){
   await page.evaluate(status=>applyPlayer(status,null,status!=='Playing'),status);
   assert.deepEqual(await page.evaluate(()=>[nodes.card===document.querySelector('.listening-card'),nodes.image===document.querySelector('.player-art img'),nodes.button===document.querySelector('[data-player-toggle]'),nodes.fill===document.querySelector('[data-progress-fill]'),nodes.button.dataset.play==='pause']),[true,true,true,true,true]);
   assert.equal(await page.locator('[data-player-toggle]').evaluate(el=>getComputedStyle(el).opacity),'1');
   assert.equal(await page.locator('[data-player-toggle]').isDisabled(),status!=='Playing');
  }
  const before=await page.locator('.player-art').boundingBox();
  await page.evaluate(()=>applyPlayer('Starting Spotify','https://preview.invalid/slow.svg',true));
  await page.waitForFunction(()=>document.querySelector('[data-player-title]').textContent==='slow.svg');
  assert.equal(await page.evaluate(()=>nodes.image===document.querySelector('.player-art img')),true);
  assert.deepEqual(await page.locator('.player-art').boundingBox(),before);
  // A later song wins even when the previous artwork finishes afterward.
  await page.evaluate(()=>applyPlayer('Playing','https://preview.invalid/new.svg'));
  await page.waitForFunction(()=>document.querySelector('.player-art img')?.src.endsWith('/new.svg'));
  assert.ok(pending.has('https://preview.invalid/slow.svg'));
  await cover(pending.get('https://preview.invalid/slow.svg'));
  await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  assert.equal(await page.locator('.player-art img').getAttribute('src'),'https://preview.invalid/new.svg');
  // Missing artwork has a stable placeholder, with no stale cover or broken icon.
  await page.evaluate(()=>applyPlayer('Playing','https://preview.invalid/broken.svg'));
  await page.waitForSelector('.player-art div.cover');
  assert.deepEqual(await page.locator('.player-art').boundingBox(),before);
  await page.evaluate(()=>applyPlayer('Paused'));
  assert.equal(await page.locator('[data-player-toggle]').getAttribute('data-play'),'resume');
  await page.evaluate(()=>applyPlayer('Playing','https://preview.invalid/restored.svg'));
  await page.waitForSelector('.player-art img');
  assert.equal(await page.locator('[data-player-toggle]').getAttribute('data-play'),'pause');
  // Navigation while an image is loading cannot replace the new view's artwork.
  await page.evaluate(()=>applyPlayer('Starting Spotify','https://preview.invalid/late.svg',true));
  await page.waitForFunction(()=>document.querySelector('.player-art').dataset.wanted.endsWith('/late.svg'));
  await page.locator('#navigation [data-nav=queue]').click();
  if(pending.has('https://preview.invalid/late.svg'))await cover(pending.get('https://preview.invalid/late.svg'));
  await page.locator('#navigation [data-nav=home]').click();
  await page.evaluate(()=>applyPlayer('Playing','https://preview.invalid/final.svg'));
  await page.waitForFunction(()=>document.querySelector('.player-art img')?.src.endsWith('/final.svg'));
  for(const width of [1000,700,500]){
   await page.setViewportSize({width,height:800});
   const box=await page.locator('.player-art').boundingBox();assert.ok(Math.abs(box.width-box.height)<1);assert.ok(box.width<=130);
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: whole-page positions stay fixed across POST success and delayed state refresh; notifications cause no layout shift; click frames, 30 status changes, artwork races and compact layouts verified.');
 }finally{
  if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500);});}
  fs.rmSync(home,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
