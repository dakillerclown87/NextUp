'use strict';
const ext=globalThis.browser || globalThis.chrome;
const status=document.getElementById('status');
async function action(action){try{const r=await ext.runtime.sendMessage({action,code:document.getElementById('code').value});status.textContent=r.error||r.status;if(action==='pair'&&!r.error)document.getElementById('code').value=''}catch{status.textContent='Could not contact the extension. Reload it from your browser’s Extensions page.'}}
for(const id of ['pair','open','select','repair','connect','disconnect'])document.getElementById(id).onclick=()=>action(id);
action('status');
setInterval(()=>action('status'),2000);
