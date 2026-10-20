"""Verified catalog PDF crops, extracted from the transfer source-image primitive.
Only source rasterization is reused. No formula/card dispatch or lifecycle lives here.
"""
from pathlib import Path
import hashlib,io,math
from PIL import Image,ImageDraw
from render_config import ByteLRU
from native_primitives import image_bytes

def ensure(ok,message):
 if not ok:raise ValueError(message)
def resolve(base,path):
 root=Path(base).resolve(); p=(root/path).resolve()
 ensure(p==root or root in p.parents,'Source paths must stay inside the project directory')
 return p

class CatalogAssets:
 def __init__(self,catalog,base):
  global fitz
  import fitz
  self.catalog=catalog;self.base=Path(base);self.cache=ByteLRU(96*1024**2);self.docs={};self.records={}
  for source in catalog['sources'].values():
   p=resolve(base,source['path'])
   ensure(hashlib.sha256(p.read_bytes()).hexdigest()==source['sha256'],'Source identity changed')
   with fitz.open(p) as doc:
    ensure(isinstance(source['page'],int) and 1<=source['page']<=len(doc),'Invalid PDF page')
    ensure(doc[source['page']-1].rotation==source['pdf_rotation'],'PDF rotation differs from catalog')
  for asset in catalog['assets'].values():
   ensure(asset['source_id'] in catalog['sources'],'Unknown PDF source')
   c=asset['crop_normalized']
   ensure(len(c)==4 and all(isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=1 for v in c) and c[0]<c[2] and c[1]<c[3],'Invalid normalized crop')
 def rasterize(self,asset_id,size):
  return self.rasterize_instance({'asset_id':asset_id},size).convert('RGBA')
 def close(self):
  for d in self.docs.values():d.close()
 def rasterize_instance(self,inst,size):
  asset=self.catalog['assets'][inst['asset_id']];source=self.catalog['sources'][asset['source_id']]
  key=('pdf',source['sha256'],source['page'],source['pdf_rotation'],asset['crop_version'],tuple(asset['crop_normalized']),tuple(size))
  im=self.cache.get(key)
  if im is not None:return im
  sid=source['id']
  if sid not in self.docs:self.docs[sid]=fitz.open(resolve(self.base,source['path']))
  page=self.docs[sid][source['page']-1];r=page.rect;c=asset['crop_normalized'];clip=fitz.Rect(c[0]*r.width,c[1]*r.height,c[2]*r.width,c[3]*r.height)
  if asset.get('embedded_image_xref'):
   xref=asset['embedded_image_xref'];rects=page.get_image_rects(xref)
   ensure(len(rects)==1,'Embedded source image must have one verified placement')
   image_rect=rects[0]*page.rotation_matrix;data=self.docs[sid].extract_image(xref);original=Image.open(io.BytesIO(data['image'])).convert('RGB')
   ensure(abs(original.width/original.height/image_rect.width*image_rect.height-1)<.0001,'Embedded source orientation does not match displayed placement')
   sx=size[0]/clip.width;sy=size[1]/clip.height
   im=Image.new('RGB',tuple(size),'white');resized=original.resize((round(image_rect.width*sx),round(image_rect.height*sy)),Image.Resampling.LANCZOS)
   im.paste(resized,(round((image_rect.x0-clip.x0)*sx),round((image_rect.y0-clip.y0)*sy)))
   self.records[str(key)+'.embedded']={'xref':xref,'original_pixel_size':list(original.size),'original_image_sha256':hashlib.sha256(data['image']).hexdigest(),'display_page_rect':list(image_rect),'method':'Untouched embedded image, page-placement affine; excludes separately overlaid non-data citation text only. Full citation retained in footer.'}
  else:
   scale=max(size[0]/clip.width,size[1]/clip.height);p=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=clip,alpha=False)
   im=Image.frombytes('RGB',(p.width,p.height),p.samples)
   if im.size!=tuple(size):im=im.resize(size,Image.Resampling.LANCZOS)
  for ex in asset.get('nondata_exclusions',[]):
   eb=ex['bbox'];xy=[(eb[0]*r.width-clip.x0)*size[0]/clip.width,(eb[1]*r.height-clip.y0)*size[1]/clip.height,(eb[2]*r.width-clip.x0)*size[0]/clip.width,(eb[3]*r.height-clip.y0)*size[1]/clip.height]
   ImageDraw.Draw(im).rectangle(xy,fill='white')
  self.records[str(key)]={'nondata_exclusions':asset.get('nondata_exclusions',[]),'source_sha256':source['sha256'],'page':source['page'],'crop_version':asset['crop_version'],'crop_normalized':c,'raster_size':list(size),'method':'original_pdf_embedded_crop_at_target_density' if asset.get('embedded_image_xref') else 'original_pdf_clip_at_native_target_density','source_limitation':'Embedded source rasters retain their original resolution limit; no detail invented'}
  return self.cache.put(key,im,image_bytes(im))
