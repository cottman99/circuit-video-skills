"""Real-weight portable prose typography; no synthetic bold or bundled fonts."""
from pathlib import Path
from functools import lru_cache
import os
from PIL import ImageFont
from matplotlib import get_data_path
from fontTools.ttLib import TTFont

def identity(path):
    face=TTFont(path, fontNumber=0)
    names=face['name']; result={'family':names.getDebugName(16) or names.getDebugName(1), 'weight':face['OS/2'].usWeightClass}
    face.close();return result

fallback=Path(get_data_path())/'fonts/ttf'
regular=Path(os.environ.get('CIRCUIT_FONT_REGULAR',fallback/'DejaVuSans.ttf')).resolve()
heading=Path(os.environ.get('CIRCUIT_FONT_HEADING',fallback/'DejaVuSans-Bold.ttf')).resolve()
ri,hi=identity(regular),identity(heading)
if ri['family']!=hi['family'] or ri['weight']!=400 or hi['weight'] not in (500,600,700):
    raise ValueError('Use the same family with authentic Regular and Medium/Semibold/Bold faces')
FAMILY=ri['family'];HEADING_WEIGHT=hi['weight'];FONTS={400:regular,HEADING_WEIGHT:heading}
DEFAULT_CONTRACT={'schema_version':'whiteboard-typography-1','family':FAMILY,'synthetic_weight':False,
 'roles':{'title':{'weight':HEADING_WEIGHT,'color':'#252a30'},'section':{'weight':HEADING_WEIGHT,'color':'#465360'},
 'body':{'weight':400,'color':'#252a30'},'subtitle':{'weight':400,'color':'#252a30'},
 'note':{'weight':400,'color':'#626970'},'navigation':{'weight':400,'color':'#626970'},'source':{'weight':400,'color':'#747b82'}},
 'metadata_font_size':22,'source_font_size':19,'pointer_policy':'preserve_appearance_and_geometry','math_policy':'preserve_authored_semantic_colors_and_dark_operators'}

def require(ok,message):
    if not ok:raise ValueError('Typography constraint: '+message)
@lru_cache(None)
def font(size,weight=400):
    require(weight in FONTS,'unsupported authentic font weight')
    return ImageFont.truetype(str(FONTS[weight]),max(1,round(size)))
def object_font(obj,scale=1):return font(obj['size']*scale,obj['font_weight'])
def validate_fonts():return [{'family':identity(p)['family'],'weight':w} for w,p in FONTS.items()]
def validate_contract(contract):require(contract==DEFAULT_CONTRACT,'font environment changed; recompile scene')
def validate_objects(objects,contract):
    validate_contract(contract)
    for obj in objects:
        if obj['kind']!='text':continue
        role=obj.get('typography_role');require(role in contract['roles'],'missing text role')
        expected=contract['roles'][role]
        require(obj.get('font_family')==FAMILY and obj.get('font_weight')==expected['weight'],'font role mismatch')
        require(obj['color']==expected['color'],'text role palette mismatch')
        if role=='source':require(obj['size']>=contract['source_font_size'],'source below role floor')
    return True

def validate_glyphs(text):
    face=TTFont(regular,fontNumber=0);chars=set().union(*(set(t.cmap) for t in face['cmap'].tables));face.close()
    missing=sorted({c for c in text if not c.isspace() and ord(c) not in chars})
    require(not missing,'missing glyphs: '+''.join(missing)+'; configure suitable fonts')
