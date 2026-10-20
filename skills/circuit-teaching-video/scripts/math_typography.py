"""Optional math style/geometry contract. Pure-stdlib auditing; lazy Matplotlib use."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import math

DEFAULT_STYLE={'engine':'matplotlib.mathtext','fontset':'stix','default':'it','size_pt':24,'dpi':150,'scale':1.0}

def fingerprint(tex,style):
    if not isinstance(tex,str) or not tex.strip():raise ValueError('nonempty TeX expression required')
    if not isinstance(style,dict):raise ValueError('style must be object')
    for k in ('engine','fontset','default'):
        if not isinstance(style.get(k),str) or not style[k]:raise ValueError('style needs '+k)
    for k in ('size_pt','dpi','scale'):
        v=style.get(k)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0:raise ValueError('positive finite '+k+' required')
    return hashlib.sha256(json.dumps({'tex':tex,'style':style},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

@contextmanager
def math_context(style=None):
    """Use the SAME context for raster/vector render and parser/pointer.prepare."""
    import matplotlib as mpl
    style=DEFAULT_STYLE if style is None else style
    fingerprint('x',style)
    if style['engine']!='matplotlib.mathtext':raise ValueError('context supports MathText only')
    with mpl.rc_context({'mathtext.fontset':style['fontset'],'mathtext.default':style['default']}):yield

def audit(record):
    errors=[]
    if not isinstance(record,dict) or not isinstance(record.get('expressions'),list):
        return {'passed':False,'errors':['expressions array required'],'pixel_evidence':'not_checked'}
    seen=set();symbols={}
    for e in record['expressions']:
        if not isinstance(e,dict):errors.append('expression must be object');continue
        eid=e.get('id')
        if not isinstance(eid,str) or not eid:errors.append('expression id required');continue
        if eid in seen:errors.append('duplicate expression '+eid)
        seen.add(eid)
        try:key=fingerprint(e.get('tex'),e.get('style'))
        except (ValueError,TypeError) as ex:errors.append(eid+': '+str(ex));continue
        if e['style']['fontset']!='stix' and not e.get('font_exception'):errors.append(eid+': non-STIX needs explicit reason')
        for k in ('render_key','layout_key'):
            if e.get(k)!=key:errors.append(eid+': stale or missing '+k)
        for k in ('reveal','pointer'):
            if k+'_key' in e and e[k+'_key']!=key:errors.append(eid+': stale '+k+'_key')
        if e.get('animated') is True:
            for k in ('reveal_key','pointer_key'):
                if e.get(k)!=key:errors.append(eid+': missing current '+k)
        if not isinstance(e.get('terms',[]),list) or not isinstance(e.get('color_bindings',[]),list):
            errors.append(eid+': terms and color_bindings must be arrays');continue
        for term in e.get('terms',[]):
            if not isinstance(term,dict):errors.append(eid+': term must be object');continue
            sid=term.get('symbol_id');tex=term.get('tex');role=term.get('role')
            if not isinstance(sid,str) or not sid or not isinstance(tex,str) or not tex:errors.append(eid+': semantic symbol and TeX required');continue
            if role not in ('variable','descriptor','unit','number','operator'):errors.append(eid+': unknown term role')
            identity=(tex,role)
            if sid in symbols and symbols[sid]!=identity:errors.append(eid+': cross-view symbol drift '+sid)
            symbols[sid]=identity
            if role in ('descriptor','unit') and term.get('upright') is not True:errors.append(eid+': descriptor/unit must be upright '+sid)
            if role=='unit' and term.get('number_spacing') is not True:errors.append(eid+': number/unit spacing required '+sid)
        for b in e.get('color_bindings',[]):
            if not isinstance(b,dict) or not b.get('semantic_id') or b.get('primitive')!='glyph':errors.append(eid+': knowledge color must bind semantic glyphs, not rules/rectangles')
    return {'passed':not errors,'errors':errors,'expressions':len(record['expressions']),'pixel_evidence':'not_checked','scope':'Declared geometry provenance and semantic consistency, not proof of actual typography, color pixels or learning'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('record');a=p.parse_args()
    try:result=audit(json.load(open(a.record)))
    except (OSError,ValueError) as e:result={'passed':False,'errors':[str(e)]}
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(not result['passed'])
