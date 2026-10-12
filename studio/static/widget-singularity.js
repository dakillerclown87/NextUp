/* Event Horizon: presentation only. Never sends playback commands. */
'use strict';
window.NextUpSingularity={create(host,render){
 const clamp=(n,a=0,b=1)=>Math.max(a,Math.min(b,n)),ease=x=>x*x*(3-2*x);
 const motion=matchMedia('(prefers-reduced-motion: reduce)');
 let desired=null,shownKey='',shownSig='',stage=null,card=null,disposed=false,raf=0;
 let mode='idle',start=0,from=0,suction=1,burst=1,last=performance.now(),w=1120,h=420,aura=0,aperture=.44;
 let sample={seconds:0,at:last,playing:false,duration:0};
 const canvas=document.createElement('canvas');canvas.className='wd-horizon-fx';canvas.setAttribute('aria-hidden','true');
 Object.assign(canvas.style,{position:'absolute',inset:'0',width:'100%',height:'100%',pointerEvents:'none'});
 const ctx=canvas.getContext('2d'),texture=new Image();let light=null;
 texture.onload=()=>{
  // Convert black matte to emission alpha for a transparent OBS browser source.
  const c=document.createElement('canvas');c.width=texture.width;c.height=texture.height;
  const g=c.getContext('2d',{willReadFrequently:true});g.drawImage(texture,0,0);
  const pixels=g.getImageData(0,0,c.width,c.height),a=pixels.data;
  for(let i=0;i<a.length;i+=4){const m=Math.max(a[i],a[i+1],a[i+2]);a[i+3]=m;for(let k=0;k<3;k++)a[i+k]=m?a[i+k]*255/m:0;}
  g.putImageData(pixels,0,0);light=c;
 };
 texture.src='/event-horizon.png?key='+encodeURIComponent(new URLSearchParams(location.search).get('key')||'');
 const particles=Array.from({length:128},(_,i)=>({angle:i*2.399963,seed:((i*73)%127)/127,r:50+(i*37)%500,speed:.08+(i%9)*.008}));
 function phase(value){mode=value;host.dataset.horizonPhase=value;}
 function mount(d){
  stage=render(host,d.p,d.current,d.items,d.imageUrl,false,d.fontUrl);
  w=d.p.canvas.width;h=d.p.canvas.height;canvas.width=w;canvas.height=h;
  card=document.createElement('div');card.className='wd-horizon-card';Object.assign(card.style,{position:'absolute',inset:'0',transformOrigin:'50% 50%',willChange:'transform,opacity'});
  host.append(card);card.append(stage);host.append(canvas);shownKey=d.key;shownSig=d.sig;
 }
 function open(d,now){mount(d);suction=0;burst=0;start=now;phase('burst');}
 function close(now){if(mode==='closing'||mode==='idle')return;from=suction;start=now;phase('closing');}
 function effect(now,s,b,dt){
  ctx.clearRect(0,0,w,h);const cx=w/2,cy=h/2,t=now/1000;
  const targetAura=mode==='idle'?.48:mode==='burst'?1-ease(clamp(b/.8)):ease(clamp(s*2.2));
  const response=1-Math.exp(-dt*9);aura+=(targetAura-aura)*response;aperture+=((mode==='idle'?.44:.45+.55*ease(s))-aperture)*response;
  const visible=aura,size=Math.min(w*.76,h*1.75)*aperture;
  if(motion.matches)return;
  if(visible>.001){
   ctx.save();ctx.globalAlpha=visible;
   // A black event horizon and a photograph-like lensed accretion disk.
   ctx.fillStyle='#010102';ctx.beginPath();ctx.arc(cx,cy,size*.095,0,Math.PI*2);ctx.fill();
   if(light)ctx.drawImage(light,cx-size*.493,cy-size*.465,size,size);
   else{ctx.strokeStyle='#efd3a0';ctx.lineWidth=2;ctx.beginPath();ctx.ellipse(cx,cy,size*.32,size*.085,-.1,0,Math.PI*2);ctx.stroke();}
   ctx.restore();
  }
  // Bounded spiral dust: deterministic, no per-frame allocations or DOM nodes.
  if(visible>.001||mode==='burst'){
   ctx.save();ctx.globalCompositeOperation='lighter';
   for(const p of particles){
    const exploding=mode==='burst',q=exploding?ease(b):((p.seed+t*p.speed)%1),r=exploding?25+q*(p.r+120):24+(1-q)*(p.r+35);
    const a=p.angle+(exploding?b*.3:t*.18+q*q*3.2),x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.38;
    if(!exploding&&Math.hypot(x-cx,y-cy)<size*.105)continue;
    const alpha=exploding?(1-b)*.75:visible*Math.sin(q*Math.PI)*(.25+.65*s);
    ctx.strokeStyle='rgba(255,210,148,'+clamp(alpha)+')';ctx.lineWidth=p.seed<.2?1.5:.8;ctx.beginPath();ctx.moveTo(x,y);
    const tail=exploding?12+q*50:2+s*20;ctx.lineTo(x-Math.cos(a+(exploding?0:.8))*tail,y-Math.sin(a+(exploding?0:.8))*tail*.38);ctx.stroke();
   }
   if(mode==='burst'&&b<1){
    const r=20+ease(b)*w*.64,g=ctx.createRadialGradient(cx,cy,0,cx,cy,r);
    g.addColorStop(0,'rgba(255,220,176,'+(1-b)*.35+')');g.addColorStop(.35,'rgba(242,161,80,'+(1-b)*.13+')');g.addColorStop(1,'rgba(240,160,80,0)');ctx.fillStyle=g;ctx.fillRect(0,0,w,h);
    ctx.strokeStyle='rgba(255,222,174,'+(1-b)*.75+')';ctx.lineWidth=1+5*(1-b);ctx.beginPath();ctx.ellipse(cx,cy,r,r*.4,0,0,Math.PI*2);ctx.stroke();
   }
   ctx.restore();
  }
 }
 function frame(now){
  if(disposed)return;const dt=Math.min(.05,Math.max(0,(now-last)/1000));last=now;
  const d=desired,active=d?.active;
  if(d){
   if(motion.matches){
    if(active){if(d.key!==shownKey||d.sig!==shownSig)mount(d);suction=0;burst=1;phase('open');}
    else{suction=1;phase('idle');}
   }else{
    if(active&&mode==='idle')open(d,now);
    if(shownKey&&mode!=='idle'&&(!active||d.key!==shownKey))close(now);
    if(mode==='closing'){
     const q=clamp((now-start)/(1100*Math.max(.2,1-from)));suction=from+(1-from)*ease(q);
     if(q===1){suction=1;phase('idle');if(active)open(d,now);}
    }else if(mode==='burst'){
     burst=clamp((now-start)/1700);if(burst===1)phase('open');
    }else if(active&&d.key===shownKey&&['open','absorbing','absorbed'].includes(mode)){
     if(d.sig!==shownSig)mount(d);
     const elapsed=sample.seconds+(sample.playing?Math.min(5,(now-sample.at)/1000):0),remaining=sample.duration-elapsed;
     const target=sample.duration>0?ease(clamp((4-remaining)/4)):0;
     // Time-based smoothing avoids visible jumps when a 1.5 s state poll arrives.
     suction+=(target-suction)*(1-Math.exp(-dt*12));
     if(target===1&&suction>.996)suction=1;
     phase(suction>.995?'absorbed':suction>.005?'absorbing':'open');
    }
   }
  }
  if(card){
   const s=clamp(suction),reveal=mode==='burst'?ease(clamp((burst-.12)/.88)):1;
   const sx=Math.max(.001,Math.pow(1-s,1.3))*Math.max(.015,reveal),sy=Math.max(.001,Math.pow(1-s,2.1))*Math.max(.015,reveal);
   card.style.transform=`translate(${Math.sin(s*Math.PI)*18}px,${Math.sin(s*Math.PI)*-12}px) rotate(${-32*s*s+(1-reveal)*9}deg) scale(${sx},${sy})`;
   card.style.opacity=String((1-Math.pow(s,3))*ease(clamp(reveal*1.8)));
   stage.setAttribute('aria-hidden',String(s>.98||!d?.active));
  }
  effect(now,suction,burst,dt);raf=requestAnimationFrame(frame);
 }
 raf=requestAnimationFrame(frame);
 return {
  request(d){
   desired=d;host.style.position='relative';host.style.overflow='hidden';host.style.aspectRatio=d.p.canvas.width+'/'+d.p.canvas.height;
   sample={seconds:Number.isFinite(d.progress)?Math.max(0,d.progress):0,at:performance.now(),playing:d.status==='Playing',duration:d.current?.track.duration||0};
   if(!stage){mount(d);suction=1;phase('idle');}
  },
  hide(){if(desired){desired={...desired,active:false};sample.playing=false;}},
  dispose(){disposed=true;cancelAnimationFrame(raf);texture.onload=null;host._titleCleanup?.();host._widgetObserver?.disconnect();canvas.remove();card?.remove();delete host.dataset.horizonPhase;host.style.overflow='';host.style.position='';}
 };
}};
