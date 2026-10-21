#!/usr/bin/env python3
"""Five-node private teaching production. Only synthesize --allow-network sends speech."""
from pathlib import Path
import argparse,asyncio,copy,hashlib,json,os,shutil,sys,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE/'scripts')]
from workflow_attempts import Attempt,atomic_write,digest,file_lock,timestamp

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def require(ok,msg):
 if not ok:raise ValueError(msg)
def identity():return {str(p.relative_to(HERE)):sha(p) for d in ('scripts','rendering','style','config','authoring') for p in sorted((HERE/d).rglob('*')) if p.is_file() and p.suffix in ('.py','.json','.md','.txt')}
def profile():return read(HERE/'config/production.json')
def commit(project,data):
 data['BuildManifest']['updated_at']=timestamp();data['BuildManifest']['version']=digest({k:v for k,v in data.items() if k!='BuildManifest'})
 atomic_write(project/'versions'/(digest(data)+'.json'),data);atomic_write(project/'CourseProject.json',data)
def verify_source(project,data):
 import fitz
 s=data['SourcePackage'];original=project/s['original_path'];require(sha(original)==s['sha256'],'SOURCE_CHANGED: original file changed')
 with fitz.open(original) as doc:
  for row in s['pages']:
   page=doc[row['page']-1];pix=page.get_pixmap(matrix=fitz.Matrix(s['page_image_width']/page.rect.width,s['page_image_width']/page.rect.width),alpha=False)
   require(hashlib.sha256(pix.tobytes('png')).hexdigest()==row['image_sha256']==sha(project/row['image_path']),'SOURCE_VISUAL_CHANGED: page image not derived from original')
   require(page.get_text()==(project/row['text_path']).read_text() and sha(project/row['text_path'])==row['text_sha256'],'SOURCE_TEXT_CHANGED: extracted text changed')
 require(s['selected_pages']==[x['page'] for x in s['pages']],'SOURCE_SCOPE_CHANGED: complete page inventory required')
def load_project(project):
 d=read(project/'CourseProject.json');require(d['schema_version']=='course-project-1','Unsupported project');verify_source(project,d);return d

def validate_plan(plan,source):
 require(isinstance(plan,dict),'PLAN_TYPE: object required')
 require(set(plan)<= {'title','formal_master','scenes','coverage','unresolved_issues','scope_statement','scope_source_sha256','selected_pages','pronunciation','layout','voice'},'INDEPENDENT_TEXT_OR_UNKNOWN_FIELD: use single formal master')
 if 'voice' in plan:
  v=plan['voice'];require(isinstance(v,dict) and set(v)=={'name','rate'} and all(isinstance(x,str) and x.strip() for x in v.values()),'VOICE_CONFIG: only nonempty name and rate strings are allowed')
 require(plan['scope_source_sha256']==source['sha256'] and plan['selected_pages']==source['selected_pages'],'SOURCE_SCOPE_BINDING: exact source and full selected scope required')
 master=plan['formal_master'];require(master and all(isinstance(n['text'],str) and n['text'].strip() for n in master),'FORMAL_MASTER: full text required')
 ids=[n['id'] for n in master];require(len(ids)==len(set(ids)),'DUPLICATE_SENTENCE');sentences={n['id']:n for n in master};pages=set(source['selected_pages'])
 for n in master:
  require(set(n)=={'id','text','source_pages','scene_id'},'FORMAL_FIELDS: no separate voice/caption text')
  require(n['source_pages'] and set(n['source_pages'])<=pages,'DANGLING_SOURCE: sentence')
 sceneids=[s['id'] for s in plan['scenes']];require(sceneids and len(sceneids)==len(set(sceneids)),'DUPLICATE_SCENE')
 require([n for s in plan['scenes'] for n in s['sentence_ids']]==ids,'SCRIPT_ORDER_OR_COVERAGE: scenes must partition complete master in order')
 require(set(plan['layout']['scenes'])==set(sceneids),'LAYOUT_SCENES: exact scene coverage required')
 visualids=set()
 for s in plan['scenes']:
  require(s['sentence_ids'] and set(s['source_pages'])<=pages,'SCENE_SOURCE: invalid scope')
  require(all(sentences[n]['scene_id']==s['id'] and set(sentences[n]['source_pages'])<=set(s['source_pages']) for n in s['sentence_ids']),'SCENE_OWNERSHIP: mismatched sentence/source')
  objs=s['source_crops']+s['formula_objects'];oi=[x['id'] for x in objs];require(oi and len(oi)==len(set(oi)),'OBJECT_IDS: missing/duplicate')
  visualids.update(s['id']+'.'+x for x in oi)
  cfg=plan['layout']['scenes'][s['id']];require(set(cfg)<= {'objects','labels'},'LAYOUT_OVERRIDE_FORBIDDEN: no formula/text substitutions');require(set(cfg['objects'])==set(oi),'LAYOUT_OBJECTS: exact coverage required')
  for c in s['source_crops']:
   b=c['bbox_normalized'];require(c['page'] in s['source_pages'] and len(b)==4 and 0<=b[0]<b[2]<=1 and 0<=b[1]<b[3]<=1,'SOURCE_CROP: invalid region');require(c['white_matte_safe'] is True,'UNSUPPORTED_ASSET_MATTE')
   require(len(cfg['objects'][c['id']])==4,'CROP_LAYOUT: x,y,width,height required')
  for f in s['formula_objects']:
   require(f['source_page'] in s['source_pages'] and f['reveal_sentence_id'] in s['sentence_ids'],'FORMULA_SOURCE_OR_TIMING');require(isinstance(f['latex'],str) and f['latex'],'FORMULA_EMPTY');require(len(cfg['objects'][f['id']])==3,'FORMULA_LAYOUT: x,y,font_size required')
  cues=set()
  for a in s['teaching_actions']:
   require(a['action']=='frame' and a['sentence_id'] in s['sentence_ids'] and a['target_id'] in oi,'UNSUPPORTED_OR_DANGLING_ACTION');require(a['sentence_id'] not in cues,'ATTENTION_CONFLICT: one explicit frame per sentence');cues.add(a['sentence_id'])
  for label in cfg.get('labels',[]):require(label['target'] in oi,'DANGLING_LABEL_TARGET')
 coverage=plan['coverage'];require(coverage and {c['source_page'] for c in coverage}==pages,'COVERAGE_PAGES: no selected page may disappear')
 covered=set()
 for c in coverage:
  require(c['source_item'].strip() and c['formal_sentence_ids'],'COVERAGE_ITEM: named item and treatment required')
  require(set(c['formal_sentence_ids'])<=set(ids) and set(c['visual_object_ids'])<=visualids,'COVERAGE_REFERENCE: invalid source treatment')
  require(all(c['source_page'] in sentences[n]['source_pages'] for n in c['formal_sentence_ids']),'COVERAGE_SOURCE: unrelated sentence anchors');covered.update(c['formal_sentence_ids'])
 require(covered==set(ids),'COVERAGE_SENTENCES: every formal sentence needs source treatment')
 require(set(plan.get('pronunciation',{}))<=set(ids),'PRONUNCIATION_REFERENCE')
 for issue in plan['unresolved_issues']:
  require(issue['source_page'] in pages and issue['severity'] in ('info','warning','blocker') and issue['description'].strip() and issue['handling'].strip(),'ISSUE_FIELDS: explicit severity and handling required')
  require(issue['severity']!='blocker','SOURCE_BLOCKED: '+issue['description'])
 from voice_adapter import plan_from_lesson,validate_spoken_policy
 validate_spoken_policy(plan_from_lesson(voice_document(plan)))
 return plan

def voice_document(plan):
 return {'narration':[{'id':n['id'],'text':n['text'],**({'speech_adaptations':plan['pronunciation'][n['id']]} if n['id'] in plan.get('pronunciation',{}) else {})} for n in plan['formal_master']],'voice':plan.get('voice',profile()['voice'])}
def export_voice(project,data):
 validate_plan(data['LessonPlan'],data['SourcePackage']);v=voice_document(data['LessonPlan']);key=digest(v);folder=project/'derived/voice'/key;folder.mkdir(parents=True,exist_ok=True);path=folder/'voice-input.json'
 if path.exists():require(read(path)==v,'CACHE_TAMPER: voice input')
 else:atomic_write(path,v)
 formal=[{'id':n['id'],'text':n['text']} for n in data['LessonPlan']['formal_master']];fp=project/'derived/formal'/digest(formal);fp.mkdir(parents=True,exist_ok=True)
 if not (fp/'formal.json').exists():atomic_write(fp/'formal.json',formal)
 require(read(fp/'formal.json')==formal,'CACHE_TAMPER: formal master')
 atomic_write(fp/'caption-refs.json',[{'narration_id':n['id'],'source_range':[0,len(n['text'])]} for n in formal])
 return path,key,fp

def setup_fonts(project):
 """Select installed SC faces for the default Chinese course profile, never download."""
 from fontTools.ttLib import TTCollection
 cache=project/'derived/fonts';cache.mkdir(parents=True,exist_ok=True);result={}
 for weight,name in [('REGULAR','Regular'),('HEADING','Bold')]:
  env='CIRCUIT_FONT_'+weight
  if os.environ.get(env):require(Path(os.environ[env]).is_file(),'FONT_MISSING');result[weight]={'path':os.environ[env],'sha256':sha(os.environ[env])};continue
  matches=list(Path('/usr/share/fonts').rglob('NotoSansCJK-'+name+'.ttc'));require(matches,'FONT_UNAVAILABLE: configure an installed Unicode font before rendering')
  collection=TTCollection(matches[0]);face=next((f for f in collection.fonts if any('Noto Sans CJK SC' in n.toUnicode() for n in f['name'].names if n.nameID in (1,4))),None);require(face is not None,'FONT_SC_FACE_MISSING')
  target=cache/('NotoSansCJKsc-'+name+'.otf')
  if not target.exists():face.save(target)
  os.environ[env]=str(target);result[weight]={'path':str(target),'sha256':sha(target),'installed_source_sha256':sha(matches[0])}
 return result

def check_font_coverage(fonts,plan):
 from fontTools.ttLib import TTFont
 texts=[plan['title']]+[n['text'] for n in plan['formal_master']]+[s['title'] for s in plan['scenes']]+[l['text'] for c in plan['layout']['scenes'].values() for l in c.get('labels',[])]
 chars={ord(c) for t in texts for c in t if not c.isspace()}
 for entry in fonts.values():
  font=TTFont(entry['path']);covered=set().union(*(set(t.cmap) for t in font['cmap'].tables if t.isUnicode()));missing=chars-covered;require(not missing,'FONT_GLYPHS_MISSING: '+','.join(hex(c) for c in sorted(missing)));font.close()

def normalize(project,data,voice_path,raw,out,projection):
 import edge_display
 r=edge_display.normalize(voice_path,raw,out,allow_whitespace_comma_projection=projection);r['_receipt_base']=str(out);return r

def dispatch(a,attempt):
 project=a.project.resolve();run=attempt.path.parent;attempt.stage(a.command);started=time.monotonic();impl=identity();attempt.environment({'implementation_sha256':digest(impl),'python':sys.version,'code_files':impl})
 if a.command=='prepare':
  require(not (project/'CourseProject.json').exists(),'PROJECT_EXISTS: choose fresh project; rework uses ingest')
  import fitz
  pages=[int(x) for x in a.pages.split(',')];require(pages==sorted(set(pages)) and pages,'SCOPE: ascending complete selected pages required')
  shutil.copyfile(a.source,run/'source-input.original.pdf');attempt.record.update(input_sha256=sha(run/'source-input.original.pdf'),input_encoding='original PDF bytes');attempt.stage('import_original');source=project/'source';source.mkdir(exist_ok=True);dst=source/'original.pdf';shutil.copyfile(run/'source-input.original.pdf',dst);rows=[]
  with fitz.open(dst) as doc:
   require(all(1<=n<=len(doc) for n in pages),'SCOPE_PAGE_RANGE')
   for n in pages:
    page=doc[n-1];im=source/f'page-{n:04d}.png';txt=source/f'page-{n:04d}.txt';page.get_pixmap(matrix=fitz.Matrix(1600/page.rect.width,1600/page.rect.width),alpha=False).save(im);txt.write_text(page.get_text())
    rows.append({'page':n,'image_path':str(im.relative_to(project)),'image_sha256':sha(im),'text_path':str(txt.relative_to(project)),'text_sha256':sha(txt),'width':page.rect.width,'height':page.rect.height})
  data={'schema_version':'course-project-1','SourcePackage':{'original_path':str(dst.relative_to(project)),'display_name':a.source.name,'sha256':sha(dst),'selected_pages':pages,'pages':rows,'page_image_width':1600,'brief':a.brief,'use_scope':'Private teaching preview; no public redistribution authorization inferred'},'LessonPlan':None,'MediaTimeline':None,'BuildManifest':{'created_at':timestamp(),'publication_allowed':False,'scientific_certification':False}}
  commit(project,data);request=(HERE/'authoring/AUTHOR_PROMPT.md').read_text();(project/'author-request.md').write_text(request+'\n\nActual source package:\n'+json.dumps(data['SourcePackage'],ensure_ascii=False,indent=2)+'\nProject root: '+str(project)+'\n');return {'status_detail':'READY_FOR_FRESH_NATIVE_AUTHOR','project':str(project/'CourseProject.json'),'author_request':str(project/'author-request.md')}
 shutil.copyfile(project/'CourseProject.json',run/'project-input.original.json');attempt.record.update(input_sha256=sha(run/'project-input.original.json'),input_encoding='unified project original JSON bytes');attempt.stage(a.command);data=load_project(project);require(sha(project/'CourseProject.json')==sha(run/'project-input.original.json'),'PROJECT_CHANGED_DURING_READ')
 if a.command=='ingest':
  shutil.copyfile(a.plan,run/'author-response.original.json');attempt.record.update(input_sha256=sha(run/'author-response.original.json'),input_encoding='raw author response JSON bytes');attempt.stage('validate_master');plan=validate_plan(read(a.plan),data['SourcePackage']);oldvoice=digest(voice_document(data['LessonPlan'])) if data['LessonPlan'] else None
  data['LessonPlan']=plan;newvoice=digest(voice_document(plan));data['BuildManifest'].pop('preview',None);data['BuildManifest'].pop('review',None)
  if oldvoice!=newvoice:data['MediaTimeline']=None
  commit(project,data);return {'plan_sha256':digest(plan),'formal_sha256':digest([{'id':n['id'],'text':n['text']} for n in plan['formal_master']]),'voice_invalidated':oldvoice!=newvoice,'previous_reviews_reused':False}
 require(data['LessonPlan'] is not None,'AUTHORING_REQUIRED: no prepared answer is fabricated')
 voice,key,formal=export_voice(project,data)
 if a.command=='voice-input':return {'voice_input':str(voice),'voice_identity':key,'formal_export':str(formal),'network_called':False}
 if a.command in ('synthesize','bind-voice'):
  if a.command=='synthesize':
   require(a.allow_network,'AUTHORIZATION_REQUIRED: explicit opt-in and task permission required before Edge transmission');raw=run/'provider_raw';raw.mkdir()
   from voice_adapter import synthesize,plan_from_lesson
   try:asyncio.run(synthesize(plan_from_lesson(read(voice)),raw))
   except ValueError as exc:
    allowed=('Provider sentence times must be positive, ordered and nonoverlapping','Provider returned text differs from spoken request')
    if str(exc) not in allowed:raise
    atomic_write(raw/'original-adapter-rejection.json',{'exception':str(exc),'raw_evidence_preserved':True});raise ValueError('PROVIDER_PROJECTION_REQUIRED: raw output retained at '+str(raw)+'; use offline bind-voice, never repeat TTS to fix metadata') from exc
  else:raw=a.raw_run.resolve()
  r=normalize(project,data,voice,raw,run/'normalized',getattr(a,'allow_whitespace_comma_projection',False));data['MediaTimeline']={'voice_identity':key,'raw_run':str(raw),'receipt_path':str(run/'normalized/voice_receipt.normalized.json'),'projection_allowed':bool(getattr(a,'allow_whitespace_comma_projection',False)),'duration':r['audio']['duration'],'captions':r['caption_windows'],'receipt_sha256':sha(run/'normalized/voice_receipt.normalized.json')};data['BuildManifest'].pop('preview',None);data['BuildManifest'].pop('review',None);commit(project,data);return {'receipt':data['MediaTimeline']['receipt_path'],'duration':r['audio']['duration'],'exact_text_equal':r['text_binding']['exact_text_equal'],'raw_overlap_count':len(r['provider_validation']['raw_overlap_evidence'])}
 require(data['MediaTimeline'] and data['MediaTimeline']['voice_identity']==key,'AUDIO_STALE_OR_MISSING: generate/bind this exact phonetic version')
 if a.command=='render':
  fonts=setup_fonts(project);check_font_coverage(fonts,data['LessonPlan']);import course_render
  r=normalize(project,data,voice,Path(data['MediaTimeline']['raw_run']),run/'revalidated_audio',data['MediaTimeline']['projection_allowed']);prof=profile()
  from workflow_attempts import environment_fingerprint
  env=environment_fingerprint(prof,course_render.pipeline.runtime_bindings());attempt.environment(env)
  cachekey=digest({'plan':data['LessonPlan'],'source':data['SourcePackage']['sha256'],'voice':key,'events':r['provider_events_sha256'],'mp3':r['audio']['source_mp3_sha256'],'pcm':r['audio']['sha256'],'projection':r['display_policy_sha256'],'implementation':impl,'environment':env['sha256'],'samples_only':a.samples_only})
  cached=project/'cache'/(cachekey+'.json')
  if cached.exists():
   saved=read(cached);require(all(Path(path).is_file() and sha(path)==h for path,h in saved['files'].items()),'CACHE_TAMPER: render artifact');course_render.pipeline.verify_scene(read(saved['scene_path']));result={**saved,'cache_reused':True}
  else:
   scene,audio=course_render.compile_course(project,data,voice,r,prof,run/'compiled');attempt.stage('render_preview');times=sorted({o['start']+o.get('duration',0)*.5 for o in scene['objects'] if o['kind'] in ('formula','asset')}|{max(0,scene['duration']-1/prof['fps'])})
   render_started=time.monotonic();result=course_render.pipeline.render(scene,run/'media',width=prof['width'],fps=prof['fps'],video=not a.samples_only,times=times,audio=audio,renderer_factory=course_render.VisibleRenderer)
   result.update(scene_path=str(run/'compiled/scene.json'),scene_digest=scene['scene_digest'],output_dir=str(run/'media'),render_wall_seconds=time.monotonic()-render_started,static_frame_cache=course_render.VisibleRenderer.last_stats,cache_reused=False)
   if not a.samples_only:result['preview_path']=str(run/'media/preview.mp4')
   result['files']={str(p):sha(p) for folder in (run/'compiled',run/'media') for p in folder.rglob('*') if p.is_file()};atomic_write(cached,result)
  result['node_wall_seconds']=time.monotonic()-started;result['implementation_sha256']=digest(impl)
  data['BuildManifest']['preview']={**result,'plan_sha256':digest(data['LessonPlan']),'voice_identity':key,'cache_key':cachekey,'audiovisual_review':'NOT_PERFORMED','publication_allowed':False};data['BuildManifest'].pop('review',None);commit(project,data);return result
 if a.command=='qa':
  setup_fonts(project);import course_render
  preview=data['BuildManifest'].get('preview');require(preview and preview['plan_sha256']==digest(data['LessonPlan']) and preview['voice_identity']==key,'PREVIEW_STALE_OR_MISSING');require(all(sha(path)==h for path,h in preview['files'].items()),'QA_ARTIFACT_CHANGED');require(preview['implementation_sha256']==digest(impl),'QA_IMPLEMENTATION_CHANGED');course_render.pipeline.verify_scene(read(preview['scene_path']))
  if a.review:
   shutil.copyfile(a.review,run/'review.original.json');review=read(a.review);require(review['source_sha256']==data['SourcePackage']['sha256'] and review['plan_sha256']==digest(data['LessonPlan']) and review['media_sha256']==preview.get('media_sha256'),'REVIEW_STALE: exact source/plan/media required');require(review['reviewer'] and review['scope'] and isinstance(review['findings'],list),'REVIEW_FIELDS');data['BuildManifest']['review']={'receipt':str(run/'review.original.json'),'sha256':sha(a.review),'has_blockers':any(f['severity']=='blocker' for f in review['findings']),'scientific_certification':False};commit(project,data)
  result={'preview':preview.get('preview_path'),'caption_policy':'full_formal_text_exact','source_coverage':'structurally_complete; fidelity requires actual source comparison','review':data['BuildManifest'].get('review',{'status':'NOT_PERFORMED'}),'publication_allowed':False,'human_listening_required':False,'checklist':['Compare full selected source with master and visuals; retain all mandatory items','Inspect complete media, dense formulas, captions, pointer states, ending','Check real audio/receipt; record actual listening capability honestly','Reauthor only affected source/master/layout data; preserve failed attempts and revalidate downstream identities']};atomic_write(run/'QA.json',result);return result
 raise ValueError('Unknown node')

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 for name in ('prepare','ingest','voice-input','synthesize','bind-voice','render','qa'):
  q=sub.add_parser(name);q.add_argument('--project',type=Path,required=True)
  if name=='prepare':q.add_argument('--source',type=Path,required=True);q.add_argument('--pages',required=True);q.add_argument('--brief',default='面向电路学习者，用中文忠实讲解完整选定单元；保留所有重要条件、符号、图表与结论，不扩写未给出的推导。')
  elif name=='ingest':q.add_argument('--plan',type=Path,required=True)
  elif name=='synthesize':q.add_argument('--allow-network',action='store_true')
  elif name=='bind-voice':q.add_argument('--raw-run',type=Path,required=True);q.add_argument('--allow-whitespace-comma-projection',action='store_true')
  elif name=='render':q.add_argument('--samples-only',action='store_true')
  elif name=='qa':q.add_argument('--review',type=Path)
 a=p.parse_args();project=a.project.resolve();attempt=Attempt(project/'attempts',digest({k:str(v) for k,v in vars(a).items()}),'invocation arguments; actual content validated after durable start',{'status':'COLLECT_AFTER_START'})
 try:
  with file_lock(project/'.project.lock'):result=dispatch(a,attempt)
  attempt.finish('SUCCESS',result);print(json.dumps({**result,'status':'SUCCESS','result_status':result.get('status'),'run_id':attempt.run_id},ensure_ascii=False));return 0
 except BaseException as exc:
  attempt.finish('FAILED',error=exc);print(json.dumps({'status':'FAILED','run_id':attempt.run_id,'stage':attempt.record['stage'],'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
