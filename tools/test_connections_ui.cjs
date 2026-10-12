/* Optional UI regression test: npm install playwright; set NEXTUP_TEST_PYTHON
   and NEXTUP_TEST_CHROMIUM if Python/Chromium are not on their usual paths. */
const {chromium}=require('playwright');
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
const {spawn}=require('child_process');
(async()=>{
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'nextup-ui-'));
 let browser,proc;
 try{
  browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM||undefined,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote']});
  proc=spawn(process.env.NEXTUP_TEST_PYTHON||'python',['-u','-m','studio.server','--no-browser'],{cwd:path.resolve(__dirname,'..'),env:{...process.env,NEXTUP_HOME:home}});
  let errors='';proc.stderr.on('data',d=>errors+=d);
  const url=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('Server startup timeout: '+errors)),10000);proc.stdout.on('data',d=>{out+=d;const m=out.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});proc.on('exit',code=>{clearTimeout(timer);reject(Error('Server exit '+code+': '+errors))})});
  const page=await browser.newPage({viewport:{width:1000,height:800}}),jsErrors=[];
  page.on('pageerror',e=>jsErrors.push(e.message));
  let authorized=false,failSave=false,available=true;
  await page.route('**/api/state',async route=>{const response=await route.fetch(),data=await response.json();data.connections.spotify=authorized;data.connections.twitch=authorized;await route.fulfill({response,json:data})});
  await page.route('**/api/devices',route=>route.fulfill({json:{devices:available?[{id:'pc',name:'Streaming PC',is_active:true},{id:'phone',name:'Phone'},{id:'restricted',name:'Restricted',is_restricted:true},{id:null,name:'No ID'}]:[]}}));
  await page.route('**/api/settings',route=>failSave?route.fulfill({status:500,json:{error:'Could not save settings'}}):route.continue());
  const settings=()=>JSON.parse(fs.readFileSync(path.join(home,'userdata','studio.json'),'utf8'));
  const connections=async()=>{await page.locator('#navigation [data-nav=settings]').click();await page.locator('#settings-page').selectOption('connections');};
  const waitSaved=text=>page.waitForFunction(text=>document.querySelector('#notice').textContent.includes(text),text);
  await page.goto(url);await page.waitForSelector('#open-player');await connections();
  for(const name of ['spotify_client_id','twitch_client_id'])assert.equal(await page.locator(`[name=${name}]`).getAttribute('type'),'password');
  await page.locator('[name=spotify_client_id]').fill('unsaved-client');
  await page.locator('[data-reveal=spotify_client_id]').click();assert.equal(await page.locator('[name=spotify_client_id]').getAttribute('type'),'text');
  await page.locator('[data-reveal=spotify_client_id]').click();assert.equal(await page.locator('[name=spotify_client_id]').getAttribute('type'),'password');
  await page.locator('#devices').click();await page.locator('#device-select').selectOption('pc');await waitSaved('Playback device saved: Streaming PC');
  assert.equal(settings().spotify_device,'pc');assert.equal(settings().spotify_client_id,'');
  assert.equal(await page.locator('[name=spotify_client_id]').inputValue(),'unsaved-client');
  assert.equal(await page.locator('#device-select option[value=restricted]').evaluate(el=>el.disabled),true);
  assert.equal(await page.locator('#device-select option').count(),4);
  await page.locator('#navigation [data-nav=home]').click();await connections();assert.match(await page.locator('#saved-device').innerText(),/Streaming PC/);
  await page.locator('#devices').click();assert.equal(await page.locator('#device-select').inputValue(),'pc');
  failSave=true;await page.locator('#device-select').selectOption('phone');await waitSaved('Could not save settings');assert.equal(await page.locator('#device-select').inputValue(),'pc');assert.equal(settings().spotify_device,'pc');failSave=false;
  await page.getByRole('button',{name:'Save connections',exact:true}).click();await waitSaved('Connections saved');assert.equal(settings().spotify_device,'pc');
  await page.reload();await page.waitForSelector('#open-player');await connections();assert.match(await page.locator('#saved-device').innerText(),/Streaming PC/);
  available=false;await page.locator('#devices').click();assert.equal(await page.locator('#device-select').inputValue(),'pc');assert.match(await page.locator('#device-select option:checked').innerText(),/unavailable/);available=true;
  await page.locator('#devices').click();await page.locator('#device-select').selectOption('');await waitSaved('Saved: use Spotify');assert.equal(settings().spotify_device,'');
  await page.locator('[name=twitch_client_id]').fill('keep-unsaved-text');authorized=true;
  await page.waitForFunction(()=>document.querySelector('#spotify-connect').textContent==='Connected'&&document.querySelector('#twitch-connect').textContent==='Connected');
  assert.equal(await page.locator('#spotify-connect').isDisabled(),true);assert.equal(await page.locator('#twitch-connect').isDisabled(),true);
  assert.equal(await page.locator('[name=twitch_client_id]').inputValue(),'keep-unsaved-text');
  await page.locator('#menu-toggle').click();await page.waitForFunction(()=>document.querySelector('#menu-toggle').getAttribute('aria-expanded')==='false');assert.equal(settings().sidebar_collapsed,true);
  await page.reload();await page.waitForSelector('#open-player');assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'),'false');
  await connections();assert.equal(await page.locator('[name=twitch_client_id]').getAttribute('type'),'password');
  for(const width of [1000,800,375]){await page.setViewportSize({width,height:800});for(let i=0;i<2;i++){await page.locator('#menu-toggle').click();await page.waitForFunction(()=>!document.querySelector('#menu-toggle').disabled);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'horizontal overflow at '+width)}}
  await page.locator('[name=youtube_player_mode]').selectOption('chrome');
  await page.getByRole('button',{name:'Save connections',exact:true}).click();await waitSaved('Connections saved');
  assert.equal(settings().youtube_player_mode,'chrome');
  await page.locator('#chrome-pair').click();assert.equal(await page.locator('#chrome-code').getAttribute('type'),'password');assert.equal((await page.locator('#chrome-code').inputValue()).length,32);
  await page.locator('#chrome-revoke').click();await waitSaved('Chrome pairing removed');assert.equal(await page.locator('#chrome-code').count(),0);
  await page.setViewportSize({width:1000,height:800});await page.screenshot({path:path.join(__dirname,'../build/connections-beta4.png'),fullPage:true});
  assert.deepEqual(jsErrors,[]);
  console.log('PASS: device auto-save, restart, failure recovery, unavailable/restricted devices, masked IDs, automatic Connected status, unsaved edits, persistent collapsible menu and responsive layout.');
 }finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(resolve=>{proc.once('exit',resolve);setTimeout(resolve,3000)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
