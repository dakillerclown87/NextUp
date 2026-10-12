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
  for(const view of ['home','rules','connections','diagnostics']){
   if(view==='home') await page.locator('#navigation [data-nav=home]').click(); else {await page.locator('#navigation [data-nav=settings]').click();await page.locator('#settings-page').selectOption(view);}
   const folds=page.locator('.panel-fold'), count=await folds.count();assert(count>0);
   for(let i=0;i<count;i++){
    const b=folds.nth(i);await b.click();assert.equal(await b.isVisible(),true);
    assert.equal(await b.getAttribute('aria-expanded'),'false');
    await b.click();assert.equal(await b.getAttribute('aria-expanded'),'true');
   }
  }
  await page.locator('#navigation [data-nav=settings]').click();await page.locator('#settings-page').selectOption('rules');
  await page.locator('.panel-fold').first().click();
  await page.locator('#navigation [data-nav=home]').click();
  await page.locator('#navigation [data-nav=settings]').click();await page.locator('#settings-page').selectOption('rules');
  assert.equal(await page.locator('.panel-fold').first().isVisible(),true);
  assert.equal(await page.locator('.panel-fold').first().getAttribute('aria-expanded'),'false');
  await page.locator('#restore-panels').click();
  assert.equal(await page.locator('.panel-minimized').count(),0);
  const state=()=>page.evaluate(async()=>await(await fetch('/api/state',{headers:{'X-NextUp-Key':sessionStorage.getItem('nextup-key')}})).json());
  await page.locator('#navigation [data-nav=queue]').click();
  await page.locator('#allow-explicit').uncheck();
  await page.waitForFunction(async()=> (await (await fetch('/api/state',{headers:{'X-NextUp-Key':sessionStorage.getItem('nextup-key')}})).json()).settings.block_explicit===true);
  await page.locator('#allow-explicit').check();
  await page.waitForFunction(async()=> (await (await fetch('/api/state',{headers:{'X-NextUp-Key':sessionStorage.getItem('nextup-key')}})).json()).settings.block_explicit===false);
  await page.locator('#navigation [data-nav=settings]').click();await page.locator('#settings-page').selectOption('rules');
  assert.equal(await page.locator('[name=allow_explicit]').isChecked(),true);
  await page.locator('[name=allow_explicit]').uncheck();
  await page.getByRole('button',{name:'Save request rules',exact:true}).click();
  await page.waitForFunction(async()=> (await (await fetch('/api/state',{headers:{'X-NextUp-Key':sessionStorage.getItem('nextup-key')}})).json()).settings.block_explicit===true);
  await page.locator('#navigation [data-nav=queue]').click();
  assert.equal(await page.locator('#allow-explicit').isChecked(),false);
  await page.locator('#spotify-native-queue').check();
  await page.waitForFunction(async()=> (await (await fetch('/api/state',{headers:{'X-NextUp-Key':sessionStorage.getItem('nextup-key')}})).json()).spotify_queue.enabled===true);
  assert.equal((await state()).settings.provider_mode,'spotify');
  assert.deepEqual(errors,[]);
  console.log('PASS: direct/nested panel expand controls, saved collapsed state, global recovery, both explicit switches, and native-queue mode switch.');
 }finally{
  if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}
  fs.rmSync(home,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1});
