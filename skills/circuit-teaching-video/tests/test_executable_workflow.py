"""Behavioral tests for the bounded content-to-preview workflow, all offline."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_workflow as w


def package():
    return json.loads((ROOT/'examples/resistor-divider/content-package.json').read_text())


class ExecutableWorkflowTests(unittest.TestCase):
    def test_one_command_builds_frozen_scene_and_actual_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(ROOT/'scripts/run_workflow.py'),
                                     str(ROOT/'examples/resistor-divider/content-package.json'),
                                     '--output', tmp, '--synthetic-audio-fixture', '--video', '--width', '320', '--fps', '2'],
                                    check=True, text=True, capture_output=True)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest['status'], 'SUCCESS')
            self.assertEqual(manifest['technical_status'], 'TECHNICAL_PREVIEW_UNREVIEWED')
            scene = json.loads(Path(manifest['scene_path']).read_text())
            w.p.verify_scene(scene)
            source = package()
            self.assertEqual(scene['semantic_model'], source['content']['semantic_model'])
            self.assertEqual({o['id'] for o in scene['objects']}, set(source['visual']['required_object_ids']))
            for original, caption in zip(source['content']['narration'], scene['captions']):
                self.assertEqual(original['text'], caption['text'])
            media = json.loads((Path(manifest['preview_path'])/'manifest.json').read_text())
            self.assertEqual(media['audio'], 'synthetic_test_tones_not_speech')
            self.assertEqual(media['decoded_frame_count'], 16)
            self.assertTrue((Path(manifest['preview_path'])/'preview.mp4').is_file())
            self.assertFalse(manifest['review']['previous_reviews_reused'])

    def test_voice_change_invalidates_audio_timing_scene_media_not_formal_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = package()
            first = w.run(source, tmp, width=320, fps=2)
            source['voice']['rate'] = '+10%'
            second = w.run(source, tmp, width=320, fps=2)
            self.assertEqual(first['node_versions']['formal_captions'], second['node_versions']['formal_captions'])
            self.assertEqual(json.loads(Path(first['artifacts']['formal_captions']).read_text()),
                             json.loads(Path(second['artifacts']['formal_captions']).read_text()))
            self.assertEqual(set(second['invalidated_nodes']), {'phonetic_voice', 'audio_events', 'timeline', 'frozen_scene', 'preview'})
            a = json.loads(Path(first['artifacts']['audio_events']).read_text())
            b = json.loads(Path(second['artifacts']['audio_events']).read_text())
            self.assertNotEqual(a['audio']['sha256'], b['audio']['sha256'])

    def test_local_pronunciation_change_keeps_formal_text(self):
        source = package()
        source['content']['narration'][0]['text'] = 'Si is silicon.'
        source['content']['narration'][0]['speech_adaptations'] = [
            {'source_range': [0, 2], 'source_text': 'Si', 'kind': 'term', 'reading': 'silicon'}]
        source['caption_refs'][0]['source_range'] = [0, 14]
        formal, voice = w.validate_package(source)
        source['content']['narration'][0]['speech_adaptations'][0]['reading'] = 'silicon material'
        revised_formal, revised_voice = w.validate_package(source)
        self.assertEqual(formal, revised_formal)
        self.assertNotEqual(voice, revised_voice)

    def test_layout_change_reuses_validated_audio_without_synthesis(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = package()
            first = w.run(source, tmp, width=320, fps=2)
            source['visual']['layout_contract']['subtitles']['horizontal_padding'] += 2
            with patch.object(w, 'make_fixture', side_effect=AssertionError('audio must not regenerate')):
                second = w.run(source, tmp, width=320, fps=2)
            self.assertEqual(second['audio_cache'], 'validated_reuse')
            self.assertEqual(first['node_versions']['audio_events'], second['node_versions']['audio_events'])
            self.assertEqual(set(second['invalidated_nodes']), {'timeline', 'frozen_scene', 'preview'})

    def test_missing_source_coverage_and_independent_caption_text_rejected(self):
        for mutate in [lambda p: p['caption_refs'].pop(),
                       lambda p: p['caption_refs'][0]['source_range'].__setitem__(1, 8),
                       lambda p: p['caption_refs'][0].update(text='A short summary'),
                       lambda p: p['content']['narration'][0].update(spoken_text='Summary')]:
            source = package()
            mutate(source)
            with self.subTest(source=source), self.assertRaises(ValueError):
                w.validate_package(source)

    def test_whole_sentence_voice_override_rejected(self):
        source = package()
        row = source['content']['narration'][0]
        row['speech_adaptations'] = [{'source_range': [0, len(row['text'])], 'source_text': row['text'],
                                     'kind': 'term', 'reading': 'Short summary'}]
        with self.assertRaisesRegex(ValueError, 'not prose'):
            w.validate_package(source)

    def test_unsat_diagnostic_stops_before_freeze_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = package()
            source['temporal']['actions'][0]['min_read_seconds'] = 10
            with patch.object(w.p, 'render', side_effect=AssertionError('UNSAT must not render')):
                manifest = w.run(source, tmp)
            self.assertEqual(manifest['status'], 'UNSAT')
            self.assertNotIn('frozen_scene', manifest['node_versions'])
            self.assertTrue(any(c['constraint'] == 'reveal_then_read_before_sentence_deadline' and
                                c['shortfall_seconds'] > 0 for c in manifest['conflicts']))
            self.assertFalse((Path(tmp)/'nodes'/'frozen_scene').exists())

    def test_layout_overflow_is_unsat_not_summary_or_shrink(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = package()
            text = 'The complete formal manuscript must remain intact. '*20
            source['content']['narration'][0].update(text=text, speech_adaptations=[])
            source['caption_refs'][0]['source_range'] = [0, len(text)]
            manifest = w.run(source, tmp)
            self.assertEqual(manifest['status'], 'UNSAT')
            self.assertTrue(any(c['constraint'] == 'caption_layout' for c in manifest['conflicts']))
            derived = json.loads(Path(manifest['artifacts']['formal_captions']).read_text())
            self.assertEqual(derived['derived_full_text'][0]['text'], text)

    def test_event_mapping_and_audio_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = package()
            _, plan = w.validate_package(source)
            directory = Path(tmp)
            receipt = w.make_fixture(plan, source['synthetic_fixture'], directory)
            for change in [lambda r: r['events'].pop(),
                           lambda r: r['events'][0].update(spoken_text='Summary'),
                           lambda r: r['events'][0].update(end_frame=999999999),
                           lambda r: r['events'][0].update(start_frame=0),
                           lambda r: r.update(speech_sha256='0'*64)]:
                invalid = copy.deepcopy(receipt)
                change(invalid)
                with self.subTest(receipt=invalid), self.assertRaises(ValueError):
                    w.validate_events(plan, invalid, directory/'audio.wav', source['synthetic_fixture'])
            with (directory/'audio.wav').open('ab') as file:
                file.write(b'tampered')
            with self.assertRaisesRegex(ValueError, 'audio bytes'):
                w.validate_events(plan, receipt, directory/'audio.wav', source['synthetic_fixture'])

    def test_cached_evidence_revalidated_and_never_silently_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = package()
            result = w.run(source, tmp, width=320, fps=2)
            path = Path(result['artifacts']['audio_events'])
            receipt = json.loads(path.read_text())
            receipt['events'][0]['spoken_text'] = 'bad'
            w.p.write(path, receipt)
            with patch.object(w, 'make_fixture', side_effect=AssertionError('do not hide corrupted evidence')):
                with self.assertRaisesRegex(ValueError, 'mapping mismatch'):
                    w.run(source, tmp, width=320, fps=2)

    def test_semantic_model_and_camera_coverage_fail_closed(self):
        for mutate in [lambda p: p['content']['semantic_model']['components'][0]['terminals'].update(a='missing'),
                       lambda p: p['content']['semantic_model']['formulas'].pop(),
                       lambda p: p['visual'].update(camera_bounds=[0, 0, 10, 10])]:
            source = package()
            mutate(source)
            with self.subTest(source=source), self.assertRaises(ValueError):
                w.validate_package(source)

    def test_run_does_not_mutate_source_and_review_never_inherited(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = package()
            original = copy.deepcopy(source)
            result = w.run(source, tmp, width=320, fps=2)
            result['review'] = {'status': 'APPROVED', 'previous_reviews_reused': True}
            w.p.write(Path(tmp)/'latest.json', result)
            repeated = w.run(source, tmp, width=320, fps=2)
            self.assertEqual(source, original)
            self.assertEqual(repeated['invalidated_nodes'], [])
            self.assertEqual(repeated['review'], {'status': 'NOT_PERFORMED', 'previous_reviews_reused': False})


if __name__ == '__main__':
    unittest.main()
