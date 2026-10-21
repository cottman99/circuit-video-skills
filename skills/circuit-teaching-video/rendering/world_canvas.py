#!/usr/bin/env python3
"""Registered bounded world adapter. Executes frozen scene; never authors inputs."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/circuit-video-mpl')
from pathlib import Path
import sys,json,hashlib,math,subprocess,argparse,re
P=Path(__file__).resolve().parent
sys.path.insert(0, str(P))
from PIL import Image,ImageDraw,ImageFilter,ImageChops
from native_primitives import Lesson as NativePrimitives,image_bytes
from render_config import RenderConfig,ByteLRU
from semantic_math import load_registry,color_tokens
from subtitle_layout import subtitle_rows
import logical_scene as native
import layout_constraints as layout
import type_styles as typography
native.FONT=typography.FONTS[400]
native.font.cache_clear()
from matplotlib import font_manager


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2))
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
ADAPTER={'id':'circuit-world-v1','scope':'portable world-canvas subset; original production painting and pointer core','capabilities':['frozen_scene','cumulative_objects','semantic_actions','local_open','direct_pan','closing_pullback','full_frame_receipts','reserved_caption_band','reserved_header_metadata','internal_subtitle_strip','full_screen_whiteboard'],'limitations':['No independent pedagogical or audible word-alignment certification','Clause timing may be explicitly estimated within measured sentence events']}

class CanvasRenderer:
    # Composition of stable raster primitives, not inheritance bypassing another adapter gate.
    raster_scale=staticmethod(NativePrimitives.raster_scale)
    asset_image=NativePrimitives.asset_image
    paint_event=NativePrimitives.paint_event
    dot=NativePrimitives.dot
    def __init__(self,scene,width=1280,fps=15,highlight_underlay=True):
        self.highlight_underlay_enabled=highlight_underlay
        self.scene=scene;self.duration=scene['duration'];self.layout=scene['layout_contract'];layout.validate_contract(self.layout,scene['render_config']);layout.validate_scene_layout(scene);self.viewport_fraction=1.0;self.config=RenderConfig(width=width,height=round(width*9/16),fps=fps)
        if width%2 or self.config.height%2:raise ValueError('Output dimensions must be even')
        adapter=scene.get('adapter','circuit-world-v1')
        if isinstance(adapter,dict):adapter=adapter.get('id')
        if adapter!='circuit-world-v1':raise ValueError('Unregistered adapter')
        ids=[o['id'] for o in scene['objects']]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate object IDs')
        self.cache=ByteLRU(128*1024**2);self.native_records={};self.native_raster_calls=0
        self.font_identity=sha(native.FONT);self.symbol_registry=load_registry();self.events=[];self.records=[]
        if scene.get('source_catalog'):
            from source_catalog_assets import CatalogAssets
            self.assets=CatalogAssets(scene['source_catalog'],scene['asset_base'])
        for o in scene['objects']:
            if o['kind'] not in ('formula','asset'):continue
            b=o['world_bounds']
            if o['kind']=='formula':e=native.equation(o['latex'],o['font_size'],10000)
            else:e={'im':Image.new('RGBA',(round(b[2]),round(b[3]))),'asset_path':o['asset_id'],'asset_sha256':o['asset_sha256']}
            e.update(id=o['id'],kind=o['kind'],origin=(0,0),xy=tuple(b[:2]),start=o['start'],duration=o.get('duration',.001),world_bounds=b,semantic_colors=o.get('semantic_colors'))
            self.events.append(e)
        self.event_by_id={e['id']:e for e in self.events}
    def native_event(self,event,scale):
        result=NativePrimitives.native_event(self,event,scale)
        key=('semantic',event['id'],result['raster_scale'])
        cached=self.cache.get(key)
        if cached is not None:return cached
        colored={'im':color_tokens(result['im'],event['formula'],event['size'],result['raster_scale'],event.get('semantic_colors'),registry=self.symbol_registry),'xy':(0,0)}
        native.pointer.prepare(colored,formula=event['formula'],size=event['size'],raster_scale=result['raster_scale'],template=event['reveal_groups'])
        for g,old in zip(colored['reveal_groups'],result['reveal_groups']):g['a'],g['b']=old['a'],old['b']
        colored['raster_scale']=result['raster_scale']
        return self.cache.put(key,colored,image_bytes(colored))
    def camera_rect(self,t):
        track=self.scene['camera_track']
        for k in track:
            if k['start']<=t<k['end']:
                u=(t-k['start'])/(k['end']-k['start'])
                return [a+(b-a)*u for a,b in zip(k['from'],k['to'])]
        return track[0]['from'] if t<track[0]['start'] else track[-1]['to']
    def transform(self,t):
        view=self.camera_rect(t);x,y,w,h=view
        # Full-screen world camera. Captions have a separate INTERNAL safe strip,
        # not an external margin or an 8/9 shrink of the whiteboard.
        u=self.config.width/self.scene['render_config']['logical_width']
        vx,vy,vw,vh=[v*u for v in self.layout['world_viewport']]
        scale=min(vw/w,vh/h)
        ox=vx+(vw-w*scale)/2;oy=vy+(vh-h*scale)/2
        return lambda p:(ox+(p[0]-x)*scale,oy+(p[1]-y)*scale),scale,view
    def teacher(self,t,tr,scale,ink):
        for e in self.events:
            if e['kind']=='formula' and e['start']<t<e['start']+e['duration']:
                p=(t-e['start'])/e['duration'];r=self.native_event(e,scale);g,q,front=native.pointer.active(r,p);rs=r['raster_scale'];x,y=e['xy']
                px=x+front[0]/rs
                candidates=[y+g['pointer_y']/rs,y+e['im'].height+12,y-14]
                for py in candidates:
                    sx,sy=tr((px,py));rad=max(2,math.ceil(7*scale))
                    crop=ink.crop((round(sx-rad),round(sy-rad),round(sx+rad+1),round(sy+rad+1)))
                    if not crop.getbbox():return {'kind':'dot','target':e['id'],'point':[px,py],'opacity':min(1,(t-e['start'])/.1,(e['start']+e['duration']-t)/.1),'geometry_source':'native_reveal_front'}
                return None
        actions=self.scene.get('teacher_actions',self.scene.get('actions',[]))
        action=next((a for a in actions if a['start']<=t<a['end']),None)
        if action:
            f=dict(action);f['opacity']=max(0,min(1,(t-f['start'])/.18,(f['end']-t)/.18));return f
    def highlight_underlay(self,content,f,tr):
        """Composite a pale frame fill BELOW immutable content and foreground marks.

        This bounded whiteboard adapter has white-matted formula/PDF rasters.
        Remove only exact white at composition time, never dilate an ink mask or
        tint/recolor the nonwhite glyph/diagram pixels. The original assets and
        native antialiasing remain unchanged. This is not a generic image keyer:
        photos, filled white symbols and non-white source backgrounds need an
        authored alpha/content matte instead of this whiteboard-only contract.
        """
        if not self.highlight_underlay_enabled or f['kind'] not in ('glow','frame'):
            return content
        layer=Image.new('RGBA',content.size)
        d=ImageDraw.Draw(layer);s=self.config.ui_scale
        for x,y,w,h in f.get('world_bounds_list',[f['world_bounds']]):
            a,z=tr((x-4,y-4)),tr((x+w+4,y+h+4))
            d.rounded_rectangle((*a,*z),radius=max(2,round(8*s)),
                                fill=(242,61,68,round(34*f['opacity'])))
        backdrop=Image.alpha_composite(Image.new('RGBA',content.size,'white'),layer)
        # Only (255,255,255) is background. Preserve every nonwhite pixel exactly,
        # including native antialiasing, semantic math colors and circuit lines.
        channels=content.convert('RGB').split()
        minimum=ImageChops.darker(ImageChops.darker(channels[0],channels[1]),channels[2])
        ink_alpha=minimum.point(lambda v:0 if v==255 else 255)
        foreground=content.convert('RGBA');foreground.putalpha(ink_alpha)
        return Image.alpha_composite(backdrop,foreground).convert('RGB')

    def annotation(self,im,f,tr,ink):
        layer=Image.new('RGBA',im.size);d=ImageDraw.Draw(layer);s=self.config.ui_scale
        boxes=f.get('world_bounds_list',[f['world_bounds']])
        for x,y,w,h in boxes:
            a,z=tr((x-4,y-4)),tr((x+w+4,y+h+4));color=(242,61,68,round(190*f['opacity']))
            if f['kind']=='arrow':
                if 'arrow_points' not in f:raise ValueError('Arrow requires frozen whitespace route')
                a,z=[tr(p) for p in f['arrow_points']];d.line([a,z],fill=color,width=max(1,round(3*s)))
                ang=math.atan2(z[1]-a[1],z[0]-a[0]);length=12*s
                d.line([(z[0]-length*math.cos(ang-.5),z[1]-length*math.sin(ang-.5)),z,(z[0]-length*math.cos(ang+.5),z[1]-length*math.sin(ang+.5))],fill=color,width=max(1,round(3*s)))
            else:d.rounded_rectangle((*a,*z),radius=max(2,round(8*s)),outline=color,width=max(1,round(3*s)))
        layer=Image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(4*s)),layer)
        # All actual visible text/formula/circuit ink participates, including chrome.
        protected=ink.filter(ImageFilter.MaxFilter(7 if self.config.width>=1920 else 5))
        layer.putalpha(ImageChops.multiply(layer.getchannel('A'),ImageChops.invert(protected)))
        im.paste(layer,(0,0),layer)
    def render(self,t,record=True):
        if not 0<=t<self.duration:raise ValueError('Time outside scene')
        tr,scale,view=self.transform(t);im=Image.new('RGB',(self.config.width,self.config.height),'white');d=ImageDraw.Draw(im);states=[]
        for o in self.scene['objects']:
            x,y,w,h=o['world_bounds'];visible=o['start']<=t<o.get('end',self.duration);inside=x+w>view[0] and x<view[0]+view[2] and y+h>view[1] and y<view[1]+view[3]
            progress=0
            if visible:
                progress=min(1,(t-o['start'])/max(.001,o.get('duration',.001))) if o['kind'] in ['formula','asset'] else 1
                if inside:
                    a,z=tr((x,y)),tr((x+w,y+h))
                    if o['kind'] in ['formula','asset']:self.paint_event(im,self.event_by_id[o['id']],progress,tr,scale)
                    elif o['kind']=='text':
                        for row in o.get('text_rows',[{'xy':o.get('xy',[x,y]),'text':o['text']}]):
                            d.text(tr(row['xy']),row['text'],font=typography.object_font(o,scale),fill=o['color'])
                    elif o['kind']=='rect':
                        if o.get('layout_role')!='board_frame' or view[2]>max(b['bounds'][2] for b in self.scene['resolved_layout'])+1e-6:
                            d.rounded_rectangle((*a,*z),radius=max(1,o.get('radius',12)*scale),outline=o.get('stroke','#bfd0de'),width=max(1,round(o.get('width',3)*scale)))
                    elif o['kind']=='line':d.line([tr(p) for p in o['points']],fill=o.get('stroke','#a4b6c6'),width=max(1,round(o.get('width',3)*scale)))
                    else:raise ValueError('Unsupported object kind '+o['kind'])
            states.append({'id':o['id'],'progress':progress,'retained_in_world':visible,'in_view':visible and inside,'world_bounds':o['world_bounds'],'screen_bounds':[*tr((x,y)),w*scale,h*scale]})
        # A persistent full-screen whiteboard owns the subtitle strip during all
        # direct pans and overview motion; camera content cannot enter that strip.
        u=self.config.width/self.scene['render_config']['logical_width']
        clip=[v*u for v in self.layout['content_clip']];band=round(clip[1]+clip[3])
        d.rectangle((0,band,im.width,im.height),fill='white')
        ink=im.convert('L').point(lambda v:255 if v<235 else 0)
        f=self.teacher(t,tr,scale,ink)
        if f:
            im=self.highlight_underlay(im,f,tr)
            d=ImageDraw.Draw(im)
            if f['kind']=='dot':self.dot(im,tr(f['point']),f['opacity'])
            else:self.annotation(im,f,tr,ink)
        d.rectangle((0,band,im.width,im.height),fill='white')
        cue=next((c for c in self.scene['captions'] if c['start']<=t<c['end']),None)
        caption_boxes=[]
        if cue:
            font=native.font(max(1,round(cue['font_size']*u)))
            for row in cue['rows']:
                x,y=[v*u for v in row['xy']];box=[v*u for v in row['background_bounds']]
                d.rounded_rectangle((box[0],box[1],box[0]+box[2],box[1]+box[3]),radius=5*u,fill='#f3f5f8')
                caption_boxes.append([v*u for v in row['bounds']])
                for unit in row['units']:
                    if unit['kind']=='text':d.text((x,y),unit['text'],font=font,fill=self.layout['subtitles']['color'])
                    else:
                        rs=max(1.0,self.raster_scale(u))
                        eq=native.equation(unit['latex'],cue['font_size']*rs,10000*rs)['im']
                        # Rasterize at or above target density, then fit the frozen
                        # logical unit box. Never upscale the logical-size bitmap.
                        eq=eq.resize((max(1,round(unit['width']*u)),max(1,round(unit['height']*u))),Image.Resampling.LANCZOS)
                        im.paste(eq,(round(x),round(y+(self.layout['subtitles']['line_height']*u-eq.height)/2)),eq)
                    x+=unit['width']*u
        shell=[v*u for v in self.layout['whiteboard']]
        d.rectangle((shell[0],shell[1],shell[0]+shell[2],shell[1]+shell[3]),outline='#bfd0de',width=max(1,round(2*u)))
        for state in states:
            state['visible_screen_bounds']=layout.intersection(state['screen_bounds'],clip) if state['in_view'] else [0,0,0,0]
        receipt={'time':t,'camera':view,'objects':states,'pointer':f,'highlight_underlay':{'enabled':self.highlight_underlay_enabled,'applied':bool(self.highlight_underlay_enabled and f and f['kind'] in ('glow','frame')),'fill_rgba':[242,61,68,34],'order':['whiteboard','attention_fill','content_ink','glyph_safe_attention_outline','captions_and_shell'],'white_matte_policy':'exact_white_only_nonwhite_pixels_unchanged'},'caption_segment':cue['id'] if cue else None,'caption_text':cue['text'] if cue else None,'caption_narration_id':cue['narration_id'] if cue else None,'caption_source_range':cue['source_range'] if cue else None,'caption_boxes':caption_boxes,'content_viewport':clip,'whiteboard_bounds':shell,'subtitle_zone':[v*u for v in self.layout['subtitle_zone']],'image_sha256':hashlib.sha256(im.tobytes()).hexdigest(),'hash_domain':'raw_rgb24','dimensions':list(im.size)}
        if record:self.records.append(receipt)
        return im,receipt

def frame_state_key(scene,t):
    """Exact static-frame memo key; animation frames remain unique.

    This only skips re-rasterization when all time-dependent render inputs are
    constant. The same encoder still emits every CFR frame and full receipt.
    """
    camera=next((c for c in scene['camera_track'] if c['start']<=t<c['end']),scene['camera_track'][-1])
    camera_key=tuple(camera['from']) if camera['from']==camera['to'] else ('moving',t)
    states=[]
    for o in scene['objects']:
        visible=o['start']<=t<o.get('end',scene['duration'])
        progress=min(1,(t-o['start'])/max(.001,o.get('duration',.001))) if visible and o['kind'] in ('formula','asset') else int(visible)
        states.append((o['id'],visible,progress))
    reveal=next((o for o in scene['objects'] if o['kind']=='formula' and o['start']<t<o['start']+o['duration']),None)
    action=next((a for a in scene.get('teacher_actions',[]) if a['start']<=t<a['end']),None)
    attention=('reveal',t) if reveal else ((action['id'],max(0,min(1,(t-action['start'])/.18,(action['end']-t)/.18))) if action else None)
    cue=next((c['id'] for c in scene['captions'] if c['start']<=t<c['end']),None)
    return (camera_key,tuple(states),attention,cue)
