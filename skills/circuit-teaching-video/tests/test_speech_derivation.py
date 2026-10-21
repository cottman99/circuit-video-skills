import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import pipeline as p
import voice_adapter as voice
from speech_text import derive_sentence,build_speech_plan,speech_identity


class SpeechDerivationTests(unittest.TestCase):
    def sample(self):
        text='At x² = 4, M1′ remains distinct; Si is silicon.'
        adaptations=[]
        for token,meaning in [('x²','power'),('M1′','identifier')]:
            start=text.index(token)
            adaptations.append({'source_range':[start,start+len(token)],'source_text':token,
                                'kind':'notation','meaning':meaning})
        start=text.index('Si')
        adaptations.append({'source_range':[start,start+2],'source_text':'Si','kind':'term','reading':'silicon'})
        return {'id':'n1','text':text,'speech_adaptations':adaptations}

    def test_formal_symbols_preserved_voice_derived_and_spans_cover_both(self):
        record=self.sample();before=copy.deepcopy(record);beat=derive_sentence(record)
        self.assertEqual(record,before)
        self.assertEqual(beat['formal_text'],record['text'])
        self.assertIn('x 的平方',beat['spoken_text'])
        self.assertIn('M1 撇',beat['spoken_text'])
        formal_cursor=spoken_cursor=0
        for span in beat['span_map']:
            self.assertEqual(span['formal_range'][0],formal_cursor)
            self.assertEqual(span['spoken_range'][0],spoken_cursor)
            formal_cursor=span['formal_range'][1];spoken_cursor=span['spoken_range'][1]
        self.assertEqual(formal_cursor,len(record['text']))
        self.assertEqual(spoken_cursor,len(beat['spoken_text']))

    def test_caption_uses_formal_master_not_pronunciation_expansion(self):
        lesson=json.loads((ROOT/'examples/resistor-divider/lesson.json').read_text())
        text='Transconductance g_m remains explicit.'
        start=text.index('g_m')
        lesson['narration'][0].update(text=text,speech_adaptations=[
            {'source_range':[start,start+3],'source_text':'g_m','kind':'notation','meaning':'subscript'}])
        lesson['captions'][0]['source_range']=[0,len(text)]
        scene=p.compile_data(lesson)
        self.assertEqual(scene['captions'][0]['text'],text)
        self.assertIn('g 下标 m',build_speech_plan(lesson['narration'])['beats'][0]['spoken_text'])

    def test_no_independent_whole_spoken_or_display_transcript(self):
        for key in ('spoken_text','display_text'):
            record=self.sample();record[key]='Short summary.'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'independent'):
                derive_sentence(record)

    def test_deletion_whole_sentence_and_stale_span_rejected(self):
        invalid=[]
        record=self.sample();record['speech_adaptations'][-1]['reading']='';invalid.append(record)
        record=self.sample();record['speech_adaptations']=[{'source_range':[0,len(record['text'])],
            'source_text':record['text'],'kind':'term','reading':'Summary'}];invalid.append(record)
        record=self.sample();record['speech_adaptations'][0]['source_range']=[0,2];invalid.append(record)
        record=self.sample();record['speech_adaptations'][0]['source_text']='x^2';invalid.append(record)
        record=self.sample();record['speech_adaptations'].append(record['speech_adaptations'][0]);invalid.append(record)
        record=self.sample();record['speech_adaptations'][0]['spoken_text']='summary';invalid.append(record)
        for record in invalid:
            with self.subTest(record=record),self.assertRaises(ValueError):
                derive_sentence(record)

    def test_typed_negative_subscript_keeps_sign_and_index(self):
        record={'id':'s','text':'Keep a_{-1} explicit.','speech_adaptations':[
            {'source_range':[5,11],'source_text':'a_{-1}','kind':'notation','meaning':'subscript'}]}
        self.assertIn('a 下标 负 1',derive_sentence(record)['spoken_text'])
        record['speech_adaptations'][0]={'source_range':[5,11],'source_text':'a_{-1}','kind':'term','reading':'a'}
        with self.assertRaises(ValueError):derive_sentence(record)

    def test_derived_voice_plan_rejects_manual_output_edit(self):
        plan=voice.plan_from_lesson({'voice':{'name':'test','rate':'+0%'},'narration':[self.sample()]})
        voice.validate_spoken_policy(plan)
        self.assertEqual(voice.speech_digest(plan),speech_identity(plan['narration'],plan['voice']))
        plan['beats'][0]['spoken_text']='Summary.'
        with self.assertRaisesRegex(ValueError,'derived'):
            voice.validate_spoken_policy(plan)

    def test_pronunciation_change_invalidates_audio_without_changing_captions(self):
        lesson=json.loads((ROOT/'examples/resistor-divider/lesson.json').read_text())
        text='Si is silicon.'
        lesson['narration'][0].update(text=text,speech_adaptations=[
            {'source_range':[0,2],'source_text':'Si','kind':'term','reading':'silicon'}])
        lesson['captions'][0]['source_range']=[0,len(text)]
        with tempfile.TemporaryDirectory() as tmp:
            audio=Path(tmp)/'source.wav';audio.write_bytes(b'Identity-only synthetic test')
            bound=p.bind_audio(lesson,audio);old=p.compile_data(bound)['captions'][0]['text']
            bound['narration'][0]['speech_adaptations'][0]['reading']='silicon material'
            with self.assertRaisesRegex(ValueError,'speech adaptation changed'):p.compile_data(bound)
            bound=p.bind_audio(bound,audio)
            self.assertEqual(p.compile_data(bound)['captions'][0]['text'],old)


if __name__=='__main__':
    unittest.main()
