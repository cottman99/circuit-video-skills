#!/usr/bin/env python3
"""Optional external MinerU basic import. Never installs models or edits a course project."""
import argparse, copy, hashlib, json, math, os, socket, sys, time
from pathlib import Path

OFFLINE = {'ORT_DISABLE_TELEMETRY':'1','HF_HUB_DISABLE_TELEMETRY':'1',
 'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','DO_NOT_TRACK':'1',
 'GRADIO_ANALYTICS_ENABLED':'False','MINERU_MODEL_SOURCE':'local',
 'MINERU_INTRA_OP_NUM_THREADS':'4','MINERU_INTER_OP_NUM_THREADS':'1',
 'MINERU_CPU_NUM_THREADS':'4','OMP_NUM_THREADS':'4'}
VERSION = 'mineru-source-adapter-1.1'

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def load(path):return json.loads(Path(path).read_text())
def save(path,data):
 p=Path(path);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,p)
def require(ok,code):
 if not ok:raise ValueError(code)
def relative_file(root,value):
 require(isinstance(value,str) and value and not Path(value).is_absolute(),'ASSET_PATH')
 p=(root/value).resolve();require(p.is_relative_to(root.resolve()),'ASSET_PATH_ESCAPE');require(p.is_file(),'ASSET_MISSING: '+value);return p

def source_input(project_path):
 project=Path(project_path).resolve();data=load(project);source=data.get('SourcePackage',data)
 root=project.parent;pdf=relative_file(root,source['original_path'])
 require(sha(pdf)==source['sha256'],'SOURCE_HASH')
 pages=source['selected_pages'];require(pages and pages==sorted(set(pages)) and all(type(p) is int and p>0 for p in pages),'SOURCE_SCOPE')
 require([p['page'] for p in source['pages']]==pages,'SOURCE_PAGE_INVENTORY')
 for page in source['pages']:require(sha(relative_file(root,page['image_path']))==page['image_sha256'],'SOURCE_IMAGE_HASH')
 return source,root,pdf

def normalize(source,raw,output_root,raw_path):
 """Keep returned order and content; provenance is not a scientific assertion."""
 require(raw.get('schema')=='docvortex.middle' and raw.get('schema_version')=='2.0','PARSER_SCHEMA')
 require(raw.get('metadata',{}).get('producer')=={'name':'mineru','version':'4.0.12'},'PARSER_VERSION')
 pages=raw['pages'];require([p['page_idx']+1 for p in pages]==source['selected_pages'],'PARSER_SCOPE')
 source_pages={p['page']:p for p in source['pages']};out=[];warnings=[]
 known={'text','paragraph_title','header','footer','page_number','equation','image','table','list','code'}
 for page in pages:
  physical=page['page_idx']+1;blocks=[];seen=set()
  for order,b in enumerate(page['blocks']):
   idx=b['index'];require(type(idx) is int and idx not in seen,'BLOCK_INDEX');seen.add(idx)
   blockid=f'page-{physical:04d}.block-{idx:04d}';box=b.get('bbox');valid=isinstance(box,list) and len(box)==4 and all(type(v) in (int,float) and math.isfinite(v) for v in box) and 0<=box[0]<box[2]<=1 and 0<=box[1]<box[3]<=1
   local=[]
   if not valid:local.append({'code':'INVALID_BBOX','handling':'Use original page for the affected block; no automatic parser fallback.'})
   if b.get('type') not in known:local.append({'code':'UNSUPPORTED_BLOCK_TYPE','handling':'Raw block retained; use original-page evidence for affected content.'})
   content=b.get('content');refs=[]
   def images(item):
    if isinstance(item,dict):
     if item.get('image_path'):
      asset=relative_file(output_root,item['image_path']);refs.append({'path':str(asset),'sha256':sha(asset),'parser_bbox':item.get('bbox')})
     for value in item.values():images(value)
    elif isinstance(item,list):
     for value in item:images(value)
   images(b)
   if b.get('type')=='equation':
    require(isinstance(content,str),'EQUATION_CONTENT');text_math=[{'type':'latex','content':content}]
   elif isinstance(content,list):
    text_math=[copy.deepcopy(s) for s in content if isinstance(s,dict) and s.get('type') in ('text','equation_inline')]
   else:text_math=[]
   if not content:local.append({'code':'EMPTY_BLOCK_CONTENT','handling':'Original page remains authoritative.'})
   block={'id':blockid,'reading_order':order,'parser_index':idx,'type':b.get('type'),
    'physical_page':physical,'bbox_normalized':box,'bbox_valid':valid,'text_math':text_math,
    'figure_refs':refs,'raw_content':content,'source_page_image':source_pages[physical]['image_path'],
    'raw_block_locator':f'/pages/{len(out)}/blocks/{order}','warnings':local}
   blocks.append(block);warnings.extend({'block_id':blockid,**w} for w in local)
  if not blocks:warnings.append({'physical_page':physical,'code':'EMPTY_PAGE','handling':'Original page retained; source coverage unresolved.'})
  out.append({'physical_page':physical,'blocks':blocks})
 result=copy.deepcopy(source)
 result['extraction']={'adapter_version':VERSION,'producer':raw['metadata']['producer'],
  'source_sha256':source['sha256'],'selected_pages':source['selected_pages'],
  'raw_output':str(raw_path),'raw_sha256':sha(raw_path),'pages':out,'warnings':warnings,
  'provider_warnings':raw.get('warnings'),'confidence':None,
  'parser_extensions':raw.get('extensions',{}),'semantic_validation':False,
  'circuit_netlist':None,'reading_order_policy':'Preserve parser array order, never sort by coordinates.',
  'fallback_policy':'Only a diagnosed affected block may use its original page/crop; no serial parser sweep.'}
 return result

def run_parser(pdf,pages,output,home,model_manifest):
 require(not any(n=='onnxruntime' or n=='mineru' or n.startswith('mineru.') for n in sys.modules),'OFFLINE_INIT_TOO_LATE')
 os.environ.update(OFFLINE);os.environ['MINERU_HOME']=str(home.resolve());os.environ['HF_HOME']=str(output/'hf-offline')
 manifest=load(model_manifest);modelroot=home/'models/MinerU-4_models_onnx';require(manifest.get('files'),'MODEL_MANIFEST_EMPTY')
 for row in manifest['files']:
  path=relative_file(modelroot,row['path']);require(path.stat().st_size==row['size'] and sha(path)==row['sha256'],'MODEL_HASH: '+row['path'])
 def deny_network(*args,**kwargs):raise RuntimeError('OFFLINE_ONLY: missing local dependency must not download')
 socket.socket.connect=deny_network;socket.create_connection=deny_network
 from importlib.metadata import version
 require(version('mineru')=='4.0.12','INSTALLED_PARSER_VERSION')
 from mineru.parser import MinerUParser
 from mineru.parser.writer import FileBasedDataWriter
 parser=MinerUParser(tier='basic',parse_mode='auto',image_analysis=True)
 result=parser.parse(str(pdf),page_range=','.join(map(str,pages)));raw=output/'raw';raw.mkdir()
 result.save(FileBasedDataWriter(str(raw)))
 return raw/'middle_json.json',{'model_manifest_sha256':sha(model_manifest),'offline_env':OFFLINE,
  'settings':{'tier':'basic','parse_mode':'auto','image_analysis':True},
  'network_evidence':'Main-process Python socket connect denied; spawned workers inherit offline/telemetry environment, not this socket guard. No whole-process-tree network audit.'}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
 group=ap.add_mutually_exclusive_group(required=True);group.add_argument('--run-local',action='store_true');group.add_argument('--raw',type=Path)
 ap.add_argument('--mineru-home',type=Path);ap.add_argument('--model-manifest',type=Path);ap.add_argument('--raw-source-sha256')
 a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False);started=time.time();status={'status':'RUNNING','started_at_unix':started,'adapter_version':VERSION};save(a.output/'attempt.json',status)
 try:
  project_sha=sha(a.project);source,root,pdf=source_input(a.project);save(a.output/'SourcePackage.input.json',source)
  if a.run_local:
   require(a.mineru_home and a.model_manifest,'EXTERNAL_SETUP_REQUIRED: manually install and cache models first')
   raw,execution=run_parser(pdf,source['selected_pages'],a.output,a.mineru_home,a.model_manifest)
  else:
   require(a.raw_source_sha256==source['sha256'],'RAW_SOURCE_BINDING_REQUIRED');raw=a.raw.resolve();execution={'mode':'Existing external parser output, not fresh parser execution','supplied_source_sha256':a.raw_source_sha256,'source_binding':'Host-supplied association, not independently re-derived'}
  require(sha(pdf)==source['sha256'] and sha(a.project)==project_sha,'SOURCE_CHANGED_DURING_IMPORT')
  result=normalize(source,load(raw),raw.parent,raw);result['source_base']=str(root);result['extraction']['input_project']={'path':str(a.project.resolve()),'sha256':project_sha};result['extraction']['execution']=execution
  result['extraction']['wall_seconds']=time.time()-started;save(a.output/'SourcePackage.import.json',result)
  status.update(status='SUCCESS',output_sha256=sha(a.output/'SourcePackage.import.json'),warnings=len(result['extraction']['warnings']))
 except BaseException as exc:
  status.update(status='FAILED',error=str(exc));raise
 finally:
  status.update(completed_at_unix=time.time(),wall_seconds=time.time()-started);save(a.output/'attempt.json',status)
if __name__=='__main__':main()
