"""Declarative widget layers and motion; JSON never executes scripts or HTML."""
import math,re
from .widget_design import number
from .widget_fonts import metadata,SYSTEM_FONTS
KINDS=('art','brand','title','artist','requester','progress','time','equalizer','queue','text','shape','image')

def color(v,default='transparent'):
    if v is None:return default
    if not isinstance(v,str) or not (v=='transparent' or re.fullmatch(r'#[a-fA-F0-9]{6}(?:[a-fA-F0-9]{2})?',v)):
        raise ValueError('Use transparent or a six/eight-digit hex color.')
    return v

def text(v,limit=2000):
    if not isinstance(v,str) or len(v)>limit or '\x00' in v:raise ValueError('Invalid widget text.')
    return v

def choice(v,options):
    if v not in options:raise ValueError('Unsupported widget style or motion.')
    return v

def boolean(v):
    if type(v) is not bool:raise ValueError('Invalid widget toggle.')
    return v

def design(v):
    for name in ('canvas','background','surface','robot'):
        if not isinstance(v.get(name,{}),dict):raise ValueError('Invalid widget '+name+'.')
    if not isinstance(v.get('background',{}).get('rect',{}),dict):raise ValueError('Invalid image placement.')
    c=v.get('canvas',{});w=number(c.get('width',1080),64,7680);h=number(c.get('height',520),64,4320)
    fonts=metadata(v.get('fonts',[]));allowed=SYSTEM_FONTS|{f['id'] for f in fonts}
    elements=v.get('elements',{})
    if not isinstance(elements,dict):raise ValueError('Widget layers must be an object.')
    out={}
    for ident,p in elements.items():
        if not isinstance(ident,str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}',ident) or not isinstance(p,dict):raise ValueError('Invalid widget layer identity.')
        kind=choice(p.get('kind',ident),KINDS);font=p.get('font','system')
        if not isinstance(font,str) or font not in allowed:raise ValueError('Choose a font included with the widget.')
        r={'kind':kind,'name':text(p.get('name',ident),80),'x':number(p.get('x',0),-w*4,w*4),'y':number(p.get('y',0),-h*4,h*4),'w':number(p.get('w',100),1,w*4),'h':number(p.get('h',40),1,h*4),'size':number(p.get('size',20),1,512),'font':font,'weight':number(p.get('weight',400),100,900),'spacing':number(p.get('spacing',0),-20,100),'visible':boolean(p.get('visible',True)),'opacity':number(p.get('opacity',1),0,1),'radius':number(p.get('radius',0),0,10000),'rotation':number(p.get('rotation',0),-36000,36000),'border':number(p.get('border',0),0,100),'z':number(p.get('z',0),-10000,10000),'color':color(p.get('color')),'fill':color(p.get('fill')),'gradient':color(p.get('gradient')),'border_color':color(p.get('border_color')),'fit':choice(p.get('fit','cover'),('cover','contain','fill')),'align':choice(p.get('align','left'),('left','center','right')),'text':text(p.get('text','')),'vinyl':boolean(p.get('vinyl',False)),'scroll':boolean(p.get('scroll',True)),'progress_style':choice(p.get('progress_style','line'),('line','wave')),'queue_direction':choice(p.get('queue_direction','vertical'),('horizontal','vertical')),'queue_count':number(p.get('queue_count',3),1,100),'queue_gap':number(p.get('queue_gap',10),0,500),'asset':p.get('asset','')}
        if not isinstance(r['asset'],str) or (r['asset'] and not re.fullmatch('[a-f0-9]{64}',r['asset'])):raise ValueError('Invalid layer image identity.')
        m=p.get('motion',{})
        if not isinstance(m,dict):raise ValueError('Invalid layer motion.')
        r['motion']={'type':choice(m.get('type','none'),('none','spin','float','pulse','custom')),'seconds':number(m.get('seconds',18),.1,3600),'direction':choice(m.get('direction','normal'),('normal','reverse','alternate')),'playing_only':boolean(m.get('playing_only',True)),'amplitude':number(m.get('amplitude',8),0,4000),'frames':[]}
        frames=m.get('frames',[])
        if not isinstance(frames,list) or len(frames)>120:raise ValueError('Use up to 120 animation keyframes per layer.')
        last=-1
        for f in frames:
            if not isinstance(f,dict):raise ValueError('Invalid animation keyframe.')
            frame={k:number(f.get(k,default),lo,hi) for k,default,lo,hi in [('offset',0,0,1),('x',0,-w*4,w*4),('y',0,-h*4,h*4),('rotate',0,-36000,36000),('scale',1,.01,100),('opacity',1,0,1)]}
            if frame['offset']<=last:raise ValueError('Keyframe offsets must increase from 0 to 1.')
            last=frame['offset'];r['motion']['frames'].append(frame)
        if r['motion']['type']=='custom' and (len(frames)<2 or r['motion']['frames'][0]['offset']!=0 or last!=1):raise ValueError('Custom motion needs at least two keyframes, starting at 0 and ending at 1.')
        out[ident]=r
    bg=v.get('background',{});asset=bg.get('image','')
    if not isinstance(asset,str) or (asset and not re.fullmatch('[a-f0-9]{64}',asset)):raise ValueError('Invalid background image identity.')
    rect=bg.get('rect',{'x':0,'y':0,'w':w,'h':h})
    background={'image':asset,'opacity':number(bg.get('opacity',1),0,1),'fit':choice(bg.get('fit','cover'),('cover','contain','stretch')),'stars':boolean(bg.get('stars',False)),'clouds':boolean(bg.get('clouds',False)),'rect':{k:number(rect.get(k,0),-4*(w if k in ('x','w') else h) if k in ('x','y') else 1,4*(w if k in ('x','w') else h)) for k in ('x','y','w','h')}}
    rb=v.get('robot',{});target=rb.get('target','art')
    if not isinstance(target,str):raise ValueError('Invalid robotic arm target.')
    if target and (target not in out or out[target]['kind']!='art'):
        if v.get('transition')=='robot':raise ValueError('Choose an artwork layer for the robotic arm.')
        target=''
    robot={'target':target,'base_x':number(rb.get('base_x',w*.855),-w*4,w*4),'base_y':number(rb.get('base_y',h*.242),-h*4,h*4),'lift_x':number(rb.get('lift_x',w*.472),-w*4,w*4),'lift_y':number(rb.get('lift_y',-h*.615),-h*4,h*4),'rest_x':number(rb.get('rest_x',w*.819),-w*4,w*4),'rest_y':number(rb.get('rest_y',-h*.33),-h*4,h*4),'seconds':number(rb.get('seconds',4.7),.5,30),'metal':color(rb.get('metal','#a6b5c4')),'grip':color(rb.get('grip','#263442')),'accent':color(rb.get('accent','#9e7af5')),'mount':boolean(rb.get('mount',True))}
    effects={'progress_color_source':choice(v.get('progress_color_source','custom'),('custom','artwork'))}
    if 'progress_colors' in v:
        palette=v['progress_colors']
        if not isinstance(palette,list) or not 2<=len(palette)<=8:raise ValueError('Choose 2–8 progress colors.')
        if any(not isinstance(c,str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',c) for c in palette):raise ValueError('Progress colors must use six-digit hex codes.')
        effects['progress_colors']=palette[:]
    if 'border_motion' in v:
        b=v['border_motion']
        if not isinstance(b,dict):raise ValueError('Invalid border animation.')
        enabled=boolean(b.get('enabled',True));target=b.get('target','')
        if not isinstance(target,str):raise ValueError('Invalid border target.')
        if enabled and (target not in out or out[target]['kind']!='shape'):raise ValueError('Choose a shape layer for the animated border.')
        palette=b.get('colors',['#33dcff','#b98aff'])
        if not isinstance(palette,list) or len(palette)!=2 or any(not isinstance(c,str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',c) for c in palette):raise ValueError('Choose two six-digit border colors.')
        effects['border_motion']={'enabled':enabled,'target':target,'colors':palette[:],'seconds':number(b.get('seconds',8),1,120),'width':number(b.get('width',1.65),.5,20),'glow':number(b.get('glow',5),0,40),'trail':number(b.get('trail',.1),.01,.5)}
    return {**effects,'canvas':{'width':w,'height':h},'elements':out,'fonts':fonts,'background':background,'robot':robot,'surface':{'transparent':boolean(v.get('surface',{}).get('transparent',False)),'radius':number(v.get('surface',{}).get('radius',24),0,10000)},'transition':choice(v.get('transition','none'),('none','fade','slide','fold','robot')),'transition_seconds':number(v.get('transition_seconds',.6),.1,30),'presentation':'standard'}
