const {chromium}=require('playwright'),{spawn}=require('child_process'),fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
(async()=>{const root=path.resolve(__dirname,'..'),home=fs.mkdtempSync(path.join(os.tmpdir(),'widget-designer-'));let proc,browser;try{
 proc=spawn('python3',['-u','tools/test_nextup_host.py','--audio-fixture'],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});let error='';proc.stderr.on('data',d=>error+=d);
 const url=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error(error||'startup timeout')),15000);proc.stdout.on('data',d=>{text+=d;const m=text.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});proc.on('exit',c=>{clearTimeout(timer);reject(Error('exit '+c+' '+error))})});
 browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote']});
 const context=await browser.newContext({viewport:{width:1200,height:920},acceptDownloads:true});
 await context.route('https://preview.invalid/**',r=>r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#13d9ed"/><stop offset="1" stop-color="#9924c7"/></linearGradient></defs><rect width="200" height="200" fill="#0b1530"/><circle cx="100" cy="80" r="62" fill="url(#g)"/><path d="M0 180L66 90 122 160 160 112 200 180V200H0Z" fill="#12293b"/></svg>'}));
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(url);await page.locator('[data-nav=widgets]').click();await page.waitForSelector('#we-preview .wd-part');

 context.setDefaultTimeout(20000);
 await page.locator('#widget-audio-refresh').click();await page.waitForFunction(()=>document.querySelectorAll('#widget-audio-app option').length===3);
 await page.locator('#widget-audio-app').selectOption('111:1001');await page.locator('#widget-audio-use').click();await page.waitForFunction(()=>state.settings.widget_audio_pid===111&&state.equalizer.status==='Listening');
 await page.waitForFunction(()=>document.querySelector('.wd-bars')?.dataset.audioMode==='application');
 const heights=()=>page.locator('#we-preview .wd-bars i').evaluateAll(b=>b.map(e=>Number(e.style.transform.match(/[\d.]+/)[0])));
 await page.waitForFunction(()=>Math.max(...[...document.querySelectorAll('#we-preview .wd-bars i')].map(e=>Number(e.style.transform.match(/[\d.]+/)?.[0]||0)))>.5);
 const low=await heights();assert(low.slice(0,8).some(v=>v>.5));
 await page.locator('#widget-audio-app').selectOption('222:2002');await page.locator('#widget-audio-use').click();await page.waitForFunction(()=>state.settings.widget_audio_pid===222);
 await page.waitForFunction(()=>[...document.querySelectorAll('#we-preview .wd-bars i')].slice(8).some(e=>Number(e.style.transform.match(/[\d.]+/)?.[0]||0)>.5));
 const high=await heights();assert(high.slice(8).some(v=>v>.5));
 // Silence should flatten the reactive bars without restoring CSS animation.
 await page.waitForFunction(()=>Math.max(...[...document.querySelectorAll('#we-preview .wd-bars i')].map(e=>Number(e.style.transform.match(/[\d.]+/)?.[0]||0)))<.06);
 assert.equal(await page.locator('#we-preview .wd-bars i').first().evaluate(e=>e.style.animationName),'none');
 await page.locator('#we-save-new').click();await page.waitForSelector('[data-preset-card]');const first=await page.evaluate(()=>widgetDraft.id);
 const card=page.locator('[data-preset-card="'+first+'"]');await card.scrollIntoViewIfNeeded();await card.frameLocator('iframe').locator('.wd-bars').waitFor();await page.waitForFunction(id=>!!document.querySelector('[data-preset-card="'+id+'"] iframe'),first);
 const cardFrame=card.frameLocator('iframe');await cardFrame.locator('[data-audio-mode=application]').waitFor();assert.equal(await card.locator('[data-preset-delete]').count(),1);
 await page.locator('#we-name').fill('Second saved card');await page.locator('#we-save-new').click();await page.waitForFunction(()=>state.settings.widget_presets.length===2);assert.equal(await page.locator('[data-preset-card]').count(),2);
 const oldUrl=await page.evaluate(id=>state.widgets.now+'&preset_id='+id,first);const old=await context.newPage();await old.goto(oldUrl);await old.waitForSelector('.wd-stage');
 await page.locator('[data-preset-delete="'+first+'"]').click();await page.waitForFunction(()=>state.settings.widget_presets.length===1);assert.equal(await page.locator('[data-preset-card="'+first+'"]').count(),0);await old.waitForFunction(()=>document.querySelector('#widget').textContent==='This widget has been removed.');
 await page.reload();await page.locator('[data-nav=widgets]').click();assert.equal(await page.locator('[data-preset-card]').count(),1);
 await page.locator('#widget-audio-mode').selectOption('animation');await page.waitForFunction(()=>document.querySelector('#we-preview .wd-bars').dataset.audioMode==='animation');assert.equal(await page.locator('#we-preview .wd-bars i').first().evaluate(e=>e.style.transform),'');
 const remaining=page.locator('[data-preset-card]');await remaining.scrollIntoViewIfNeeded();await remaining.frameLocator('iframe').locator('.wd-stage').waitFor();await remaining.frameLocator('iframe').locator('.wd-bars').waitFor();assert(await remaining.frameLocator('iframe').locator('body').innerText());await remaining.screenshot({path:path.join(root,'build/NextUp-saved-card.png')});
 // Follow mode routes actual fixture PCM using the conductor, with no manual selection.
 await page.locator('#widget-audio-mode').selectOption('follow');
 await page.waitForFunction(()=>state.equalizer.application==='Spotify');
 await page.evaluate(()=>api('settings',{youtube_player_mode:'chrome'}));
 await page.evaluate(()=>api('test-playback',{provider:'youtube'}));
 await page.waitForFunction(()=>state.equalizer.application==='Chrome');
 await page.waitForFunction(()=>[...document.querySelectorAll('#we-preview .wd-bars i')].slice(8).some(e=>Number(e.style.transform.match(/[\d.]+/)?.[0]||0)>.5));
 await page.evaluate(()=>api('test-playback',{provider:'youtube',status:'Paused'}));
 await page.waitForFunction(()=>state.equalizer.status.includes('waiting for playback'));
 await page.waitForFunction(()=>Math.max(...[...document.querySelectorAll('#we-preview .wd-bars i')].map(e=>Number(e.style.transform.match(/[\d.]+/)?.[0]||0)))<.06);
 await page.evaluate(()=>api('test-playback',{provider:'spotify',status:'Paused'}));
 await page.evaluate(()=>api('settings',{youtube_player_mode:'embedded'}));
 await page.evaluate(()=>api('test-playback',{provider:'youtube'}));
 await page.waitForFunction(()=>state.equalizer.application==='NextUp YouTube player');
 await page.evaluate(()=>api('test-playback',{provider:'spotify'}));
 await page.waitForFunction(()=>state.equalizer.application==='Spotify');
 await page.reload();await page.locator('[data-nav=widgets]').click();assert.equal(await page.locator('#widget-audio-mode').inputValue(),'follow');assert(await page.locator('#widget-audio-app').isDisabled());
 await page.locator('#widget-audio-panel').screenshot({path:path.join(root,'build/NextUp-follow-settings.png')});
 await page.locator('#widget-audio-mode').selectOption('animation');await page.waitForFunction(()=>state.equalizer.status==='Animation');
 assert.deepEqual(errors,[]);await page.screenshot({path:path.join(root,'build/NextUp-reactive-widgets.png'),fullPage:true});console.log('PASS: automatic Spotify/Chrome/embedded switching, pause/resume and persisted follow setting; application discovery/selection, real fixture PCM→FFT→WebSocket→bars, low/high frequency sources, silence, stop capture, saved inline preview cards, deletion by ID, removed URL, persistence.');
 }finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
