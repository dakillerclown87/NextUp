/* Real NextUp UI/server, simulated slow Spotify failure. No live accounts. */
const {chromium}=require('playwright');
const {spawn}=require('child_process');
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),home=fs.mkdtempSync(path.join(os.tmpdir(),'nextup-recovery-'));
 let proc,browser;
 try{
  proc=spawn(process.env.NEXTUP_TEST_PYTHON||'python3',['-u','tools/test_nextup_host.py'],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});
  const url=await new Promise((resolve,reject)=>{
   let out='',err='';const timer=setTimeout(()=>reject(Error(err||'Startup timeout')),12000);
   proc.stderr.on('data',d=>err+=d);proc.stdout.on('data',d=>{out+=d;const m=out.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});
   proc.on('exit',code=>{clearTimeout(timer);reject(Error('Server exit '+code+' '+err))});
  });
  browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote']});
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.waitForSelector('.hero');
  await page.locator('#navigation [data-nav=queue]').click();
  let calls=0,release,received;const gate=new Promise(r=>release=r),seen=new Promise(r=>received=r);
  await page.route('**/api/playback',async route=>{calls++;received();await gate;await route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Spotify has no track loaded.'})})});
  await page.locator('[data-play=resume]').click();await seen;
  assert.equal(await page.locator('[data-play=resume]').isDisabled(),true);
  await page.locator('[data-play=resume]').dispatchEvent('click');assert.equal(calls,1);
  release();await page.waitForFunction(()=>!document.querySelector('[data-play=resume]').disabled);
  await page.route('**/api/state',async route=>{
   const response=await route.fetch(),data=await response.json();
   data.playback.status='Needs attention';data.playback.error='Spotify has no track loaded.';data.playback.busy=false;
   await route.fulfill({response,json:data});
  });
  await page.waitForFunction(()=>document.querySelector('.playback-error')?.textContent.includes('no track loaded'));
  assert.equal(await page.locator('#queue-playback-status').innerText(),'Needs attention');
  assert.deepEqual(errors,[]);
  console.log('PASS: Queue blocks duplicate Start clicks, releases controls after failure, and displays playback error/status.');
 }finally{
  if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}
  fs.rmSync(home,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1});
