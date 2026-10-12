/* Exercise actual title geometry and browser animation, including resize and cleanup. */
const {chromium}=require('playwright'),path=require('path'),fs=require('fs'),assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.NEXTUP_TEST_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote']});
 try{
 const page=await browser.newPage({viewport:{width:900,height:300}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.setContent('<style>body{margin:0}#widget{width:900px}</style><div id="widget"></div>');
 await page.addScriptTag({path:path.resolve(__dirname,'../studio/static/widget-renderer.js')});
 const preset=process.env.NEXTUP_MIFFY_WIDGET?JSON.parse(fs.readFileSync(process.env.NEXTUP_MIFFY_WIDGET)):null;
 await page.evaluate(p=>{window.preset=p||{...NextUpWidget.defaults(),colors:{bg:'#101329',text:'#fff7eb'},equalizer:false};window.showTitle=title=>NextUpWidget.render(document.querySelector('#widget'),window.preset,{track:{title,artists:['Timecop1983'],duration:240},requester:'MoonWatcher'},[],window.preset.background_data||'');showTitle('Midnight Drive')},preset);
 await page.waitForTimeout(100);assert.equal(await page.locator('.wd-title-text').evaluate(e=>e.getAnimations().length),0);
 const long='Midnight Drive — A Journey Beyond the Moon and Stars (Extended Night Sky Edition)';
 await page.evaluate(t=>showTitle(t),long);await page.waitForFunction(()=>document.querySelector('.wd-title-text').getAnimations().length===1);
 assert.equal(await page.locator('[data-part=title]').getAttribute('title'),long);
 await page.evaluate(()=>{window.text=document.querySelector('.wd-title-text');window.scroller=text.getAnimations()[0]});
 await page.waitForTimeout(2200);assert(await page.evaluate(()=>new DOMMatrix(getComputedStyle(text).transform).m41<0));
 await page.evaluate(()=>{scroller.pause();const k=scroller.effect.getKeyframes(),d=scroller.effect.getTiming().duration;scroller.currentTime=d*(k[2].offset+k[3].offset)/2});
 assert(await page.evaluate(()=>Math.abs(text.getBoundingClientRect().right-text.parentElement.getBoundingClientRect().right)<1),'the ending must be completely visible');
 if(process.env.NEXTUP_SCROLL_PREVIEW)await page.screenshot({path:process.env.NEXTUP_SCROLL_PREVIEW});
 await page.evaluate(()=>scroller.currentTime=scroller.effect.getTiming().duration+500);
 assert(await page.evaluate(()=>Math.abs(new DOMMatrix(getComputedStyle(text).transform).m41)<.1),'pause at the start of the next pass');
 await page.evaluate(()=>text.parentElement.style.width=(text.scrollWidth+20)+'px');await page.waitForFunction(()=>text.getAnimations().length===0);
 await page.evaluate(()=>text.parentElement.style.width='260px');await page.waitForFunction(()=>text.getAnimations().length===1);
 const width=await page.evaluate(()=>text.scrollWidth);await page.evaluate(()=>text.parentElement.style.fontSize='42px');await page.waitForFunction(w=>text.scrollWidth>w,width);
 await page.waitForFunction(()=>{const a=text.getAnimations()[0];return a&&a.effect.getKeyframes()[2].transform===`translateX(-${text.scrollWidth-text.parentElement.clientWidth}px)`});
 await page.emulateMedia({reducedMotion:'reduce'});await page.waitForFunction(()=>text.getAnimations().length===0);
 await page.evaluate(()=>text.parentElement.scrollLeft=text.scrollWidth);assert(await page.evaluate(()=>Math.abs(text.getBoundingClientRect().right-text.parentElement.getBoundingClientRect().right)<1));
 await page.emulateMedia({reducedMotion:'no-preference'});await page.waitForFunction(()=>text.getAnimations().length===1);
 await page.evaluate(()=>{window.oldText=text;window.oldAnimation=text.getAnimations()[0];showTitle('New Song')});
 await page.waitForTimeout(100);assert(await page.evaluate(()=>!oldText.isConnected&&oldAnimation.playState==='idle'&&document.querySelector('.wd-title-text').getAnimations().length===0));
 assert.deepEqual(errors,[]);console.log('PASS: fitting titles, actual sideways motion, full ending, pause/return, width/font changes, reduced motion/manual scroll, track reset and animation cleanup.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
