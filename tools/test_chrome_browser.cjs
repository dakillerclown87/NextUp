/* Real extension + local NextUp integration, with a simulated YouTube page.
   Set NEXTUP_TEST_PYTHON and NEXTUP_TEST_CHROMIUM; install Playwright. */
const {chromium}=require('playwright'),fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const root=path.resolve(__dirname,'..');
const source=`import asyncio\nimport studio.server as server\nfrom unittest.mock import AsyncMock\noriginal=server.Studio\ndef create(*a,**k):\n s=original(*a,**k)\n s.settings.save({'youtube_player_mode':'chrome','block_explicit':False})\n async def resolve(ident):\n  return {'provider':'youtube','id':ident,'title':'Browser test song','artists':['Test artist'],'artist_ids':['test'],'duration':30,'explicit':False,'url':'https://www.youtube.com/watch?v='+ident,'art':''}\n s.youtube.resolve=resolve\n return s\nserver.Studio=create\nasyncio.run(server.run(open_browser=False))\n`;
(async()=>{let proc,context;const home=fs.mkdtempSync(path.join(os.tmpdir(),'nextup-chrome-'));try{
 proc=spawn(process.env.NEXTUP_TEST_PYTHON||'python',['-u','-c',source],{cwd:root,env:{...process.env,NEXTUP_HOME:home}});let err='';proc.stderr.on('data',d=>err+=d);
 const url=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('Server startup: '+err)),15000);proc.stdout.on('data',d=>{out+=d;const match=out.match(/Dashboard URL: (http[^\s]+)/);if(match){clearTimeout(timer);resolve(match[1])}});proc.on('exit',c=>{clearTimeout(timer);reject(Error('Server exit '+c+err))})});
 context=await chromium.launchPersistentContext(path.join(home,'profile'),{executablePath:process.env.NEXTUP_TEST_CHROMIUM||undefined,headless:true,ignoreDefaultArgs:['--disable-extensions'],args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--autoplay-policy=no-user-gesture-required','--disable-extensions-except='+path.join(root,'chrome-extension'),'--load-extension='+path.join(root,'chrome-extension')]});
 const sw=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker',{timeout:10000}),id=new URL(sw.url()).host;
 // Thirty seconds of valid PCM silence, sufficient to exercise real media events.
 const wave=Buffer.alloc(44+8000*30*2);wave.write('RIFF');wave.writeUInt32LE(wave.length-8,4);wave.write('WAVEfmt ',8);wave.writeUInt32LE(16,16);wave.writeUInt16LE(1,20);wave.writeUInt16LE(1,22);wave.writeUInt32LE(8000,24);wave.writeUInt32LE(16000,28);wave.writeUInt16LE(2,32);wave.writeUInt16LE(16,34);wave.write('data',36);wave.writeUInt32LE(wave.length-44,40);
 await context.route('https://www.youtube.com/**',route=>{const u=new URL(route.request().url());const vid=u.searchParams.get('v')||'abcdefghijk';return route.fulfill({contentType:'text/html',body:`<!doctype html><title>YouTube test fixture</title><ytd-watch-flexy video-id="${vid}"><video class="html5-main-video" controls src="data:audio/wav;base64,${wave.toString('base64')}"></video></ytd-watch-flexy>`})});
 const app=await context.newPage();await app.goto(url);await app.waitForSelector('#open-player');await app.locator('[data-nav=connections]').click();await app.locator('#chrome-pair').click();const code=await app.locator('#chrome-code').inputValue();assert.equal(await app.locator('#chrome-code').getAttribute('type'),'password');
 const yt=await context.newPage();await yt.goto('https://www.youtube.com/watch?v=abcdefghijk');
 const popup=await context.newPage();await popup.goto('chrome-extension://'+id+'/popup.html');await popup.locator('#code').fill(code);await popup.locator('#pair').click();await popup.waitForFunction(()=>document.querySelector('#status').textContent.includes('Connected'));
 await yt.bringToFront();await popup.evaluate(()=>document.querySelector('#select').click());await popup.waitForFunction(()=>document.querySelector('#status').textContent.includes('selected'));
 await app.evaluate(()=>api('request',{url:'https://www.youtube.com/watch?v=abcdefghijk'}));await app.evaluate(()=>api('playback',{action:'resume'}));
 assert.equal(await yt.evaluate(()=>document.querySelector('video').paused),false);
 await app.evaluate(()=>api('playback',{action:'pause'}));assert.equal(await yt.evaluate(()=>document.querySelector('video').paused),true);
 await app.evaluate(()=>api('playback',{action:'resume'}));assert.equal(await yt.evaluate(()=>document.querySelector('video').paused),false);
 await yt.evaluate(()=>{document.querySelector('video').currentTime=29.8});
 await app.waitForFunction(async()=>!(await api('state')).queue.current,{},{timeout:15000});
 await app.evaluate(()=>api('request',{url:'https://www.youtube.com/watch?v=lmnopqrstuv'}));await app.evaluate(()=>api('playback',{action:'resume'}));await app.evaluate(()=>api('chrome-revoke',{}));
 await yt.waitForFunction(()=>document.querySelector('video').paused);
 const tokenSaved=await sw.evaluate(async()=>Boolean((await chrome.storage.local.get('token')).token));assert.equal(tokenSaved,true); // server revocation, not account credential exposure
 console.log('PASS: real extension pairing, chosen tab, page navigation, play/pause/resume acknowledgements, ended event, and revocation pause. YouTube page/media were simulated.');
 }finally{if(context)await context.close();if(proc){proc.kill('SIGINT');await new Promise(r=>{proc.once('exit',r);setTimeout(r,3000)})}fs.rmSync(home,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
