"""Actual P1/P0 seam tests. Synthetic audio is never claimed to be speech."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'fixtures'))
import run_workflow as w
import prefreeze_gate as bridge
from source_model_gate import GateError
from build_original_fixture import bind_master
FIX = ROOT/'examples/rc-evidence'


def package():
    return json.loads((FIX/'content-package.json').read_text())


def sync_formal(p):
    evidence = p['source_model_evidence']
    bind_master(evidence)
    p['content']['narration'] = [{'id': n['id'], 'text': n['text']} for n in evidence['master']['sentences']]
    p['caption_refs'] = [{'id': c['id'], 'narration_id': c['span_id'], 'source_range': c['source_range']}
                         for c in evidence['caption_refs']]


class PrefreezeIntegrationTests(unittest.TestCase):
    def assert_blocked(self, p, expected, root=FIX):
        with tempfile.TemporaryDirectory() as tmp:
            with (patch.object(w, 'make_fixture', side_effect=AssertionError('failed gate must not synthesize')),
                 patch.object(w, 'solve', side_effect=AssertionError('failed gate must not solve')),
                 patch.object(w.p, 'compile_data', side_effect=AssertionError('failed gate must not freeze')),
                 patch.object(w.p, 'render', side_effect=AssertionError('failed gate must not render'))):
                with self.assertRaises(GateError) as ctx:
                    w.run(p, tmp, source_root=root, width=320, fps=2)
            self.assertEqual(ctx.exception.code, expected)
            latest = json.loads((Path(tmp)/'latest.json').read_text())
            self.assertEqual(latest['status'], 'FAILED')
            self.assertEqual(latest['stage'], 'pre_freeze_gate')
            self.assertEqual(latest['error_code'], 'PREFREEZE_GATE_FAILED')
            self.assertEqual(latest['error']['detail']['code'], expected)
            self.assertEqual(latest['source_model_gate']['status'], 'BLOCKED')
            self.assertFalse(any(latest['new_artifacts'].values()))
            self.assertNotIn('scene_path', latest)
            self.assertFalse((Path(tmp)/'nodes').exists())
            self.assertFalse((Path(tmp)/'latest_success.json').exists())

    def test_cli_source_to_actual_video_and_hash_bound_frozen_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            process = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/run_workflow.py'),
                                      str(FIX/'content-package.json'), '--output', tmp,
                                      '--synthetic-audio-fixture', '--video', '--width', '320', '--fps', '2'],
                                     capture_output=True, text=True, timeout=60)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(result['status'], 'SUCCESS')
            binding = result['source_model_gate']
            self.assertEqual(binding['status'], bridge.STATUS)
            self.assertFalse(binding['scientific_approval'])
            self.assertFalse(binding['audiovisual_approval'])
            self.assertFalse(binding['publication_allowed'])
            artifact = json.loads(Path(result['artifacts']['formal_export']).read_text())
            self.assertEqual(binding, artifact['binding'])
            self.assertEqual(binding['output_sha256'], w.p.digest(artifact['export']))
            self.assertEqual(binding['evidence_package_sha256'], w.p.digest(package()['source_model_evidence']))
            scene = json.loads(Path(result['scene_path']).read_text())
            lesson = json.loads(Path(result['scene_path']).with_name('lesson-derived.json').read_text())
            media = json.loads((Path(result['preview_path'])/'manifest.json').read_text())
            for captured in (scene['source_model_gate'], scene['workflow_binding']['source_model_gate'],
                             lesson['source_model_gate'], media['source_model_gate']):
                self.assertEqual(captured, binding)
            w.p.verify_scene(scene)
            self.assertIn('scripts/prefreeze_gate.py', scene['runtime']['files'])
            self.assertEqual(scene['semantic_model'], package()['content']['semantic_model'])
            self.assertEqual([c['text'] for c in scene['captions']],
                             [n['text'] for n in package()['content']['narration']])
            self.assertEqual(media['decoded_frame_count'], 28)
            self.assertTrue((Path(result['preview_path'])/'preview.mp4').is_file())
            self.assertEqual(media['audio'], 'synthetic_test_tones_not_speech')

    def test_source_byte_tamper_stops_before_downstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'original_rc_source.txt'
            source.write_text('Tampered original source')
            self.assert_blocked(package(), 'SOURCE_HASH_MISMATCH', Path(tmp))

    def test_invalid_formula_blocks(self):
        p = package();p['source_model_evidence']['models'][0]['formulas'][0]['expression'] = '2*R/(1+s*R*C)'
        self.assert_blocked(p, 'MATH_IDENTITY_FAILED')

    def test_conflicting_assumption_blocks(self):
        p = package();p['source_model_evidence']['assumptions'][0]['value'] = False
        self.assert_blocked(p, 'ASSUMPTION_CONFLICT')

    def test_reordered_script_is_not_a_valid_export(self):
        p = package();spans = p['source_model_evidence']['master']['sentences']
        spans[0], spans[2] = spans[2], spans[0];sync_formal(p)
        self.assert_blocked(p, 'PREREQUISITE_ORDER')

    def test_summary_caption_replacement_and_master_drift_block(self):
        p = package();p['caption_refs'][0]['text'] = 'A short summary'
        self.assert_blocked(p, 'CAPTION_EXPORT_MISMATCH')
        p = package();p['content']['narration'][0]['text'] = 'A short summary'
        self.assert_blocked(p, 'FORMAL_EXPORT_MISMATCH')

    def test_missing_or_forged_gate_does_not_fall_back(self):
        p = package();del p['source_model_evidence'];self.assert_blocked(p, 'GATE_REQUIRED')
        p = package();p['source_model_evidence'] = {'status': bridge.STATUS}
        self.assert_blocked(p, 'SCHEMA')

    def test_visual_expression_and_model_links_cannot_silently_drift(self):
        p = package();next(o for o in p['visual']['objects'] if o['id']=='model.impedance')['latex'] = '2R'
        self.assert_blocked(p, 'FORMULA_VISUAL_MISMATCH')
        p = package();p['content']['semantic_model']['components'][0]['terminals']['to'] = 'n'
        self.assert_blocked(p, 'MODEL_EXPORT_MISMATCH')

    def test_valid_model_revision_invalidates_gate_timing_and_scene_not_audio_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = package();first = w.run(p, tmp, source_root=FIX, width=320, fps=2)
            p['source_model_evidence']['models'][0]['parameters'][0]['sample'] = 1300
            with patch.object(w, 'make_fixture', side_effect=AssertionError('same speech fixture is reusable')):
                second = w.run(p, tmp, source_root=FIX, width=320, fps=2)
            self.assertNotEqual(first['source_model_gate']['input_sha256'], second['source_model_gate']['input_sha256'])
            self.assertNotEqual(first['source_model_gate']['output_sha256'], second['source_model_gate']['output_sha256'])
            self.assertEqual(first['node_versions']['formal_captions'], second['node_versions']['formal_captions'])
            self.assertEqual(first['node_versions']['audio_events'], second['node_versions']['audio_events'])
            self.assertEqual(set(second['invalidated_nodes']), {'formal_export', 'timeline', 'frozen_scene', 'preview'})
            self.assertFalse(second['review']['previous_reviews_reused'])

    def test_layout_and_voice_remain_separate_from_formal_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = package();first = w.run(p, tmp, source_root=FIX, width=320, fps=2)
            p['visual']['layout_contract']['subtitles']['horizontal_padding'] += 2
            with patch.object(w, 'make_fixture', side_effect=AssertionError('layout must not resynthesize')):
                layout = w.run(p, tmp, source_root=FIX, width=320, fps=2)
            self.assertEqual(first['source_model_gate'], layout['source_model_gate'])
            self.assertEqual(set(layout['invalidated_nodes']), {'timeline', 'frozen_scene', 'preview'})
            p['voice']['rate'] = '+10%'
            voice = w.run(p, tmp, source_root=FIX, width=320, fps=2)
            self.assertEqual(layout['source_model_gate'], voice['source_model_gate'])
            self.assertEqual(layout['node_versions']['formal_captions'], voice['node_versions']['formal_captions'])
            self.assertEqual(set(voice['invalidated_nodes']), {'phonetic_voice','audio_events','timeline','frozen_scene','preview'})

    def test_prior_success_does_not_authorize_failed_gate_or_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = package();first = w.run(p, tmp, source_root=FIX, width=320, fps=2)
            p['source_model_evidence']['models'][0]['formulas'][0]['expression'] = 'R'
            with (patch.object(w, 'make_fixture', side_effect=AssertionError('blocked, even with cache')),
                 patch.object(w.p, 'render', side_effect=AssertionError('blocked, even with old preview'))):
                with self.assertRaises(GateError):w.run(p, tmp, source_root=FIX, width=320, fps=2)
            latest = json.loads((Path(tmp)/'latest.json').read_text())
            self.assertEqual(latest['status'], 'FAILED')
            self.assertEqual(latest['source_model_gate']['status'], 'BLOCKED')
            self.assertFalse(latest['new_artifacts']['formal_export'])
            self.assertNotIn('artifacts', latest)
            self.assertNotIn('node_versions', latest)
            self.assertNotIn('scene_digest', latest)
            self.assertEqual(json.loads((Path(tmp)/'latest_success.json').read_text())['run_id'], first['run_id'])

    def test_legacy_route_explicitly_ungated_and_never_inherits_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            w.run(package(), tmp, source_root=FIX, width=320, fps=2)
            legacy = json.loads((ROOT/'examples/resistor-divider/content-package.json').read_text())
            result = w.run(legacy, tmp, width=320, fps=2)
            self.assertEqual(result['source_model_gate']['status'], 'UNGATED_LEGACY_PREVIEW')
            self.assertNotIn('input_sha256', result['source_model_gate'])
            self.assertNotIn('formal_export', result['artifacts'])
            self.assertFalse(result['new_artifacts']['formal_export'])
            self.assertFalse(result['review']['previous_reviews_reused'])
            scene = json.loads(Path(result['scene_path']).read_text())
            self.assertEqual(scene['source_model_gate'], result['source_model_gate'])

    def test_direct_legacy_compile_does_not_trust_a_claimed_gate(self):
        lesson = json.loads((ROOT/'examples/resistor-divider/lesson.json').read_text())
        lesson['source_model_gate'] = {'status': bridge.STATUS, 'scientific_approval': True}
        scene = w.p.compile_data(lesson)
        self.assertEqual(scene['source_model_gate']['status'], 'UNGATED_LEGACY_PREVIEW')
        self.assertFalse(scene['source_model_gate']['scientific_approval'])
        with tempfile.TemporaryDirectory() as tmp:
            media = w.p.render(scene, tmp, width=320, fps=2)
            self.assertEqual(media['source_model_gate']['status'], 'NOT_REVALIDATED_LOW_LEVEL_RENDER')
            self.assertFalse(media['source_model_gate']['scientific_approval'])

    def test_changed_valid_source_revision_rechecks_gate_and_invalidates_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root/'original_rc_source.txt'
            shutil.copyfile(FIX/'original_rc_source.txt', source)
            p=package();first=w.run(p, root/'out', source_root=root, width=320, fps=2)
            source.write_text(source.read_text()+'\nOriginal fixture revision: notation unchanged.\n')
            h=hashlib.sha256(source.read_bytes()).hexdigest()
            p['source_model_evidence']['sources'][0]['sha256']=h
            p['source_model_evidence']['regions'][0]['artifact_sha256']=h
            p['content']['sources']=bridge.projected_sources(p['source_model_evidence'])
            second=w.run(p, root/'out', source_root=root, width=320, fps=2)
            self.assertNotEqual(first['source_model_gate']['input_sha256'],second['source_model_gate']['input_sha256'])
            self.assertNotEqual(first['scene_digest'],second['scene_digest'])
            self.assertEqual(first['node_versions']['formal_captions'],second['node_versions']['formal_captions'])
            self.assertEqual(second['audio_cache'],'validated_reuse')

    def test_independent_gate_cli_failure_contains_no_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=package();p['source_model_evidence']['sources'][0]['path']='missing.txt'
            path=Path(tmp)/'input.json';path.write_text(json.dumps(p))
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/prefreeze_gate.py'),str(path)],
                                  capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,1)
            answer=json.loads(result.stdout)
            self.assertEqual(answer['status'],'BLOCKED')
            self.assertFalse(answer['formal_export_allowed'])
            self.assertNotIn('export',answer)

if __name__ == '__main__':
    unittest.main()
