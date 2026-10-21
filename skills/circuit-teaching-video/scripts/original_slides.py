"""Source-native page animation: project-owned regions, one manuscript, real onsets.

No PDF reconstruction, translation, OCR semantics, word alignment or new TTS.
The bounded reveal adapter requires explicitly declared uniform-background regions.
Original colored ink is preserved; optional role colors affect neutral ink only.
"""
from pathlib import Path
from types import SimpleNamespace
import copy, math, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageOps

SCHEMA='original-slide-scene-1'
def require(ok, message):
    if not ok: raise ValueError(message)
def number(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def rgb(value): return isinstance(value,list) and len(value)==3 and all(type(x) is int and 0<=x<=255 for x in value)
def is_plan(plan): return plan.get('layout',{}).get('schema')=='original-slide-layout-1'
def profile():
    return json.loads((Path(__file__).resolve().parents[1]/'config/original-slide.json').read_text())

def validate_scene_plan(scene, cfg, layout):
    require(set(scene)=={'id','title','source_page','source_pages','sentence_ids','source_objects','teaching_actions'},'ORIGINAL_SCENE_FIELDS: original objects only; no replacements or reflow')
    require(set(layout)<={'schema','scenes','semantic_colors','presentation'},'ORIGINAL_LAYOUT_FIELDS: no source transforms or replacement text')
    require(scene.get('source_pages')==[scene.get('source_page')],'ORIGINAL_PAGE: exactly one original page per scene')
    require(set(cfg)=={'background_rgb','mask_policy'} and rgb(cfg['background_rgb']) and cfg['mask_policy']=='uniform-background','UNSUPPORTED_BACKGROUND: explicit uniform background required')
    palette=layout.get('semantic_colors',{})
    require(isinstance(palette,dict) and all(isinstance(k,str) and k.strip() and rgb(v) for k,v in palette.items()),'SEMANTIC_COLORS: named RGB roles required')
    overrides=layout.get('presentation',{})
    require(set(overrides)<={'reveal_seconds','move_seconds','minimum_dwell_seconds','minimum_complete_page_seconds'},'PRESENTATION_OVERRIDE: timing defaults only')
    require(all(number(v) and v>0 for v in overrides.values()),'PRESENTATION_TIMING: positive finite values required')
    objects=scene.get('source_objects');require(isinstance(objects,list) and objects,'SOURCE_OBJECTS: semantic regions required')
    ids=[o['id'] for o in objects];require(len(ids)==len(set(ids)) and 'source_page' not in ids,'OBJECT_IDS: duplicate or reserved source_page')
    byid={o['id']:o for o in objects}
    for o in objects:
        require(set(o)<={'id','regions','reveal_sentence_id','reveal_with','focus_point','ink_role','edge_background_tolerance','edge_tolerance_reason'},'SOURCE_OBJECT_FIELDS: no replacement text/image/geometry')
        require(isinstance(o['id'],str) and o['id'].strip(),'OBJECT_ID')
        require(isinstance(o.get('regions'),list) and o['regions'],'SOURCE_REGIONS')
        for b in o['regions']:
            require(isinstance(b,list) and len(b)==4 and all(type(v) is int for v in b) and 0<=b[0]<b[2] and 0<=b[1]<b[3],'SOURCE_REGION: integer source-pixel xyxy bounds')
        if 'reveal_with' in o:
            require('reveal_sentence_id' not in o and o['reveal_with'] in byid and o['reveal_with']!=o['id'],'REVEAL_OWNER: valid owner, no independent child reveal')
            require(not ({'ink_role','edge_background_tolerance','edge_tolerance_reason'} & set(o)),'REVEAL_OWNER: color and boundary evidence belong to reveal owner')
        else: require('reveal_sentence_id' in o and (o['reveal_sentence_id'] is None or o['reveal_sentence_id'] in scene['sentence_ids']),'REVEAL_SENTENCE: same-page sentence or null at page entry')
        tolerance=o.get('edge_background_tolerance',0)
        require(type(tolerance) is int and 0<=tolerance<=10,'EDGE_TOLERANCE: integer 0–10, validation only')
        if tolerance:require(isinstance(o.get('edge_tolerance_reason'),str) and o['edge_tolerance_reason'].strip(),'EDGE_TOLERANCE_REASON: inspected faint background evidence required')
        if 'ink_role' in o:
            require(o['ink_role'] in palette,'INK_ROLE: unknown semantic role')
            require(min(cfg['background_rgb'])>=200,'INK_ROLE_BACKGROUND: dark neutral ink on a light background only')
        if 'focus_point' in o: require(len(o['focus_point'])==2 and all(number(v) for v in o['focus_point']),'FOCUS_POINT: source-pixel point required')
    def owner(oid,seen=()):
        require(oid not in seen,'REVEAL_OWNER: cycle')
        return owner(byid[oid]['reveal_with'],(*seen,oid)) if 'reveal_with' in byid[oid] else oid
    for oid in ids: owner(oid)
    for a in scene['teaching_actions']:
        require(set(a)<={'sentence_id','target_id','action','timing_basis','text_range'},'FOCUS_FIELDS')
        require(a['action']=='focus' and a['sentence_id'] in scene['sentence_ids'] and a['target_id'] in byid,'FOCUS_REFERENCE: valid sentence and semantic target required')
        basis=a.get('timing_basis','sentence_onset')
        require(basis in ('sentence_onset','estimated_text_position'),'FOCUS_TIMING: unsupported precision')
        require((basis=='estimated_text_position')==('text_range' in a),'FOCUS_TIMING: estimated cue needs explicit source text range')
    return ids

def _mask(size, regions):
    out=Image.new('L',size);d=ImageDraw.Draw(out)
    for x0,y0,x1,y1 in regions: d.rectangle((x0,y0,x1-1,y1-1),fill=255)
    return out

def _wrap(text,font,width,max_lines):
    lines=[];line=''
    for c in text:
        require(font.getlength(c)<=width,'CAPTION_LAYOUT_UNSAT: glyph wider than band')
        if line and font.getlength(line+c)>width: lines.append(line);line=c
        else: line+=c
    if line: lines.append(line)
    require(''.join(lines)==text and len(lines)<=max_lines,'CAPTION_LAYOUT_UNSAT: full text needs more lines; revise authored sentence segmentation')
    return lines

def _focus_point(o, background, prof):
    h,w=background.shape;r=prof['pointer_clearance'];regions=o['regions']
    candidates=[o['focus_point']] if 'focus_point' in o else [[b[2]+r+2,(b[1]+b[3])/2] for b in regions]+[[b[0]-r-2,(b[1]+b[3])/2] for b in regions]+[[(b[0]+b[2])/2,b[3]+r+2] for b in regions]+[[(b[0]+b[2])/2,b[1]-r-2] for b in regions]
    for p in candidates:
        x,y=map(round,p)
        if not (r<=x<w-r and r<=y<h-r):continue
        if not any(b[0]-3*r<=x<=b[2]+3*r and b[1]-3*r<=y<=b[3]+3*r for b in regions):continue
        if background[y-r:y+r+1,x-r:x+r+1].all():return [x,y]
    raise ValueError('POINTER_LAYOUT_UNSAT: supply a nearby clear focus_point for '+o['id'])

def compile_course(project,data,voice_input,receipt,prof,output):
    import pipeline
    from caption_contract import resolve_captions
    project=Path(project);P=data['LessonPlan'];S=data['SourcePackage'];R=receipt
    V=pipeline.json.loads(Path(voice_input).read_text());prof={**prof,**P['layout'].get('presentation',{})}
    require(prof['fps']==60,'ORIGINAL_SLIDE_FPS: this profile is validated at 60 fps')
    windows={w['sentence_id']:w for w in R['caption_windows']}
    require(len(windows)==len(R['caption_windows'])==len(P['formal_master']),'CAPTION_WINDOWS: incomplete/duplicate')
    require([(s['sentence_id'],s['formal_text']) for s in R['raw_sentences']]==[(n['id'],n['text']) for n in P['formal_master']],'FORMAL_RECEIPT_MISMATCH')
    narration=[{**n,'start':windows[n['id']]['start'],'end':windows[n['id']]['end']} for n in V['narration']]
    refs=[{'id':'caption-'+n['id'],'narration_id':n['id'],'source_range':[0,len(n['text'])],'start':n['start'],'end':n['end']} for n in narration]
    D=R['audio']['duration'];captions,coverage=resolve_captions(narration,refs,D)
    font_path=pipeline.typography.FONTS[400];font=ImageFont.truetype(str(font_path),prof['caption_font_size'])
    for n in narration:
        require(len(n['text'])/(n['end']-n['start'])<=prof['max_caption_codepoints_per_second'],'TIMING_UNSAT: full caption reading budget '+n['id'])
    page_rows={x['page']:x for x in S['pages']};pages=[];allobjects=[];cues=[];maxheight=0
    for i,s in enumerate(P['scenes']):
        row=page_rows[s['source_page']];path=project/row['image_path'];im=Image.open(path).convert('RGB');a=np.asarray(im);height,width=a.shape[:2]
        require(width==prof['width'],'SOURCE_GEOMETRY: page raster width differs; no silent resizing')
        maxheight=max(maxheight,height);cfg=P['layout']['scenes'][s['id']];deviation=np.abs(a.astype('int16')-np.array(cfg['background_rgb'],dtype='int16')).max(axis=2);background=deviation==0
        start=0 if i==0 else windows[s['sentence_ids'][0]]['start'];end=windows[P['scenes'][i+1]['sentence_ids'][0]]['start'] if i+1<len(P['scenes']) else D
        byid={o['id']:copy.deepcopy(o) for o in s['source_objects']}
        def owner(oid):return owner(byid[oid]['reveal_with']) if 'reveal_with' in byid[oid] else oid
        roots={oid for oid in byid if owner(oid)==oid};masks={}
        for oid,o in byid.items():
            for b in o['regions']:require(b[2]<=width and b[3]<=height,'SOURCE_REGION_BOUNDS: '+oid)
            masks[oid]=np.asarray(_mask((width,height),o['regions']))>0
            o.update(id=s['id']+'.'+oid,local_id=oid,page_id=s['id'],owner_id=s['id']+'.'+owner(oid))
            if oid in roots:
                # A clear margin catches cut through source ink; it cannot certify semantic completeness.
                m=prof['edge_clearance_pixels']
                mask_image=_mask((width,height),o['regions'])
                inner=ImageOps.expand(mask_image,border=m,fill=255).filter(ImageFilter.MinFilter(2*m+1)).crop((m,m,width+m,height+m))
                inner_array=np.asarray(inner)>0
                require(inner_array.any(),'SOURCE_REGION_SMALL: owner union needs a clear interior')
                border=masks[oid] & ~inner_array
                # Source-edge clipping is already part of the authoritative page,
                # not a new crop introduced by this object's mask.
                tolerance=o.get('edge_background_tolerance',0)
                require((deviation[border]<=tolerance).all(),'SOURCE_OBJECT_EDGE_INK: enlarge complete semantic region '+oid)
                o['edge_validation']={'tolerance':tolerance,'nonexact_boundary_pixels':int(np.count_nonzero(deviation[border])),'maximum_boundary_deviation':int(deviation[border].max()) if border.any() else 0,'physical_page_edge_exempt':True,'source_pixels_modified':False}

                at=start if o['reveal_sentence_id'] is None else windows[o['reveal_sentence_id']]['start']
                duration=0 if o['reveal_sentence_id'] is None else prof['reveal_seconds']
                if o['reveal_sentence_id'] is not None:require(at+duration<=windows[o['reveal_sentence_id']]['end'],'TIMING_UNSAT: reveal exceeds its anchor sentence '+oid)
                require(at+duration+prof['minimum_complete_page_seconds']<=end,'TIMING_UNSAT: object not fully visible before page end '+oid)
                o.update(start=at,duration=duration)
            o['focus_point']=_focus_point(o,background,prof) if any(x['target_id']==oid for x in s['teaching_actions']) else o.get('focus_point')
        roots=list(roots)
        for x,oid in enumerate(roots):
            for other in roots[x+1:]:require(not np.any(masks[oid]&masks[other]&~background),'SOURCE_OBJECT_OVERLAP: use one reveal owner for shared ink')
        for oid,o in byid.items():
            root=byid[owner(oid)]
            if owner(oid)!=oid:
                require(not np.any(masks[oid]&~masks[owner(oid)]),'REVEAL_OWNER_BOUNDS: focus child must stay in parent region')
                o.update(start=root['start'],duration=root['duration'])
        sentence_map={n['id']:n for n in P['formal_master']}
        for action in s['teaching_actions']:
            obj=byid[action['target_id']];window=windows[action['sentence_id']];at=window['start'];basis=action.get('timing_basis','sentence_onset')
            if basis=='estimated_text_position':
                b=action['text_range'];text=sentence_map[action['sentence_id']]['text']
                require(isinstance(b,list) and len(b)==2 and all(type(v) is int for v in b) and 0<=b[0]<b[1]<=len(text),'FOCUS_TEXT_RANGE')
                at+=(window['end']-window['start'])*b[0]/len(text)
            at=max(at,obj['start']+obj['duration'])
            cues.append({'id':s['id']+'.focus-'+str(len(cues)),'page_id':s['id'],'target_id':obj['id'],'sentence_id':action['sentence_id'],'start':at,'anchor_sentence_end':window['end'],'point':obj['focus_point'],'regions':obj['regions'],'timing_basis':basis,'text_range':action.get('text_range'),'measured_word_alignment':False,'reveal_ready_adjustment':at-window['start'] if basis=='sentence_onset' else None})
        page={'id':s['id'],'source_page':s['source_page'],'path':str(path.resolve()),'sha256':row['image_sha256'],'width':width,'height':height,'start':start,'end':end,'background_rgb':cfg['background_rgb'],'object_ids':[o['id'] for o in byid.values()]};pages.append(page);allobjects.extend(byid.values())
    require([p['source_page'] for p in pages]==S['selected_pages'],'SOURCE_PAGE_ORDER: complete original scope required')
    for page in pages:
        pc=[c for c in cues if c['page_id']==page['id']]
        require([c['start'] for c in pc]==sorted(c['start'] for c in pc),'FOCUS_ORDER: explicit semantic cue order required')
        for j,c in enumerate(pc):
            c['end']=pc[j+1]['start'] if j+1<len(pc) else page['end'];c['move_seconds']=prof['move_seconds'] if j and c['point']!=pc[j-1]['point'] else 0
            require(c['start']>=page['start'] and c['end']<=page['end'] and min(c['end'],c['anchor_sentence_end'])-c['start']>=c['move_seconds']+prof['minimum_dwell_seconds'],'TIMING_UNSAT: reveal/move/dwell cannot fit cue '+c['id'])
            c['from_point']=pc[j-1]['point'] if j else c['point']
    H=math.ceil((maxheight+prof['caption_band_minimum'])/2)*2
    require(H-maxheight>=prof['caption_max_lines']*prof['caption_line_height'],'CAPTION_LAYOUT_UNSAT: subtitle band too short')
    for c in captions:c['lines']=_wrap(c['text'],font,prof['width']-2*prof['caption_horizontal_padding'],prof['caption_max_lines'])
    scene={'schema_version':SCHEMA,'title':P['title'],'duration':D,'profile':prof,'width':prof['width'],'height':H,'page_area_height':maxheight,'pages':pages,'objects':allobjects,'focus_cues':cues,'narration':narration,'captions':captions,'caption_coverage':coverage,'voice':V['voice'],'semantic_colors':P['layout'].get('semantic_colors',{}),'caption_font':str(font_path),'runtime':pipeline.runtime_bindings(),'adapter_sha256':pipeline.sha(__file__),'source_pdf':str((project/S['original_path']).resolve()),'source_pdf_sha256':S['sha256'],'production_bindings':{'source_sha256':S['sha256'],'plan_sha256':pipeline.digest(P),'voice_input_sha256':pipeline.sha(voice_input),'provider_events_sha256':R['provider_events_sha256'],'raw_mp3_sha256':R['audio']['source_mp3_sha256'],'display_policy_sha256':R['display_policy_sha256']},'timing_evidence':{'sentence_onsets':'measured provider SentenceBoundary','caption_end':'exclusive display window; not acoustic sentence endpoint','phrase_cues':'explicit text-position estimate only when declared','word_alignment':False}}
    audio=Path(R['_receipt_base'])/R['audio']['path'];require(pipeline.sha(audio)==R['audio']['sha256'],'AUDIO_HASH: PCM changed')
    scene['audio_binding']=pipeline.bind_audio({**scene,'captions':refs},audio)['audio_binding'];scene['scene_digest']=pipeline.digest(scene);verify_scene(scene)
    output=Path(output);output.mkdir(parents=True,exist_ok=True);pipeline.write(output/'scene.json',scene)
    return scene,audio

def verify_scene(scene):
    import pipeline
    from caption_contract import resolve_captions, validate_audio_binding
    require(scene.get('schema_version')==SCHEMA,'ORIGINAL_SCENE_SCHEMA')
    x=copy.deepcopy(scene);expected=x.pop('scene_digest',None);require(expected==pipeline.digest(x),'Compiled scene was modified')
    require(scene['runtime']==pipeline.runtime_bindings() and scene['adapter_sha256']==pipeline.sha(__file__),'Runtime or fonts changed; recompile authored input')
    require(pipeline.sha(scene['source_pdf'])==scene['source_pdf_sha256'],'SOURCE_CHANGED: original PDF')
    for p in scene['pages']:require(pipeline.sha(p['path'])==p['sha256'],'SOURCE_CHANGED: original page raster')
    resolved,coverage=resolve_captions(scene['narration'],[{'id':c['id'],'narration_id':c['narration_id'],'source_range':c['source_range'],'start':c['start'],'end':c['end']} for c in scene['captions']],scene['duration'])
    require([c['text'] for c in resolved]==[c['text'] for c in scene['captions']] and coverage==scene['caption_coverage'] and coverage['status']=='PASS','CAPTION_FULL_TEXT: modified caption')
    require(all(''.join(c['lines'])==c['text'] for c in scene['captions']),'CAPTION_FULL_TEXT: rendered lines changed')
    validate_audio_binding(scene['audio_binding'],scene['narration'],resolved,scene['voice'])

def validate_frame(scene,config,receipt):
    require(receipt['source_transform']=='identity_pixels','SOURCE_GEOMETRY_CHANGED')
    require(receipt['caption_complete'] and receipt['caption_within_band'],'CAPTION_LAYOUT_UNSAT')
    focus=receipt['focus']
    if focus:
        require(focus['target_id'] in receipt['fully_revealed_objects'],'FOCUS_BEFORE_REVEAL')
        require(focus['target_id']==focus['highlight_target_id'],'FOCUS_TARGET_MISMATCH')
        x,y=focus['point'];require(0<=x<scene['width'] and 0<=y<receipt['source_height'],'POINTER_OUTSIDE_SOURCE')

class OriginalSlideRenderer:
    last_stats=None
    def __init__(self,scene,width,fps):
        require(width==scene['width'] and fps==scene['profile']['fps'],'SOURCE_GEOMETRY: no renderer rescaling')
        self.scene=scene;self.config=SimpleNamespace(height=scene['height']);self.records=[];self.stats={'rendered_frames':0,'exact_static_cache_hits':0};OriginalSlideRenderer.last_stats=self.stats;self._page=None;self._last=None
        self.font=ImageFont.truetype(scene['caption_font'],scene['profile']['caption_font_size'])
    def state(self,t):
        page=next((p for p in self.scene['pages'] if p['start']<=t<p['end']),self.scene['pages'][-1]);objects=[o for o in self.scene['objects'] if o['page_id']==page['id']]
        cap=next((c for c in self.scene['captions'] if c['start']<=t<c['end']),None)
        focus=next((c for c in reversed(self.scene['focus_cues']) if c['page_id']==page['id'] and c['start']<=t<c['end']),None)
        progress={o['id']:min(1,max(0,(t-o['start'])/o['duration'])) if o['duration'] else float(t>=o['start']) for o in objects}
        point=None
        if focus:
            u=min(1,max(0,(t-focus['start'])/focus['move_seconds'])) if focus['move_seconds'] else 1;u=u*u*(3-2*u)
            point=[focus['from_point'][i]*(1-u)+focus['point'][i]*u for i in (0,1)]
        return page,objects,cap,focus,progress,point
    def _load(self,page,objects):
        if self._page==page['id']:return
        self._page=page['id'];self.original=Image.open(page['path']).convert('RGB');a=np.asarray(self.original);self.background=Image.fromarray((np.all(a==np.array(page['background_rgb']),axis=2)*255).astype('uint8'));colored=a.copy();self.masks={}
        neutral=(a.max(2)-a.min(2)<=4)&(a.min(2)<250)
        for o in objects:
            self.masks[o['id']]=_mask(self.original.size,o['regions'])
            if o.get('ink_role'):
                require(min(page['background_rgb'])>=200,'INK_ROLE_BACKGROUND: dark neutral ink on a light background only')
                mask=(np.asarray(self.masks[o['id']])>0)&neutral&(np.asarray(self.background)==0);ink=np.array(self.scene['semantic_colors'][o['ink_role']]);bg=np.array(page['background_rgb'],dtype=float);v=np.clip((bg-a[mask].astype(float))/bg,0,1);colored[mask]=(bg-v*(bg-ink)).astype('uint8')
        self.colored=Image.fromarray(colored)
    def page_frame(self,t,annotations=True,tint=True):
        page,objects,cap,focus,progress,point=self.state(t);self._load(page,objects);out=(self.colored if tint else self.original).copy();prof=self.scene['profile']
        if annotations and focus:
            layer=Image.new('RGB',out.size,tuple(page['background_rgb']));d=ImageDraw.Draw(layer)
            for b in focus['regions']:d.rounded_rectangle((b[0],b[1],b[2]-1,b[3]-1),radius=10,fill=tuple(prof['highlight_fill']),outline=tuple(prof['highlight_outline']),width=2)
            out.paste(layer,(0,0),ImageChops.multiply(self.background,self.masks[focus['target_id']]))
        for o in objects:
            if o['owner_id']!=o['id'] or progress[o['id']]>=1:continue
            blank=Image.new('RGB',out.size,tuple(page['background_rgb']));alpha=self.masks[o['id']].point(lambda v:round(v*(1-progress[o['id']])));out.paste(blank,(0,0),alpha)
        if annotations and point:
            layer=Image.new('RGBA',out.size);d=ImageDraw.Draw(layer);x,y=point;r=prof['pointer_radius'];color=tuple(prof['pointer_color']);d.ellipse((x-r*1.8,y-r*1.8,x+r*1.8,y+r*1.8),fill=(*color,95));layer=layer.filter(ImageFilter.GaussianBlur(5));d=ImageDraw.Draw(layer);d.ellipse((x-r,y-r,x+r,y+r),fill=(255,255,255,255),outline=(*color,255),width=4);d.ellipse((x-3,y-3,x+3,y+3),fill=(*color,255));layer.putalpha(ImageChops.multiply(layer.getchannel('A'),self.background));out.paste(layer,(0,0),layer)
        return out
    def render(self,t,record=True):
        page,objects,cap,focus,progress,point=self.state(t);key=(page['id'],cap['id'] if cap else None,tuple(progress.items()),focus['id'] if focus else None,tuple(point) if point else None)
        if self._last and self._last[0]==key:
            self.stats['exact_static_cache_hits']+=1;im=self._last[1];receipt=copy.deepcopy(self._last[2]);receipt['time']=t
        else:
            self.stats['rendered_frames']+=1;im=Image.new('RGB',(self.scene['width'],self.scene['height']),tuple(page['background_rgb']));im.paste(self.page_frame(t),(0,0));d=ImageDraw.Draw(im);top=self.scene['page_area_height'];d.rectangle((0,top,self.scene['width'],self.scene['height']),fill='white');d.line((0,top,self.scene['width'],top),fill='#d8dfe6',width=2)
            lines=cap['lines'] if cap else [];lineh=self.scene['profile']['caption_line_height'];y=top+(self.scene['height']-top-len(lines)*lineh)/2
            for line in lines:d.text(((self.scene['width']-self.font.getlength(line))/2,y),line,font=self.font,fill='#20262c');y+=lineh
            receipt={'time':t,'page_id':page['id'],'source_page':page['source_page'],'source_sha256':page['sha256'],'source_transform':'identity_pixels','source_height':page['height'],'caption_id':cap['id'] if cap else None,'caption_text':cap['text'] if cap else None,'caption_complete':not cap or ''.join(lines)==cap['text'],'caption_within_band':len(lines)<=self.scene['profile']['caption_max_lines'],'fully_revealed_objects':[k for k,v in progress.items() if v==1],'focus':None if not focus else {'cue_id':focus['id'],'target_id':focus['target_id'],'highlight_target_id':focus['target_id'],'point':point,'timing_basis':focus['timing_basis'],'phase':'move' if t<focus['start']+focus['move_seconds'] else 'dwell','word_alignment':False}}
            self._last=(key,im,copy.deepcopy(receipt))
        if record:self.records.append(receipt)
        return im,receipt
