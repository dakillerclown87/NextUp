/* Pointer editing stays local until release; saved previews use the read-only overlay. */
'use strict';
let widgetScaleText=true;
const widgetTextParts=new Set(['brand','title','artist','requester','time','queue']);
const widgetLimit=(n,lo,hi)=>Math.max(lo,Math.min(hi,n));
function widgetHasBackground(){return !!(widgetDraft?.background_data||widgetDraft?.background.image)}
function widgetPart(key=widgetSelected){return key==='background'?widgetDraft.background.rect:widgetDraft.elements[key]}
function widgetNode(key=widgetSelected){return $('#we-preview '+(key==='background'?'.wd-background':'[data-part="'+key+'"]'))}
function widgetBackgroundClamp(p){const c=widgetDraft.canvas;p.w=widgetLimit(p.w,8,c.width*4);p.h=widgetLimit(p.h,4,c.height*4);p.x=widgetLimit(p.x,8-p.w,c.width-8);p.y=widgetLimit(p.y,4-p.h,c.height-4)}
function widgetControls(){
 if(!widgetDraft||!$('#we-part'))return;
 if(widgetSelected==='background'&&!widgetHasBackground())widgetSelected=Object.keys(widgetDraft.elements)[0];
 const bg=widgetSelected==='background',p=widgetPart();if(!p){for(const id of ['we-x','we-y','we-w','we-h','we-size','we-visible','we-font','we-weight','we-spacing','we-font-upload','we-font-remove'])$('#'+id).disabled=true;widgetAdvancedControls();return}
 if(bg){$('#we-part').value='background';for(const k of ['x','y','w','h'])$('#we-'+k).value=Math.round(p[k]*100)/100;$('#we-size').value='';}
 else widgetElementControls();
 for(const id of ['we-x','we-y','we-w','we-h','we-size','we-visible','we-font','we-weight','we-spacing','we-font-upload'])$('#'+id).disabled=bg;
 if(bg)$('#we-font-remove').disabled=true;
 const stage=$('#we-preview .wd-stage');if(!stage)return;stage.classList.toggle('wd-bg-edit',bg);
 stage.querySelectorAll('.wd-selected').forEach(e=>e.classList.remove('wd-selected'));widgetNode()?.classList.add('wd-selected');
 stage.querySelector('.wd-gizmo')?.remove();
 if(!bg&&!p.visible)return;
 const box=document.createElement('div');box.className='wd-gizmo';box.dataset.targetPart=widgetSelected;
 Object.assign(box.style,{left:p.x+'px',top:p.y+'px',width:p.w+'px',height:p.h+'px'});
 const positions={nw:[0,0],n:[50,0],ne:[100,0],e:[100,50],se:[100,100],s:[50,100],sw:[0,100],w:[0,50]};
 for(const [dir,[x,y]] of Object.entries(positions)){
  const h=document.createElement('button');h.type='button';h.className='wd-handle';h.dataset.resize=dir;
  h.setAttribute('aria-label','Resize '+(bg?'background':widgetLayerLabel(widgetSelected))+' '+dir);
  h.title='Drag to resize';Object.assign(h.style,{left:x+'%',top:y+'%',cursor:dir+'-resize'});box.append(h);
 }
 const move=document.createElement('button');move.type='button';move.className='wd-handle wd-move-handle';move.dataset.movePart=widgetSelected;move.setAttribute('aria-label','Drag selected layer '+widgetLayerLabel(widgetSelected));move.title='Drag selected layer, even behind other shapes';move.textContent='✥';Object.assign(move.style,{left:'50%',top:'-20px',width:'24px',height:'20px',cursor:'move',pointerEvents:'auto'});box.append(move);
 stage.append(box);
}
function widgetApplyGeometry(){const p=widgetPart(),el=widgetNode();if(!p||!el)return;Object.assign(el.style,{left:p.x+'px',top:p.y+'px',width:p.w+'px',height:p.h+'px'});if(p.size)el.style.fontSize=p.size+'px';widgetControls()}
function widgetResize(start,dir,dx,dy,keepRatio,bg){
 const free=widgetDraft.format==='nextup-widget-v3';const c=widgetDraft.canvas,minX=bg?start.x+start.w-c.width*4:(free?-c.width*4:0),minY=bg?start.y+start.h-c.height*4:(free?-c.height*4:0),maxX=bg?start.x+c.width*4:(free?c.width*4:c.width),maxY=bg?start.y+c.height*4:(free?c.height*4:c.height);
 let left=dir.includes('w')?widgetLimit(start.x+dx,minX,start.x+start.w-8):start.x;
 let right=dir.includes('e')?widgetLimit(start.x+start.w+dx,start.x+8,maxX):start.x+start.w;
 let top=dir.includes('n')?widgetLimit(start.y+dy,minY,start.y+start.h-4):start.y;
 let bottom=dir.includes('s')?widgetLimit(start.y+start.h+dy,start.y+4,maxY):start.y+start.h;
 if(keepRatio&&dir.length===2){
  const west=dir.includes('w'),north=dir.includes('n'),ax=west?start.x+start.w:start.x,ay=north?start.y+start.h:start.y;
  let factor=Math.abs(dx/start.w)>=Math.abs(dy/start.h)?(right-left)/start.w:(bottom-top)/start.h;
  const maxW=(bg||free)?c.width*4:(west?ax:c.width-ax),maxH=(bg||free)?c.height*4:(north?ay:c.height-ay);
  factor=widgetLimit(factor,Math.max(8/start.w,4/start.h),Math.min(maxW/start.w,maxH/start.h));
  const w=start.w*factor,h=start.h*factor;left=west?ax-w:ax;right=left+w;top=north?ay-h:ay;bottom=top+h;
 }
 return {x:left,y:top,w:right-left,h:bottom-top};
}
document.addEventListener('pointerdown',e=>{
 const host=e.target.closest('#we-preview');if(!host||e.button!==0||widgetDrag)return;
 const move=e.target.closest('[data-move-part]'),handle=e.target.closest('[data-resize]'),part=e.target.closest('.wd-part'),background=e.target.closest('.wd-background');
 const key=move?move.dataset.movePart:handle?handle.closest('.wd-gizmo').dataset.targetPart:background&&widgetSelected==='background'?'background':part?.dataset.part;if(!key)return;
 e.preventDefault();widgetSelected=key;widgetControls();const p=widgetPart(),stage=host.querySelector('.wd-stage');
 clearTimeout(widgetSaveTimer);widgetDrag={host,id:e.pointerId,part:key,dir:handle?.dataset.resize||'',start:structuredClone(p),startX:e.clientX,startY:e.clientY,scale:stage.getBoundingClientRect().width/widgetDraft.canvas.width,changed:false};
 host.setPointerCapture(e.pointerId);widgetNode()?.focus({preventScroll:true});
});
document.addEventListener('pointermove',e=>{
 const d=widgetDrag;if(!d||d.id!==e.pointerId)return;e.preventDefault();const p=widgetPart(d.part),dx=(e.clientX-d.startX)/d.scale,dy=(e.clientY-d.startY)/d.scale,bg=d.part==='background';
 if(d.dir){Object.assign(p,widgetResize(d.start,d.dir,dx,dy,e.shiftKey,bg));if(widgetScaleText&&(widgetTextParts.has(p.kind||d.part)||p.kind==='text')&&d.dir.length===2)p.size=widgetLimit(d.start.size*Math.min(p.w/d.start.w,p.h/d.start.h),widgetDraft.format==='nextup-widget-v3'?1:8,widgetDraft.format==='nextup-widget-v3'?512:96);}
 else{p.x=d.start.x+dx;p.y=d.start.y+dy;if(!bg&&widgetDraft.format!=='nextup-widget-v3'){p.x=widgetLimit(p.x,0,widgetDraft.canvas.width-p.w);p.y=widgetLimit(p.y,0,widgetDraft.canvas.height-p.h)}}
 if(bg)widgetBackgroundClamp(p);else widgetClamp(p);d.changed=JSON.stringify(p)!==JSON.stringify(d.start);widgetApplyGeometry();
});
function widgetEndDrag(cancel=false){const d=widgetDrag;if(!d)return;widgetDrag=null;if(cancel)Object.assign(widgetPart(d.part),d.start);if(d.host.hasPointerCapture(d.id))d.host.releasePointerCapture(d.id);if(d.changed&&!cancel)widgetChanged();else{widgetPaint();if(widgetLive&&widgetDirty)widgetChanged(false)}}
document.addEventListener('pointerup',e=>{if(widgetDrag?.id===e.pointerId)widgetEndDrag()});
document.addEventListener('pointercancel',e=>{if(widgetDrag?.id===e.pointerId)widgetEndDrag(true)});
document.addEventListener('lostpointercapture',e=>{if(widgetDrag?.id===e.pointerId)widgetEndDrag(true)});
window.addEventListener('blur',()=>widgetEndDrag(true));
document.addEventListener('keydown',e=>{
 if(e.key==='Escape'&&widgetDrag){e.preventDefault();widgetEndDrag(true);return}
 if(!e.target.closest('#we-preview')||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
 const p=widgetPart();if(!p)return;e.preventDefault();const n=e.shiftKey?10:1;
 p.x+=e.key==='ArrowLeft'?-n:e.key==='ArrowRight'?n:0;p.y+=e.key==='ArrowUp'?-n:e.key==='ArrowDown'?n:0;
 if(widgetSelected==='background')widgetBackgroundClamp(p);else widgetClamp(p);widgetChanged();widgetNode()?.focus({preventScroll:true});
});
document.addEventListener('wheel',e=>{
 if(widgetSelected!=='background'||!e.target.closest('#we-preview')||widgetDrag||e.ctrlKey||!widgetHasBackground())return;e.preventDefault();
 const p=widgetDraft.background.rect,c=widgetDraft.canvas,stage=$('#we-preview .wd-stage').getBoundingClientRect(),px=(e.clientX-stage.left)*c.width/stage.width,py=(e.clientY-stage.top)*c.height/stage.height;
 const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?300:1),factor=widgetLimit(Math.exp(-delta*.0015),Math.max(8/p.w,4/p.h),Math.min(c.width*4/p.w,c.height*4/p.h));
 p.x=px-(px-p.x)*factor;p.y=py-(py-p.y)*factor;p.w*=factor;p.h*=factor;widgetBackgroundClamp(p);widgetChanged();
},{passive:false});
function widgetSavedPreview(id){
 const preset=state.settings.widget_presets.find(p=>p.id===id);if(!preset){notice('Save this widget first.',true);return}
 document.querySelector('#widget-saved-preview')?.remove();
 const dialog=document.createElement('dialog');dialog.id='widget-saved-preview';dialog.dataset.presetId=id;dialog.className='widget-preview-dialog';dialog.setAttribute('aria-label','Saved widget preview');
 const width=preset.canvas?.width||600,height=preset.canvas?.height||(preset.layout==='queue'?480:260);dialog.style.width=Math.min(width+48,1400)+'px';
 const bar=document.createElement('div');bar.className='row between';const title=document.createElement('h2');title.textContent=preset.name+' — saved preview';bar.append(title);
 const close=document.createElement('button');close.textContent='Close preview';close.addEventListener('click',()=>dialog.close());bar.append(close);dialog.append(bar);
 const frame=document.createElement('iframe');frame.title=preset.name+' live widget';frame.className='widget-saved-frame';frame.style.aspectRatio=width+'/'+height;
 frame.src=state.widgets[preset.layout==='spectrum'?'now':preset.layout]+'&preset_id='+encodeURIComponent(id);dialog.append(frame);
 const hint=document.createElement('p');hint.className='hint';hint.textContent='Live playback using the saved design. Save your edits to update this preview.';dialog.append(hint);
 const refresh=document.createElement('button');refresh.textContent='Refresh preview';refresh.addEventListener('click',()=>{frame.src=frame.src});dialog.append(refresh);
 const previous=document.activeElement;dialog.addEventListener('close',()=>{dialog.remove();if(previous?.isConnected)previous.focus()},{once:true});document.body.append(dialog);dialog.showModal();close.focus();
}
