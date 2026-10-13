const {chromium}=require('playwright'),{spawn}=require('child_process'),fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
(async()=>{const root=path.resolve(__dirname,'..'),home=fs.mkdtempSync(path.join(os.tmpdir(),'widget-designer-'));let proc,browser;try{
 proc=spawn('python3',['-u','tools/test_nextup_host.py'],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});let error='';proc.stderr.on('data',d=>error+=d);
 const url=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error(error||'startup timeout')),15000);proc.stdout.on('data',d=>{text+=d;const m=text.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});proc.on('exit',c=>{clearTimeout(timer);reject(Error('exit '+c+' '+error))})});
 browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote']});
 const context=await browser.newContext({viewport:{width:1200,height:920},acceptDownloads:true});
 await context.route('https://preview.invalid/**',r=>r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#13d9ed"/><stop offset="1" stop-color="#9924c7"/></linearGradient></defs><rect width="200" height="200" fill="#0b1530"/><circle cx="100" cy="80" r="62" fill="url(#g)"/><path d="M0 180L66 90 122 160 160 112 200 180V200H0Z" fill="#12293b"/></svg>'}));
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(url);await page.locator('[data-nav=widgets]').click();await page.waitForSelector('#we-preview .wd-part');
 await page.locator('#import-widget').setInputFiles(path.join(root,'docs/Neon-Drift-Widget.json'));await page.waitForFunction(()=>document.querySelector('#we-name').value==='Neon Drift');
 assert.equal(await page.locator('[data-preset-edit]').count(),0);await page.locator('#we-save-new').click();await page.waitForSelector('[data-preset-edit]');
 const first=await page.evaluate(()=>widgetDraft.id);assert(first);
 // Drag song title, then verify saved position.
 const title=page.locator('#we-preview [data-part=title]');await title.scrollIntoViewIfNeeded();const bounds=await title.boundingBox();const oldX=Number(await page.locator('#we-x').inputValue());
 await page.mouse.move(bounds.x+20,bounds.y+20);await page.mouse.down();await page.mouse.move(bounds.x+44,bounds.y+40,{steps:5});await page.mouse.up();assert(Number(await page.locator('#we-x').inputValue())>oldX);
 await page.locator('#we-save').click();await page.waitForFunction(()=>document.querySelector('#we-status').textContent==='Saved widget');
 await page.locator('#we-live').check();await page.locator('[data-we-hex=accent]').evaluate(e=>e.closest('details').open=true);await page.locator('[data-we-hex=accent]').fill('#FFCC33');
 await page.waitForFunction(()=>state.settings.widget_presets[0].colors.accent==='#FFCC33');
 const overlayUrl=await page.evaluate(()=>state.widgets.now+'&preset_id='+widgetDraft.id);const overlay=await context.newPage();await overlay.setViewportSize({width:800,height:300});overlay.on('pageerror',e=>errors.push(e.message));await overlay.goto(overlayUrl);await overlay.waitForSelector('.wd-stage');
 assert.equal(await overlay.locator('.wd-stage').evaluate(e=>e.style.getPropertyValue('--accent')),'#FFCC33');
 assert(await overlay.locator('.wd-background').evaluate(e=>e.complete&&e.naturalWidth>0));
 await page.locator('[data-we-hex=accent]').evaluate(e=>e.closest('details').open=true);await page.locator('[data-we-hex=accent]').fill('#ABCDEF');await overlay.waitForFunction(()=>document.querySelector('.wd-stage').style.getPropertyValue('--accent')==='#ABCDEF');
 // Save as new while live editing is off; original stays unchanged.
 await page.locator('#we-live').uncheck();await page.locator('#we-name').fill('Neon Drift Copy');await page.locator('[data-we-hex=accent]').evaluate(e=>e.closest('details').open=true);await page.locator('[data-we-hex=accent]').fill('#13D9ED');await page.locator('#we-save-new').click();await page.waitForFunction(()=>state.settings.widget_presets.length===2);
 const records=await page.evaluate(()=>state.settings.widget_presets);assert.equal(records[0].id,first);assert.equal(records[0].colors.accent,'#ABCDEF');assert.notEqual(records[1].id,first);
 // Upload a real JPEG and retain the resulting image in a portable export.
 const jpeg=await page.locator('#we-preview').screenshot({type:'jpeg'});await page.locator('#we-image').evaluate(e=>e.closest('details').open=true);await page.locator('#we-image').setInputFiles({name:'background.jpg',mimeType:'image/jpeg',buffer:jpeg});await page.waitForFunction(()=>!!widgetDraft.background_data);await page.locator('#we-save').click();await page.waitForFunction(()=>!widgetDraft.background_data&&!!widgetDraft.background.image);
 const downloading=page.waitForEvent('download');await page.locator('#we-export').click();const file=await downloading;const json=JSON.parse(fs.readFileSync(await file.path(),'utf8'));assert(json.background_data.startsWith('data:image/png;base64,'));assert(!json.id);assert.equal(json.format,'nextup-widget-v2');
 // Original sample remains importable and can render independently.
 await page.locator('#import-widget').setInputFiles(path.join(root,'docs/Neon-Drift-Widget.json'));await page.locator('#we-save-new').click();await page.waitForFunction(()=>state.settings.widget_presets.length===3);
 const finalUrl=await page.evaluate(()=>state.widgets.now+'&preset_id='+widgetDraft.id);await overlay.goto(finalUrl);await overlay.waitForSelector('.wd-background');await overlay.waitForFunction(()=>document.querySelector('.wd-background').complete);await overlay.screenshot({path:path.join(root,'build/Neon-Drift-Widget-preview.png')});
 const start=await overlay.locator('.fill').evaluate(e=>parseFloat(e.style.width));await overlay.waitForTimeout(600);assert((await overlay.locator('.fill').evaluate(e=>parseFloat(e.style.width)))>start);
 await page.reload();await page.locator('[data-nav=widgets]').click();assert.equal(await page.locator('[data-preset-edit]').count(),3);
 assert.deepEqual(errors,[]);console.log('PASS: import draft, save new, drag, persistent changes, live OBS hex updates, background loads, copy preserves original, JPEG upload/export embeds PNG, smooth progress, reload retains presets.');
 }finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
