/* Real launcher UI and local request API; provider metadata is deterministic. */
const {chromium}=require('playwright'),{spawn}=require('child_process'),fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),home=fs.mkdtempSync(path.join(os.tmpdir(),'nextup-song-input-'));let browser,proc;
 try{
  proc=spawn('python3',['-u','tools/test_nextup_host.py','--request-fixture'],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});
  const url=await new Promise((resolve,reject)=>{let output='',err='';const timer=setTimeout(()=>reject(Error(err||'Startup timed out')),12000);proc.stderr.on('data',d=>err+=d);proc.stdout.on('data',d=>{output+=d;const m=output.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});proc.on('exit',c=>{clearTimeout(timer);reject(Error(err+' exit '+c))})});
  browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
  const page=await browser.newPage({viewport:{width:1100,height:800}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://preview.invalid/**',r=>r.fulfill({status:204}));await page.goto(url);
  await page.locator('#search-form').waitFor();
  assert.equal(await page.locator('body').getAttribute('data-page'),'home');
  const input=page.locator('#search-form [name=text]'),provider=page.locator('#search-form [name=provider]'),button=page.locator('#search-form [type=submit]');
  const done=()=>page.waitForFunction(()=>document.querySelector('#search-form')?.getAttribute('aria-busy')==='false'&&document.querySelector('#song-status').textContent.startsWith('Queued:'));
  await provider.selectOption('youtube');await input.fill('https://open.spotify.com/track/'+'A'.repeat(22));assert.equal(await button.innerText(),'Add song');await button.click();await done();
  assert.equal(await input.inputValue(),'');assert.match(await page.locator('#song-status').innerText(),/Spotify/);assert.equal(await provider.inputValue(),'youtube');
  await input.fill('https://youtu.be/abcdefghijk?si=share');await button.click();await done();assert.equal(await input.inputValue(),'');assert.match(await page.locator('#song-status').innerText(),/YouTube/);assert.equal(await page.locator('#search-results .songrow').count(),0);
  assert.equal(await page.locator('.request-card').filter({hasText:'Youtube abcdefghijk'}).count(),1);
  const state=await page.evaluate(async()=>{const r=await fetch('/api/state',{headers:{'X-NextUp-Key':sessionStorage.getItem('nextup-key')}});return r.json()});
  const added=state.queue.items.find(x=>x.track.id==='abcdefghijk');assert.equal(added.status,'queued');assert.equal(added.reviewed,true);
  await page.locator('#navigation [data-nav=queue]').click();
  assert.equal(await page.locator('.songrow').filter({hasText:'Youtube abcdefghijk'}).locator('[data-approve]').count(),0);
  await page.locator('#spotify-native-queue').check();await page.waitForFunction(()=>state.settings.spotify_native_queue===true);
  assert.equal(await page.evaluate(()=>state.settings.provider_mode),'mixed');
  await page.locator('#fallback-form [name=fallback_provider]').selectOption('youtube');
  await page.locator('#fallback-form [name=fallback_youtube_playlist]').fill('https://www.youtube.com/playlist?list=PLabcdefghijk');
  await page.locator('#fallback-form [name=fallback_enabled]').check();
  await page.locator('#fallback-form button.primary').click();
  await page.waitForFunction(()=>state.settings.fallback_enabled&&state.settings.fallback_provider==='youtube');
  assert.equal(await page.evaluate(()=>state.settings.fallback_youtube_playlist),'PLabcdefghijk');
  await page.locator('#fallback-check').click();await page.waitForFunction(()=>document.querySelector('#fallback-status').textContent.includes('API key'));assert.equal(await page.locator('#fallback-check').isEnabled(),true);
  await provider.selectOption('spotify');await input.fill('Artist and title');assert.equal(await button.innerText(),'Search');await button.click();await page.locator('#search-results [data-add-url]').first().waitFor();assert.equal(await page.locator('#search-results .songrow').count(),2);
  // Switching the search provider clears the old provider's choices.
  await provider.selectOption('youtube');assert.equal(await page.locator('#search-results .songrow').count(),0);
  await provider.selectOption('spotify');await button.click();await page.locator('#search-results [data-add-url]').first().click();await done();assert.equal(await input.inputValue(),'');assert.equal(await page.locator('#search-results .songrow').count(),0);
  await input.fill('https://www.youtube.com/playlist?list=123');await button.click();await page.waitForFunction(()=>document.querySelector('#song-status').classList.contains('error'));assert.match(await page.locator('#song-status').innerText(),/video link/);assert.notEqual(await input.inputValue(),'');assert.equal(await button.isEnabled(),true);
  let submissions=0;await page.route('**/api/song-input',async r=>{submissions++;await new Promise(resolve=>setTimeout(resolve,600));await r.continue()});
  await input.fill('https://youtu.be/lmnopqrstuv');await page.evaluate(()=>{const f=document.querySelector('#search-form');f.requestSubmit();f.requestSubmit()});
  await page.waitForFunction(()=>document.querySelector('#search-form [name=text]').disabled);await done();assert.equal(submissions,1);
  await page.locator('#navigation [data-nav=home]').click();assert.equal(await page.locator('#search-results .songrow').count(),0);assert.equal(await input.inputValue(),'');
  assert.deepEqual(errors,[]);console.log('PASS: Home unrated YouTube with review enabled, no second approval, mixed native mode, YouTube fallback settings, Spotify → YouTube direct links, link/provider mismatch, name-search selection, cleared stale results, visible invalid-link error, and duplicate-submit guard in real launcher UI + local API.');
 }finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,2000)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
