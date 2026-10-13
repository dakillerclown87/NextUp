/* Shared, data-only renderer for the editor and OBS overlays. */
'use strict';
window.NextUpWidget=(()=>{
 const fontCache=new Map();
 const fontStacks={system:'Segoe UI,system-ui,sans-serif',sans:'Arial,Helvetica,sans-serif',serif:'Georgia,Times New Roman,serif',mono:'Consolas,Courier New,monospace'};
 const labels={art:'Album artwork',brand:'Heading / label',title:'Song title',artist:'Artist',requester:'Requester',progress:'Progress bar',time:'Song time',equalizer:'Equalizer',queue:'Queue list'};
 const cloudCss=`.wd-clouds{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:hidden}.wd-cloud{position:absolute;left:0;width:100%;height:24%;animation:wd-drift 64s linear infinite;will-change:transform;opacity:.72}.wd-cloud-far{height:18%;animation-duration:92s;animation-direction:reverse;opacity:.42}.wd-cloud-shape{display:block;width:34%;height:100%;background:radial-gradient(ellipse 22% 35% at 28% 53%,#e1d3f3aa 10%,#c3ade559 58%,#b6a0db00 100%),radial-gradient(ellipse 25% 42% at 48% 42%,#f0e4ffb3 5%,#d2bcea66 55%,#b6a0db00 100%),radial-gradient(ellipse 24% 32% at 69% 58%,#e0cef299 8%,#bba3dd55 58%,#b6a0db00 100%),radial-gradient(ellipse 38% 23% at 49% 69%,#c7b1e280 5%,#b19ad044 55%,#b6a0db00 100%);filter:blur(2px)}.wd-cloud:nth-child(2) .wd-cloud-shape{transform:scaleX(.85)}.wd-cloud-far .wd-cloud-shape{transform:scaleX(1.15)}@keyframes wd-drift{from{transform:translateX(-40%)}to{transform:translateX(110%)}}@media(prefers-reduced-motion:reduce){.wd-cloud{animation:none;transform:translateX(55%)}.wd-cloud-far{transform:translateX(8%)}}`;
 function clouds(){
  const layer=document.createElement('div');layer.className='wd-clouds';layer.setAttribute('aria-hidden','true');
  // Soft radial puffs fade to transparent on every edge; no closed flat-bottom path.
  layer.innerHTML=[{top:'84%',delay:-20},{top:'86%',delay:-52},{top:'0%',delay:-28,far:true},{top:'1%',delay:-71,far:true}].map(c=>`<div class="wd-cloud${c.far?' wd-cloud-far':''}" style="top:${c.top};animation-delay:${c.delay}s"><span class="wd-cloud-shape"></span></div>`).join('');
  return layer;
 }
 function backgroundEffects(stage,p){
  if(p.background.clouds)stage.append(clouds());
  if(p.background.stars){const stars=document.createElement('div');stars.className='wd-stars';stars.setAttribute('aria-hidden','true');stars.innerHTML=Array.from({length:18},(_,i)=>`<span class="wd-star" style="left:${4+(i*31)%93}%;top:${i%2?82+(i%4)*3:4+(i%5)*3}%;animation-delay:-${i*.61}s;animation-duration:${3+i%4}s">✦</span>`).join('');stage.append(stars)}
 }
 const css=`[data-eq-style=rounded] i{border-radius:99px}[data-eq-style=mirror]{align-items:center!important}[data-eq-style=mirror] i{transform-origin:center!important;border-radius:99px}.wd-horizon{background:transparent!important;border:0!important;overflow:visible!important}.wd-horizon:before{content:'';position:absolute;inset:18% 3%;border:1px solid var(--line);border-radius:28px;background:radial-gradient(ellipse at 95% 0%,#d7aa6630,transparent 65%),linear-gradient(120deg,var(--panel),var(--bg));box-shadow:inset 0 1px 0 #ffe7b025,0 12px 35px #0005}.wd-horizon:after{content:'';position:absolute;left:31%;right:8%;top:18%;height:1px;background:linear-gradient(90deg,transparent,var(--accent),transparent)}.wd-horizon [data-part=art]{box-shadow:0 5px 20px #0008;border:1px solid #ffe6b330;border-radius:12px}.wd-horizon [data-part=brand]{letter-spacing:5px!important;color:var(--accent)}.wd-horizon [data-part=progress]{box-shadow:0 0 12px #fbd89325}.wd-horizon [data-part=artist]{color:var(--accent2)}.wd-prism{background:radial-gradient(ellipse at 100% 0,color-mix(in srgb,var(--accent2) 17%,transparent),transparent 60%),radial-gradient(ellipse at 0 100%,color-mix(in srgb,var(--accent) 12%,transparent),transparent 55%),linear-gradient(120deg,var(--panel),var(--bg))!important;border-color:color-mix(in srgb,var(--accent) 40%,var(--line))!important;box-shadow:inset 0 0 0 1px #ffffff0a}.wd-prism:before{content:'';position:absolute;left:28%;right:4%;top:1px;height:2px;background:linear-gradient(90deg,transparent,var(--accent),var(--accent2),transparent);opacity:.7}.wd-prism [data-part=art]{border:1px solid #ffffff30;box-shadow:0 8px 30px #0008}.wd-prism [data-part=brand]{color:var(--muted);letter-spacing:4px!important}.wd-prism [data-part=progress]{box-shadow:0 0 14px color-mix(in srgb,var(--accent2) 15%,transparent)}.wd-fold-rail{position:absolute;left:0;right:0;top:calc(50% - 6px);height:12px;border-radius:20px;background:linear-gradient(90deg,var(--accent),var(--accent2));pointer-events:none}.wd-fold-dot{position:absolute;left:50%;top:50%;width:12px;height:12px;border-radius:50%;transform:translate(-50%,-50%);background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 0 18px color-mix(in srgb,var(--accent) 45%,transparent);pointer-events:none}.wd-fold-dot[hidden]{display:none}.wd-part[data-part=title]{text-overflow:clip!important}.wd-title-text{display:inline-block;width:max-content;white-space:nowrap;vertical-align:top;pointer-events:none}@media(prefers-reduced-motion:reduce){.wd-part[data-part=title].wd-title-overflow{overflow-x:auto;scrollbar-width:none}.wd-part[data-part=title]::-webkit-scrollbar{display:none}}.wd-space:not(.wd-edit) .wd-background{animation:wd-float 8s ease-in-out infinite;transform-origin:center}@keyframes wd-float{0%,100%{transform:scale(1.02) translateY(0)}50%{transform:scale(1.02) translateY(-3px)}}@media(prefers-reduced-motion:reduce){.wd-space:not(.wd-edit) .wd-background{animation:none}}.wd-stars{position:absolute;inset:0;pointer-events:none;overflow:hidden}.wd-star{position:absolute;color:#fff0c6;font-size:14px;text-shadow:0 0 6px #f9d787;animation:wd-twinkle 4s ease-in-out infinite;line-height:1}@keyframes wd-twinkle{0%,100%{opacity:.06;transform:scale(.35) rotate(0deg)}50%{opacity:1;transform:scale(1.3) rotate(15deg)}}@media(prefers-reduced-motion:reduce){.wd-star{animation:none;opacity:.6}}.wd-stage{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:24px;background:linear-gradient(130deg,var(--panel),var(--bg));color:var(--text);font-family:Segoe UI,system-ui,sans-serif;transform-origin:top left;box-sizing:border-box}.wd-background{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.wd-part{position:absolute;overflow:hidden;box-sizing:border-box;line-height:1.2}.wd-part[data-part=title]{font-weight:700;white-space:nowrap;text-overflow:ellipsis}.wd-part[data-part=artist]{color:var(--accent2);white-space:nowrap;text-overflow:ellipsis}.wd-part[data-part=brand]{letter-spacing:3px;color:var(--accent)}.wd-part[data-part=requester],.wd-part[data-part=time]{color:var(--muted)}.wd-part[data-part=art]{border-radius:16px;background:var(--bg);display:grid;place-items:center;color:var(--accent);font-size:60px}.wd-part img{width:100%;height:100%;object-fit:cover}.wd-part .fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:inherit}.wd-part[data-part=progress]{background:var(--line);border-radius:20px}.wd-part[data-part=time]{display:flex;justify-content:space-between}.wd-bars{display:flex;align-items:flex-end;gap:4px;height:100%;width:100%}.wd-bars i{flex:1;background:linear-gradient(0deg,var(--accent),var(--accent2));transform-origin:bottom;animation:wd-dance .9s ease-in-out infinite alternate;animation-play-state:paused}.playing .wd-bars i{animation-play-state:running}@keyframes wd-dance{from{transform:scaleY(.2)}to{transform:scaleY(.98)}}.wd-queue-row{display:flex;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}.wd-queue-row img{width:44px;height:44px;border-radius:8px}.wd-queue-row small{color:var(--muted);display:block;font-size:.7em}.wd-queue-row div{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.wd-edit .wd-part{cursor:move;touch-action:none;outline:1px dashed #ffffff55}.wd-edit .wd-selected{outline:2px solid var(--accent)}@media(prefers-reduced-motion:reduce){.wd-bars i{animation:none}}`;
 function style(){if(document.getElementById('wd-styles'))return;const el=document.createElement('style');el.id='wd-styles';el.textContent=css+cloudCss;document.head.append(el)}
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const time=s=>Math.floor((s||0)/60)+':'+String(Math.floor((s||0)%60)).padStart(2,'0');
 function defaults(layout='spectrum'){
  const part=(x,y,w,h,size=20)=>({x,y,w,h,size,visible:true});
  const elements=layout==='queue'?{brand:part(28,20,730,30,15),queue:part(28,65,738,400,24)}:{art:part(26,54,160,160),brand:part(212,30,530,24,14),title:part(212,68,548,46,34),artist:part(212,122,390,34,25),requester:part(212,164,390,25,16),progress:part(212,218,548,8),time:part(212,237,548,22,14),equalizer:part(638,126,122,72)};
  if(layout==='gradient'){elements.art.x=602;elements.title.w=540;elements.title.x=28;for(const k of ['brand','artist','requester','progress','time']){elements[k].x=28;elements[k].w=Math.min(elements[k].w,545)}elements.equalizer.visible=false}
  return {canvas:{width:800,height:layout==='queue'?500:300},elements,background:{image:'',opacity:.5,fit:'cover'}};
 }
 function loadFonts(host,p,fontUrl){
  const ids=new Set((p.fonts||[]).map(f=>f.id));
  for(const[id,item]of fontCache)if(!ids.has(id)){document.fonts.delete(item.face);fontCache.delete(id)}
  return Promise.all((p.fonts||[]).map(info=>{
   if(fontCache.has(info.id))return fontCache.get(info.id).promise;
   const url=p.font_data?.[info.id]||fontUrl?.(info);
   if(!url)return Promise.reject(Error('Font file is missing. Upload it again.'));
   const face=new FontFace('NextUpFont_'+info.id,'url('+JSON.stringify(url)+')');document.fonts.add(face);
   const promise=face.load().then(()=>face).catch(()=>{fontCache.delete(info.id);document.fonts.delete(face);throw Error('A custom font could not load. Upload a valid font file again.');});
   fontCache.set(info.id,{face,promise});return promise;
  }));
 }
 function scrollTitle(element){
  const text=document.createElement('span');text.className='wd-title-text';text.textContent=element.textContent;
  element.title=text.textContent;element.setAttribute('aria-label',text.textContent);element.replaceChildren(text);
  const motion=matchMedia('(prefers-reduced-motion: reduce)');let animation=null,lastDistance=-1,lastReduced=null;
  function update(){
   const distance=Math.max(0,text.scrollWidth-element.clientWidth),reduced=motion.matches;
   if(Math.abs(distance-lastDistance)<1&&lastReduced===reduced)return;
   lastDistance=distance;lastReduced=reduced;animation?.cancel();animation=null;element.scrollLeft=0;
   element.classList.toggle('wd-title-overflow',distance>1);
   if(distance<=1||reduced)return;
   const hold=1800,travel=Math.max(1500,distance/28*1000),duration=2*(hold+travel);
   animation=text.animate([
    {transform:'translateX(0)',offset:0},
    {transform:'translateX(0)',offset:hold/duration},
    {transform:`translateX(-${distance}px)`,offset:(hold+travel)/duration},
    {transform:`translateX(-${distance}px)`,offset:(2*hold+travel)/duration},
    {transform:'translateX(0)',offset:1}
   ],{duration,iterations:Infinity,easing:'linear'});
  }
  const observer=new ResizeObserver(update);observer.observe(element);observer.observe(text);motion.addEventListener('change',update);update();
  return ()=>{observer.disconnect();motion.removeEventListener('change',update);animation?.cancel()};
 }
 function render(host,p,current,items,imageUrl,edit=false,fontUrl=null){
  if(p.format==='nextup-widget-v3')return NextUpWidgetV3.render(host,p,current,items,imageUrl,edit,fontUrl);
  window.NextUpWidgetV3?.dispose(host);style();host._titleCleanup?.();host._titleCleanup=null;host.dataset.fontStatus='loading';loadFonts(host,p,fontUrl).then(()=>{host.dataset.fontStatus='loaded'}).catch(error=>{host.dataset.fontStatus='error';host.dispatchEvent(new CustomEvent('widget-font-error',{bubbles:true,detail:error.message}))});const t=current?.track||{title:'Nothing playing',artists:[],duration:0};host.replaceChildren();host.style.aspectRatio=p.canvas.width+'/'+p.canvas.height;
  const stage=document.createElement('div');stage.className='wd-stage'+(edit?' wd-edit':'')+(p.background.stars?' wd-space':'')+(p.presentation==='prism'?' wd-prism':'')+(p.presentation==='horizon'?' wd-horizon':'');stage.style.width=p.canvas.width+'px';stage.style.height=p.canvas.height+'px';for(const[k,v]of Object.entries(p.colors))if(/^#[\da-f]{6}$/i.test(v))stage.style.setProperty('--'+k,v);host.append(stage);
  if(imageUrl){const img=document.createElement('img');img.className='wd-background';img.alt='';img.src=imageUrl;img.style.opacity=p.background.opacity;img.style.objectFit=p.background.fit==='stretch'?'fill':p.background.fit;const r=p.background.rect||{x:0,y:0,w:p.canvas.width,h:p.canvas.height};Object.assign(img.style,{inset:'auto',left:r.x+'px',top:r.y+'px',width:r.w+'px',height:r.h+'px'});if(edit){img.tabIndex=0;img.setAttribute('aria-label','Move background image')}stage.append(img)}
  backgroundEffects(stage,p);
  const bars='<div class="wd-bars" data-eq-style="'+esc(p.equalizer_style||'bars')+'" data-eq-response="'+esc(JSON.stringify(p.equalizer_response||{}))+'" data-eq-color-source="'+esc(p.equalizer_color_source||'custom')+'" data-eq-art="'+esc(t.art||'')+'">'+Array.from({length:16},(_,i)=>`<i style="height:${30+(i*13)%70}%;animation-delay:-${i*.16}s;animation-duration:${.6+(i%5)*.18}s"></i>`).join('')+'</div>';
  const content={brand:esc(p.label??(p.layout==='queue'?'NEXTUP · UP NEXT':'NEXTUP • NOW PLAYING')),title:esc(t.title),artist:esc((t.artists||[]).join(', ')),requester:'Requested by '+esc(current?.requester||'—'),art:t.art?.startsWith('https://')?`<img src="${esc(t.art)}" alt="Album artwork" referrerpolicy="no-referrer">`:'♫',progress:'<div class="fill" style="width:0"></div>',time:'<span id="elapsed">0:00</span><span>'+time(t.duration)+'</span>',equalizer:bars,queue:items.length?items.slice(0,6).map(row=>`<div class="wd-queue-row">${row.track.art?.startsWith('https://')?`<img src="${esc(row.track.art)}" alt="" referrerpolicy="no-referrer">`:''}<div>${esc(row.track.title)}<small>${esc(row.track.artists.join(', '))} · @${esc(row.requester)}</small></div></div>`).join(''):'The queue is clear'};
  for(const [key,part] of Object.entries(p.elements)){if(!part.visible||(key==='equalizer'&&!p.equalizer))continue;const el=document.createElement('div');el.className='wd-part';el.dataset.part=key;el.style.cssText=`left:${part.x}px;top:${part.y}px;width:${part.w}px;height:${part.h}px;font-size:${part.size}px`;el.style.fontFamily=fontStacks[part.font]||((p.fonts||[]).some(f=>f.id===part.font)?'NextUpFont_'+part.font+',Segoe UI,sans-serif':fontStacks.system);el.style.fontWeight=part.weight??(key==='title'?700:400);el.style.letterSpacing=(part.spacing??(key==='brand'?3:0))+'px';el.innerHTML=content[key]||'';if(edit){el.tabIndex=0;el.setAttribute('aria-label','Move '+labels[key])}stage.append(el);if(key==='title')host._titleCleanup=scrollTitle(el)}
  const resize=()=>{stage.style.transform='scale('+host.clientWidth/p.canvas.width+')'};resize();host._widgetObserver?.disconnect();host._widgetObserver=new ResizeObserver(resize);host._widgetObserver.observe(host);return stage;
 }

 const foldFull='inset(0px 0px round 24px)',foldLine='inset(calc(50% - 6px) 0px round 24px)',foldDot='inset(calc(50% - 6px) calc(50% - 6px) round 24px)';
 function resetPresentation(host){window.NextUpWidgetV3?.dispose(host);host._fold?.dispose();host._fold=null;host._horizon?.dispose();host._horizon=null}
 function hidePresentation(host){window.NextUpWidgetV3?.hide(host);host._fold?.hide();host._horizon?.hide()}
 function present(host,p,current,items,imageUrl,fontUrl,status,progress=0){
  if(p.format==='nextup-widget-v3')return NextUpWidgetV3.present(host,p,current,items,imageUrl,fontUrl,status,progress);
  if(p.transition==='horizon'){host._fold?.dispose();host._fold=null;if(!host._horizon)host._horizon=NextUpSingularity.create(host,render);host._horizon.request({p,current,items,imageUrl,fontUrl,status,progress,active:!!current&&['Playing','Paused'].includes(status),key:current?JSON.stringify([current.id,current.track.provider,current.track.id]):'',sig:JSON.stringify([p,current,items])});return}
  host._horizon?.dispose();host._horizon=null;
  host.style.position='relative';host.style.aspectRatio=p.canvas.width+'/'+p.canvas.height;
  if(!host._fold)host._fold=foldController(host);
  host._fold.request({p,current,items,imageUrl,fontUrl,active:!!current&&['Playing','Paused'].includes(status),key:current?JSON.stringify([current.id,current.track.provider,current.track.id]):'',sig:JSON.stringify([p,current,items])});
 }
 function foldController(host){
  let desired=null,busy=false,disposed=false,shownKey=null,shownSig='',stage=null,dot=null,rail=null,animation=null,contentAnimations=[];
  host.style.position='relative';
  function draw(d){
   stage=render(host,d.p,d.current,d.items,d.imageUrl,false,d.fontUrl);
   dot=document.createElement('div');dot.className='wd-fold-dot';dot.setAttribute('aria-hidden','true');
   for(const k of ['accent','accent2'])dot.style.setProperty('--'+k,d.p.colors[k]);host.append(dot);
   rail=document.createElement('div');rail.className='wd-fold-rail';rail.setAttribute('aria-hidden','true');stage.append(rail);settle(false);
  }
  function settle(open){stage.style.clipPath=open?foldFull:foldDot;stage.setAttribute('aria-hidden',String(!open));dot.hidden=open;rail.style.opacity=open?'0':'1';stage.querySelectorAll('.wd-part').forEach(e=>e.style.opacity=open?'':'0')}
  async function move(open){
   dot.hidden=true;stage.setAttribute('aria-hidden',String(!open));
   host.dataset.foldPhase=open?'opening':'closing';
   const frames=open?[foldDot,foldLine,foldFull]:[foldFull,foldLine,foldDot];
   const duration=matchMedia('(prefers-reduced-motion: reduce)').matches?0:900;
   contentAnimations=[...stage.querySelectorAll('.wd-part')].map(e=>e.animate(open?[{opacity:0,offset:0},{opacity:0,offset:.4},{opacity:1,offset:1}]:[{opacity:1,offset:0},{opacity:0,offset:.4},{opacity:0,offset:1}],{duration,fill:'forwards'}));
   contentAnimations.push(rail.animate(open?[{opacity:1,offset:0},{opacity:1,offset:.42},{opacity:0,offset:.75},{opacity:0,offset:1}]:[{opacity:0,offset:0},{opacity:1,offset:.4},{opacity:1,offset:1}],{duration,fill:'forwards'}));
   animation=stage.animate(frames.map((clipPath,i)=>({clipPath,offset:i===1?(open?.42:.58):i/2})),{duration,easing:'cubic-bezier(.4,0,.2,1)',fill:'forwards'});
   try{await animation.finished}catch{return}
   if(disposed)return;settle(open);animation.cancel();animation=null;contentAnimations.forEach(a=>a.cancel());contentAnimations=[];
  }
  async function run(){
   if(busy||disposed)return;busy=true;
   try{while(!disposed&&desired){const d=desired;
    if(shownKey&&(!d.active||shownKey!==d.key)){await move(false);shownKey=null;continue}
    if(!d.active){if(!stage)draw(d);dot.hidden=false;stage.setAttribute('aria-hidden','true');host.dataset.foldPhase='idle';break}
    if(!shownKey){draw(d);shownKey=d.key;shownSig=d.sig;await move(true);if(disposed)break;host.dataset.foldPhase='open';continue}
    if(shownSig!==d.sig){draw(d);shownSig=d.sig;settle(true)}
    host.dataset.foldPhase='open';break;
   }}finally{busy=false}
  }
  return {request(d){desired=d;run()},hide(){if(desired){desired={...desired,active:false};run()}},dispose(){disposed=true;animation?.cancel();contentAnimations.forEach(a=>a.cancel());host._titleCleanup?.();host._widgetObserver?.disconnect();dot?.remove();delete host.dataset.foldPhase;host.style.position=''}};
 }
 return {render,present,resetPresentation,hidePresentation,defaults,labels,time,esc,style,scrollTitle,backgroundEffects};
})();
