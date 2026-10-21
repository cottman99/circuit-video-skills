"""Offline cache regressions. Synthetic audio only; network client is forbidden."""
import asyncio,copy,json,shutil,subprocess,sys,tempfile,types,unittest,wave
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import voice_adapter as voice

def write_wav(path,duration,rate=24000,channels=1,width=2):
    with wave.open(str(path),'wb') as w:
        w.setparams((channels,width,rate,round(rate*duration),'NONE','not compressed'))
        w.writeframes(b'\0'*(round(rate*duration)*channels*width))

def forbid_network(*args,**kwargs):raise AssertionError('Offline tests must not synthesize')

@unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg is needed for offline audio cache tests')
class VoiceCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.audio=self.base/'audio';self.audio.mkdir()
        self.plan=voice.plan_from_lesson({'voice':{'name':'offline-test','rate':'+0%'},'narration':[{'id':'s1','text':'Test.'}]})
        self.stub=patch.dict(sys.modules,{'edge_tts':types.SimpleNamespace(Communicate=forbid_network)});self.stub.start()
    def tearDown(self):self.stub.stop();self.tmp.cleanup()
    def cache(self,duration=1.25,event=None):
        original=self.base/'original.wav';write_wav(original,duration)
        mp3=self.audio/'narration.mp3'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(original),'-c:a','libmp3lame',str(mp3)],check=True)
        event=event or {'type':'SentenceBoundary','text':'Test.','offset':0,'duration':10_000_000}
        request={'text':'Test.',**self.plan['voice']}
        metadata={'request_sha256':voice.digest(request),'request':request,'events':[event],'mp3_sha256':voice.sha(mp3),'provider':'offline-synthetic'}
        voice.dump(self.audio/'provider_events.json',metadata)
    def run_cached(self):return asyncio.run(voice.synthesize(self.plan,self.base))
    def test_stale_short_wav_is_rederived_from_verified_mp3(self):
        self.cache();wav=self.audio/'narration.wav';write_wav(wav,.25);old_hash=voice.sha(wav)
        result=self.run_cached()
        self.assertGreater(result['audio']['duration'],1)
        self.assertNotEqual(result['audio']['sha256'],old_hash)
        self.assertEqual(result['audio']['source_mp3_sha256'],voice.sha(self.audio/'narration.mp3'))
        self.assertTrue(result['provider_validation']['pcm_rederived_from_verified_mp3'])
        self.assertTrue(result['provider_validation']['sentence_bounds_within_pcm'])
        self.assertEqual((result['audio']['sample_rate'],result['audio']['channels'],result['audio']['sample_width_bytes']),(24000,1,2))
    def test_short_verified_mp3_rejects_sentence_past_pcm(self):
        self.cache(duration=.25);write_wav(self.audio/'narration.wav',2)
        with self.assertRaisesRegex(ValueError,'beyond decoded PCM'):self.run_cached()
        self.assertFalse((self.base/'voice_receipt.json').exists())
    def test_invalid_cached_mp3_cannot_be_hidden_by_valid_wav(self):
        self.cache();write_wav(self.audio/'narration.wav',2);(self.audio/'narration.mp3').write_bytes(b'not original mp3')
        with self.assertRaisesRegex(ValueError,'MP3 hash mismatch'):self.run_cached()
    def test_nonfinite_boundary_rejected(self):
        self.cache(event={'type':'SentenceBoundary','text':'Test.','offset':0,'duration':float('nan')})
        with self.assertRaisesRegex(ValueError,'finite numeric'):self.run_cached()
    def test_negative_boundary_rejected(self):
        self.cache(event={'type':'SentenceBoundary','text':'Test.','offset':-100,'duration':10_000_000})
        with self.assertRaisesRegex(ValueError,'positive, ordered'):self.run_cached()
    def test_changed_request_rejected_without_network(self):
        self.cache();self.plan['voice']['rate']='+10%'
        with self.assertRaisesRegex(ValueError,'Cached request changed'):self.run_cached()
if __name__=='__main__':unittest.main()
