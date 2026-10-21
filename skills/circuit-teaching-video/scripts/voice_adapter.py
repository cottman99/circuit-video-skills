#!/usr/bin/env python3
"""Optional Edge TTS sentence-boundary adapter. Only explicit --synthesize sends text.
Input uses the same lesson narration records, never a second authored transcript.
This adapter is network-dependent and was not exercised against the live provider
in the public release smoke test. No word-alignment or pronunciation claim.
"""
from pathlib import Path
import argparse,asyncio,copy,hashlib,json,math,os,re,subprocess,sys,tempfile,time,wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rendering'))
from speech_text import build_speech_plan
HERE=Path.cwd()
def validate_spoken_policy(plan):
 ensure(plan.get('narration'),'Missing complete formal transcript')
 expected=build_speech_plan(plan['narration'],plan['voice'])
 ensure(plan.get('beats')==expected['beats'],'Spoken output/span map must be derived from the formal transcript, not independently edited')


def load(p):return json.loads(Path(p).read_text())

def dump(p,d):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2))

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def digest(d):return hashlib.sha256(json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def speech_digest(plan):
 validate_spoken_policy(plan)
 return digest(build_speech_plan(plan['narration'],plan['voice']))

def norm(t):return re.sub(r'\s+','',t)

def ensure(ok,msg):
 if not ok:raise ValueError(msg)

async def synthesize(plan,base=HERE):
 import edge_tts
 validate_spoken_policy(plan)
 base=Path(base);audio_dir=base/'audio';audio_dir.mkdir(exist_ok=True)
 text=''.join(b['spoken_text'] for b in plan['beats']);voice=plan['voice'];request={'text':text,**voice};rh=digest(request)
 meta_path=audio_dir/'provider_events.json';mp3=audio_dir/'narration.mp3';wav=audio_dir/'narration.wav'
 if meta_path.exists() and mp3.exists():
  meta=load(meta_path);ensure(meta['request_sha256']==rh,'Cached request changed: use fresh output directory')
  ensure(sha(mp3)==meta['mp3_sha256'],'Cached MP3 hash mismatch')
 else:
  events=[];started=time.time()
  # One natural paragraph per request. No sentence-by-sentence synthesis or audition pass.
  try:
   with mp3.open('wb') as f:
    async for chunk in edge_tts.Communicate(text,voice['name'],rate=voice['rate'],boundary='SentenceBoundary',proxy=os.environ.get('HTTPS_PROXY')).stream():
     if chunk['type']=='audio':f.write(chunk['data'])
     else:events.append(chunk)
  except Exception as e:
   dump(audio_dir/'tts_blocker.json',{'exception':type(e).__name__,'message':str(e),'request_sha256':rh,'provider':'edge_tts','voice':voice,'requested_at_unix':started,'no_fabricated_boundaries':True});raise
  meta={'request_sha256':rh,'request':request,'events':events,'mp3_sha256':sha(mp3),'provider':'edge_tts','paragraph_requests':1};dump(meta_path,meta)
 events=[e for e in meta['events'] if e['type']=='SentenceBoundary']
 ensure(norm(''.join(e['text'] for e in events))==norm(text),'Provider returned text differs from spoken request')
 ensure(len(events)==len(plan['beats']),'Provider did not return one boundary per authored sentence; regroup before proceeding')
 # A cached WAV is never trusted independently of the verified MP3. Decode to
 # a temporary file on every run, check PCM and all sentence bounds, then replace
 # the output atomically. A stale/tampered WAV cannot manufacture valid evidence.
 mp3_hash=sha(mp3);metadata_hash=sha(meta_path)
 sentences=[]
 with tempfile.TemporaryDirectory(prefix='.decode-',dir=audio_dir) as temporary:
  decoded=Path(temporary)/'decoded.wav'
  subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(mp3),'-map','0:a:0','-vn','-c:a','pcm_s16le','-ar','24000','-ac','1',str(decoded)],check=True)
  ensure(sha(mp3)==mp3_hash and sha(meta_path)==metadata_hash,'Audio input changed during decode')
  with wave.open(str(decoded)) as w:
   frames=w.getnframes();sr=w.getframerate();channels=w.getnchannels();width=w.getsampwidth();compression=w.getcomptype();pcm=w.readframes(frames)
  ensure((sr,channels,width,compression)==(24000,1,2,'NONE'),'Decoded audio must be 24 kHz mono 16-bit PCM')
  ensure(frames>0 and len(pcm)==frames*channels*width,'Decoded PCM is empty or truncated')
  duration=frames/sr;previous_end=0.0
  for index,(beat,e) in enumerate(zip(plan['beats'],events)):
   ensure(norm(beat['spoken_text'])==norm(e['text']),f"Provider sentence mapping mismatch at {beat['id']}")
   offset=e['offset'];span=e['duration']
   ensure(all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (offset,span)),'Provider sentence timing must be finite numeric values')
   start=offset/1e7;end=(offset+span)/1e7
   ensure(0<=start<end and start>=previous_end,'Provider sentence times must be positive, ordered and nonoverlapping')
   ensure(end<=duration+1/sr,'Provider sentence extends beyond decoded PCM duration')
   previous_end=end
   sentences.append({'sentence_id':beat['sentence_id'],'spoken_text':beat['spoken_text'],'formal_text':beat['formal_text'],'formal_text_sha256':beat['formal_text_sha256'],'span_map':beat['span_map'],'start':start,'end':end,'provider_event_indices':[index],'boundary_source':'provider SentenceBoundary'})
  audio={'path':'audio/narration.wav','sha256':sha(decoded),'pcm_sha256':hashlib.sha256(pcm).hexdigest(),'pcm_frames':frames,'sample_rate':sr,'channels':channels,'sample_width_bytes':width,'duration':duration,'source_mp3_sha256':mp3_hash,'decode_method':'ffmpeg_pcm_s16le_24000hz_mono_fresh_decode'}
  decoded.replace(wav)
 receipt={'schema_version':1,'speech_sha256':speech_digest(plan),'provider':'edge_tts','voice':voice,'provider_events_path':'audio/provider_events.json','provider_events_sha256':metadata_hash,'provider_validation':{'text_exact_match':True,'boundary_granularity':'sentence','paragraph_requests':1,'asr_used':False,'manual_word_timing_used':False,'cached_request_revalidated':True,'pcm_rederived_from_verified_mp3':True,'sentence_bounds_within_pcm':True},'audio':audio,'sentences':sentences}
 dump(base/'voice_receipt.json',receipt);return receipt

def plan_from_lesson(lesson):
 narration=[{k:copy.deepcopy(n[k]) for k in ('id','text','speech_adaptations') if k in n} for n in lesson['narration']]
 # Derive before stripping any legacy fields so competing transcripts fail closed.
 result=build_speech_plan(lesson['narration'],lesson['voice'])
 result['narration']=narration
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('lesson',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--synthesize',action='store_true');a=p.parse_args()
 if not a.synthesize:p.error('Use --synthesize only after authorizing transmission of narration text to the provider')
 a.output.mkdir(parents=True,exist_ok=True)
 result=asyncio.run(synthesize(plan_from_lesson(load(a.lesson)),a.output));print(json.dumps({'status':'measured_sentence_receipt','duration':result['audio']['duration']}))
if __name__=='__main__':main()
