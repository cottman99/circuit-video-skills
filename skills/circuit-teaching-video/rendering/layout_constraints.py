"""Reusable, data-driven whiteboard safe zones. No lesson-specific coordinates.
Compilation resolves exact text ink into authored board-relative zones; renderer
consumes frozen geometry. Screen chrome never follows the world-camera pan.
"""
import math,re
from PIL import Image,ImageDraw
import type_styles as typography
from caption_contract import validate_compiled_captions

SCHEMA='whiteboard-layout-1'
TOKENS=('g_mb','g_m','r_o','R_D','C_in','C_out')
def require(ok,msg):
    if not ok:raise ValueError('Layout constraint: '+msg)
def contains(outer,inner,tol=1e-6):
    x,y,w,h=outer;a,b,c,d=inner
    return a>=x-tol and b>=y-tol and a+c<=x+w+tol and b+d<=y+h+tol
def intersects(a,b,tol=1e-6):
    return min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0])>tol and min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1])>tol
def intersection(a,b):
    x=max(a[0],b[0]);y=max(a[1],b[1]);r=min(a[0]+a[2],b[0]+b[2]);bot=min(a[1]+a[3],b[1]+b[3])
    return [x,y,max(0,r-x),max(0,bot-y)]
def union(boxes):
    x=min(b[0] for b in boxes);y=min(b[1] for b in boxes)
    return [x,y,max(b[0]+b[2] for b in boxes)-x,max(b[1]+b[3] for b in boxes)-y]
def relative(board,f):return [board[0]+board[2]*f[0],board[1]+board[3]*f[1],board[2]*f[2],board[3]*f[3]]
def validate_contract(contract,config):
    require(contract.get('schema_version')==SCHEMA,'missing or unsupported layout contract')
    canvas=[0,0,config['logical_width'],config['logical_height']]
    for key in ('whiteboard','world_viewport','content_clip','subtitle_zone'):
        b=contract[key];require(len(b)==4 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in b) and min(b[2:])>0,'invalid '+key)
        require(contains(canvas,b),key+' outside logical canvas')
    require(contract['world_viewport']==canvas,'whiteboard must fill screen without content shrink')
    require(contains(contract['whiteboard'],contract['subtitle_zone']),'subtitles must remain inside whiteboard')
    require(not intersects(contract['content_clip'],contract['subtitle_zone']),'body and subtitle reserved zones overlap')
    require(contract['whiteboard'][0]<=canvas[2]*.005 and contract['whiteboard'][1]<=canvas[3]*.005 and canvas[2]-sum(contract['whiteboard'][::2])<=canvas[2]*.005 and canvas[3]-sum(contract['whiteboard'][1::2])<=canvas[3]*.005,'whiteboard must fill screen edge to edge')
    require(contract['subtitle_zone'][1]>=canvas[3]*.85 and sum(contract['subtitle_zone'][1::2])>=canvas[3]*.97,'subtitle strip must be anchored inside bottom of whiteboard')
    style=contract['subtitles'];require(style['font_size']>=style['minimum_font_size'],'subtitle font below readability floor')
    require(style.get('font_family')==typography.FAMILY and style.get('font_weight')==400 and style.get('color')==typography.DEFAULT_CONTRACT['roles']['subtitle']['color'],'subtitle typography role mismatch')
    require(style['max_lines'] in (1,2),'subtitles may occupy at most two lines')
    require(style['line_height']>=style['font_size'],'invalid subtitle line height')
    zones=contract['board_zones']
    for k,b in zones.items():require(contains([0,0,1,1],b),'board zone outside board: '+k)
    require(zones['metadata'][0]>=.5 and zones['metadata'][1]<.2 and zones['metadata'][1]+zones['metadata'][3]<=zones['body'][1],'metadata must be in top-right header above body')
    require(zones['title'][0]+zones['title'][2]<=.5,'title must remain in left header')
    require(zones['subtitle_reserve'][1]>=.85,'board subtitle reserve must remain at bottom')
    require(not intersects(zones['title'],zones['metadata']),'title and metadata zones overlap')
    require(not intersects(zones['metadata'],zones['body']),'metadata and body zones overlap')
    require(not intersects(zones['body'],zones['subtitle_reserve']),'body and subtitle reserve overlap')

def wrap_text(text,font,max_width):
    """Exact-content measured wrapping; punctuation stays with its phrase."""
    rows=[];row=''
    for ch in text:
        if row and font.getlength(row+ch)>max_width:
            cuts=[i+1 for i,c in enumerate(row) if c in '；，、：,;: ' and i>len(row)//2]
            if cuts:
                cut=cuts[-1];rows.append(row[:cut]);row=row[cut:]+ch
            else:rows.append(row);row=ch
        else:row+=ch
    if row:rows.append(row)
    require(''.join(rows)==text,'wrapping altered content')
    require(all(font.getlength(r)<=max_width+1e-6 for r in rows),'unbreakable text overflow')
    require(all(r.strip('，。；：！？、,.!?;: ') for r in rows),'punctuation-only line')
    return rows

def apply_board_layout(objects,boards,contract,native):
    draw=ImageDraw.Draw(Image.new('RGB',(1,1)));byid={o['id']:o for o in objects};resolved=[]
    for board in boards:
        rules=board['layout'];zones={k:relative(board['bounds'],b) for k,b in contract['board_zones'].items()}
        metadata=rules['metadata_objects'];require(len(metadata)==len(set(metadata)),'duplicate metadata object')
        cursor=zones['metadata'][1]
        for oid in metadata:
            require(oid in byid,'missing metadata object '+oid);o=byid[oid]
            require(o['kind']=='text','metadata must be text '+oid)
            minimum=contract['metadata'].get('source_minimum_font_size',contract['metadata']['minimum_font_size']) if o.get('typography_role')=='source' else contract['metadata']['minimum_font_size']
            require(o['size']>=minimum,'metadata font below readability floor '+oid)
            font=typography.object_font(o);rows=wrap_text(o['text'],font,zones['metadata'][2]);require(len(rows)<=contract['metadata']['max_lines_per_object'],'metadata exceeds line count '+oid)
            placed=[]
            for text in rows:
                bb=draw.textbbox((0,0),text,font=font);xy=[zones['metadata'][0]-bb[0],cursor-bb[1]];bounds=[zones['metadata'][0],cursor,bb[2]-bb[0],bb[3]-bb[1]]
                placed.append({'text':text,'xy':xy,'bounds':bounds});cursor+=max(bounds[3],o['size'])+contract['metadata']['line_gap']
            cursor+=contract['metadata']['object_gap']-contract['metadata']['line_gap']
            o.update(text_rows=placed,xy=placed[0]['xy'],world_bounds=union([p['bounds'] for p in placed]),layout_role='metadata',layout_board=board['id'],layout_zone='metadata')
            require(contains(zones['metadata'],o['world_bounds']),'metadata overflow '+oid+'; expand zone or reauthor, never silently shrink')
        for oid in rules['title_objects']:
            o=byid[oid];o.update(layout_role='title',layout_board=board['id'],layout_zone='title')
        byid[rules['border_object']].update(layout_role='board_frame',layout_board=board['id'])
        resolved.append({'board_id':board['id'],'bounds':board['bounds'],'zones':zones,'metadata_objects':metadata,'title_objects':rules['title_objects']})
    return resolved

def validate_objects(objects,resolved):
    byid={o['id']:o for o in objects}
    for board in resolved:
        zones=board['zones'];bid=board['board_id'];members=[]
        for o in objects:
            if not o['id'].startswith(bid+'.') or o.get('layout_role')=='board_frame':continue
            zone=o.get('layout_zone','body');require(contains(zones[zone],o['world_bounds']),o['id']+' outside '+zone+' zone')
            members.append(o)
        # Mutually disjoint text/ink rectangles, except intentional source circuit
        # regions/connector strokes; temporal intervals prevent preview false positives.
        for i,a in enumerate(members):
            if a['kind']=='line':continue
            for b in members[i+1:]:
                if b['kind']=='line' or min(a['end'],b['end'])<=max(a['start'],b['start']):continue
                require(not intersects(a['world_bounds'],b['world_bounds']), 'object collision '+a['id']+' / '+b['id'])

def caption_units(text,size,native):
    font=native.font(size);out=[]
    for token in re.split(r'(g_mb|g_m|r_o|R_D|C_in|C_out)',text):
        if not token:continue
        if token in TOKENS:
            latex=token.replace('_mb','_{mb}').replace('_in','_{\\mathrm{in}}').replace('_out','_{\\mathrm{out}}')
            im=native.equation(latex,size,10000)['im'];out.append({'kind':'math','text':token,'latex':latex,'width':im.width,'height':im.height})
        else:
            bb=font.getbbox(token);out.append({'kind':'text','text':token,'width':font.getlength(token),'ink_bounds':[bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1]]})
    return out

def compile_captions(segments,contract,native):
    style=contract['subtitles'];zone=contract['subtitle_zone'];size=style['font_size'];pad=style['horizontal_padding'];maxw=zone[2]-2*pad
    out=[]
    for seg in segments:
        rows=wrap_text(seg['text'],native.font(size),maxw)
        # Text wrapping is conservative for native math runs, then verify exact mixed widths.
        require(len(rows)<=style['max_lines'],'subtitle exceeds maximum lines '+seg['id'])
        height=len(rows)*style['line_height'];require(height<=zone[3],'subtitle height overflow '+seg['id'])
        y=zone[1]+(zone[3]-height)/2;placed=[]
        for row in rows:
            units=caption_units(row,size,native);width=sum(u['width'] for u in units)
            require(width<=maxw,'subtitle mixed text/math width overflow '+seg['id'])
            x=zone[0]+(zone[2]-width)/2
            background=[x-pad,y,width+2*pad,style['line_height']];ink=[];cursor=x
            for unit in units:
                if unit['kind']=='text':
                    bx,by,bw,bh=unit['ink_bounds'];ink.append([cursor+bx,y+by,bw,bh])
                else:ink.append([cursor,y+(style['line_height']-unit['height'])/2,unit['width'],unit['height']])
                cursor+=unit['width']
            bounds=union([background]+ink);require(contains(zone,bounds),'subtitle glyph ink outside internal strip '+seg['id'])
            placed.append({'text':row,'units':units,'xy':[x,y],'background_bounds':background,'ink_bounds':union(ink),'bounds':bounds});y+=style['line_height']
        out.append({'id':seg['id'],'text':seg['text'],'start':seg['start'],'end':seg['audio_end'],'coordinate_space':'screen','safe_band':zone,'font_size':size,'rows':placed,
                    'narration_id':seg['narration_id'],'source_range':seg['source_range'],'text_sha256':seg['text_sha256']})
    return out

def camera_at(scene,t):
    track=scene['camera_track']
    for k in track:
        if k['start']<=t<k['end']:
            u=(t-k['start'])/(k['end']-k['start']);return [a+(b-a)*u for a,b in zip(k['from'],k['to'])]
    return track[0]['from'] if t<track[0]['start'] else track[-1]['to']

def screen_geometry(scene,config,t):
    view=camera_at(scene,t);u=config['width']/scene['render_config']['logical_width'];vx,vy,vw,vh=[v*u for v in scene['layout_contract']['world_viewport']]
    scale=min(vw/view[2],vh/view[3]);ox=vx+(vw-view[2]*scale)/2;oy=vy+(vh-view[3]*scale)/2
    def transform(box):return [ox+(box[0]-view[0])*scale,oy+(box[1]-view[1])*scale,box[2]*scale,box[3]*scale]
    return view,transform,scale,u

def validate_scene_layout(scene):
    validate_compiled_captions(scene)
    typography.validate_objects(scene['objects'],scene['typography_contract'])
    validate_contract(scene['layout_contract'],scene['render_config']);validate_objects(scene['objects'],scene['resolved_layout'])
    c=scene['layout_contract'];zone=c['subtitle_zone']
    for cue in scene['captions']:
        require(cue['safe_band']==zone,'caption safe band changed '+cue['id'])
        require(cue['font_size']>=c['subtitles']['minimum_font_size'],'caption below font floor')
        require(''.join(row['text'] for row in cue['rows'])==cue['text'],'caption rows lost text')
        require(len(cue['rows'])<=c['subtitles']['max_lines'],'too many caption lines')
        for row in cue['rows']:
            require(contains(row['bounds'],row['ink_bounds']),'caption ink not included in row bounds '+cue['id'])
            require(contains(zone,row['bounds']),'caption out of internal strip '+cue['id'])
            require(not intersects(c['content_clip'],row['bounds']),'caption collides with world content')
    return True

def validate_frame_layout(scene,config,receipt):
    """Verify receipts against independently computed authored geometry, not claims."""
    view,tr,scale,u=screen_geometry(scene,config,receipt['time']);contract=scene['layout_contract'];clip=[v*u for v in contract['content_clip']];shell=[v*u for v in contract['whiteboard']];zone=[v*u for v in contract['subtitle_zone']]
    close=lambda a,b:len(a)==len(b) and all(abs(x-y)<1e-5 for x,y in zip(a,b))
    require(close(receipt['camera'],view),'receipt camera differs from track')
    for key,expected in [('whiteboard_bounds',shell),('subtitle_zone',zone),('content_viewport',clip)]:require(close(receipt.get(key,[]),expected),'missing/stale '+key)
    byid={o['id']:o for o in scene['objects']}
    for row in receipt['objects']:
        expected=tr(byid[row['id']]['world_bounds']);require(close(row['screen_bounds'],expected),'incorrect transformed bounds '+row['id'])
        clipped=intersection(expected,clip) if row['in_view'] else [0,0,0,0]
        require(close(row.get('visible_screen_bounds',[]),clipped),'incorrect clipped bounds '+row['id'])
        if clipped[2] and clipped[3]:require(not intersects(clipped,zone),'world content entered subtitle strip '+row['id'])
    cue=next((c for c in scene['captions'] if c['start']<=receipt['time']<c['end']),None)
    expected=[[v*u for v in row['bounds']] for row in cue['rows']] if cue else []
    require(receipt.get('caption_segment')==(cue['id'] if cue else None),'incorrect caption cue')
    require(receipt.get('caption_text')==(cue['text'] if cue else None),'rendered caption text differs from full formal-text cue')
    require(receipt.get('caption_source_range')==(cue['source_range'] if cue else None),'rendered caption source range differs')
    require(receipt.get('caption_narration_id')==(cue['narration_id'] if cue else None),'rendered caption narration ID differs')
    require(len(receipt.get('caption_boxes',[]))==len(expected),'caption row count differs')
    for actual,wanted in zip(receipt['caption_boxes'],expected):
        require(close(actual,wanted),'caption bounds differ from frozen layout');require(contains(shell,actual) and contains(zone,actual),'caption outside whiteboard')
    return True

def geometry_sweep(scene,config):
    """Full timeline analytical check only; does not render or certify encoded pixels."""
    validate_scene_layout(scene);count=math.ceil(scene['duration']*config['fps']-1e-8);transition_frames=0;min_caption_gap=math.inf
    for i in range(count):
        t=i/config['fps'];view,tr,scale,u=screen_geometry(scene,config,t);c=scene['layout_contract'];clip=[v*u for v in c['content_clip']];zone=[v*u for v in c['subtitle_zone']]
        require(not intersects(clip,zone),'content/caption overlap during camera interpolation')
        if any(k['start']<=t<k['end'] and k['from']!=k['to'] for k in scene['camera_track']):transition_frames+=1
        min_caption_gap=min(min_caption_gap,zone[1]-(clip[1]+clip[3]))
    return {'status':'PASS','evidence_level':'analytical_geometry_only','frames_checked':count,'transition_frames_checked':transition_frames,'minimum_content_caption_gap_pixels':min_caption_gap,'full_screen_world_viewport':True,'inside_whiteboard_subtitles':True,'metadata_and_content_bounds':'measured_and_disjoint','encoded_video':'NOT ASSESSED BY GEOMETRY SWEEP; see bound encoded-media QA','limits':['Geometry sweep is not encoded-pixel/motion review or full audiovisual listening.','Overview intentionally reduces text size; local-view font floors do not certify overview readability.']}
