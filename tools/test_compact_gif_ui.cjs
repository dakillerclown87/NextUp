/* Compact launcher and GIF round trips through the real UI/server. Optional Miffy preset via NEXTUP_MIFFY_WIDGET. */
const {chromium}=require('playwright');
const {spawn,execFileSync}=require('child_process');
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
  const fixtureArt=async page=>page.route('https://preview.invalid/**',r=>r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#252e66"/><stop offset="1" stop-color="#846bb2"/></linearGradient></defs><rect width="200" height="200" fill="url(#g)"/><circle cx="100" cy="100" r="51" fill="#c4afe8"/><ellipse cx="100" cy="108" rx="78" ry="22" fill="none" stroke="#fbe5ac" stroke-width="9" transform="rotate(-25 100 100)"/><circle cx="30" cy="30" r="3" fill="white"/><circle cx="167" cy="48" r="2" fill="white"/></svg>'}));
  const page=await browser.newPage({viewport:{width:820,height:570}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await fixtureArt(page);await page.goto(url);await page.waitForSelector('.hero');


  assert.equal(await page.locator('body').getAttribute('data-compact'),'true');
  for(const width of [820,640]){await page.setViewportSize({width,height:570});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert((await page.locator('#sidebar').boundingBox()).width<=166);assert(await page.locator('#menu-toggle').isVisible());}
  await page.setViewportSize({width:820,height:570});await page.screenshot({path:path.join(root,'build/NextUp-compact22.png')});
  await page.locator('#compact-toggle').click();await page.waitForFunction(()=>document.body.dataset.compact==='false');
  await page.reload();await page.waitForFunction(()=>document.body.dataset.compact==='false');
  await page.locator('#compact-toggle').click();await page.waitForFunction(()=>document.body.dataset.compact==='true');
  await page.locator('#navigation [data-nav=widgets]').click();
  const overlay=await browser.newPage({viewport:{width:900,height:300}});await fixtureArt(overlay);
  if(process.env.NEXTUP_MIFFY_WIDGET){
   await page.locator('#import-widget').setInputFiles(process.env.NEXTUP_MIFFY_WIDGET);
   await page.waitForFunction(()=>widgetDraft.name==='Miffy Moonlight');
   await page.locator('#we-save-new').click();await page.waitForFunction(()=>state.settings.widget_presets.length===1);
   const overlayURL=await page.evaluate(()=>state.widgets.now+'&preset_id='+widgetDraft.id);
   await overlay.goto(overlayURL);await overlay.waitForSelector('.wd-star');
   await overlay.waitForFunction(()=>[...document.images].every(im=>im.complete));
   assert.equal(await overlay.locator('.wd-star').count(),18);
   const first=await overlay.locator('.wd-star').first().evaluate(e=>getComputedStyle(e).opacity);
   await overlay.waitForFunction(a=>getComputedStyle(document.querySelector('.wd-star')).opacity!==a,first);
   const hasClouds=JSON.parse(fs.readFileSync(process.env.NEXTUP_MIFFY_WIDGET)).background.clouds;
   if(hasClouds){
    assert.equal(await overlay.locator('.wd-cloud').count(),4);
    const cloud=await overlay.locator('.wd-cloud').first().elementHandle();
    const before=await cloud.evaluate(e=>getComputedStyle(e).transform);
    await overlay.waitForTimeout(1800);
    assert(await cloud.evaluate(e=>e.isConnected),'state polling should not restart the cloud animation');
    assert.notEqual(await cloud.evaluate(e=>getComputedStyle(e).transform),before);
    const saved=await page.evaluate(()=>api('widget-export',{id:widgetDraft.id}));assert.equal(saved.background.clouds,true);
    if(process.env.NEXTUP_MIFFY_FRAMES){
     fs.mkdirSync(process.env.NEXTUP_MIFFY_FRAMES,{recursive:true});
     await overlay.evaluate(()=>{window.previewAnimations=document.getAnimations().map(a=>{const t=a.currentTime;a.pause();return{a,t}})});
     for(let frame=0;frame<72;frame++){
      await overlay.evaluate(t=>window.previewAnimations.forEach(({a,t:start})=>a.currentTime=start+t),frame*1000/12);
      await overlay.screenshot({path:path.join(process.env.NEXTUP_MIFFY_FRAMES,String(frame).padStart(3,'0')+'.png')});
     }
     await overlay.evaluate(()=>window.previewAnimations.forEach(({a})=>a.play()));
    }
    await overlay.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await cloud.evaluate(e=>getComputedStyle(e).animationName),'none');
    await overlay.emulateMedia({reducedMotion:'no-preference'});
    assert.equal(await page.locator('#we-clouds, #we-stars').count(),0);
    assert.equal(await page.locator('#we-preview .wd-cloud').count(),4);
   }
   await overlay.screenshot({path:process.env.NEXTUP_MIFFY_PREVIEW||path.join(root,'build/Miffy-preview.png')});
  }
  const baseCount=await page.evaluate(()=>state.settings.widget_presets.length);
  let gifBytes=Buffer.from('R0lGODlhIAAgAIEAAP8iIgAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQAMgAAACwAAAAAIAAgAAAINQABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzIsaPHjyBDihxJsqTJkyhTqlzJUmRAACH5BAEyAAEALAAAAAAgACAAgSIi/wAAAAAAAAAAAAg1AAEIHEiwoMGDCBMqXMiwocOHECNKnEixosWLGDNq3Mixo8ePIEOKHEmypMmTKFOqXMlSZEAAOw==','base64');
  assert.equal(await page.locator('#we-stars, #we-clouds').count(),0);
  // A valid GIF with comments at the 20 MiB boundary exercises all transfer limits.
  if(process.env.NEXTUP_LARGE_GIF){
   let left=20*1024*1024-gifBytes.length-3;const chunks=[];
   while(left){let n=Math.min(255,left-1);if(left-n-1===1)n--;chunks.push(Buffer.from([n]),Buffer.alloc(n,65));left-=n+1;}
   gifBytes=Buffer.concat([gifBytes.subarray(0,-1),Buffer.from([0x21,0xfe]),...chunks,Buffer.from([0,0x3b])]);
   assert.equal(gifBytes.length,20*1024*1024);
  }
  await page.locator('#we-image').setInputFiles({name:'animation.gif',mimeType:'image/gif',buffer:gifBytes});
  await page.waitForFunction(()=>widgetDraft.background_data?.startsWith('data:image/gif'));
  await page.locator('#we-name').fill('GIF test');await page.locator('#we-save-new').click();
  await page.waitForFunction(n=>state.settings.widget_presets.length===n,baseCount+1);
  const exported=await page.evaluate(()=>api('widget-export',{id:widgetDraft.id}));
  assert.equal(exported.background_data,'data:image/gif;base64,'+gifBytes.toString('base64'));
  await page.locator('#import-widget').setInputFiles({name:'roundtrip.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(exported))});
  await page.waitForFunction(()=>widgetDraft.name==='GIF test'&&!widgetDraft.id);
  await page.locator('#we-save-new').click();await page.waitForFunction(n=>state.settings.widget_presets.length===n,baseCount+2);
  const gifURL=await page.evaluate(()=>state.widgets.now+'&preset_id='+widgetDraft.id);
  await overlay.goto(gifURL);await overlay.waitForSelector('.wd-background');
  const assetURL=await overlay.locator('.wd-background').getAttribute('src');
  const response=await overlay.request.get(new URL(assetURL,gifURL).href);assert(response.headers()['content-type'].startsWith('image/gif'));
  assert.equal(Buffer.compare(await response.body(),gifBytes),0);
  // Canvas drawImage can expose only a GIF's first frame. Sample the rendered page instead.
  const seen=new Set();
  for(let i=0;i<12&&seen.size<2;i++){
   const png=await overlay.screenshot({clip:{x:650,y:150,width:4,height:4}});
   const rgb=JSON.parse(execFileSync(process.env.NEXTUP_TEST_PYTHON||'python3',['-c','import sys,io,json;from PIL import Image;print(json.dumps(Image.open(io.BytesIO(sys.stdin.buffer.read())).convert("RGB").getpixel((1,1))))'],{input:png}).toString());
   if(rgb[0]>200&&rgb[2]<100)seen.add('red');if(rgb[2]>200&&rgb[0]<100)seen.add('blue');
   await overlay.waitForTimeout(160);
  }
  assert.deepEqual([...seen].sort(),['blue','red'],'GIF must render both animation frames');
  await page.reload();await page.locator('#navigation [data-nav=widgets]').click();assert.equal(await page.locator('[data-preset-card]').count(),baseCount+2);
  assert.deepEqual(errors,[]);console.log('PASS: compact defaults, 640px overflow, toggle persistence; optional Miffy import, star/cloud animation, persistence and reduced motion; GIF upload/save/export/reimport, MIME, exact bytes, both rendered animation frames and saved previews; removed animation controls and optional 20 MiB GIF transfer.');
 }finally{if(browser)await browser.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,1500)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
