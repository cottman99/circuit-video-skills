#!/usr/bin/env python3
"""Audit renderer-exported pointer samples; not forced alignment or perceptual proof."""
import argparse
import json
import math
from pathlib import Path


def audit(data):
    findings=[]
    def add(code,status,detail): findings.append(dict(code=code,status=status,detail=detail))
    def num(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
    def vec(v,n): return isinstance(v,list) and len(v)==n and all(num(x) for x in v)
    def box(v): return vec(v,4) and v[2]>=0 and v[3]>=0
    duration=data.get('duration');size=data.get('output_size')
    if not num(duration) or duration<=0 or not vec(size,2) or min(size)<=0: raise ValueError('Invalid duration/output size')
    policy=data.get('production_policy')
    if policy is None:add('production_policy','unknown','Declare infinite persistent canvas and semantic pointer defaults or explicit user exception')
    else:
        default=policy.get('layout')=='infinite_persistent_canvas' and policy.get('pointer')=='semantic_teacher_pointer'
        exception=policy.get('explicit_user_exception')
        authorized=isinstance(exception,str) and bool(exception.strip())
        add('production_policy','pass' if default else 'review' if authorized else 'fail',policy)
    safe=data.get('viewport_safe_area')
    if safe is None:add('safe_area','unknown','No viewport safe area supplied')
    elif not box(safe) or safe[0]<0 or safe[1]<0 or safe[0]+safe[2]>size[0] or safe[1]+safe[3]>size[1]:raise ValueError('Invalid viewport safe area')
    events=data.get('events',[]);samples=data.get('samples',[]);ids={}
    for e in events:
        eid=e['id']
        if eid in ids: add('event_identity','fail',eid)
        ids[eid]=e
        if not all(num(e.get(k)) for k in ('start','end')) or not 0<=e['start']<e['end']<=duration: raise ValueError('Invalid event span: '+eid)
        kind=e.get('kind');role=e.get('semantic_role')
        valid=kind in ('dot','frame','arrow') and bool(e.get('target_id'))
        valid &= (kind!='dot' or role in ('reveal','point')) and (kind!='frame' or role=='region') and (kind!='arrow' or role=='relation' and bool(e.get('source_id')) and e['source_id']!=e.get('target_id'))
        add('semantic_role','pass' if valid else 'fail',eid)
    for i,a in enumerate(events):
        for b in events[i+1:]:
            if max(a['start'],b['start'])<min(a['end'],b['end']) and a.get('target_id')!=b.get('target_id'):
                add('primary_attention_overlap','fail',[a['id'],b['id']])
    byid={eid:[] for eid in ids}
    for s in samples:
        eid=s['event_id'];e=ids.get(eid)
        if e is None: add('sample_event','fail',eid);continue
        t=s.get('time')
        if not num(t) or not e['start']<=t<=e['end']:add('sample_span','fail',eid);continue
        byid[eid].append(s)
        opacity=s.get('opacity')
        if not num(opacity) or not 0<=opacity<=1: add('opacity','fail',eid);continue
        if opacity==0:continue
        p=s.get('point');radius=s.get('radius');bounds=s.get('overlay_bounds')
        if not vec(p,2) or not num(radius) or radius<0: raise ValueError('Invalid pointer geometry')
        if bounds is None and e.get('kind')=='dot':bounds=[p[0]-radius,p[1]-radius,2*radius,2*radius]
        if not box(bounds):add('overlay_bounds','unknown',eid)
        else:
            x,y,w,h=bounds
            add('viewport','pass' if x>=0 and y>=0 and x+w<=size[0] and y+h<=size[1] else 'fail',eid)
            if safe is not None:add('safe_area','pass' if x>=safe[0] and y>=safe[1] and x+w<=safe[0]+safe[2] and y+h<=safe[1]+safe[3] else 'fail',eid)
        cid=s.get('camera_id');tcid=s.get('target_camera_id')
        add('camera_consistency','unknown' if cid is None or tcid is None else 'pass' if cid==tcid else 'fail',eid)
        if not box(s.get('target_bounds')):add('target_geometry','unknown',eid)
        glyphs=s.get('glyph_bounds')
        if glyphs is None:add('glyph_occlusion','unknown',eid)
        elif any(not box(b) for b in glyphs):raise ValueError('Invalid glyph boxes')
        elif e.get('kind')=='dot':
            hit=any((p[0]-max(x,min(p[0],x+w)))**2+(p[1]-max(y,min(p[1],y+h)))**2<radius**2 for x,y,w,h in glyphs)
            add('glyph_occlusion','fail' if hit else 'pass',eid)
        else:add('glyph_occlusion','review',eid+': inspect arrow path/frame stroke and glow; bounding boxes alone do not establish non-occlusion')
        if e.get('semantic_role')=='reveal':
            progress=s.get('progress');expected=s.get('expected_progress');front=s.get('reveal_front');offset=s.get('offset')
            if not all(num(v) for v in (progress,expected)) or not vec(front,2) or not vec(offset,2):add('reveal_tracking','unknown',eid)
            else:
                ok=0<=progress<=1 and 0<=expected<=1 and abs(progress-expected)<=1e-6 and all(abs(p[i]-front[i]-offset[i])<=1e-4 for i in (0,1))
                add('reveal_tracking','pass' if ok else 'fail',eid)
    for eid,e in ids.items():
        ss=sorted(byid[eid],key=lambda s:s['time'])
        if not ss:add('sample_coverage','unknown',eid);continue
        if not any(num(s.get('opacity')) and s['opacity']>0 for s in ss):add('visible_sample_coverage','unknown',eid)
        times=[s['time'] for s in ss]
        if len(set(times))!=len(times):add('sample_identity','fail',eid)
        add('sample_coverage','review',{'event':eid,'span':[e['start'],e['end']],'sample_span':[times[0],times[-1]],'samples':len(ss),'max_gap':max([b-a for a,b in zip(times,times[1:])],default=0),'note':'Sampled evidence only; inspect transitions, line wraps, fractions, camera moves and final holds'})
        progress=[s['progress'] for s in ss if num(s.get('progress'))]
        if any(b<a for a,b in zip(progress,progress[1:])):add('reveal_progress_monotonic','fail',eid)
    if not events:add('pointer_coverage','unknown' if data.get('pointer_requested',False) or policy and policy.get('pointer')=='semantic_teacher_pointer' else 'pass','No events; valid when pointer not requested')
    add('manual_review','review','Check rendered reveal fronts, glyph clearance including glow, semantic attention, frame/arrow routes, fade/hold and audio pacing. Declared equal camera IDs do not prove the renderer applies transforms correctly.')
    counts={v:sum(f['status']==v for f in findings) for v in ('pass','fail','unknown','review')}
    return dict(schema_version='1.0',automatic_checks_passed=counts['fail']==0,complete_evidence=counts['unknown']==0,counts=counts,findings=findings,scope='Sampled declared screen geometry only. Progress must come from the renderer actual reveal function; proportional audio-interval reveal is not word-level forced alignment.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('audit_file');p.add_argument('--output');a=p.parse_args()
    try:r=audit(json.loads(Path(a.audit_file).read_text()))
    except (KeyError,TypeError,ValueError,OSError) as e:r={'automatic_checks_passed':False,'error':str(e)}
    text=json.dumps(r,ensure_ascii=False,indent=2);print(text)
    if a.output:Path(a.output).write_text(text+'\n')
    raise SystemExit(0 if r['automatic_checks_passed'] else 1)
