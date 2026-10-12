// Real Chromium messaging/injection against a local fixture at the YouTube origin.
// No YouTube request, account, or desktop pairing credential is used.
const {chromium}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'nextup-extension-'));
 const extension=path.join(dir,'extension');fs.cpSync(path.join(__dirname,'../chrome-extension'),extension,{recursive:true});
 // Simulate an already-open tab that never received its declarative script.
 const manifest=JSON.parse(fs.readFileSync(path.join(extension,'manifest.json')));delete manifest.content_scripts;
 fs.writeFileSync(path.join(extension,'manifest.json'),JSON.stringify(manifest));
 let browser;
 try{
  browser=await chromium.launchPersistentContext(path.join(dir,'profile'),{
   executablePath:process.env.CHROMIUM_PATH,headless:true,ignoreDefaultArgs:['--disable-extensions'],
   args:['--no-sandbox',`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]
  });
  await browser.route('https://www.youtube.com/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><html><body><video class="html5-main-video"></video></body></html>'}));
  const page=await browser.newPage();await page.goto('https://www.youtube.com/watch?v=abcdefghijk');
  const worker=browser.serviceWorkers()[0]||await browser.waitForEvent('serviceworker');
  const result=await worker.evaluate(async()=>{
   const tabs=await chrome.tabs.query({url:'https://www.youtube.com/*'});tabId=tabs[0].id;
   let initiallyMissing=false;try{await chrome.tabs.sendMessage(tabId,{type:'ping'},{frameId:0})}catch{initiallyMissing=true}
   const repaired=await attachPlayer(true);
   const ping=await chrome.tabs.sendMessage(tabId,{type:'ping'},{frameId:0});
   const repairedAgain=await attachPlayer(true);
   const pause=await chrome.tabs.sendMessage(tabId,{type:'tick',managed:null,command:{seq:'pause',action:'pause'}},{frameId:0});
   return {initiallyMissing,repaired,ping,repairedAgain,pause};
  });
  assert.equal(result.initiallyMissing,true);assert.equal(result.repaired,true);assert.equal(result.ping.version,12);
  assert.equal(result.repairedAgain,true);assert.equal(result.pause.ok,true);
  console.log('PASS: real Chromium missing-script recovery, ping, idempotent reinjection and pause acknowledgement');
 }finally{if(browser)await browser.close();fs.rmSync(dir,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
