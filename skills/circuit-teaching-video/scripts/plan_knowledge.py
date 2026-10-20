#!/usr/bin/env python3
"""Deterministic knowledge-plan normalization, not a knowledge-truth evaluator."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True

EDGE_TYPES = {'prerequisite', 'causal', 'contrast', 'part_of', 'feedback', 'related'}
ID = re.compile(r'^[a-z][a-z0-9_.-]*$')
class PlanError(ValueError): pass

def need(ok, message):
    if not ok: raise PlanError(message)
def text(value, where):
    need(isinstance(value, str) and bool(value.strip()), where + ': nonempty text required')
def seq(value, where, nonempty=True):
    need(isinstance(value, list) and (bool(value) or not nonempty), where + ': list required')
    return value

def index(rows, where):
    out = {}
    for row in seq(rows, where):
        need(isinstance(row, dict), where + ': object required')
        key = row.get('id')
        need(isinstance(key, str) and ID.fullmatch(key), where + ': stable authored id required')
        need(key not in out, where + ': duplicate id ' + key)
        out[key] = row
    return out

def refs(values, universe, where, nonempty=True):
    seq(values, where, nonempty)
    need(all(isinstance(x, str) for x in values), where + ': string references required')
    need(len(set(values)) == len(values), where + ': duplicate reference')
    need(set(values) <= set(universe), where + ': dangling reference')

def rect(value, where):
    need(isinstance(value,list) and len(value)==4 and all(type(x) in (int,float) and math.isfinite(x) for x in value), where + ': finite [x,y,w,h] required')
    need(value[2]>0 and value[3]>0,where + ': positive dimensions required')
    return value

def contains(outer, inner):
    x,y,w,h=outer; a,b,c,d=inner
    return x<=a and y<=b and a+c<=x+w and b+d<=y+h

def normalize(value):
    need(isinstance(value,dict), 'plan: object required')
    p=copy.deepcopy(value)
    need(p.get('schema_version')=='1.0','schema_version must be 1.0')
    text(p.get('question'),'question')
    sources=index(p.get('sources'),'sources')
    for s in sources.values():
        text(s.get('locator'),'source locator'); text(s.get('basis'),'source basis')
    graph=p.get('knowledge_graph'); need(isinstance(graph,dict),'knowledge_graph: object required')
    nodes=index(graph.get('nodes'),'knowledge nodes')
    for n in nodes.values():
        text(n.get('statement'),'knowledge statement'); refs(n.get('source_refs'),sources,'knowledge sources')
    seq(graph.get('edges'),'knowledge edges',False)
    edges=index(graph['edges'],'knowledge edges') if graph['edges'] else {}
    incoming={n:set() for n in nodes}; outgoing={n:set() for n in nodes}
    for e in edges.values():
        need(e.get('type') in EDGE_TYPES,'unknown edge type')
        refs([e.get('from'),e.get('to')],nodes,'edge endpoints',True) if e.get('from')!=e.get('to') else need(e.get('from') in nodes,'dangling edge')
        text(e.get('reason'),'edge reason')
        if e['type']=='prerequisite':
            incoming[e['to']].add(e['from']);outgoing[e['from']].add(e['to'])
    indegrees={n:len(v) for n,v in incoming.items()}; ready=sorted(n for n,d in indegrees.items() if not d);order=[]
    while ready:
        n=ready.pop(0);order.append(n)
        for target in sorted(outgoing[n]):
            indegrees[target]-=1
            if not indegrees[target]: ready.append(target);ready.sort()
    need(len(order)==len(nodes),'prerequisite cycle; feedback/related edges may loop but prerequisites may not')
    objects=index(p.get('objects'),'objects')
    for o in objects.values():
        need(o.get('kind') in {'circuit','formula','text','plot'},'unsupported object kind')
        refs(o.get('knowledge_refs'),nodes,'object knowledge refs')
        rect(o.get('bounds'),'object '+o['id'])
    boards=index(p.get('boards'),'boards')
    for b in boards.values():
        text(b.get('question'),'board question');text(b.get('conclusion'),'board conclusion')
        for premise in seq(b.get('premises'),'board premises'): text(premise,'premise')
        refs(b.get('knowledge_refs'),nodes,'board knowledge refs')
        refs(b.get('source_refs'),sources,'board source refs')
        need({s for n in b['knowledge_refs'] for s in nodes[n]['source_refs']}<=set(b['source_refs']),'board omits knowledge source refs')
        refs(b.get('object_refs'),objects,'board object refs')
        need({s for oid in b['object_refs'] for n in objects[oid]['knowledge_refs'] for s in nodes[n]['source_refs']}<=set(b['source_refs']),'board omits object knowledge source refs')
        refs(b.get('retained_objects'),objects,'board retained objects')
        need(set(b['retained_objects'])<=set(b['object_refs']),'retained objects must be on board')
        bounds=rect(b.get('bounds'),'board bounds')
        layout=b.setdefault('layout',{})
        need(isinstance(layout,dict),'layout must be an object')
        need(set(layout)<={'left_fraction','gap_fraction'},'unknown layout option')
        left=layout.setdefault('left_fraction',0.48);gap=layout.setdefault('gap_fraction',0.04)
        need(type(left) in (float,int) and type(gap) in (float,int) and 0<left<1 and 0<=gap<1 and left+gap<1,'invalid layout fractions')
        x,y,w,h=bounds;split=x+w*left;right=split+w*gap
        circuits=[objects[k] for k in b['object_refs'] if objects[k]['kind']=='circuit']
        need(bool(circuits),'local board needs circuit/context diagram')
        for oid in b['object_refs']:
            o=objects[oid];r=o['bounds'];need(contains(bounds,r),'object outside board '+oid)
            if o['kind']=='circuit': need(r[0]+r[2]<=split,'circuit must remain in left lane')
            if o['kind']=='formula': need(r[0]>=right,'formula must remain in right lane')
        for i,oid in enumerate(b['object_refs']):
            a=objects[oid]['bounds']
            for other in b['object_refs'][i+1:]:
                z=objects[other]['bounds']
                need(not (min(a[0]+a[2],z[0]+z[2])>max(a[0],z[0]) and min(a[1]+a[3],z[1]+z[3])>max(a[1],z[1])), 'overlapping board objects: '+oid+' / '+other)
        formulas=[o for o in b['object_refs'] if objects[o]['kind']=='formula']
        need(set(formulas+[o['id'] for o in circuits])<=set(b['retained_objects']),'circuit and cumulative formulas must be retained')
        # Derive a preservation contract, never erase the authored local policy.
        required={'formula_retention':'cumulative','reveal':'fast_then_read','pointer':'semantic_teacher_pointer','legend':False}
        policy=b.setdefault('local_policy',{})
        need(isinstance(policy,dict),'local_policy must be object')
        for k,v in required.items():
            need(k not in policy or policy[k]==v,'local behavior regression: '+k)
            policy[k]=v
    visits=index(p.get('camera_visits'),'camera visits')
    seen=set();visited_boards=set();retained=set();route=[]
    for v in visits.values():
        need(v.get('board_id') in boards,'visit references unknown board')
        b=boards[v['board_id']];visited_boards.add(b['id'])
        text(v.get('transition_purpose'),'transition purpose')
        targets=v.get('focus_objects');refs(targets,objects,'visit focus objects')
        need(set(targets)<=set(b['object_refs']),'visit focus objects not on board')
        # A board may show a complete derivation; its internal order uses the DAG.
        current=set(b['knowledge_refs'])
        displayed={n for oid in b['object_refs'] for n in objects[oid]['knowledge_refs']}
        role=v.setdefault('role','explain')
        need(role in ('explain','preview'),'visit role must be explain or preview')
        newly_introduced=sorted(current-seen) if role=='explain' else []
        if role=='explain':
            need(displayed<=seen|current,'board objects introduce undeclared or premature knowledge')
            for n in current: need(incoming[n]<=seen|current,'camera route uses prerequisite before introduction: '+n)
            seen|=current
        retained.update(b['retained_objects'])
        route.append({'visit_id':v['id'],'board_id':b['id'],'introduced_knowledge':newly_introduced,'role':role,'retained_world_objects':sorted(retained),'availability':'planned retention after local reveal; not initially visible or audio-timed','reasoning_order':[n for n in order if n in current]})
        view=v.setdefault('view_bounds',list(b['bounds']));rect(view,'visit view_bounds')
        need(contains(b['bounds'],view),'camera view outside local board')
        for oid in targets: need(contains(view,objects[oid]['bounds']),'camera clips focused object '+oid)
        # Retained objects persist in world; a semantic zoom may temporarily crop them.
    need(visited_boards==set(boards),'camera route omits a board')
    need(seen==set(nodes),'knowledge nodes missing from boards')
    p['derived']={'visit_states':route,'board_reasoning_order':{b['id']:[n for n in order if n in b['knowledge_refs']] for b in boards.values()},'prerequisite_order':order,'scope':'Declared structure and geometry only; no truth, reading-time, render or learning certification','renderer':'existing persistent_board_v1; no automatic global camera adapter'}
    return p

def check(value):
    try:
        p=normalize(value)
        return {'passed':True,'errors':[],'normalized':p}
    except (ValueError,TypeError,KeyError,AttributeError) as e:
        return {'passed':False,'errors':[str(e)]}

def canonical(p): return json.dumps(p,ensure_ascii=False,sort_keys=True,indent=2)+'\n'

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('plan',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
    try: result=check(json.loads(a.plan.read_text()))
    except (OSError,ValueError) as e: result={'passed':False,'errors':[str(e)]}
    if result['passed'] and a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(canonical(result['normalized']))
        result={'passed':True,'errors':[],'output':str(a.output),'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}
    print(canonical(result),end='');return 0 if result['passed'] else 1
if __name__=='__main__':sys.exit(main())
