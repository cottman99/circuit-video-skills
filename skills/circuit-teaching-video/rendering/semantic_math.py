"""Deterministic, source-token-aware math identity colors; no layout changes.

Only registered base/subscript atoms are colored. Operators, arithmetic superscripts, prose, and unknown atoms stay neutral.
Prime suffixes inherit the registered variable identity. Attribution uses source offsets
on real MathText Char nodes, never substrings of the rendered glyph stream.
"""
from pathlib import Path
import json
import re
import types

REGISTRY_PATH = Path(__file__).resolve().parents[1] / 'style/symbol-registry.json'
HEX = re.compile(r'#[0-9a-fA-F]{6}\Z')
OPAQUE = {'text', 'operatorname', 'mathrm', 'mathregular', 'textrm', 'textnormal'}

def load_registry(overrides=None):
    """Load fixed versioned identities. Overrides are explicit id -> hex colors.

    Additional identities require id -> {latex, color, role}; no random fallback.
    A project must reuse the same resolved registry for formulas and curves.
    """
    result = json.loads(REGISTRY_PATH.read_text())
    for key, value in (overrides or {}).items():
        if isinstance(value, str):
            if key not in result['symbols']:
                raise ValueError('New symbol requires latex, color and role: '+key)
            result['symbols'][key]['color'] = value
        else:
            if not isinstance(value, dict) or not all(value.get(k) for k in ('latex','color','role')):
                raise ValueError('New symbol requires latex, color and role: '+key)
            result['symbols'][key] = dict(value)
    seen = set()
    for key, value in result['symbols'].items():
        if not HEX.fullmatch(value['color']): raise ValueError('Invalid RGB color: '+key)
        atoms = _atoms(value['latex'])
        if len(atoms)!=1 or atoms[0]['start']!=0 or atoms[0]['end']!=len(value['latex']):
            raise ValueError('Registry latex must be one base/subscript atom: '+key)
        identity = atoms[0]['identity']
        if identity in seen: raise ValueError('Duplicate symbol identity: '+identity)
        seen.add(identity)
    return result

def symbol_color(symbol, registry=None, unknown_policy=None):
    """Exact registry id for curve/label styling; None means neutral."""
    registry = registry or load_registry()
    policy = unknown_policy or registry['unknown_policy']
    if policy not in ('neutral','error'): raise ValueError('Unknown policy: '+policy)
    if symbol in registry['symbols']: return registry['symbols'][symbol]['color']
    if policy=='error': raise ValueError('Unregistered symbol: '+symbol)
    return None

def _argument(s, i):
    while i<len(s) and s[i].isspace(): i+=1
    if i==len(s): return i,i,i
    if s[i]=='{':
        depth=1;j=i+1
        while j<len(s) and depth:
            if s[j]=='{':depth+=1
            elif s[j]=='}':depth-=1
            j+=1
        if depth: raise ValueError('Unbalanced math group')
        return i+1,j-1,j
    if s[i]=='\\':
        m=re.match(r'\\[A-Za-z]+|\\.',s[i:]);j=i+len(m[0])
        return i,j,j
    return i,i+1,i+1

def _subscript(s):
    s=re.sub(r'\s+','',s)
    # Roman subscript labels retain their typography but share the same identity.
    m=re.fullmatch(r'\\(?:mathrm|mathregular)\{([A-Za-z0-9]+)\}',s)
    if m:return m[1]
    m=re.fullmatch(r'\\rm([A-Za-z0-9]+)',s)
    if m:return m[1]
    return s if re.fullmatch(r'[A-Za-z0-9]+',s) else None

def _atoms(s):
    atoms=[];i=0
    while i<len(s):
        if s[i]=='\\':
            m=re.match(r'\\([A-Za-z]+)|\\.',s[i:]);cmd=m[1];i+=len(m[0])
            if cmd in OPAQUE:
                _,_,i=_argument(s,i)
            continue
        if not s[i].isalpha() or not s[i].isascii():i+=1;continue
        start=i;base=s[i];i+=1;sub=None;subspan=None;primes=[]
        while i<len(s):
            j=i
            while j<len(s) and s[j].isspace():j+=1
            if j<len(s) and s[j] in '_^':
                op=s[j];a,b,i=_argument(s,j+1)
                if op=='_':sub=_subscript(s[a:b]);subspan=(a,b)
                elif re.fullmatch(r"(?:\\prime|')+",s[a:b]):primes.append((a,b))
                continue
            if j<len(s) and s[j]=="'":primes.append((j,j+1));i=j+1;continue
            if s.startswith(r"\prime",j) and (j+6==len(s) or not s[j+6].isalpha()):
                primes.append((j,j+6));i=j+6;continue
            break
        # Bare letters never accidentally turn a glyph string gm into g_m.
        identity=base+('_'+sub if sub is not None else '')
        atoms.append({'identity':identity,'start':start,'end':i,'base':start,'subspan':subspan,'prime_spans':primes})
    return atoms

def token_assignments(formula, registry=None, mappings=None, unknown_policy=None):
    """Return exact source spans. Legacy glyph keys resolve registered IDs only."""
    registry=registry or load_registry()
    policy=unknown_policy or registry['unknown_policy']
    if policy not in ('neutral','error'):raise ValueError('Unknown policy: '+policy)
    symbols=registry['symbols']
    selected = symbols
    if mappings is not None:
        selected={}
        for m in mappings:
            key=m.get('symbol',m.get('glyphs'))
            if key not in symbols:raise ValueError('Unregistered mapping; add explicit registry symbol: '+str(key))
            color=m.get('color',symbols[key]['color'])
            if not HEX.fullmatch(color):raise ValueError('Invalid RGB color: '+str(key))
            if key in selected:raise ValueError('Duplicate mapping: '+key)
            selected[key]={**symbols[key],'color':color}
    identities={_atoms(v['latex'])[0]['identity']:(k,v) for k,v in selected.items()}
    result=[]
    for atom in _atoms(formula):
        if atom['identity'] not in identities:
            if policy=='error':raise ValueError('Unregistered formula atom: '+atom['identity'])
            continue
        key,value=identities[atom['identity']]
        spans=[(atom['base'],atom['base']+1),*atom['prime_spans']]
        if atom['subspan']:spans.append(atom['subspan'])
        result.append({**atom,'symbol':key,'color':value['color'],'spans':spans})
    return result

def glyph_assignments(formula, size, registry=None, mappings=None, unknown_policy=None):
    """Bind source atoms to actual MathText glyphs, preserving STIX geometry.

    Uses Matplotlib's internal node API, guarded by exact public-parser geometry
    comparison. Unsupported API/version changes fail closed, not heuristic color.
    """
    import matplotlib._mathtext as mt
    from matplotlib.mathtext import MathTextParser
    from matplotlib.font_manager import FontProperties
    from matplotlib.ft2font import LoadFlags
    assignments=token_assignments(formula,registry,mappings,unknown_policy)
    positions={i:a['color'] for a in assignments for lo,hi in a['spans'] for i in range(lo,hi)}
    class TaggedParser(mt.Parser):
        def symbol(self,s,loc,toks):
            nodes=super().symbol(s,loc,toks)
            # Parser math source is the content between dollars (loc starts at 0).
            color=positions.get(loc)
            if color:
                def mark(node):
                    if isinstance(node,mt.Char):
                        original=node.render
                        def render(this,output,x,y):
                            index=len(output.glyphs);original(output,x,y)
                            if not hasattr(output,'semantic_targets'):output.semantic_targets={}
                            output.semantic_targets[index]=color
                        node.render=types.MethodType(render,node)
                    for child in getattr(node,'children',[]):mark(child)
                for node in nodes:mark(node)
            return nodes
    prop=FontProperties(size=size*72/150,math_fontfamily='stix')
    fontset=mt.StixFonts(prop,LoadFlags.NO_HINTING)
    parser=TaggedParser()
    box=parser.parse('$'+formula+'$',fontset,prop.get_size_in_points(),72)
    output=mt.ship(box);z=output.to_vector()
    expected=MathTextParser('path').parse('$'+formula+'$',dpi=72,prop=prop)
    def geometry(v):return (v.width,v.height,v.depth,[(f.fname,fs,c,x,y)for f,fs,c,x,y in v.glyphs],v.rects)
    if geometry(z)!=geometry(expected):raise ValueError('Semantic parser geometry differs from public STIX parser')
    return z,getattr(output,'semantic_targets',{})

def color_tokens(im,formula,size,raster_scale,mappings=None,*,registry=None,unknown_policy=None):
    import numpy as np
    from scipy.ndimage import label,find_objects
    from PIL import Image,ImageColor
    z,targets=glyph_assignments(formula,size,registry,mappings,unknown_policy)
    if not targets:return im.copy()
    boxes=[];s=150*raster_scale/72
    for f,fs,c,x,y in z.glyphs:
        f.set_size(fs,72);b=f.load_char(c).bbox
        boxes.append([(x+b[0]/64)*s,(z.height-z.depth-y-b[3]/64)*s,(x+b[2]/64)*s,(z.height-z.depth-y-b[1]/64)*s])
    for x,y,w,h in z.rects:boxes.append([x*s,(z.height-z.depth-y-h)*s,(x+w)*s,(z.height-z.depth-y)*s])
    a=np.array(im);ink=(a[:,:,:3].min(axis=2)<254)&(a[:,:,3]>20);cc,n=label(ink)
    for cid,sl in enumerate(find_objects(cc),1):
        yy,xx=sl;cx=(xx.start+xx.stop)/2;cy=(yy.start+yy.stop)/2
        def dist(b):
            x0,y0,x1,y1=b
            return max(x0-cx,cx-x1,0)**2+max(y0-cy,cy-y1,0)**2+.025*((cx-(x0+x1)/2)**2+(cy-(y0+y1)/2)**2)
        k=min(range(len(boxes)),key=lambda k:dist(boxes[k]))
        if k in targets:
            mask=cc==cid;strength=(255-a[mask,:3].min(axis=1))/231
            a[mask,:3]=np.clip(255-strength[:,None]*(255-np.array(ImageColor.getrgb(targets[k]))),0,255).astype('uint8')
    return Image.fromarray(a)
