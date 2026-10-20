"""Deterministic ink-front teacher pointer. All geometry is local/world before camera."""
import math_style
import math
import numpy as np
from PIL import Image,ImageDraw,ImageFilter
from matplotlib.mathtext import MathTextParser
from matplotlib.font_manager import FontProperties

def prepare(ev, formula=None, size=None, raster_scale=1.0, template=None):
 src=ev['im'];a=np.asarray(src);ink=(a[:,:,:3].min(axis=2)<254)&(a[:,:,3]>20)
 H,W=ink.shape;groups=[]
 if template is not None:
  # Preserve authored semantic groups across raster sizes. At a higher DPI,
  # two touching glyph components can separate; that must not retime the reveal.
  for original in template:
   groups.append({'boxes':[[v*raster_scale for v in box] for box in original['template_boxes']]})
   for boxes in original.get('after_boxes',[]):
    groups.append({'boxes':[[v*raster_scale for v in box] for box in boxes],'bar':True})
 elif formula:
  z=MathTextParser('path').parse('$'+formula+'$',dpi=72,prop=FontProperties(size=size*72/150));s=150*raster_scale/72
  ref=None;prev=-1
  for f,fs,c,x,y in z.glyphs:
   f.set_size(fs,72);bb=f.load_char(c).bbox
   box=[(x+bb[0]/64)*s,(z.height-z.depth-y-bb[3]/64)*s,(x+bb[2]/64)*s,(z.height-z.depth-y-bb[1]/64)*s]
   if not groups or x<prev-2 or abs(y-ref)>max(fs*.45,4):groups.append({'boxes':[]});ref=y
   groups[-1]['boxes'].append(box);prev=x
  bars=[]
  for x,y,w,h in z.rects:
   box=[x*s,(z.height-z.depth-y-h)*s,(x+w)*s,(z.height-z.depth-y)*s]
   # Fraction bars belong to the immediately preceding numerator, never a cursor track.
   centers=[sum((b[1]+b[3])/2 for b in g['boxes'])/len(g['boxes']) for g in groups]
   above=[k for k,c in enumerate(centers) if c<box[1] and max(b[2] for b in groups[k]['boxes'])>box[0]+4*raster_scale and min(b[0] for b in groups[k]['boxes'])<box[2]-4*raster_scale]
   k=min(above,key=lambda k:abs(centers[k]-box[1])) if above else 0
   bars.append((k,{'boxes':[box],'bar':True}))
  for k,g in sorted(bars,key=lambda item:item[0],reverse=True):groups.insert(k+1,g)
 else:groups=[{'boxes':[[0,0,W,H]]}]
 from scipy.ndimage import label,find_objects
 cc,n=label(ink);slices=find_objects(cc);ys,xs=np.where(ink);labels=np.zeros(len(xs),int)
 assignments=np.zeros(n+1,int)
 for cid,sl in enumerate(slices,1):
  yy,xx=sl;cx=(xx.start+xx.stop)/2;cy=(yy.start+yy.stop)/2;best=float('inf');winner=0
  for k,g in enumerate(groups):
   for x0,y0,x1,y1 in g['boxes']:
    dist=max(x0-cx,cx-x1,0)**2+max(y0-cy,cy-y1,0)**2
    dist+=.025*((cx-(x0+x1)/2)**2+(cy-(y0+y1)/2)**2)
    if dist<best:best=dist;winner=k
  assignments[cid]=winner
 labels=assignments[cc[ys,xs]]
 out=[]
 for k,g in enumerate(groups):
  mask=np.zeros((H,W),np.uint8);ok=labels==k;mask[ys[ok],xs[ok]]=a[ys[ok],xs[ok],3]
  if not ok.any():continue
  xx=xs[ok];yy=ys[ok];bounds=[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)]
  part=src.copy();part.putalpha(Image.fromarray(mask));out.append({'image':part,'bounds':bounds,'template_boxes':g['boxes'],'weight':120+max(24,(bounds[2]-bounds[0])/raster_scale)*(.5 if g.get('bar') else 1),'bar':g.get('bar',False)})
 main=[]
 for g in out:
  if g.get('bar') and main:
   main[-1].setdefault('after',[]).append(g['image']);main[-1].setdefault('after_boxes',[]).append(g['template_boxes'])
  else:main.append(g)
 out=main
 for g in out:
  x0,y0,x1,y1=g['bounds'];g['pointer_y']=y1+12*raster_scale
  for cy in [y1+12*raster_scale,y0-12*raster_scale,y1+22*raster_scale,y0-22*raster_scale,y1+34*raster_scale,y0-34*raster_scale,H+12*raster_scale,-12*raster_scale]:
   margin=max(1,math.ceil(7*raster_scale));patch=ink[max(0,int(cy)-margin):max(0,int(cy)+margin+1),max(0,x0-margin):min(W,x1+margin+1)]
   if patch.size==0 or not patch.any():g['pointer_y']=cy;break
 ev['reveal_groups']=out;ev['formula']=formula;ev['size']=size
 total=sum(g['weight'] for g in out);v=0
 for g in out:g['a']=v/total;v+=g['weight'];g['b']=v/total

def active(ev,p):
 gs=ev.get('reveal_groups',[])
 if not gs:return None
 g=next((g for g in gs if p<g['b']),gs[-1]);q=max(0,min(1,(p-g['a'])/(g['b']-g['a'])))
 x0,y0,x1,y1=g['bounds'];return g,q,(x0+(x1-x0)*q,y1)

def draw(im,ev,p):
 for g in ev['reveal_groups']:
  q=max(0,min(1,(p-g['a'])/(g['b']-g['a'])))
  if q<=0:continue
  x0,y0,x1,y1=g['bounds'];end=round(x0+(x1-x0)*q)
  part=g['image'].crop((0,0,end,g['image'].height));im.paste(part,ev['xy'],part)
  if q>=1:
   for bar in g.get('after',[]):im.paste(bar,ev['xy'],bar)

def dot(im,point,opacity=1,radius=4):
 if opacity<=0:return
 x,y=point;r=radius
 # Small soft halo, crisp bright tip. No pulse, blink, permanent trail or underline.
 glow=Image.new('RGBA',(64,64));d=ImageDraw.Draw(glow);d.ellipse((32-r*1.6,32-r*1.6,32+r*1.6,32+r*1.6),fill=(243,36,72,round(125*opacity)))
 glow=glow.filter(ImageFilter.GaussianBlur(5));d=ImageDraw.Draw(glow);d.ellipse((32-r,32-r,32+r,32+r),fill=(243,36,72,round(255*opacity)));d.ellipse((30.5,30.5,33.5,33.5),fill=(255,205,213,round(255*opacity)))
 im.paste(glow,(round(x-32),round(y-32)),glow)
