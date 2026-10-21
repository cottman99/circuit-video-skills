#!/usr/bin/env python3
"""Offline semantic timeline audit. Declared geometry is not rendered-media certification."""
import argparse, hashlib, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'rendering'))
from caption_contract import resolve_captions


def audit(scene, root='.'):
    findings=[]; root=Path(root).resolve()
    def add(code, status, detail, evidence='declared_exact'):
        findings.append(dict(code=code,status=status,detail=detail,evidence=evidence))
    def finite(values, positive=False):
        if not all(isinstance(x,(int,float)) and math.isfinite(x) and (x>0 if positive else True) for x in values):raise ValueError('Nonfinite or invalid geometry')
    def interval(v):
        a,b=float(v['start']),float(v['end'])
        if not (math.isfinite(a) and math.isfinite(b) and 0<=a<b<=duration): raise ValueError('Invalid interval')
        return a,b
    duration=float(scene['duration'])
    if not math.isfinite(duration) or duration<=0: raise ValueError('Invalid duration')
    objects={o['id']:o for o in scene.get('semantic_objects',[])}
    if len(objects)!=len(scene.get('semantic_objects',[])):add('object_identity','fail','Duplicate IDs')
    for o in objects.values():
        if not o.get('persistent',True) and o.get('role')!='teacher_overlay':add('retention','review',o['id']+' removed: check explicit pedagogical reason','human_review')
    keys=scene.get('camera_keyframes',[])
    if keys and (keys!=sorted(keys,key=lambda x:x['time']) or len({k['time'] for k in keys})!=len(keys)):raise ValueError('Camera times must strictly increase')
    size=scene.get('output_size',[16,9]);finite(size,True)
    if len(size)!=2:raise ValueError('output_size must have two entries')
    aspect=float(size[0])/float(size[1])
    safe=scene.get('viewport_safe_area',[0,0,*size]);finite(safe)
    if len(safe)!=4 or safe[0]<0 or safe[1]<0 or safe[2]<=0 or safe[3]<=0 or safe[0]+safe[2]>size[0] or safe[1]+safe[3]>size[1]:raise ValueError('Invalid safe area')
    for k in keys:
        finite([k['time'],*k['center']]);finite([k['viewport_width']],True)
        if len(k['center'])!=2 or not 0<=k['time']<=duration:raise ValueError('Invalid camera')
        if k.get('easing','linear') not in ('linear','smoothstep','smooth','hold'):raise ValueError('Unsupported easing')
    for o in objects.values():
        box=o.get('world_bounds',o.get('local_bounds',[]));finite(box)
        if len(box)!=4 or min(box[2:])<0:raise ValueError('Invalid bounds')
        finite(o.get('world_origin',[0,0]));finite([o.get('visible_from',0),o.get('draw_duration',0)])
        if o.get('visible_from',0)<0 or o.get('draw_duration',0)<0:raise ValueError('Negative draw time')
    def camera(t):
        if not keys:return None
        a=keys[0]
        for b in keys[1:]:
            if t<=b['time']:
                q=max(0,min(1,(t-a['time'])/(b['time']-a['time'])))
                easing=b.get('easing','linear')
                if easing in ('smoothstep','smooth'):q=q*q*(3-2*q)
                elif easing=='hold':q=0 if q<1 else 1
                elif easing!='linear':raise ValueError('Unsupported camera easing '+easing)
                c=[x+(y-x)*q for x,y in zip(a['center'],b['center'])];w=a['viewport_width']+(b['viewport_width']-a['viewport_width'])*q
                return c,w
            a=b
        return a['center'],a['viewport_width']
    def bounds(o):
        b=o.get('world_bounds')
        if b is not None:return b
        x,y,w,h=o['local_bounds'];ox,oy=o.get('world_origin',[0,0]);return [ox+x,oy+y,w,h]
    focuses=scene.get('focus_windows',[])
    if not focuses:add('focus_coverage','unknown','No focus windows supplied')
    if focuses:
        merged=[]
        for a,b in sorted(interval(f) for f in focuses):
            if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
            else:merged.append([a,b])
        gaps=[];cursor=0
        for a,b in merged:
            if a>cursor:gaps.append([cursor,a])
            cursor=max(cursor,b)
        if cursor<duration:gaps.append([cursor,duration])
        add('focus_timeline_coverage','review' if gaps else 'pass',{'audited_windows':merged,'undeclared_intervals':gaps,'note':'Gaps may be intentional transitions; no full-timeline claim without review.'},'coverage_accounting')
        if merged[-1][1]<duration:add('terminal_focus_coverage','unknown','Terminal interval has no declared focus; overview/last-frame framing not established')
    for f in focuses:
        a,b=interval(f);oid=f['target_id'];o=objects.get(oid)
        if o is None:add('focus_target','fail',oid);continue
        if not keys:add('viewport_clip','unknown',oid+': no camera data');continue
        # All camera segment boundaries plus window endpoints. Monotone common interpolation
        # makes each rectangular edge constraint affine in q: endpoints establish containment.
        times=sorted({a,b,*[k['time'] for k in keys if a<k['time']<b]})
        x,y,w,h=bounds(o);ok=True
        for t in times:
            c,vw=camera(t);vh=vw/aspect
            left=c[0]-vw/2+safe[0]*vw/size[0];top=c[1]-vh/2+safe[1]*vh/size[1]
            right=left+safe[2]*vw/size[0];bottom=top+safe[3]*vh/size[1]
            ok &= x>=left-1e-8 and y>=top-1e-8 and x+w<=right+1e-8 and y+h<=bottom+1e-8
        add('viewport_clip','pass' if ok else 'fail',oid+' '+str([a,b]),'mathematically_verified_declared_geometry')
        if f.get('inspection'):
            moving=False
            for ka,kb in zip(keys,keys[1:]):
                if max(a,ka['time'])<min(b,kb['time']) and (ka['center']!=kb['center'] or ka['viewport_width']!=kb['viewport_width']):
                    if kb.get('easing')!='hold' or a<kb['time']<b:moving=True
            for m in scene.get('motion_windows',[]):
                ma,mb=interval(m)
                if m.get('target_id') in (None,oid) and max(a,ma)<min(b,mb):moving=True
            complete=o.get('visible_from',0)+o.get('draw_duration',0)
            add('inspection_stability','fail' if moving or complete>a else 'pass',oid+' '+str([a,b]))
    mentions=scene.get('narration_mentions',[])
    if not mentions:add('narration_reveal','unknown','No aligned narration mentions')
    for n in mentions:
        a,b=interval(n);o=objects.get(n['target_id'])
        ready=o.get('visible_from',0)+(o.get('draw_duration',0) if n.get('requires_complete',True) else 0) if o else math.inf
        add('narration_reveal','pass' if ready<=a else 'fail',n['target_id']+' ready='+str(ready)+' mention='+str(a))
    cues=scene.get('subtitles',scene.get('captions',[]))
    # Time-window coverage is not spoken-text coverage. Legacy declarations
    # without canonical narration/reference slices cannot earn a textual PASS.
    if 'narration' not in scene:
        add('subtitle_text_coverage','unknown','Missing canonical narration and source-reference captions')
    else:
        try:
            _,coverage=resolve_captions(scene['narration'],cues,duration,compiled=bool(cues and 'text' in cues[0]))
            add('subtitle_text_coverage','pass' if scene['narration'] else 'unknown',coverage,'exact_ordered_source_slices')
        except (KeyError,TypeError,ValueError) as error:
            add('subtitle_text_coverage','fail',str(error))
    if not cues:add('subtitle_coverage','unknown','No subtitle cues')
    else:
        ordered=sorted(cues,key=lambda x:x['start']);last=0
        for c in ordered:
            a,b=interval(c)
            add('subtitle_overlap','fail' if a<last-1e-6 else 'pass',str([a,b]));last=max(last,b)
            lines=c.get('text','').splitlines()
            orphan=any(len(''.join(ch for ch in line if ch.isalnum()))<=1 for line in lines)
            add('subtitle_orphan','review' if orphan else 'pass',c.get('text','Unmaterialized source-reference caption'),'heuristic')
        windows=scene.get('speech_windows')
        if windows is None:add('subtitle_coverage','unknown','No measured speech windows; silence is not assumed speech')
        for s in windows or []:
            a,b=interval(s);cursor=a
            for c in ordered:
                if c['end']<=cursor:continue
                if c['start']>cursor+scene.get('subtitle_gap_tolerance',0.08):break
                cursor=max(cursor,c['end'])
                if cursor>=b:break
            add('subtitle_coverage','pass' if cursor>=b else 'fail',str([a,b]))
    if 'overlays' not in scene:add('overlay_lifetime','unknown','Overlay declarations absent; [] means intentionally none')
    for overlay in scene.get('overlays',[]):
        a,b=interval(overlay);oid=overlay['target_id']
        valid=oid in objects and any(f['target_id']==oid and f['start']<=a and b<=f['end'] for f in focuses)
        add('overlay_lifetime','pass' if valid else 'fail',overlay['id'])
        if overlay.get('flash') or overlay.get('breathing'):add('overlay_motion','fail',overlay['id'])
    params=scene.get('parameters',{});uses=scene.get('parameter_uses',[])
    if not uses:add('parameter_consistency','unknown','No artifact parameter references')
    for use in uses:
        p=params.get(use['parameter_id']);ok=p is not None and p.get('unit')==use.get('unit') and p.get('value')==use.get('value') and p.get('model_id')==use.get('model_id')
        add('parameter_consistency','pass' if ok else 'fail',use['parameter_id']+' @ '+use.get('artifact','unknown'))
    files=scene.get('provenance',[])
    if not files:add('provenance','unknown','No artifact hashes supplied')
    for f in files:
        p=(root/f['path']).resolve()
        if root not in p.parents:raise ValueError('Provenance path escapes root')
        ok=p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']
        add('provenance','pass' if ok else 'fail',f['path'],'cryptographic_integrity_not_truth')
    add('rendered_review','review','Inspect encoded focus geometry, subtitle legibility, glow strength, actual spoken content, pacing and final-frame transitions','sampled_manual_pending')
    counts={s:sum(f['status']==s for f in findings) for s in ('pass','fail','unknown','review')}
    return {'schema_version':'1.0','automatic_checks_passed':counts['fail']==0,'complete_evidence':counts['unknown']==0,'counts':counts,'findings':findings,'scope':'Exact checks concern supplied declarations only; hashes prove bytes, not provenance truth. No perceptual/learning certification.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('scene');p.add_argument('--root');p.add_argument('--output');a=p.parse_args()
    try:r=audit(json.loads(Path(a.scene).read_text()),a.root or Path(a.scene).parent)
    except (KeyError,TypeError,ValueError,OSError,ZeroDivisionError) as e:r={'automatic_checks_passed':False,'error':str(e)}
    text=json.dumps(r,ensure_ascii=False,indent=2);print(text)
    if a.output:Path(a.output).write_text(text+'\n')
    raise SystemExit(0 if r['automatic_checks_passed'] else 1)
