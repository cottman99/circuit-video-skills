"""Thin authored-course adapter to the existing measured whiteboard renderer."""
from pathlib import Path
import copy,hashlib,json,math,sys
from PIL import Image,ImageChops,ImageDraw,ImageFilter
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'rendering')]
import pipeline
import logical_scene as native
from world_canvas import frame_state_key

def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def compile_course(project,data,voice_input,receipt,profile,output):
 P=data['LessonPlan'];S=data['SourcePackage'];V=json.loads(voice_input.read_text());R=receipt
 windows={w['sentence_id']:w for w in R['caption_windows']}
 require(len(windows)==len(R['caption_windows'])==len(P['formal_master']),'Incomplete/duplicate sentence windows')
 require([(x['sentence_id'],x['formal_text']) for x in R['raw_sentences']]==[(x['id'],x['text']) for x in P['formal_master']],'Formal receipt mismatch')
 for n in P['formal_master']:
  w=windows[n['id']];require(len(n['text'])/(w['end']-w['start'])<=profile['max_caption_codepoints_per_second'],'TIMING_UNSAT: full caption reading budget '+n['id'])
 D=R['audio']['duration'];W=profile['width'];H=W*9/16;gap=profile['board_gap'];pan=profile['camera_pan_seconds']
 narration=[{**n,'start':windows[n['id']]['start'],'end':windows[n['id']]['end']} for n in V['narration']]
 captions=[{'id':'caption-'+n['id'],'narration_id':n['id'],'source_range':[0,len(n['text'])],'start':n['start'],'end':n['end']} for n in narration]
 L={'schema_version':'circuit-lesson-1','title':P['title'],'duration':D,'sources':[],
 'required_capabilities':['frozen_scene','cumulative_objects','semantic_actions','direct_pan','full_frame_receipts','internal_subtitle_strip'],
 'knowledge_graph':{'nodes':[],'edges':[]},'layout_contract':profile['layout_contract'],'objects':[],'boards':[],'camera_track':[],
 'narration':narration,'captions':captions,'voice':V['voice'],'teacher_actions':[],'source_catalog':{'sources':{},'assets':{}}}
 import fitz
 with fitz.open(project/S['original_path']) as doc:
  for page in S['selected_pages']:
   sid='source-page-'+str(page);L['sources'].append({'id':sid,'locator':f"{S['display_name']} page {page}",'basis':S['use_scope']})
   L['source_catalog']['sources'][sid]={'id':sid,'path':S['original_path'],'sha256':S['sha256'],'page':page,'pdf_rotation':doc[page-1].rotation,'redistribution_basis':S['use_scope']}
  for i,s in enumerate(P['scenes']):
   bid=s['id'];cfg=P['layout']['scenes'][bid];x=i*(W+gap);start=0 if not i else windows[s['sentence_ids'][0]]['start'];end=windows[P['scenes'][i+1]['sentence_ids'][0]]['start'] if i+1<len(P['scenes']) else D
   ready=start+(pan if i else 0);ids=[];targets={};bounds=[x,0,W,H]
   def add(o):
    o.update(start=o.get('start',start),end=D);L['objects'].append(o);ids.append(o['id'])
   add({'id':bid+'.border','kind':'rect','world_bounds':[x+2,2,W-4,H-4],'stroke':'#bfd0de','width':2})
   add({'id':bid+'.title','kind':'text','text':s['title'],'world_bounds':[x+60,35,1,1],'xy':[x+60,35],'size':profile['heading_size'],'typography_role':'title'})
   add({'id':bid+'.source','kind':'text','text':'源页 '+','.join(map(str,s['source_pages'])),'world_bounds':[x+W-400,28,1,1],'size':profile['source_label_size'],'typography_role':'source'})
   L['knowledge_graph']['nodes'].append({'id':bid,'statement':s['title'],'source_refs':['source-page-'+str(p) for p in s['source_pages']]})
   # Scene order is presentation order, not an invented scientific prerequisite.
   for c in s['source_crops']:
    oid=bid+'.'+c['id'];targets[c['id']]=oid;box=cfg['objects'][c['id']];r=doc[c['page']-1].rect;b=c['bbox_normalized'];aspect=(b[2]-b[0])*r.width/((b[3]-b[1])*r.height)
    require(abs(box[2]/box[3]/aspect-1)<.025,'LAYOUT_ASPECT: source crop would distort '+c['id'])
    require(c['white_matte_safe'] is True,'UNSUPPORTED_ASSET_MATTE: needs explicit alpha adapter')
    L['source_catalog']['assets'][oid]={'source_id':'source-page-'+str(c['page']),'crop_normalized':b,'crop_version':pipeline.digest(c),'white_matte_safe':True,'nondata_exclusions':c.get('nondata_exclusions',[])}
    add({'id':oid,'kind':'asset','asset_id':oid,'world_bounds':[x+box[0],*box[1:]],'start':ready,'duration':profile['asset_reveal_seconds'],'knowledge_refs':[bid]})
   reveal_slots={}
   for f in s['formula_objects']:
    nid=f['reveal_sentence_id'];reveal_slots.setdefault(nid,[]).append(f['id'])
   for f in s['formula_objects']:
    oid=bid+'.'+f['id'];targets[f['id']]=oid;box=cfg['objects'][f['id']];w=windows[f['reveal_sentence_id']];group=reveal_slots[f['reveal_sentence_id']]
    available=w['end']-max(w['start'],ready)-profile['reveal_settle_seconds']
    step=min(profile['object_reveal_seconds'],available/len(group));require(step>=.3,'TIMING_UNSAT: no readable reveal window '+f['id'])
    fs=max(w['start'],ready)+group.index(f['id'])*step;span=step*.8
    require(fs+span+profile['reveal_settle_seconds']<=w['end'],'TIMING_UNSAT: formula exceeds sentence')
    add({'id':oid,'kind':'formula','latex':f['latex'],'world_bounds':[x+box[0],box[1],1,1],'font_size':box[2],'start':fs,'duration':span,'read_window':[fs+span,w['end']],'knowledge_refs':[bid]})
   byid={o['id']:o for o in L['objects']}
   for label in cfg.get('labels',[]):
    target=byid[targets[label['target']]];xy=[x+label['xy'][0],label['xy'][1]]
    add({'id':bid+'.'+label['id'],'kind':'text','text':label['text'],'world_bounds':[*xy,1,1],'xy':xy,'size':label['size'],'typography_role':'body','start':target['start']})
   for j,a in enumerate(s['teaching_actions']):
    require(a['action']=='frame','UNSUPPORTED_ACTION: no silent fallback');o=byid[targets[a['target_id']]];w=windows[a['sentence_id']]
    begin=max(w['start']+.15,o['start']+o.get('duration',0)+.08);finish=min(w['end']-.12,end)
    require(finish-begin>.25,'TIMING_UNSAT: no attention window')
    L['teacher_actions'].append({'id':bid+'.focus-'+str(j),'kind':'frame','target':o['id'],'start':begin,'end':finish,'timing_basis':'measured sentence display, not word alignment'})
   L['boards'].append({'id':bid,'bounds':bounds,'object_refs':ids,'layout':{'title_objects':[bid+'.title'],'metadata_objects':[bid+'.source'],'border_object':bid+'.border'}})
   if i:L['camera_track'].append({'start':start,'end':ready,'from':[x-(W+gap),0,W,H],'to':bounds})
   L['camera_track'].append({'start':ready,'end':end,'from':bounds,'to':bounds})
 L['teacher_actions'].sort(key=lambda a:a['start'])
 for a,b in zip(L['teacher_actions'],L['teacher_actions'][1:]):require(a['end']<=b['start'],'TIMING_UNSAT: overlapping attention actions; reauthor explicit intent')
 L['required_object_ids']=[o['id'] for o in L['objects']]
 audio=Path(R['_receipt_base'])/R['audio']['path'];require(sha(audio)==R['audio']['sha256'],'AUDIO_HASH: measured PCM changed')
 L=pipeline.bind_audio(L,audio);scene=pipeline.compile_data(L,project)
 scene['production_bindings']={'source_sha256':S['sha256'],'plan_sha256':pipeline.digest(P),'voice_input_sha256':sha(voice_input),'raw_provider_events_sha256':R['provider_events_sha256'],'raw_mp3_sha256':R['audio']['source_mp3_sha256'],'display_policy_sha256':R['display_policy_sha256'],'profile':profile,'wrapper_sha256':sha(__file__)}
 scene['timing_evidence']={'kind':'measured_provider_onset_display_schedule','raw_intervals_preserved':True,'word_alignment':False}
 scene.pop('scene_digest');scene['scene_digest']=pipeline.digest(scene);pipeline.verify_scene(scene)
 output.mkdir(parents=True,exist_ok=True);pipeline.write(output/'lesson.json',L);pipeline.write(output/'scene.json',scene)
 return scene,audio

class VisibleRenderer(pipeline.CanvasRenderer):
 """Native reveal-front pointer, configured whitespace placement and exact cache."""
 last_stats=None
 def __init__(self,*a,**kw):
  super().__init__(*a,**kw);self._last=None;self.stats={'rendered_frames':0,'exact_static_cache_hits':0};VisibleRenderer.last_stats=self.stats
  self.pointer_profile=self.scene['production_bindings']['profile']['pointer']
 def teacher(self,t,tr,scale,ink):
  for e in self.events:
   if e['kind']=='formula' and e['start']<t<e['start']+e['duration']:
    r=self.native_event(e,scale);g,q,front=native.pointer.active(r,(t-e['start'])/e['duration']);px=e['xy'][0]+front[0]/r['raster_scale'];off=self.pointer_profile['whitespace_offset']
    for py in [e['xy'][1]+e['im'].height+off,e['xy'][1]-off]:
     sx,sy=tr((px,py));rad=math.ceil((self.pointer_profile['core_radius']+2)*self.config.ui_scale)
     if sy-rad<0 or sy+rad>self.layout['content_clip'][3]*self.config.ui_scale:continue
     if not ink.crop((round(sx-rad),round(sy-rad),round(sx+rad+1),round(sy+rad+1))).getbbox():return {'kind':'dot','target':e['id'],'point':[px,py],'opacity':min(1,(t-e['start'])/.1,(e['start']+e['duration']-t)/.1),'geometry_source':'native_reveal_front_x_whitespace','word_alignment':False}
    raise ValueError('LAYOUT_UNSAT: no visible pointer whitespace for '+e['id'])
  return super().teacher(t,tr,scale,ink)
 def dot(self,im,point,opacity):
  s=self.config.ui_scale;r=self.pointer_profile['core_radius']*s;pad=math.ceil(self.pointer_profile['glow_padding']*s);glow=Image.new('RGBA',(2*pad+1,2*pad+1));d=ImageDraw.Draw(glow)
  d.ellipse((pad-r*1.5,pad-r*1.5,pad+r*1.5,pad+r*1.5),fill=(243,36,72,round(155*opacity)));glow=glow.filter(ImageFilter.GaussianBlur(6*s));d=ImageDraw.Draw(glow)
  d.ellipse((pad-r,pad-r,pad+r,pad+r),fill=(243,36,72,round(255*opacity)));d.ellipse((pad-2*s,pad-2*s,pad+2*s,pad+2*s),fill=(255,205,213,round(255*opacity)))
  xy=(round(point[0]-pad),round(point[1]-pad));channels=im.crop((*xy,xy[0]+2*pad+1,xy[1]+2*pad+1)).convert('RGB').split();minimum=ImageChops.darker(ImageChops.darker(channels[0],channels[1]),channels[2]);protected=minimum.point(lambda v:255 if v<255 else 0).filter(ImageFilter.MaxFilter(3));glow.putalpha(ImageChops.multiply(glow.getchannel('A'),ImageChops.invert(protected)));im.paste(glow,xy,glow)
 def render(self,t,record=True):
  key=frame_state_key(self.scene,t)
  if self._last and self._last[0]==key:
   self.stats['exact_static_cache_hits']+=1;im=self._last[1];r=copy.deepcopy(self._last[2]);r['time']=t
   if record:self.records.append(r)
   return im,r
  self.stats['rendered_frames']+=1;im,r=super().render(t,record);self._last=(key,im,copy.deepcopy(r));return im,r
