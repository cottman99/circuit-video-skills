#!/usr/bin/env python3
"""Compile one authored lesson, render frozen world geometry, and check media.
No network, TTS, uploading, or publication. Unvoiced previews are labeled silent.
"""
from pathlib import Path
import argparse,copy,hashlib,json,math,subprocess,sys,os,tempfile
os.environ.setdefault("MPLCONFIGDIR",str(Path(tempfile.gettempdir())/"circuit-video-matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME",str(Path(tempfile.gettempdir())/"circuit-video-cache"))
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'rendering'))
from PIL import Image,ImageDraw
import logical_scene as native
import type_styles as typography
import layout_constraints as layout
from world_canvas import CanvasRenderer,ADAPTER

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(data):return json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(data):return hashlib.sha256(canonical(data).encode()).hexdigest()
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def require(ok,message):
    if not ok:raise ValueError(message)
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def rectangle(box):return isinstance(box,list) and len(box)==4 and all(finite(x) for x in box) and min(box[2:])>0

def runtime_bindings():
    result={p.relative_to(ROOT).as_posix():sha(p) for folder in ['rendering','style'] for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and p.suffix in ['.py','.json']}
    result['scripts/pipeline.py']=sha(__file__)
    return {'files':result,'fonts':{str(w):sha(p) for w,p in typography.FONTS.items()}}

def compile_data(lesson,base=None):
    L=copy.deepcopy(lesson);require(L.get('schema_version')=='circuit-lesson-1','Unsupported authored schema')
    D=L['duration'];require(finite(D) and D>0,'Invalid duration')
    require(set(L.get('required_capabilities',[]))<=set(ADAPTER['capabilities']),'Unsupported renderer capability')
    catalog=L.get('source_catalog')
    if catalog:
        require(base is not None,'PDF source catalog requires a project base directory')
        from source_catalog_assets import CatalogAssets
        assets=CatalogAssets(catalog,base);assets.close()
    objects=L['objects'];ids=[o['id'] for o in objects];require(len(ids)==len(set(ids)),'Duplicate object IDs')
    require(set(L['required_object_ids'])==set(ids),'Incomplete authored object universe')
    nodes={n['id'] for n in L['knowledge_graph']['nodes']};require(len(nodes)==len(L['knowledge_graph']['nodes']),'Duplicate knowledge IDs')
    adjacency={n:[] for n in nodes}
    for edge in L['knowledge_graph']['edges']:
        require(edge['from'] in nodes and edge['to'] in nodes,'Dangling knowledge edge')
        require(edge['type'] in ['prerequisite','related','feedback'],'Unknown knowledge edge type')
        if edge['type']=='prerequisite':adjacency[edge['from']].append(edge['to'])
    visited={}
    def visit(n):
        require(visited.get(n)!=1,'Cyclic prerequisites')
        if visited.get(n)==2:return
        visited[n]=1
        for to in adjacency[n]:visit(to)
        visited[n]=2
    for n in nodes:visit(n)
    sources={s['id'] for s in L['sources']};require(len(sources)==len(L['sources']),'Duplicate source IDs')
    for n in L['knowledge_graph']['nodes']:require(set(n.get('source_refs',[]))<=sources,'Dangling source reference')
    boards=L['boards'];boardids=[b['id'] for b in boards];require(len(boardids)==len(set(boardids)),'Duplicate board IDs')
    for b in boards:
        require(rectangle(b['bounds']),'Invalid board bounds')
        require(set(b['object_refs'])<=set(ids),'Missing board object')
        require(all(i.startswith(b['id']+'.') for i in b['object_refs']),'Board object IDs must use their board prefix')
    require(set().union(*(set(b['object_refs']) for b in boards))==set(ids),'Every object must belong to a board')
    contract=copy.deepcopy(L['layout_contract']);config={'logical_width':1920,'logical_height':1080}
    contract['subtitles']['font_family']=typography.FAMILY
    layout.validate_contract(contract,config)
    draw=ImageDraw.Draw(Image.new('RGB',(1,1)))
    alltext=''.join(o.get('text','') for o in objects)+''.join(c['display_text'] for c in L.get('captions',[]))
    typography.validate_glyphs(alltext)
    for o in objects:
        require(o['kind'] in ['formula','asset','text','rect','line'],'Public adapter does not support this object kind')
        require(rectangle(o['world_bounds']),'Invalid authored bounds: '+o['id'])
        require(finite(o['start']) and finite(o['end']) and 0<=o['start']<o['end']<=D,'Invalid object timing')
        require(o['end']==D,'Cumulative objects must persist in world until the end')
        require(set(o.get('knowledge_refs',[]))<=nodes,'Missing object knowledge node')
        if o['kind']=='text':
            role=o['typography_role'];require(role in typography.DEFAULT_CONTRACT['roles'],'Unknown text role')
            require(finite(o['size']) and o['size']>=19,'Text below example adapter minimum')
            style=typography.DEFAULT_CONTRACT['roles'][role];o.update(font_family=typography.FAMILY,font_weight=style['weight'],color=style['color'])
            o.setdefault('xy',o['world_bounds'][:2]);box=draw.textbbox((0,0),o['text'],font=typography.object_font(o))
            o['world_bounds']=[o['xy'][0]+box[0],o['xy'][1]+box[1],box[2]-box[0],box[3]-box[1]]
        if o['kind']=='asset':
            require(catalog and o.get('asset_id') in catalog['assets'],'Missing source catalog asset')
            asset=catalog['assets'][o['asset_id']];source=catalog['sources'][asset['source_id']]
            require(source.get('redistribution_basis'),'Record the source rights or permission basis')
            require(asset.get('white_matte_safe') is True,'Only verified white-background circuit crops support this underlay adapter')
            require(finite(o['duration']) and 0<o['duration']<D-o['start'],'Invalid asset reveal')
            o['asset_sha256']=source['sha256']
        if o['kind']=='formula':
            require(finite(o['duration']) and 0<o['duration']<D-o['start'],'Invalid formula reveal')
            require(finite(o['font_size']) and o['font_size']>=24,'Formula below minimum')
            equation=native.equation(o['latex'],o['font_size'],10000)
            require(equation['size']==o['font_size'],'Implicit math shrinking is unsupported')
            o['world_bounds'][2:]=list(equation['im'].size)
            rw=o['read_window'];require(o['start']+o['duration']<=rw[0]<rw[1]<=D,'Read window precedes complete formula')
        if o['kind']=='line':require(len(o['points'])>=2 and all(len(p)==2 and all(finite(v) for v in p) for p in o['points']),'Invalid polyline')
    resolved=layout.apply_board_layout(objects,boards,contract,native);layout.validate_objects(objects,resolved)
    captions=[];previous=0
    for c in L.get('captions',[]):
        require(0<=c['start']<c['end']<=D and c['start']>=previous,'Overlapping or invalid captions');previous=c['end']
        captions.append({**c,'audio_end':c['end']})
    captions=layout.compile_captions(captions,contract,native)
    byid={o['id']:o for o in objects};actions=[];previous=0
    for a in L.get('teacher_actions',[]):
        require(a['kind'] in ['frame','arrow'],'Unsupported authored attention kind')
        require(a['target'] in byid,'Dangling attention target');target=byid[a['target']]
        require(0<=a['start']<a['end']<=D and a['start']>=previous,'Invalid or overlapping attention');previous=a['end']
        require(a['start']>=target['start']+target.get('duration',0),'Attention target is not fully revealed')
        if a['kind']=='arrow':require(len(a.get('arrow_points',[]))==2,'Arrow needs authored whitespace route')
        actions.append({**a,'world_bounds':target['world_bounds']})
    camera=L['camera_track'];previous=0
    for c in camera:
        require(c['start']==previous and c['start']<c['end']<=D,'Camera track gap/overlap');previous=c['end']
        require(rectangle(c['from']) and rectangle(c['to']),'Invalid camera bounds')
    require(previous==D,'Camera must cover complete timeline')
    scene={'schema_version':'circuit-compiled-scene-1','adapter':'circuit-world-v1','duration':D,'objects':objects,'camera_track':camera,
      'layout_contract':contract,'render_config':config,'typography_contract':copy.deepcopy(typography.DEFAULT_CONTRACT),
      'resolved_layout':resolved,'captions':captions,'teacher_actions':actions,'knowledge_graph':L['knowledge_graph'],
      'sources':L['sources'],'source_digest':digest(lesson),'runtime':runtime_bindings(),
      'timing_evidence':'authored_seconds_not_measured_speech','review_status':'not_audiovisually_reviewed'}
    if catalog:scene.update(source_catalog=catalog,asset_base=str(Path(base).resolve()))
    layout.validate_scene_layout(scene);scene['scene_digest']=digest(scene);return scene

def verify_scene(scene):
    require(scene.get('schema_version')=='circuit-compiled-scene-1','Unsupported compiled scene')
    candidate=copy.deepcopy(scene);expected=candidate.pop('scene_digest',None);require(digest(candidate)==expected,'Compiled scene was modified')
    require(scene['runtime']==runtime_bindings(),'Runtime or fonts changed; recompile authored input')
    layout.validate_scene_layout(scene)

def render(scene,out,width=1280,fps=15,video=False,times=None,audio=None):
    verify_scene(scene);require(width>0 and width%32==0,'Width must be positive and divisible by 32')
    require(finite(fps) and fps>0,'Invalid fps');out=Path(out);out.mkdir(parents=True,exist_ok=True)
    r=CanvasRenderer(scene,width=width,fps=fps);count=math.ceil(scene['duration']*fps)
    manifest={'status':'technical_preview_unreviewed','audio':'silent' if audio is None else 'user_supplied_not_alignment_certified',
      'scene_digest':scene['scene_digest'],'width':width,'height':r.config.height,'fps':fps,'frames':count,'checks':[]}
    if not video:
        times=times if times is not None else [0,scene['duration']/2,max(0,scene['duration']-1/fps)]
        for i,t in enumerate(times):
            im,receipt=r.render(t);layout.validate_frame_layout(scene,{'width':width,'fps':fps},receipt)
            im.save(out/f'frame-{i:03d}.png')
        write(out/'receipts.json',r.records);manifest['sampled_frames']=len(times)
    else:
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{width}x{r.config.height}','-framerate',str(fps),'-i','-']
        if audio:
            audio=Path(audio).resolve();require(audio.is_file(),'Missing user audio')
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(audio)]));duration=float(probe['format']['duration'])
            require(abs(duration-scene['duration'])<=1/fps,'Audio duration must match authored timeline; no hidden truncation or padding')
            cmd+=['-i',str(audio),'-c:a','aac','-b:a','192k','-ar','48000'];manifest['audio_sha256']=sha(audio)
        cmd+=['-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',str(out/'preview.mp4')]
        process=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        try:
            with (out/'receipts.jsonl').open('w') as receipts:
                for i in range(count):
                    im,receipt=r.render(i/fps,record=False);layout.validate_frame_layout(scene,{'width':width,'fps':fps},receipt)
                    process.stdin.write(im.tobytes());receipts.write(canonical(receipt)+'\n')
            process.stdin.close();require(process.wait()==0,'FFmpeg encoding failed')
        except BaseException:
            process.kill();process.wait();raise
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(out/'preview.mp4')]))
        stream=next(s for s in probe['streams'] if s['codec_type']=='video');require(int(stream['nb_read_frames'])==count,'Encoded frame count mismatch')
        subprocess.run(['ffmpeg','-v','error','-i',str(out/'preview.mp4'),'-f','null','-'],check=True)
        manifest.update(media_sha256=sha(out/'preview.mp4'),decoded_frame_count=int(stream['nb_read_frames']),checks=['full_decode','exact_frame_count','per_frame_geometry'])
    write(out/'manifest.json',manifest);return manifest

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    c=sub.add_parser('compile');c.add_argument('lesson',type=Path);c.add_argument('--output',required=True,type=Path)
    r=sub.add_parser('render');r.add_argument('scene',type=Path);r.add_argument('--output',required=True,type=Path);r.add_argument('--width',default=1280,type=int);r.add_argument('--fps',default=15,type=int);r.add_argument('--video',action='store_true');r.add_argument('--times');r.add_argument('--audio',type=Path)
    a=ap.parse_args()
    try:
        if a.command=='compile':
            require(a.lesson.resolve()!=a.output.resolve(),'Cannot overwrite authored source')
            scene=compile_data(json.loads(a.lesson.read_text()),a.lesson.parent);write(a.output,scene);print(json.dumps({'status':'compiled','objects':len(scene['objects']),'source_digest':scene['source_digest']}))
        else:
            result=render(json.loads(a.scene.read_text()),a.output,a.width,a.fps,a.video,[float(t) for t in a.times.split(',')] if a.times else None,a.audio);print(json.dumps(result))
    except (ValueError,KeyError,OSError,ImportError,subprocess.CalledProcessError) as exc:
        print(json.dumps({'status':'failed','reason':str(exc)}),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
