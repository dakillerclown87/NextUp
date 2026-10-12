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

 context.setDefaultTimeout(15000);
 async function select(part){await page.locator('#we-part').selectOption(part);}
 async function geometry(){return page.evaluate(()=>structuredClone(widgetPart()));}
 async function drag(dir,dx,dy,shift=false){
  const h=page.locator('.wd-gizmo [data-resize='+dir+']');await h.scrollIntoViewIfNeeded();const b=await h.boundingBox();
  const x=b.x+b.width/2+(dir.includes('e')?-3:dir.includes('w')?3:0),y=b.y+b.height/2+(dir.includes('s')?-3:dir.includes('n')?3:0);
  await page.mouse.move(x,y);if(shift)await page.keyboard.down('Shift');await page.mouse.down();await page.mouse.move(x+dx,y+dy,{steps:6});await page.mouse.up();if(shift)await page.keyboard.up('Shift');
 }
 // Every visible component has mouse resize controls, including tiny progress bars.
 for(const part of ['art','brand','title','artist','requester','progress','time','equalizer']){
  await select(part);assert.equal(await page.locator('.wd-gizmo [data-resize]').count(),8);const before=await geometry();await drag('e',-18,0);const after=await geometry();assert(after.w<before.w,part+' width');assert.equal(after.h,before.h);
 }
 await select('art');const art=await geometry();await drag('se',40,40,true);const larger=await geometry();assert(larger.w>art.w);assert(Math.abs(larger.w/larger.h-art.w/art.h)<.001);
 await select('title');const text=await geometry();await drag('se',-25,-12);assert((await geometry()).size<text.size);
 // Escape cancels an in-progress edit without saving its temporary dimensions.
 const beforeCancel=await geometry(),h=await page.locator('[data-resize=e]').boundingBox();await page.mouse.move(h.x+h.width/2,h.y+h.height/2);await page.mouse.down();await page.mouse.move(h.x-50,h.y+h.height/2);await page.keyboard.press('Escape');await page.mouse.up();assert.deepEqual(await geometry(),beforeCancel);
 // Mouse editing also works at a narrower window size.
 await page.setViewportSize({width:850,height:900});await select('art');const narrow=await geometry();await drag('w',20,0);assert((await geometry()).x>narrow.x);
 await page.locator('#we-edit-background').click();const bg=await geometry();await drag('se',-130,-60);const smaller=await geometry();assert(smaller.w<bg.w&&smaller.h<bg.h);
 const img=page.locator('#we-preview .wd-background');const ib=await img.boundingBox();await page.mouse.move(ib.x+40,ib.y+40);await page.mouse.down();await page.mouse.move(ib.x+65,ib.y+60,{steps:5});await page.mouse.up();const moved=await geometry();assert(moved.x>smaller.x&&moved.y>smaller.y);
 await page.mouse.move(ib.x+70,ib.y+70);await page.mouse.wheel(0,-120);await page.waitForFunction(w=>widgetDraft.background.rect.w>w,moved.w);const zoomed=await geometry();
 await page.locator('#we-save').click();await page.waitForFunction(()=>!widgetDirty);const saved=await page.evaluate(()=>structuredClone(widgetDraft));assert.deepEqual(saved.background.rect,zoomed);
 // Preview is an in-app dialog showing persisted data with no editor handles.
 await page.locator('#we-preview-saved').click();await page.waitForSelector('#widget-saved-preview[open]');const frame=page.frameLocator('#widget-saved-preview iframe');await frame.locator('.wd-background').waitFor();
 assert.equal(await frame.locator('.wd-gizmo').count(),0);assert(Math.abs(await frame.locator('.wd-background').evaluate(e=>parseFloat(e.style.width))-zoomed.w)<.01);assert.equal(context.pages().length,1);
 await page.getByRole('button',{name:'Close preview',exact:true}).click();await page.waitForSelector('#widget-saved-preview',{state:'detached'});assert.equal(await page.locator('#widget-saved-preview').count(),0);
 await page.reload();await page.locator('[data-nav=widgets]').click();await page.locator('[data-preset-preview="'+first+'"]').click();await page.waitForSelector('#widget-saved-preview[open]');await page.keyboard.press('Escape');await page.waitForSelector('#widget-saved-preview',{state:'detached'});
 await page.locator('[data-preset-edit="'+first+'"]').click();assert.deepEqual(await page.evaluate(()=>widgetDraft.background.rect),zoomed);
 await page.locator('#we-edit-background').click();await page.locator('#we-reset-background').click();assert.deepEqual(await geometry(),{x:0,y:0,w:800,h:300});await page.locator('#we-save-new').click();await page.waitForFunction(()=>state.settings.widget_presets.length===2);assert.deepEqual(await page.evaluate(id=>state.settings.widget_presets.find(p=>p.id===id).background.rect,first),zoomed);
 await select('art');await page.locator('#we-preview').screenshot({path:path.join(root,'build/NextUp-resize-editor.png')});await page.locator('[data-edit-widget=queue]').click();await select('queue');const list=await geometry();await drag('s',0,-30);assert((await geometry()).h<list.h);await page.locator('#we-save-new').click();await page.waitForFunction(()=>state.settings.widget_presets.length===3);await page.locator('#we-preview-saved').click();await page.frameLocator('#widget-saved-preview iframe').locator('.wd-queue-row').first().waitFor();await page.getByRole('button',{name:'Close preview',exact:true}).click();assert.deepEqual(errors,[]);
 console.log('PASS: eight handle directions available, all element types resize, aspect lock, text scaling, Escape cancel, narrow viewport, background move/resize/zoom/reset, save-copy isolation, persistence, and in-app saved previews from both entry points.');
 }finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
