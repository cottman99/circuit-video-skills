"""Synthetic DEVELOPMENT fixtures only; no real-TTS or heldout success claim."""
from pathlib import Path
import copy,hashlib,json,subprocess,sys,tempfile,unittest,wave,math,struct
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts')]
import course_video as cv
from voice_adapter import plan_from_lesson

def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');return p
class Nodes(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.project=self.base/'project';self.pdf=self.base/'synthetic-development.pdf'
  import fitz
  d=fitz.open();p=d.new_page(width=600,height=400);p.insert_text((45,45),'SYNTHETIC DEVELOPMENT: resistor law');p.insert_text((45,75),'Voltage equals current times resistance. V = I R.');p.draw_line((100,160),(220,160));p.draw_rect((220,145,300,175));p.draw_line((300,160),(420,160));p.insert_text((245,135),'R');d.save(self.pdf);d.close()
  self.call('prepare','--source',str(self.pdf),'--pages','1');s=cv.read(self.project/'CourseProject.json')['SourcePackage']
  self.plan={'title':'电阻关系教学测试','scope_source_sha256':s['sha256'],'selected_pages':[1],'formal_master':[{'id':'s1','text':'先看电阻示意图。','source_pages':[1],'scene_id':'board'},{'id':'s2','text':'电压等于电流乘电阻。','source_pages':[1],'scene_id':'board'}],
  'scenes':[{'id':'board','title':'电阻关系','sentence_ids':['s1','s2'],'source_pages':[1],'source_crops':[{'id':'circuit','page':1,'bbox_normalized':[.1,.25,.8,.55],'white_matte_safe':True,'nondata_exclusions':[]}],'formula_objects':[{'id':'law','latex':'V=IR','source_page':1,'reveal_sentence_id':'s2'}],'teaching_actions':[{'sentence_id':'s1','target_id':'circuit','action':'frame'}]}],
  'coverage':[{'source_page':1,'source_item':'complete illustrative resistor relationship','formal_sentence_ids':['s1','s2'],'visual_object_ids':['board.circuit','board.law']}],'unresolved_issues':[],'scope_statement':'Complete one-page synthetic development example, not real TTS or a heldout.','pronunciation':{},'layout':{'scenes':{'board':{'objects':{'circuit':[100,270,700,200],'law':[1050,340,54]},'labels':[]}}}}
  self.planpath=write(self.base/'plan.json',self.plan)
 def tearDown(self):self.tmp.cleanup()
 def call(self,*args,ok=True):
  c=[sys.executable,str(ROOT/'scripts/course_video.py'),args[0],'--project',str(self.project),*args[1:]];r=subprocess.run(c,capture_output=True,text=True,timeout=90)
  if ok:self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  else:self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
  return json.loads((r.stdout if r.returncode==0 else r.stderr).strip().splitlines()[-1])
 def ingest(self):return self.call('ingest','--plan',str(self.planpath))
 def raw(self):
  v=self.call('voice-input');vp=Path(v['voice_input']);plan=plan_from_lesson(cv.read(vp));raw=self.base/'raw';(raw/'audio').mkdir(parents=True)
  w=raw/'audio/narration.wav'
  with wave.open(str(w),'wb') as f:
   f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i*.1))) for i in range(144000)))
  mp3=raw/'audio/narration.mp3';subprocess.run(['ffmpeg','-v','error','-i',str(w),str(mp3)],check=True)
  req={'text':''.join(x['spoken_text'] for x in plan['beats']),**plan['voice']};events=[{'type':'SentenceBoundary','text':x['spoken_text'],'offset':int(t*1e7),'duration':int(2.7*1e7)} for x,t in zip(plan['beats'],[.1,3.0])]
  write(raw/'audio/provider_events.json',{'provider':'edge_tts','paragraph_requests':1,'request':req,'request_sha256':cv.digest(req),'events':events,'mp3_sha256':cv.sha(mp3),'fixture_only':'SYNTHETIC_AUDIO_NOT_PROVIDER_EXECUTION'})
  return raw
 def test_source_tamper(self):
  p=self.project/'source/page-0001.png';p.write_bytes(b'not a page');self.call('ingest','--plan',str(self.planpath),ok=False);self.assertEqual(cv.read(self.project/'attempts/latest.json')['status'],'FAILED')
 def test_script_order_and_source(self):
  self.plan['scenes'][0]['sentence_ids'].reverse();write(self.planpath,self.plan);self.call('ingest','--plan',str(self.planpath),ok=False)
 def test_caption_override(self):
  self.plan['formal_master'][0]['display_text']='summary';write(self.planpath,self.plan);self.call('ingest','--plan',str(self.planpath),ok=False)
 def test_whole_sentence_voice_rejected(self):
  self.plan['pronunciation']['s1']=[{'kind':'term','source_range':[0,8],'source_text':self.plan['formal_master'][0]['text'],'reading':'其他讲稿'}];write(self.planpath,self.plan);self.call('ingest','--plan',str(self.planpath),ok=False)
 def test_coverage_rejected(self):
  self.plan['coverage'][0]['formal_sentence_ids']=['s1'];write(self.planpath,self.plan);self.call('ingest','--plan',str(self.planpath),ok=False)
 def test_unsupported_action(self):
  self.plan['scenes'][0]['teaching_actions'][0]['action']='arrow';write(self.planpath,self.plan);self.call('ingest','--plan',str(self.planpath),ok=False)
 def test_voice_config_rejected_before_transmission(self):
  for value in ({'name':'voice','rate':'+0%','text':'replacement'}, {'name':'','rate':'+0%'}, {'name':'voice','rate':2}, {'name':'voice'}, None):
   with self.subTest(value=value):
    self.plan['voice']=value;write(self.planpath,self.plan);r=self.call('ingest','--plan',str(self.planpath),ok=False);self.assertIn('VOICE_CONFIG',r['error']);self.assertIsNone(cv.read(self.project/'CourseProject.json')['LessonPlan'])
 def test_voice_and_layout_invalidation(self):
  self.ingest();v1=self.call('voice-input');raw=self.raw();self.call('bind-voice','--raw-run',str(raw));self.plan['layout']['scenes']['board']['objects']['law'][0]+=20;write(self.planpath,self.plan);res=self.ingest();v2=self.call('voice-input');self.assertFalse(res['voice_invalidated']);self.assertEqual(v1['voice_identity'],v2['voice_identity']);self.assertIsNotNone(cv.read(self.project/'CourseProject.json')['MediaTimeline'])
  self.plan['voice']={'name':'zh-CN-YunxiNeural','rate':'+0%'};write(self.planpath,self.plan);r=self.ingest();v3=self.call('voice-input');self.assertTrue(r['voice_invalidated']);self.assertNotEqual(v3['voice_identity'],v2['voice_identity']);self.assertEqual(v3['formal_export'],v1['formal_export']);self.assertIsNone(cv.read(self.project/'CourseProject.json')['MediaTimeline'])
 def test_real_cli_synthetic_render_cache_and_failure(self):
  self.ingest();raw=self.raw();self.call('bind-voice','--raw-run',str(raw));r=self.call('render');self.assertTrue(Path(r['preview_path']).is_file());again=self.call('render');self.assertTrue(again['cache_reused']);self.assertEqual(r['media_sha256'],again['media_sha256']);self.call('qa')
  self.plan['layout']['scenes']['board']['objects']['law'][0]=1900;write(self.planpath,self.plan);self.ingest();self.call('render',ok=False);latest=cv.read(self.project/'attempts/latest.json');self.assertEqual(latest['status'],'FAILED');self.assertNotIn('preview_path',latest);self.assertTrue((self.project/'attempts/latest_success.json').exists())
 def test_raw_receipt_tamper(self):
  self.ingest();raw=self.raw();meta=cv.read(raw/'audio/provider_events.json');meta['events'][0]['text']='arbitrary';write(raw/'audio/provider_events.json',meta);self.call('bind-voice','--raw-run',str(raw),ok=False)
 def test_temporal_unsat_diagnostic(self):
  self.plan['formal_master'][1]['text']='此处保留完整而较长的正式稿件，不允许为了赶上音频而把字幕改写成摘要。';write(self.planpath,self.plan);self.ingest();raw=self.raw();self.call('bind-voice','--raw-run',str(raw));r=self.call('render',ok=False);self.assertIn('TIMING_UNSAT',r['error'])
 def test_normalized_window_tamper_not_trusted(self):
  self.ingest();raw=self.raw();self.call('bind-voice','--raw-run',str(raw));d=cv.read(self.project/'CourseProject.json');d['MediaTimeline']['captions'][0]['end']=.11;write(self.project/'CourseProject.json',d);r=self.call('render','--samples-only');scene=cv.read(r['scene_path']);self.assertAlmostEqual(scene['captions'][0]['end'],3.0)
 def test_no_network_without_explicit_opt_in(self):
  self.ingest();r=self.call('synthesize',ok=False);self.assertIn('AUTHORIZATION_REQUIRED',r['error'])
if __name__=='__main__':unittest.main()
