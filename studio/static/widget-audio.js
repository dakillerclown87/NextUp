/* Shared level stream for the editor, saved previews and OBS browser sources. */
'use strict';
window.NextUpAudio=(()=>{
 let socket=null,address='',retry=null,mode='animation',last=0,levels=Array(32).fill(0),previous=performance.now();
 function connect(base){
  const url=new URL('/audio',base),source=new URL(base);url.searchParams.set('key',source.searchParams.get('key')||'');url.protocol=url.protocol==='https:'?'wss:':'ws:';
  if(address===url.href&&socket)return;address=url.href;clearTimeout(retry);
  if(socket){socket.onclose=null;socket.close()}socket=new WebSocket(address);
  socket.onmessage=e=>{try{const d=JSON.parse(e.data);if(!['animation','application'].includes(d.mode)||!Array.isArray(d.levels)||d.levels.length!==32)return;mode=d.mode;levels=d.levels.map(v=>Number.isFinite(v)?Math.max(0,Math.min(1,v)):0);last=performance.now();}catch{}};
  socket.onclose=()=>{socket=null;last=0;retry=setTimeout(()=>connect(base),2000)};
  socket.onerror=()=>socket?.close();
 }
 const artworkCache=new Map();
 function artworkPalette(art){
  const url=paletteURL(art);if(!art||!url)return Promise.resolve([]);
  const cached=artworkCache.get(url);if(cached&&cached.expires>performance.now())return cached.promise;
  if(artworkCache.size>=64)artworkCache.delete(artworkCache.keys().next().value);
  const entry={expires:performance.now()+600000};
  entry.promise=fetch(url,{signal:AbortSignal.timeout(6500)}).then(r=>r.ok?r.json():null).then(d=>Array.isArray(d?.colors)&&d.colors.length>=2&&d.colors.length<=8&&d.colors.every(c=>/^#[a-f0-9]{6}$/i.test(c))?d.colors:[]).catch(()=>[]).then(colors=>{if(!colors.length)entry.expires=performance.now()+30000;return colors});
  artworkCache.set(url,entry);return entry.promise;
 }
 const rgb=c=>[1,3,5].map(i=>parseInt(c.slice(i,i+2),16));
 const hex=c=>'#'+c.map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join('');
 const blend=(a,b,t)=>hex(rgb(a).map((v,i)=>v+(rgb(b)[i]-v)*t));
 function spread(colors){return Array.from({length:8},(_,i)=>{const x=i*(colors.length-1)/7;return blend(colors[Math.floor(x)],colors[Math.ceil(x)],x%1)})}
 function equalizerColors(group,now){
  const css=getComputedStyle(group),valid=(v,f)=>/^#[a-f0-9]{6}$/i.test(v)?v:f;
  const a=valid(css.getPropertyValue('--accent').trim(),'#28d8ef'),b=valid(css.getPropertyValue('--accent2').trim(),'#af71f0');
  const fallback=spread([a,b]),art=group.dataset.eqArt||'',source=group.dataset.eqColorSource||'custom',key=JSON.stringify([source,art,a,b,paletteURL(art)]);
  let state=group._eqColors;if(!state)state=group._eqColors={current:fallback,from:fallback,to:fallback,at:now,key:null};
  if(state.key!==key){
   state.key=key;state.from=state.current;state.to=fallback;state.at=now;
   if(source==='artwork'&&art)artworkPalette(art).then(colors=>{if(state.key!==key||!group.isConnected)return;state.from=state.current;state.to=colors.length?spread(colors):fallback;state.at=performance.now()});
  }
  const u=matchMedia('(prefers-reduced-motion: reduce)').matches?1:Math.max(0,Math.min(1,(now-state.at)/650)),t=u*u*(3-2*u);
  state.current=state.from.map((c,i)=>blend(c,state.to[i],t));return state.current;
 }
 function colorStops(gradient,colors){colors.forEach((c,i)=>gradient.addColorStop(i/(colors.length-1),c))}
 function circular(group,bands,now,colors){
  let canvas=group.querySelector('canvas');if(!canvas){group._barMarkup=group.innerHTML;group.replaceChildren();canvas=document.createElement('canvas');canvas.setAttribute('aria-label','Circular audio visualizer');canvas.style.cssText='display:block;width:100%;height:100%;object-fit:contain';group.append(canvas)}
  const rect=group.getBoundingClientRect(),w=Math.max(1,Math.round(rect.width)),h=Math.max(1,Math.round(rect.height)),scale=Math.min(devicePixelRatio||1,2);if(canvas.width!==Math.round(w*scale)||canvas.height!==Math.round(h*scale)){canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale)}
  const g=canvas.getContext('2d');g.setTransform(scale,0,0,scale,0,0);g.clearRect(0,0,w,h);const size=Math.min(w,h),cx=w/2,cy=h/2,r=size*.31,style=group.dataset.eqStyle,css=getComputedStyle(group),a=css.getPropertyValue('--accent').trim()||'#28d8ef',b=css.getPropertyValue('--accent2').trim()||'#af71f0',gradient=g.createLinearGradient(cx-r,cy-r,cx+r,cy+r);colorStops(gradient,colors);g.strokeStyle=gradient;g.fillStyle=gradient;g.lineCap='round';
  const playing=!!group.closest('.playing'),reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;const level=i=>{if(reduced)return .12;if(mode==='application'){const x=(i%1+1)%1*31,lo=Math.floor(x);return bands[lo]+(bands[Math.min(31,lo+1)]-bands[lo])*(x-lo)}return playing?.25+.22*Math.sin(i*19+now/440)+.18*Math.sin(i*39-now/620):.04};
  if(style==='circle-dots'||style==='particle-sphere'){
   const sphere=style==='particle-sphere',count=sphere?112:180,base=size*.295;
   // A periodic sampling seam prevents a jump between the first and last bars.
   const sample=t=>{const x=((t%1+1)%1)*32,lo=Math.floor(x),f=x-lo;return mode==='application'?bands[lo%32]*(1-f)+bands[(lo+1)%32]*f:Math.max(0,level(t))};
   const energy=bands.reduce((sum,v)=>sum+v,0)/32;
   const dot=(x,y,radius)=>{g.beginPath();g.arc(x,y,radius,0,Math.PI*2);g.fill()};
   g.lineWidth=Math.max(.65,size*(sphere?.006:.002));
   for(let i=0;i<count;i++){
    const t=i/count,angle=t*Math.PI*2-Math.PI/2,cos=Math.cos(angle),sin=Math.sin(angle);
    const v=reduced?.12:sample(t),detail=.65+.35*Math.pow(Math.sin(i*2.39996),2);
    const len=size*(.004+.175*Math.pow(Math.max(0,v),.8)*detail);
    g.globalAlpha=.9;g.beginPath();g.moveTo(cx+cos*base,cy+sin*base);g.lineTo(cx+cos*(base+len),cy+sin*(base+len));g.stroke();
    if(!sphere){g.globalAlpha=1;dot(cx+cos*(base+len),cy+sin*(base+len),Math.max(.7,size*.0027))}
    g.globalAlpha=sphere?.65:.48;dot(cx+cos*(base-size*.018),cy+sin*(base-size*.018),Math.max(.65,size*.0021));
   }
   if(sphere){
    // Equal-area points on a 3D sphere, rotated and perspective projected.
    // Keep the geometry deterministic; silence stops rotation rather than inventing beats.
    const active=!reduced&&(mode==='application'?energy>.006:playing);
    const state=group._sphere||(group._sphere={phase:0,last:now});
    if(active)state.phase+=Math.min(.1,(now-state.last)/1000)*(.18+(mode==='application'?energy:.25)*.65);state.last=now;
    const phase=reduced?0:state.phase,points=[],n=720,rad=base*.84;
    for(let i=0;i<n;i++){
     const y=1-2*(i+.5)/n,lat=Math.sqrt(1-y*y),angle=i*2.3999632297+phase;
     const x=Math.cos(angle)*lat,z=Math.sin(angle)*lat;
     const yy=y*Math.cos(.32)-z*Math.sin(.32),zz=y*Math.sin(.32)+z*Math.cos(.32);
     const band=reduced?0:sample(i/n),ripple=active?1+.045*band*Math.sin(i*.19+phase*9):1;
     const depth=2.8/(2.8-zz*.3);points.push({x:cx+x*rad*depth*ripple,y:cy+yy*rad*depth*ripple,z:zz});
    }
    points.sort((p,q)=>p.z-q.z);
    for(const p of points){g.globalAlpha=.12+.73*(p.z+1)/2;dot(p.x,p.y,Math.max(.45,size*(.0009+.0012*(p.z+1)/2)))}
   }
   g.globalAlpha=1;
  }
  else if(style==='circle-bars'){g.lineWidth=Math.max(1,size*.009);for(let i=0;i<72;i++){const angle=i/72*Math.PI*2-Math.PI/2,len=size*(.015+.15*Math.max(0,level(i/72)));g.beginPath();g.moveTo(cx+Math.cos(angle)*r,cy+Math.sin(angle)*r);g.lineTo(cx+Math.cos(angle)*(r+len),cy+Math.sin(angle)*(r+len));g.stroke()}}
  else{const lobes=style==='orb'?2:1;for(let layer=0;layer<lobes;layer++){const points=[];for(let i=0;i<128;i++){const angle=i/128*Math.PI*2,live=Math.max(0,level(i/128)),wave=style==='orb'&&!reduced&&playing?Math.sin(angle*3+now/1700+layer*2)*size*.022:0,rad=r+live*size*(style==='orb'?.14:.13)+wave;points.push([cx+Math.cos(angle)*rad,cy+Math.sin(angle)*rad])}g.beginPath();g.moveTo((points[127][0]+points[0][0])/2,(points[127][1]+points[0][1])/2);for(let i=0;i<128;i++){const p=points[i],next=points[(i+1)%128];g.quadraticCurveTo(p[0],p[1],(p[0]+next[0])/2,(p[1]+next[1])/2)}g.closePath();g.globalAlpha=style==='orb'?.5:.95;g.lineWidth=style==='orb'?size*.035:Math.max(1,size*.006);g.stroke();}g.globalAlpha=1}
 }
 // LED cells stay on a fixed grid. Levels change illumination, never cell geometry.
 function led(group,bands,now,colors){
  let canvas=group.querySelector('canvas');
  if(!canvas){group._barMarkup=group.innerHTML;group.replaceChildren();canvas=document.createElement('canvas');canvas.style.cssText='display:block;width:100%;height:100%;object-fit:contain';group.append(canvas)}
  canvas.setAttribute('aria-label','LED audio equalizer');
  const rect=group.getBoundingClientRect(),w=Math.max(1,Math.round(rect.width)),h=Math.max(1,Math.round(rect.height)),scale=Math.min(devicePixelRatio||1,2);
  if(canvas.width!==Math.round(w*scale)||canvas.height!==Math.round(h*scale)){canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale)}
  const g=canvas.getContext('2d');g.setTransform(scale,0,0,scale,0,0);g.clearRect(0,0,w,h);
  const css=getComputedStyle(group),gradient=g.createLinearGradient(0,h,0,0);
  colorStops(gradient,colors);g.fillStyle=gradient;
  const columns=Math.max(1,Math.min(24,Math.floor(w/6))),pitchX=w/columns,gapX=pitchX*.24,cellW=pitchX-gapX;
  const rows=Math.max(1,Math.min(32,Math.floor(h/Math.max(4,cellW*.6)))),pitchY=h/rows,cellH=pitchY*.68;
  const playing=!!group.closest('.playing'),reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  for(let col=0;col<columns;col++){
   let level=0;
   if(reduced)level=.25;
   else if(mode==='application'){
    const lo=Math.floor(col*32/columns),hi=Math.max(lo+1,Math.floor((col+1)*32/columns));
    for(let i=lo;i<hi;i++)level=Math.max(level,bands[i]);
   }else if(playing)level=.36+.24*Math.sin(col*.57+now/470)+.19*Math.sin(col*1.21-now/740);
   level=Math.max(0,Math.min(1,level))*rows;
   for(let row=0;row<rows;row++){
    const light=Math.max(0,Math.min(1,level-row));g.globalAlpha=.07+.93*light;
    g.fillRect(col*pitchX+gapX/2,h-(row+1)*pitchY+(pitchY-cellH)/2,cellW,cellH);
   }
  }
  g.globalAlpha=1;group.dataset.audioMode=mode;
 }
 function paletteURL(art){if(!address)return null;const url=new URL(address);url.protocol=url.protocol==='wss:'?'https:':'http:';url.pathname='/art-palette';url.searchParams.set('art',art);return url.href}

 const responseDefaults={sensitivity:1,attack_ms:45,release_ms:220,bass:0};
 function responseBands(group,dt,now){
  const key=group.dataset.eqResponse||'';
  let state=group._eqResponse;
  if(!state)state=group._eqResponse={key:null,options:responseDefaults,bands:Array(32).fill(0)};
  if(state.key!==key){
   let input={};try{input=JSON.parse(key)||{}}catch{}
   const clamp=(name,lo,hi)=>Number.isFinite(input[name])?Math.max(lo,Math.min(hi,input[name])):responseDefaults[name];
   state.options={sensitivity:clamp('sensitivity',.25,4),attack_ms:clamp('attack_ms',5,250),release_ms:clamp('release_ms',40,1000),bass:clamp('bass',0,200)};state.key=key;
  }
  const p=state.options;
  for(let i=0;i<32;i++){
   // The captured FFT bands run from low to high frequency. Taper bass gain over the first eight.
   const gain=p.sensitivity*(1+p.bass/100*Math.max(0,1-i/8));
   const target=mode==='application'&&now-last<400?Math.min(1,levels[i]*gain):0;
   const tau=(target>state.bands[i]?p.attack_ms:p.release_ms)/1000;
   state.bands[i]+=(target-state.bands[i])*(1-Math.exp(-dt/tau));
  }
  return state.bands;
 }
 function animate(now){
  const dt=Math.min(.1,(now-previous)/1000);previous=now;
  for(const group of document.querySelectorAll('.wd-bars,.bars')){
   const smoothed=responseBands(group,dt,now),colors=equalizerColors(group,now);
   if(group.dataset.eqStyle==='led'){led(group,smoothed,now,colors);continue}
   if(['circle-bars','circle-wave','orb','circle-dots','particle-sphere'].includes(group.dataset.eqStyle)){circular(group,smoothed,now,colors);continue}
   if(group.querySelector('canvas')){group.innerHTML=group._barMarkup||Array.from({length:24},()=>'<i></i>').join('');delete group._barMarkup}
   const bars=[...group.querySelectorAll('i')];group.dataset.audioMode=mode;
   const colorBackground='linear-gradient(0deg,'+colors.join(',')+')';
   bars.forEach((bar,i)=>{
    if(bar._eqColorBackground!==colorBackground){bar.style.background=colorBackground;bar._eqColorBackground=colorBackground}
    if(mode==='application'){
     if(bar.dataset.decorativeHeight===undefined){bar.dataset.decorativeHeight=bar.style.height;bar.dataset.decorativeDuration=bar.style.animationDuration;bar.dataset.decorativeDelay=bar.style.animationDelay;bar.style.animation='none';bar.style.height='100%';}
     const lo=Math.floor(i*32/bars.length),hi=Math.max(lo+1,Math.floor((i+1)*32/bars.length));let value=0;for(let n=lo;n<hi;n++)value=Math.max(value,smoothed[n]);
     bar.style.transform='scaleY('+Math.max(.015,value).toFixed(4)+')';
    }else if(bar.dataset.decorativeHeight!==undefined){bar.style.height=bar.dataset.decorativeHeight;bar.style.animation='';bar.style.animationDuration=bar.dataset.decorativeDuration;bar.style.animationDelay=bar.dataset.decorativeDelay;bar.style.transform='';delete bar.dataset.decorativeHeight;delete bar.dataset.decorativeDuration;delete bar.dataset.decorativeDelay;}
   });
  }
  requestAnimationFrame(animate);
 }
 requestAnimationFrame(animate);
 window.addEventListener('pagehide',()=>{clearTimeout(retry);if(socket){socket.onclose=null;socket.close();socket=null}address=''});
 return {connect,paletteURL,artworkPalette};
})();
