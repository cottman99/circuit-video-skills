import copy,hashlib,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import pipeline as p
import voice_adapter as voice

class VoiceInputTests(unittest.TestCase):
    def test_same_lesson_source(self):
        l={'voice':{'name':'example','rate':'+0%'},'narration':[{'id':'s1','text':'resistor one'}]}
        plan=voice.plan_from_lesson(l);voice.validate_spoken_policy(plan)
        self.assertEqual(plan['beats'][0]['spoken_text'],l['narration'][0]['text'])
        self.assertNotIn('display_text',plan['beats'][0])
        a=voice.speech_digest(plan);l['narration'][0]['text']='resistor two';self.assertNotEqual(a,voice.speech_digest(voice.plan_from_lesson(l)))
    def test_no_dual_transcript_in_voice_plan(self):
        with self.assertRaises(ValueError):voice.plan_from_lesson({'voice':{},'narration':[{'id':'s1','display_text':'summary','spoken_text':'Full narration.'}]})

@unittest.skipUnless(importlib.util.find_spec('fitz'),'Optional PyMuPDF not installed')
class PdfInputTests(unittest.TestCase):
    def setup_catalog(self,base):
        import fitz
        path=base/'original.pdf';doc=fitz.open();page=doc.new_page(width=200,height=100);page.draw_line((20,50),(180,50));page.insert_text((50,30),'Original test');doc.save(path);doc.close()
        return {'sources':{'sample':{'id':'sample','path':'original.pdf','sha256':p.sha(path),'page':1,'pdf_rotation':0,'redistribution_basis':'Original generated test'}},'assets':{'sample-crop':{'source_id':'sample','crop_version':'1','crop_normalized':[0,0,1,1],'white_matte_safe':True}}}
    def test_pdf_render_integrated(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);catalog=self.setup_catalog(base);l=json.loads((ROOT/'examples/resistor-divider/lesson.json').read_text());l['source_catalog']=catalog
            o=next(o for o in l['objects'] if o['id']=='model.current');o.update(kind='asset',asset_id='sample-crop',world_bounds=[1050,270,400,200])
            scene=p.compile_data(l,base);r=p.CanvasRenderer(scene,width=640,fps=5);im,receipt=r.render(2.4)
            self.assertEqual(im.size,(640,360));self.assertTrue(r.assets.records);r.assets.close()
    def test_changed_pdf_rejected(self):
        from source_catalog_assets import CatalogAssets
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);catalog=self.setup_catalog(base);(base/'original.pdf').write_bytes(b'changed')
            with self.assertRaises(ValueError):CatalogAssets(catalog,base)
    def test_path_escape_rejected(self):
        from source_catalog_assets import CatalogAssets
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);catalog=self.setup_catalog(base);catalog['sources']['sample']['path']='../outside.pdf'
            with self.assertRaises(ValueError):CatalogAssets(catalog,base)
    def test_crop_rejected(self):
        from source_catalog_assets import CatalogAssets
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);catalog=self.setup_catalog(base);catalog['assets']['sample-crop']['crop_normalized']=[0,0,2,1]
            with self.assertRaises(ValueError):CatalogAssets(catalog,base)
if __name__=='__main__':unittest.main()
