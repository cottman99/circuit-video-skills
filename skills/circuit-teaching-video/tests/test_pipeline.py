import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import pipeline as p
import layout_constraints as layout
from world_canvas import CanvasRenderer,frame_state_key
from PIL import Image,ImageChops

def lesson():return json.loads((ROOT/'examples/resistor-divider/lesson.json').read_text())
class PipelineTests(unittest.TestCase):
    def test_compile_determinism(self):self.assertEqual(p.compile_data(lesson()),p.compile_data(lesson()))
    def test_author_not_mutated(self):
        l=lesson();before=copy.deepcopy(l);p.compile_data(l);self.assertEqual(l,before)
    def reject(self,modify):
        l=lesson();modify(l)
        with self.assertRaises((ValueError,KeyError)):p.compile_data(l)
    def test_duplicate_identity(self):self.reject(lambda l:l['objects'].append(copy.deepcopy(l['objects'][0])))
    def test_missing_universe(self):self.reject(lambda l:l['required_object_ids'].pop())
    def test_asset_without_catalog_rejected(self):self.reject(lambda l:l['objects'][0].update(kind='asset'))
    def test_unsupported_capability(self):self.reject(lambda l:l['required_capabilities'].append('word_alignment'))
    def test_dependency_cycle(self):self.reject(lambda l:l['knowledge_graph']['edges'].append({'from':'evaluate','to':'model','type':'prerequisite'}))
    def test_camera_gap(self):self.reject(lambda l:l['camera_track'][1].update(start=3.1))
    def test_nonfinite_geometry(self):self.reject(lambda l:l['objects'][0]['world_bounds'].__setitem__(0,float('nan')))
    def test_nonpersistent_object(self):self.reject(lambda l:l['objects'][0].update(end=3))
    def test_premature_read_window(self):self.reject(lambda l:next(o for o in l['objects'] if o['kind']=='formula').update(read_window=[0,1]))
    def test_caption_overlap(self):self.reject(lambda l:l['captions'][1].update(start=2))
    def test_caption_overflow(self):self.reject(lambda l:l['captions'][0].update(display_text='Very long caption. '*100))
    def test_title_collision(self):self.reject(lambda l:next(o for o in l['objects'] if o['id']=='model.title').update(xy=[1050,50]))
    def test_scene_tamper(self):
        scene=p.compile_data(lesson());scene['duration']=100
        with self.assertRaises(ValueError):p.verify_scene(scene)
    def test_runtime_tamper(self):
        scene=p.compile_data(lesson());scene['runtime']['files']['scripts/pipeline.py']='0'*64
        scene.pop('scene_digest');scene['scene_digest']=p.digest(scene)
        with self.assertRaises(ValueError):p.verify_scene(scene)
    def test_moving_and_static_keys(self):
        scene=p.compile_data(lesson());self.assertNotEqual(frame_state_key(scene,3.1),frame_state_key(scene,3.2))
        self.assertEqual(frame_state_key(scene,2.3),frame_state_key(scene,2.4))
    def test_still_frame_receipt_geometry(self):
        scene=p.compile_data(lesson());r=CanvasRenderer(scene,width=640,fps=5)
        for t in [0,.75,2.4,3.5,6,7.9]:
            im,receipt=r.render(t);self.assertEqual(im.size,(640,360));self.assertTrue(layout.validate_frame_layout(scene,{'width':640,'fps':5},receipt));self.assertEqual(len(receipt['objects']),len(scene['objects']))
    def test_underlay_preserves_all_nonwhite_ink(self):
        scene=p.compile_data(lesson());r=CanvasRenderer(scene,width=640,fps=5)
        original=Image.new('RGB',(640,360),'white');original.putpixel((100,100),(36,100,181));original.putpixel((101,100),(254,254,254))
        f={'kind':'frame','world_bounds':[90,90,30,30],'opacity':1}
        result=r.highlight_underlay(original,f,lambda p:p)
        self.assertEqual(original.getpixel((100,100)),result.getpixel((100,100)))
        self.assertEqual(original.getpixel((101,100)),result.getpixel((101,100)))
        self.assertNotEqual(result.getpixel((105,105)),(255,255,255))
    def test_caption_math_rasterizes_at_native_density(self):
        from unittest.mock import patch
        import logical_scene as native
        l=lesson();l['captions'][0]['display_text']='Transconductance g_m remains explicit.'
        scene=p.compile_data(l)
        for width,expected_size in [(640,34),(3840,68)]:
            r=CanvasRenderer(scene,width=width,fps=15)
            with patch.object(native,'equation',wraps=native.equation) as raster:
                image,receipt=r.render(2.4)
                self.assertTrue(raster.call_args_list)
                self.assertTrue(all(call.args[1]>=expected_size for call in raster.call_args_list))
                self.assertTrue(layout.validate_frame_layout(scene,{'width':width,'fps':15},receipt))
                self.assertEqual(image.width,width)
    def test_original_example_not_external_source(self):
        l=lesson();self.assertEqual(len(l['sources']),1);self.assertEqual(l['sources'][0]['id'],'original')
if __name__=='__main__':unittest.main()
