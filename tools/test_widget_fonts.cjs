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
 // Each file format must parse, persist, and load in a separate overlay document.
 const choices=[['title','Serif.ttf'],['artist','Gothic.otf'],['requester','Mono.woff'],['time','Mono.woff2']];
 for(const [part,file] of choices){
  await page.locator('#we-part').selectOption(part);
  await page.locator('#we-font-upload').setInputFiles(path.join(root,'build/font-fixtures',file));
  await page.waitForFunction(({part,file})=>widgetDraft.fonts.some(f=>f.name===file&&f.id===widgetDraft.elements[part].font),{part,file});
  await page.waitForFunction(()=>document.querySelector('#we-preview').dataset.fontStatus==='loaded');
  assert.match(await page.locator('#we-preview [data-part='+part+']').evaluate(e=>getComputedStyle(e).fontFamily),/NextUpFont_/);
 }
 await page.locator('#we-part').selectOption('title');await page.locator('#we-weight').selectOption('800');await page.locator('#we-spacing').fill('2.5');
 await page.locator('#we-save').click();await page.waitForFunction(()=>!widgetDirty);
 const overlayUrl=await page.evaluate(()=>state.widgets.now+'&preset_id='+widgetDraft.id);const overlay=await context.newPage();overlay.on('pageerror',e=>errors.push(e.message));await overlay.setViewportSize({width:800,height:300});await overlay.goto(overlayUrl);
 await overlay.waitForFunction(()=>document.querySelector('#widget')?.dataset.fontStatus==='loaded');
 for(const [part] of choices){
  const font=await overlay.locator('[data-part='+part+']').evaluate(e=>{const name=getComputedStyle(e).fontFamily.split(',')[0];return {name,loaded:document.fonts.check('20px '+name)}});
  assert.match(font.name,/NextUpFont_/);assert(font.loaded);
 }
 assert.equal(await overlay.locator('[data-part=title]').evaluate(e=>getComputedStyle(e).fontWeight),'800');
 assert.equal(await overlay.locator('[data-part=title]').evaluate(e=>getComputedStyle(e).letterSpacing),'2.5px');
 await page.locator('#we-live').check();await page.locator('#we-weight').selectOption('400');await page.locator('#we-spacing').fill('1.2');
 await overlay.waitForFunction(()=>getComputedStyle(document.querySelector('[data-part=title]')).letterSpacing==='1.2px');
 assert.equal(await overlay.locator('[data-part=title]').evaluate(e=>getComputedStyle(e).fontWeight),'400');await page.locator('#we-live').uncheck();
 const downloading=page.waitForEvent('download');await page.locator('#we-export').click();const exported=await downloading;const json=JSON.parse(fs.readFileSync(await exported.path(),'utf8'));
 assert.equal(Object.keys(json.font_data).length,4);assert(!json.id);
 for(const f of json.fonts)assert(json.font_data[f.id].startsWith('data:font/'+f.format+';base64,'));
 await page.locator('#import-widget').setInputFiles({name:'Portable-font-widget.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(json))});
 await page.locator('#we-save-new').click();await page.waitForFunction(()=>state.settings.widget_presets.length===2);
 assert.notEqual(await page.evaluate(()=>widgetDraft.id),first);
 await page.locator('#we-part').selectOption('title');await page.locator('#we-font-remove').click();await page.locator('#we-save').click();await page.waitForFunction(()=>!widgetDirty);
 const presets=await page.evaluate(()=>state.settings.widget_presets);assert.equal(presets[0].fonts.length,4);assert.equal(presets[1].fonts.length,3);assert.equal(presets[1].elements.title.font,'system');
 await page.locator('#we-font-upload').setInputFiles({name:'invalid.ttf',mimeType:'font/ttf',buffer:Buffer.from('not a font')});
 await page.waitForFunction(()=>document.body.textContent.includes('This font could not be read'));assert.equal(await page.evaluate(()=>widgetDraft.fonts.length),3);
 // Exported JSON may contain fonts, never a remote font URL.
 const unsafe=structuredClone(json);unsafe.font_data[unsafe.fonts[0].id]='https://example.invalid/font.ttf';
 await page.locator('#import-widget').setInputFiles({name:'unsafe.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(unsafe))});await page.waitForFunction(()=>document.body.textContent.includes('Invalid embedded font data'));assert.equal(await page.evaluate(()=>widgetDraft.fonts.length),3);
 await page.reload();await page.locator('[data-nav=widgets]').click();await page.locator('[data-preset-edit="'+first+'"]').click();
 await page.waitForFunction(()=>document.querySelector('#we-preview').dataset.fontStatus==='loaded');assert.equal(await page.evaluate(()=>widgetDraft.fonts.length),4);
 await overlay.screenshot({path:path.join(root,'build/NextUp-custom-fonts-preview.png')});assert.deepEqual(errors,[]);
 console.log('PASS: TTF/OTF/WOFF/WOFF2 upload, saved font serving, four independent text fonts, live overlay weight/spacing, embedded export/import, copy preserves original, removal fallback, invalid font rejection, external URL rejection, reload.');
 }finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
