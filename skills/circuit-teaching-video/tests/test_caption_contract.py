import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import pipeline as p
from caption_contract import resolve_captions
import check_video_decisions as decisions


def lesson():
    return json.loads((ROOT/'examples/resistor-divider/lesson.json').read_text())


class CaptionContractTests(unittest.TestCase):
    def test_single_source_and_exact_reconstruction(self):
        source = lesson()
        scene = p.compile_data(source)
        for n in source['narration']:
            actual = ''.join(c['text'] for c in scene['captions'] if c['narration_id'] == n['id'])
            self.assertEqual(actual, n['text'])
        self.assertEqual(scene['caption_coverage']['status'], 'PASS')
        self.assertNotIn('text', source['captions'][0])

    def test_authored_captions_reject_text_even_if_equal(self):
        for field in ('text', 'display_text', 'spoken_text'):
            source = lesson()
            source['captions'][0][field] = source['narration'][0]['text']
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'references and times only'):
                p.compile_data(source)

    def test_summary_cannot_be_subtitle(self):
        source = lesson()
        source['captions'][0]['display_text'] = 'Model summary'
        with self.assertRaisesRegex(ValueError, 'references and times only'):
            p.compile_data(source)

    def test_legacy_unbound_captions_rejected(self):
        source = lesson()
        source.pop('narration')
        with self.assertRaisesRegex(ValueError, 'authoritative narration'):
            p.compile_data(source)

    def test_missing_duplicated_and_reordered_text_rejected(self):
        for span in ([1, 20], [0, 20], [20, 5], [-1, 20], [False, 20]):
            source = lesson()
            source['captions'][0]['source_range'] = span
            with self.subTest(span=span), self.assertRaises(ValueError):
                p.compile_data(source)
        source = lesson()
        cue = source['captions'][0]
        extra = dict(cue, id='duplicate-range', start=1.5)
        cue['end'] = 1.5
        source['captions'].insert(1, extra)
        with self.assertRaisesRegex(ValueError, 'duplicated'):
            p.compile_data(source)

    def test_missing_narration_caption_rejected(self):
        source = lesson()
        source['captions'].pop()
        with self.assertRaisesRegex(ValueError, 'no full subtitles'):
            p.compile_data(source)

    def test_contiguous_multicue_unicode_slices(self):
        text = '先说明条件，保留负号 − 与 M1′，然后给出结论。'
        narration = [{'id':'s', 'text':text, 'start':1, 'end':4}]
        split = 6
        cues = [{'id':'a','narration_id':'s','source_range':[0,split],'start':1,'end':2},
                {'id':'b','narration_id':'s','source_range':[split,len(text)],'start':2,'end':4}]
        resolved, report = resolve_captions(narration,cues,5)
        self.assertEqual(''.join(c['text'] for c in resolved),text)
        self.assertEqual(report['formal_codepoints'],len(text))
        cues[1]['source_range'][0] = split-1
        with self.assertRaisesRegex(ValueError,'duplicated'):
            resolve_captions(narration,cues,5)

    def test_gap_overlap_nonfinite_and_wrong_source_rejected(self):
        for update in ({'start':.1},{'end':2.9},{'end':3.1},{'start':float('nan')},
                       {'narration_id':'missing'},{'kind':'visual_annotation'}):
            source = lesson()
            source['captions'][0].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                p.compile_data(source)

    def test_board_annotation_is_independent_of_subtitles(self):
        source = lesson()
        next(o for o in source['objects'] if o['id']=='model.why')['text']='A visual summary.'
        scene = p.compile_data(source)
        self.assertNotIn('A visual summary.', ''.join(c['text'] for c in scene['captions']))
        self.assertEqual(scene['captions'][0]['text'], source['narration'][0]['text'])

    def test_compiled_text_and_render_units_cannot_substitute_summary(self):
        for target in ('text','row','unit'):
            scene = p.compile_data(lesson())
            if target == 'text': scene['captions'][0]['text']='Summary'
            elif target == 'row': scene['captions'][0]['rows'][0]['text']='Summary'
            else: scene['captions'][0]['rows'][0]['units'][0]['text']='Summary'
            scene.pop('scene_digest')
            scene['scene_digest']=p.digest(scene)
            with self.subTest(target=target), self.assertRaises(ValueError):
                p.verify_scene(scene)

    def test_frame_receipt_tracks_exact_text_and_source(self):
        scene=p.compile_data(lesson())
        renderer=p.CanvasRenderer(scene,width=640,fps=15)
        _,receipt=renderer.render(1)
        self.assertEqual(receipt['caption_text'],scene['narration'][0]['text'])
        receipt['caption_text']='Summary'
        with self.assertRaisesRegex(ValueError,'caption text'):
            p.layout.validate_frame_layout(scene,{'width':640,'fps':15},receipt)

    def test_time_only_legacy_audit_cannot_claim_text_coverage(self):
        scene={'duration':1,'subtitles':[{'text':'Summary','start':0,'end':1}],
               'speech_windows':[{'start':0,'end':1}]}
        result=decisions.audit(scene)
        finding=next(f for f in result['findings'] if f['code']=='subtitle_text_coverage')
        self.assertEqual(finding['status'],'unknown')
        scene['narration']=[{'id':'n','text':'Full explanation.','start':0,'end':1}]
        result=decisions.audit(scene)
        finding=next(f for f in result['findings'] if f['code']=='subtitle_text_coverage')
        self.assertEqual(finding['status'],'fail')

    def test_audio_binding_invalidated_by_transcript_timing_voice_and_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio=Path(tmp)/'recording.wav'
            audio.write_bytes(b'Identity test only; no decoding is attempted.')
            original=lesson()
            bound=p.bind_audio(original,audio)
            self.assertNotIn('audio_binding',original)
            p.compile_data(bound)
            for change in ('transcript','timing','voice'):
                changed=copy.deepcopy(bound)
                if change=='transcript':
                    changed['narration'][0]['text']=changed['narration'][0]['text'].replace('ideal','Ideal')
                elif change=='timing':
                    changed['narration'][0]['end']=2.9
                    changed['captions'][0]['end']=2.9
                else: changed['voice']={'name':'another','rate':'+0%'}
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,'changed'):
                    p.compile_data(changed)
            scene=p.compile_data(bound)
            audio.write_bytes(b'Changed recording')
            with self.assertRaisesRegex(ValueError,'Audio differs'):
                p.render(scene,Path(tmp)/'out',audio=audio)

    def test_audio_without_binding_or_transcript_rejected_before_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            for empty in (False,True):
                source=lesson()
                if empty:source['narration']=[];source['captions']=[]
                scene=p.compile_data(source)
                with self.subTest(empty=empty),self.assertRaisesRegex(ValueError,'Audio'):
                    p.render(scene,Path(tmp)/'out',audio=Path(tmp)/'absent.wav')


if __name__ == '__main__':
    unittest.main()
