/* Fallback settings and playback through the real UI/server with simulated Spotify. */
const {chromium}=require('playwright');
const {spawn}=require('child_process');
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),home=fs.mkdtempSync(path.join(os.tmpdir(),'nextup-recovery-'));
 let proc,browser;
 try{
  proc=spawn(process.env.NEXTUP_TEST_PYTHON||'python3',['-u','tools/test_nextup_host.py','--fallback-fixture'],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});
  const url=await new Promise((resolve,reject)=>{
   let out='',err='';const timer=setTimeout(()=>reject(Error(err||'Startup timeout')),12000);
   proc.stderr.on('data',d=>err+=d);proc.stdout.on('data',d=>{out+=d;const m=out.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});
   proc.on('exit',code=>{clearTimeout(timer);reject(Error('Server exit '+code+' '+err))});
  });
  browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote']});
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.waitForSelector('.hero');

  page.on('dialog',d=>d.accept());
  await page.locator('#navigation [data-nav=queue]').click();
  const form=page.locator('#fallback-form');
  await form.locator('[name=fallback_enabled]').check();
  await form.locator('[name=fallback_playlist]').fill('https://open.spotify.com/playlist/'+'A'.repeat(22)+'?si=test');
  await form.locator('[name=fallback_shuffle]').uncheck();
  await form.locator('button.primary').click();
  await page.waitForFunction(()=>state.settings.fallback_enabled && state.settings.fallback_playlist==='A'.repeat(22));
  await page.reload();await page.locator('#navigation [data-nav=queue]').click();
  assert(await form.locator('[name=fallback_enabled]').isChecked());
  assert.equal(await form.locator('[name=fallback_shuffle]').isChecked(),false);
  await page.locator('details[data-collapse=fallback] summary').click();
  assert.equal(await form.isVisible(),false);
  await page.locator('details[data-collapse=fallback] summary').click();
  assert(await form.isVisible());
  await page.locator('#clear-queue').click();
  await page.waitForFunction(()=>state.queue.items.length===0);
  await page.locator('[data-play=next]').click();
  await page.waitForFunction(()=>state.playback.fallback_active);
  assert.equal(await page.locator('#fallback-status').innerText(),'Playing from your fallback playlist');
  await page.evaluate(()=>api('request',{url:'https://open.spotify.com/track/'+'V'.repeat(22)}));
  await page.waitForFunction(()=>state.queue.items.length===1);
  assert(await page.evaluate(()=>state.playback.fallback_active));
  await page.locator('[data-play=next]').click();
  await page.waitForFunction(()=>!state.playback.fallback_active && state.playback.current.track.id==='V'.repeat(22));
  await page.locator('[data-play=next]').click();
  await page.waitForFunction(()=>state.playback.fallback_active && state.playback.current.track.id==='1'.repeat(22));
  await form.locator('[name=fallback_enabled]').uncheck();await form.locator('button.primary').click();
  await page.waitForFunction(()=>!state.settings.fallback_enabled);
  await page.locator('[data-play=next]').click();await page.waitForFunction(()=>state.playback.status==='Queue empty');
  assert.deepEqual(errors,[]);
  await page.setViewportSize({width:900,height:700});await form.scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(root,'build/NextUp-fallback.png'),fullPage:true});
  console.log('PASS: saved fallback settings, URL normalization, reload persistence, collapse/reopen, empty queue start, viewer priority, cursor continuation and disable. Provider playback simulated.');
 }finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
