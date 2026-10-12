const {chromium}=require('playwright'),{spawn}=require('child_process'),fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
(async()=>{const root=path.resolve(__dirname,'..'),home=fs.mkdtempSync(path.join(os.tmpdir(),'widget-designer-'));let proc,browser;try{
 proc=spawn('python3',['-u','tools/test_nextup_host.py'],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});let error='';proc.stderr.on('data',d=>error+=d);
 const url=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error(error||'startup timeout')),15000);proc.stdout.on('data',d=>{text+=d;const m=text.match(/Dashboard URL: (http[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});proc.on('exit',c=>{clearTimeout(timer);reject(Error('exit '+c+' '+error))})});
 browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote']});
 const context=await browser.newContext({viewport:{width:1200,height:920},acceptDownloads:true});
 await context.route('https://preview.invalid/**',r=>r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#13d9ed"/><stop offset="1" stop-color="#9924c7"/></linearGradient></defs><rect width="200" height="200" fill="#0b1530"/><circle cx="100" cy="80" r="62" fill="url(#g)"/><path d="M0 180L66 90 122 160 160 112 200 180V200H0Z" fill="#12293b"/></svg>'}));
 context.setDefaultTimeout(15000);const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(url);await page.locator('[data-nav=widgets]').click();await page.waitForSelector('#we-preview .wd-part');
 // Built-ins keep their existing URLs and update in already-open previews.
 const pages=[];
 for(const kind of ['now','gradient','queue']){
  const url=await page.evaluate(k=>state.widgets[k],kind),p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));
  const response=await p.goto(url);assert.equal(response.status(),200);await p.waitForSelector('.brand');pages.push([kind,p,url]);
 }
 await page.locator('#widget-branding').uncheck();
 for(const [kind,p,url]of pages){await p.waitForFunction(text=>document.querySelector('.brand')?.textContent===text,kind==='queue'?'UP NEXT':'NOW PLAYING');assert.equal(p.url(),url);assert(!await p.locator('#widget').innerText().then(t=>t.includes('NEXTUP')));}
 await page.reload();await page.locator('[data-nav=widgets]').click();assert.equal(await page.locator('#widget-branding').isChecked(),false);
 await page.locator('[data-edit-widget=now]').click();assert.equal(await page.locator('#we-label').inputValue(),'NOW PLAYING');
 await page.locator('#we-now-playing').click();assert.equal(await page.locator('#we-preview [data-part=brand]').innerText(),'Now Playing');
 await page.locator('#we-save-new').click();await page.waitForSelector('[data-preset-edit]');const first=await page.evaluate(()=>widgetDraft.id);
 const custom=await context.newPage();custom.on('pageerror',e=>errors.push(e.message));await custom.goto(await page.evaluate(()=>state.widgets.now+'&preset_id='+widgetDraft.id));await custom.waitForSelector('[data-part=brand]');assert.equal(await custom.locator('[data-part=brand]').innerText(),'Now Playing');
 await page.locator('#we-live').check();await page.locator('#we-label').fill('Música 🎵 <b>live</b>');await custom.waitForFunction(()=>document.querySelector('[data-part=brand]')?.textContent==='Música 🎵 <b>live</b>');assert.equal(await custom.locator('[data-part=brand] b').count(),0);
 await page.locator('#we-label').fill('');await custom.waitForFunction(()=>document.querySelector('[data-part=brand]')?.textContent==='');
 await page.locator('#we-now-playing').click();await custom.waitForFunction(()=>document.querySelector('[data-part=brand]')?.textContent==='Now Playing');await page.locator('#we-live').uncheck();
 const downloading=page.waitForEvent('download');await page.locator('#we-export').click();const exported=await downloading;const json=JSON.parse(fs.readFileSync(await exported.path(),'utf8'));assert.equal(json.label,'Now Playing');
 await page.locator('#we-label').fill('My Mix');await page.locator('#we-save-new').click();await page.waitForFunction(()=>state.settings.widget_presets.length===2);assert.equal(await page.evaluate(id=>state.settings.widget_presets.find(p=>p.id===id).label,first),'Now Playing');
 await page.locator('#import-widget').setInputFiles({name:'heading.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(json))});await page.waitForFunction(()=>document.querySelector('#we-label').value==='Now Playing');assert.equal(await page.locator('#we-label').inputValue(),'Now Playing');
 // The v1 renderer also honors the heading, escapes it, and permits blank text.
 for(const kind of ['spectrum','gradient','queue']){
  const p=await page.evaluate(async layout=>api('widget-save',{preset:{format:'nextup-widget-v1',name:'Legacy '+layout,layout,equalizer:true,label:'Now Playing <b>safe</b>'},as_new:true}),kind);
  const url=await page.evaluate(({kind,id})=>state.widgets[kind==='spectrum'?'now':kind]+'&preset_id='+id,{kind,id:p.id});await custom.goto(url);await custom.waitForSelector('.brand');assert.equal(await custom.locator('.brand').first().innerText(),'Now Playing <b>safe</b>');assert.equal(await custom.locator('.brand b').count(),0);
 }
 await page.locator('#widget-branding').check();for(const [,p]of pages)await p.waitForFunction(()=>document.querySelector('.brand')?.textContent.startsWith('NEXTUP'));
 await custom.goto(await page.evaluate(id=>state.widgets.now+'&preset_id='+id,first));await custom.waitForSelector('[data-part=brand]');assert.equal(await custom.locator('[data-part=brand]').innerText(),'Now Playing');
 assert.deepEqual(errors,[]);console.log('PASS: built-in overlays, live branding switch, reload persistence, heading edit/blank/Unicode/HTML escaping, custom live updates, portable export/import, saved-copy isolation and all three legacy layouts.');
 }finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
