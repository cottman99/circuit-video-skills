from pathlib import Path
import copy,json,subprocess,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'));import mineru_source as ms

class Adapter(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name);(self.p/'images').mkdir();(self.p/'images/figure.jpg').write_bytes(b'fixture image')
  self.source={'sha256':'a'*64,'selected_pages':[3],'pages':[{'page':3,'image_path':'source/page-0003.png'}],'original_path':'source/original.pdf'}
  self.raw={'schema':'docvortex.middle','schema_version':'2.0','metadata':{'producer':{'name':'mineru','version':'4.0.12'}},'pages':[{'page_idx':2,'blocks':[
   {'index':5,'type':'header','bbox':[.1,.1,.5,.2],'content':[{'type':'text','content':'Field heading'}]},
   {'index':2,'type':'equation','bbox':[.1,.3,.5,.4],'content':r'x=y+z','image_path':'images/figure.jpg'},
   {'index':7,'type':'text','bbox':[.1,.5,.5,.6],'content':[{'type':'text','content':'Use '},{'type':'equation_inline','content':'x'},{'type':'text','content':' only under the stated condition.'}]},
   {'index':8,'type':'image','bbox':[.1,.6,.5,.9],'content':[{'type':'image_body','bbox':[.1,.6,.5,.9],'image_path':'images/figure.jpg','content':''}]}]}]}
  self.rawpath=self.p/'middle_json.json';self.rawpath.write_text(json.dumps(self.raw))
 def tearDown(self):self.tmp.cleanup()
 def norm(self):return ms.normalize(self.source,self.raw,self.p,self.rawpath)
 def test_preserves_order_headers_math_original(self):
  r=self.norm();self.assertEqual([x['parser_index'] for x in r['extraction']['pages'][0]['blocks']],[5,2,7,8]);self.assertEqual(r['extraction']['pages'][0]['blocks'][0]['type'],'header');self.assertEqual(r['original_path'],self.source['original_path']);self.assertEqual(r['extraction']['pages'][0]['blocks'][1]['text_math'][0]['content'],'x=y+z');self.assertIsNone(r['extraction']['confidence']);self.assertIsNone(r['extraction']['provider_warnings']);self.assertFalse(r['extraction']['semantic_validation']);self.assertIsNone(r['extraction']['circuit_netlist'])
 def test_figure_bytes_and_source_page_bound(self):
  b=self.norm()['extraction']['pages'][0]['blocks'][3];self.assertEqual(b['physical_page'],3);self.assertEqual(b['figure_refs'][0]['sha256'],ms.sha(self.p/'images/figure.jpg'))
 def test_unknown_block_retained_warning(self):
  self.raw['pages'][0]['blocks'][0]['type']='unknown';r=self.norm();self.assertEqual(r['extraction']['pages'][0]['blocks'][0]['raw_content'],self.raw['pages'][0]['blocks'][0]['content']);self.assertEqual(r['extraction']['warnings'][0]['code'],'UNSUPPORTED_BLOCK_TYPE')
 def test_invalid_bbox_warning_no_repair(self):
  self.raw['pages'][0]['blocks'][0]['bbox']=[0,0,2,1];b=self.norm()['extraction']['pages'][0]['blocks'][0];self.assertFalse(b['bbox_valid']);self.assertEqual(b['bbox_normalized'],[0,0,2,1])
 def test_missing_or_extra_page_rejected(self):
  self.raw['pages'][0]['page_idx']=3
  with self.assertRaisesRegex(ValueError,'PARSER_SCOPE'):self.norm()
 def test_missing_asset_rejected(self):
  (self.p/'images/figure.jpg').unlink()
  with self.assertRaisesRegex(ValueError,'ASSET_MISSING'):self.norm()
 def test_escape_rejected(self):
  self.raw['pages'][0]['blocks'][1]['image_path']='../secret'
  with self.assertRaisesRegex(ValueError,'ASSET_PATH_ESCAPE'):self.norm()
 def test_duplicate_index_rejected(self):
  self.raw['pages'][0]['blocks'][1]['index']=5
  with self.assertRaisesRegex(ValueError,'BLOCK_INDEX'):self.norm()
 def test_version_rejected(self):
  self.raw['metadata']['producer']['version']='unreviewed'
  with self.assertRaisesRegex(ValueError,'PARSER_VERSION'):self.norm()
 def test_external_import_records_source_base(self):
  source=self.p/'source';source.mkdir();(source/'original.pdf').write_bytes(b'fake PDF bytes for offline binding fixture');(source/'page.png').write_bytes(b'fake page image');s=copy.deepcopy(self.source);s['sha256']=ms.sha(source/'original.pdf');s['pages'][0].update(image_path='source/page.png',image_sha256=ms.sha(source/'page.png'));project=self.p/'CourseProject.json';project.write_text(json.dumps({'SourcePackage':s}));out=self.p/'import';r=subprocess.run([sys.executable,str(ROOT/'scripts/mineru_source.py'),'--project',str(project),'--output',str(out),'--raw',str(self.rawpath),'--raw-source-sha256',s['sha256']],capture_output=True,timeout=10);self.assertEqual(r.returncode,0,r.stderr);result=ms.load(out/'SourcePackage.import.json');self.assertEqual(result['source_base'],str(self.p));self.assertEqual(result['extraction']['input_project']['sha256'],ms.sha(project));self.assertIn('not independently re-derived',result['extraction']['execution']['source_binding'])
 def test_source_or_project_mutation_during_parse_rejected(self):
  for target in ('source','project'):
   with self.subTest(target=target):
    base=self.p/target;base.mkdir();source=base/'source';source.mkdir();pdf=source/'original.pdf';pdf.write_bytes(b'synthetic original');image=source/'page.png';image.write_bytes(b'synthetic page');s=copy.deepcopy(self.source);s['sha256']=ms.sha(pdf);s['pages'][0].update(image_path='source/page.png',image_sha256=ms.sha(image));project=base/'CourseProject.json';project.write_text(json.dumps({'SourcePackage':s}));out=base/'import'
    def mutate(*args):
     changed=pdf if target=='source' else project;changed.write_bytes(changed.read_bytes()+b'changed');return self.rawpath,{'mode':'synthetic mocked parser; not real execution'}
    argv=['mineru_source.py','--project',str(project),'--output',str(out),'--run-local','--mineru-home',str(base),'--model-manifest',str(base/'unused.json')]
    with patch.object(ms,'run_parser',side_effect=mutate),patch.object(sys,'argv',argv):
     with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_DURING_IMPORT'):ms.main()
    self.assertEqual(ms.load(out/'attempt.json')['status'],'FAILED');self.assertFalse((out/'SourcePackage.import.json').exists())
 def test_failed_import_has_record_and_no_export(self):
  out=self.p/'failed';r=subprocess.run([sys.executable,str(ROOT/'scripts/mineru_source.py'),'--project',str(self.p/'missing.json'),'--output',str(out),'--raw',str(self.rawpath),'--raw-source-sha256','x'],capture_output=True,timeout=10);self.assertNotEqual(r.returncode,0);self.assertEqual(ms.load(out/'attempt.json')['status'],'FAILED');self.assertFalse((out/'SourcePackage.import.json').exists())
 def test_missing_models_fail_before_import(self):
  manifest=self.p/'manifest.json';manifest.write_text(json.dumps({'files':[{'path':'missing.onnx','size':1,'sha256':'x'}]}))
  with self.assertRaisesRegex(ValueError,'ASSET_MISSING'):ms.run_parser(self.p/'unused.pdf',[3],self.p,self.p,manifest)
  self.assertNotIn('onnxruntime',sys.modules);self.assertEqual(ms.os.environ['ORT_DISABLE_TELEMETRY'],'1')
if __name__=='__main__':unittest.main()
