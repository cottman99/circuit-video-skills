"""Synthetic DEVELOPMENT checks only: generated PDF and tone, never real TTS.

No private lecture material, external requests, or held-out success claims. Pixel
comparisons are made before lossy H.264 encoding, which is tested separately.
"""
from pathlib import Path
import copy
import importlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

import fitz
import numpy as np
from PIL import Image, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_video as cv


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return path


class SyntheticOriginalSlideFixture(unittest.TestCase):
    """All source geometry, text, and audio are created by this test file."""

    @classmethod
    def setUpClass(cls):
        cls.font_tmp = tempfile.TemporaryDirectory(prefix='original-slide-font-test-')
        cls.original_font_env = {key: os.environ.get(key) for key in
                                 ('CIRCUIT_FONT_REGULAR', 'CIRCUIT_FONT_HEADING')}
        # Freeze and restore the caller's font paths, rather than leaking paths
        # into this class's temporary directory to later discovered tests.
        cls.pipeline = importlib.import_module('pipeline')
        cls.original_fonts = dict(cls.pipeline.typography.FONTS)
        cv.setup_fonts(Path(cls.font_tmp.name))
        cls.adapter = importlib.import_module('original_slides')
        cls.pipeline.typography.FONTS = {
            400: Path(os.environ['CIRCUIT_FONT_REGULAR']),
            700: Path(os.environ['CIRCUIT_FONT_HEADING']),
        }

    @classmethod
    def tearDownClass(cls):
        cls.pipeline.typography.FONTS = cls.original_fonts
        for key, value in cls.original_font_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.font_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='original-slide-synthetic-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.project = self.base / 'project'
        source = self.project / 'source'
        source.mkdir(parents=True)
        self.pdf = source / 'original.pdf'
        with fitz.open() as document:
            page = document.new_page(width=1600, height=600)
            page.insert_text((60, 75), 'SYNTHETIC DEVELOPMENT ONLY', fontsize=25)
            page.insert_text((120, 230), 'V = I R', fontsize=40)
            page.insert_text((400, 270), 'original red source note', fontsize=22,
                             color=(0.9, 0.1, 0.1))
            page.draw_line((900, 230), (1070, 230), width=3)
            page.draw_rect((1070, 205, 1180, 255), width=3)
            page.draw_line((1180, 230), (1370, 230), width=3, color=(0.1, 0.3, 0.9))
            page.insert_text((1100, 190), 'R', fontsize=22)
            # Static ink outside all semantic regions must never disappear.
            page.insert_text((70, 550), 'Keep original page language and coordinates.', fontsize=21)
            document.save(self.pdf)
        self.page_path = source / 'page-0001.png'
        with fitz.open(self.pdf) as document:
            document[0].get_pixmap(alpha=False).save(self.page_path)
            (source / 'page-0001.txt').write_text(document[0].get_text())
        self.original = np.asarray(Image.open(self.page_path).convert('RGB'))
        self.duration = 4.0
        self.audio = self.base / 'synthetic-tone.wav'
        sample_rate = 24000
        samples = np.arange(int(self.duration * sample_rate), dtype=float)
        pcm = (900 * np.sin(2 * math.pi * 440 * samples / sample_rate)).astype('<i2')
        with wave.open(str(self.audio), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm.tobytes())
        master = [
            {'id': 's1', 'text': '先看公式。', 'source_pages': [1], 'scene_id': 'page'},
            {'id': 's2', 'text': '再看电阻。', 'source_pages': [1], 'scene_id': 'page'},
            {'id': 's3', 'text': '观察全图。', 'source_pages': [1], 'scene_id': 'page'},
        ]
        self.plan = {
            'title': '合成原页开发测试',
            'scope_source_sha256': cv.sha(self.pdf),
            'selected_pages': [1],
            'formal_master': master,
            'scenes': [{
                'id': 'page', 'title': '原页不重排', 'source_page': 1,
                'source_pages': [1], 'sentence_ids': ['s1', 's2', 's3'],
                'source_objects': [
                    {'id': 'heading', 'regions': [[40, 35, 900, 100]],
                     'reveal_sentence_id': None},
                    {'id': 'formula', 'regions': [[80, 150, 720, 300]],
                     'reveal_sentence_id': 's1', 'focus_point': [750, 225]},
                    {'id': 'diagram', 'regions': [[820, 145, 1460, 400]],
                     'reveal_sentence_id': 's2', 'focus_point': [1490, 270]},
                    {'id': 'resistor', 'regions': [[1040, 175, 1210, 280]],
                     'reveal_with': 'diagram', 'focus_point': [1230, 300]},
                ],
                'teaching_actions': [
                    {'sentence_id': 's1', 'target_id': 'formula', 'action': 'focus'},
                    {'sentence_id': 's2', 'target_id': 'resistor', 'action': 'focus'},
                    {'sentence_id': 's3', 'target_id': 'diagram', 'action': 'focus'},
                ],
            }],
            'coverage': [{
                'source_page': 1, 'source_item': 'Entire synthetic resistor page',
                'formal_sentence_ids': ['s1', 's2', 's3'],
                'visual_object_ids': ['page.heading', 'page.formula', 'page.diagram', 'page.resistor'],
            }],
            'scope_statement': 'Synthetic development fixture, not real TTS or a held-out evaluation.',
            'unresolved_issues': [], 'pronunciation': {},
            'layout': {
                'schema': 'original-slide-layout-1',
                'semantic_colors': {},
                'scenes': {'page': {'background_rgb': [255, 255, 255],
                                    'mask_policy': 'uniform-background'}},
            },
        }
        self.source = {
            'original_path': 'source/original.pdf', 'sha256': cv.sha(self.pdf),
            'selected_pages': [1], 'page_image_width': 1600,
            'pages': [{'page': 1, 'image_path': 'source/page-0001.png',
                       'image_sha256': cv.sha(self.page_path),
                       'text_path': 'source/page-0001.txt',
                       'text_sha256': cv.sha(source / 'page-0001.txt'),
                       'width': 1600, 'height': 600}],
        }
        self.receipt = {
            'fixture_only': 'SYNTHETIC_AUDIO_AND_SENTENCE_EVENTS_NOT_PROVIDER_EXECUTION',
            'caption_windows': [
                {'sentence_id': 's1', 'start': 0.1, 'end': 1.4},
                {'sentence_id': 's2', 'start': 1.4, 'end': 2.8},
                {'sentence_id': 's3', 'start': 2.8, 'end': self.duration},
            ],
            'raw_sentences': [{'sentence_id': n['id'], 'formal_text': n['text']}
                              for n in master],
            'audio': {'duration': self.duration, 'path': self.audio.name,
                      'sha256': cv.sha(self.audio), 'source_mp3_sha256': cv.sha(self.audio)},
            'provider_events_sha256': cv.digest({'fixture': 'synthetic boundaries'}),
            'display_policy_sha256': cv.digest({'fixture': 'synthetic windows'}),
            '_receipt_base': str(self.base),
        }
        self.profile = self.adapter.profile()

    def compile(self):
        scene_plan = self.plan['scenes'][0]
        self.adapter.validate_scene_plan(scene_plan, self.plan['layout']['scenes']['page'],
                                         self.plan['layout'])
        voice_path = write_json(self.base / 'voice-input.json', cv.voice_document(self.plan))
        scene, audio = self.adapter.compile_course(
            self.project, {'LessonPlan': self.plan, 'SourcePackage': self.source},
            voice_path, self.receipt, self.profile, self.base / 'compiled')
        self.assertEqual(audio, self.audio)
        return scene

    def renderer(self, scene):
        return self.adapter.OriginalSlideRenderer(scene, width=1600, fps=60)

    def call_cli(self, project, *args, ok=True):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/course_video.py'), args[0],
             '--project', str(project), *args[1:]],
            capture_output=True, text=True, timeout=150)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads((result.stdout if result.returncode == 0 else result.stderr).strip().splitlines()[-1])


class OriginalSlideUnitTests(SyntheticOriginalSlideFixture):
    def test_fully_revealed_page_is_pixel_identical_without_annotations_or_tint(self):
        scene = self.compile()
        rendered = self.renderer(scene).page_frame(3.9, annotations=False, tint=False)
        np.testing.assert_array_equal(np.asarray(rendered), self.original)
        self.assertEqual(rendered.size, (1600, 600))
        self.assertEqual(scene['pages'][0]['width'], 1600)
        self.assertEqual(scene['height'], 730)
        self.assertEqual(scene['source_pdf_sha256'], cv.sha(self.pdf))

    def test_existing_colored_ink_is_unchanged_when_neutral_ink_is_tinted(self):
        self.plan['layout']['semantic_colors'] = {'relationship': [30, 110, 190]}
        self.plan['scenes'][0]['source_objects'][1]['ink_role'] = 'relationship'
        scene = self.compile()
        rendered = np.asarray(self.renderer(scene).page_frame(3.9, annotations=True, tint=True))
        colored = self.original.max(axis=2).astype(int) - self.original.min(axis=2).astype(int) > 4
        self.assertGreater(np.count_nonzero(colored), 100)
        np.testing.assert_array_equal(rendered[colored], self.original[colored])
        formula = np.zeros(self.original.shape[:2], dtype=bool)
        formula[150:300, 80:720] = True
        neutral_ink = formula & ~colored & (self.original.min(axis=2) < 240)
        self.assertTrue(np.any(rendered[neutral_ink] != self.original[neutral_ink]))

    def test_cumulative_reveal_owner_child_and_static_background(self):
        scene = self.compile()
        render = self.renderer(scene)
        objects = {o['id']: o for o in scene['objects']}
        self.assertEqual(objects['page.resistor']['owner_id'], 'page.diagram')
        self.assertEqual(objects['page.resistor']['start'], objects['page.diagram']['start'])
        self.assertEqual(objects['page.resistor']['duration'], objects['page.diagram']['duration'])
        before = np.asarray(render.page_frame(0.05, annotations=False, tint=False))
        self.assertTrue(np.all(before[150:300, 80:720] == 255))
        self.assertTrue(np.all(before[145:400, 820:1460] == 255))
        np.testing.assert_array_equal(before[500:600], self.original[500:600])
        middle = np.asarray(render.page_frame(1.6, annotations=False, tint=False))
        np.testing.assert_array_equal(middle[150:300, 80:720], self.original[150:300, 80:720])
        ink = self.original[145:400, 820:1460].min(axis=2) < 200
        self.assertTrue(np.all(middle[145:400, 820:1460][ink] >= self.original[145:400, 820:1460][ink]))
        self.assertTrue(np.any(middle[145:400, 820:1460][ink] != self.original[145:400, 820:1460][ink]))
        progress = render.state(1.6)[4]
        self.assertAlmostEqual(progress['page.resistor'], progress['page.diagram'])
        self.assertEqual(progress['page.formula'], 1)
        final = np.asarray(render.page_frame(2.1, annotations=False, tint=False))
        np.testing.assert_array_equal(final, self.original)

    def test_focus_moves_quickly_then_dwells_and_uses_shared_highlight_target(self):
        scene = self.compile()
        render = self.renderer(scene)
        previous, cue = scene['focus_cues'][:2]
        self.assertEqual(cue['target_id'], 'page.resistor')
        self.assertAlmostEqual(cue['move_seconds'], 0.28)
        self.assertLess(cue['move_seconds'], cue['end'] - cue['start'] - cue['move_seconds'])
        start = render.state(cue['start'])[-1]
        halfway = render.state(cue['start'] + cue['move_seconds'] / 2)[-1]
        arrived = render.state(cue['start'] + cue['move_seconds'])[-1]
        self.assertEqual(start, previous['point'])
        np.testing.assert_allclose(halfway, np.mean([previous['point'], cue['point']], axis=0))
        self.assertEqual(arrived, cue['point'])
        self.assertEqual(render.state(cue['end'] - 0.01)[-1], cue['point'])
        for moment, phase in ((cue['start'] + 0.05, 'move'), (cue['start'] + 0.4, 'dwell')):
            _, receipt = render.render(moment)
            self.assertEqual(receipt['focus']['phase'], phase)
            self.assertEqual(receipt['focus']['target_id'], receipt['focus']['highlight_target_id'])
            self.assertIn(receipt['focus']['target_id'], receipt['fully_revealed_objects'])
            self.adapter.validate_frame(scene, {}, receipt)

    def test_sentence_onset_and_explicit_estimate_are_distinguished(self):
        self.plan['scenes'][0]['teaching_actions'][2].update(
            timing_basis='estimated_text_position', text_range=[2, 4])
        scene = self.compile()
        first, _, estimated = scene['focus_cues']
        self.assertEqual(first['timing_basis'], 'sentence_onset')
        self.assertEqual(first['start'], 0.6)  # Delay is disclosed, not invented word alignment.
        self.assertAlmostEqual(first['reveal_ready_adjustment'], 0.5)
        self.assertAlmostEqual(estimated['start'], 2.8 + 1.2 * 2 / 5)
        self.assertEqual(estimated['timing_basis'], 'estimated_text_position')
        self.assertEqual(estimated['text_range'], [2, 4])
        self.assertIsNone(estimated['reveal_ready_adjustment'])
        self.assertFalse(estimated['measured_word_alignment'])
        self.assertFalse(scene['timing_evidence']['word_alignment'])
        self.assertEqual([n['start'] for n in scene['narration']], [0.1, 1.4, 2.8])

    def test_estimated_cue_requires_explicit_valid_formal_text_range(self):
        for update in ({'timing_basis': 'estimated_text_position'},
                       {'text_range': [1, 2]},
                       {'timing_basis': 'word_alignment'},
                       {'timing_basis': 'estimated_text_position', 'text_range': [0, 999]}):
            with self.subTest(update=update):
                saved = copy.deepcopy(self.plan)
                self.plan['scenes'][0]['teaching_actions'][2].update(update)
                with self.assertRaisesRegex(ValueError, 'FOCUS_TIMING|FOCUS_TEXT_RANGE'):
                    self.compile()
                self.plan = saved

    def test_region_bounds_and_ink_cut_are_rejected(self):
        for regions, reason in (([[80, 150, 1601, 300]], 'SOURCE_REGION_BOUNDS'),
                                ([[125, 200, 720, 300]], 'SOURCE_OBJECT_EDGE_INK'),
                                ([[80, 150, 83, 300]], 'SOURCE_REGION_SMALL')):
            with self.subTest(regions=regions):
                self.plan['scenes'][0]['source_objects'][1]['regions'] = regions
                with self.assertRaisesRegex(ValueError, reason):
                    self.compile()

    def test_faint_boundary_tolerance_is_explicit_validation_only_and_never_hides_dark_ink(self):
        # Deliberately mutate a synthetic raster for this compiler-boundary
        # check and rebind its exact hash. The CLI separately verifies actual
        # PDF-to-raster derivation, so this is not a production import shortcut.
        altered = self.original.copy()
        altered[150, 100] = [245, 245, 245]
        Image.fromarray(altered).save(self.page_path)
        self.source['pages'][0]['image_sha256'] = cv.sha(self.page_path)
        with self.assertRaisesRegex(ValueError, 'SOURCE_OBJECT_EDGE_INK'):
            self.compile()
        owner = self.plan['scenes'][0]['source_objects'][1]
        owner['edge_background_tolerance'] = 10
        owner['edge_tolerance_reason'] = 'Inspected synthetic RGB 245 boundary speckle; no dark source ink.'
        scene = self.compile()
        validation = next(o for o in scene['objects'] if o['id'] == 'page.formula')['edge_validation']
        self.assertEqual(validation['tolerance'], 10)
        self.assertEqual(validation['maximum_boundary_deviation'], 10)
        self.assertEqual(validation['nonexact_boundary_pixels'], 1)
        self.assertFalse(validation['source_pixels_modified'])
        np.testing.assert_array_equal(
            np.asarray(self.renderer(scene).page_frame(3.9, annotations=False, tint=False)), altered)
        self.assertEqual(scene['pages'][0]['sha256'], cv.sha(self.page_path))
        altered[150, 100] = [200, 200, 200]
        Image.fromarray(altered).save(self.page_path)
        self.source['pages'][0]['image_sha256'] = cv.sha(self.page_path)
        with self.assertRaisesRegex(ValueError, 'SOURCE_OBJECT_EDGE_INK'):
            self.compile()

    def test_physical_source_edge_is_preserved_but_a_new_one_pixel_cut_is_rejected(self):
        altered = self.original.copy()
        altered[210:225, 0:2] = [0, 0, 0]
        Image.fromarray(altered).save(self.page_path)
        self.source['pages'][0]['image_sha256'] = cv.sha(self.page_path)
        self.plan['scenes'][0]['source_objects'][1]['regions'] = [[0, 150, 720, 300]]
        scene = self.compile()
        owner = next(o for o in scene['objects'] if o['id'] == 'page.formula')
        self.assertTrue(owner['edge_validation']['physical_page_edge_exempt'])
        self.assertFalse(owner['edge_validation']['source_pixels_modified'])
        page = self.renderer(scene).page_frame(3.9, annotations=False, tint=False)
        self.assertEqual(page.size, (1600, 600))
        np.testing.assert_array_equal(np.asarray(page), altered)
        self.assertTrue(np.all(np.asarray(page)[210:225, 0:2] == 0))
        # Moving the mask inward by one pixel creates a new ink cut. Being
        # near the image edge must not exempt this authored boundary.
        self.plan['scenes'][0]['source_objects'][1]['regions'] = [[1, 150, 720, 300]]
        with self.assertRaisesRegex(ValueError, 'SOURCE_OBJECT_EDGE_INK'):
            self.compile()

    def test_boundary_tolerance_rejects_invalid_values_missing_reasons_and_child_overrides(self):
        invalid = [
            {'edge_background_tolerance': -1}, {'edge_background_tolerance': 11},
            {'edge_background_tolerance': True}, {'edge_background_tolerance': 1.5},
            {'edge_background_tolerance': '10'}, {'edge_background_tolerance': 10},
            {'edge_background_tolerance': 10, 'edge_tolerance_reason': ''},
            {'edge_background_tolerance': 10, 'edge_tolerance_reason': '   '},
            {'edge_background_tolerance': 10, 'edge_tolerance_reason': None},
        ]
        original_owner = copy.deepcopy(self.plan['scenes'][0]['source_objects'][1])
        for update in invalid:
            with self.subTest(update=update):
                self.plan['scenes'][0]['source_objects'][1] = {**original_owner, **update}
                with self.assertRaisesRegex(ValueError, 'EDGE_TOLERANCE'):
                    self.compile()
        self.plan['scenes'][0]['source_objects'][1] = original_owner
        self.plan['scenes'][0]['source_objects'][3].update(
            edge_background_tolerance=10, edge_tolerance_reason='Child must not own boundary tolerance.')
        with self.assertRaisesRegex(ValueError, 'REVEAL_OWNER'):
            self.compile()

    def test_overlapping_regions_with_identical_union_do_not_create_false_ink_edges(self):
        baseline = self.renderer(self.compile()).page_frame(0.35, annotations=False, tint=False)
        original_mask = self.adapter._mask((1600, 600), [[80, 150, 720, 300]])
        # The internal rectangle seams cross the source V glyph, while their
        # complete union has the same genuinely clear outer edge as before.
        regions = [[80, 150, 140, 300], [125, 150, 720, 300]]
        self.assertTrue(np.any(self.original[150:300, 123:142] != 255))
        self.assertEqual(original_mask.tobytes(), self.adapter._mask((1600, 600), regions).tobytes())
        self.plan['scenes'][0]['source_objects'][1]['regions'] = regions
        renderer = self.renderer(self.compile())
        self.assertEqual(baseline.tobytes(), renderer.page_frame(0.35, annotations=False, tint=False).tobytes())
        np.testing.assert_array_equal(
            np.asarray(renderer.page_frame(3.9, annotations=False, tint=False)), self.original)

    def test_repeated_target_is_stationary_dwell_not_a_cached_phantom_move(self):
        self.plan['scenes'][0]['teaching_actions'][1]['target_id'] = 'formula'
        # Keep unrelated reveals static so the frame-cache assertion isolates
        # the zero-distance pointer cue rather than a changing diagram.
        self.plan['scenes'][0]['source_objects'][2]['reveal_sentence_id'] = None
        scene = self.compile()
        first, repeated = scene['focus_cues'][:2]
        self.assertEqual(first['point'], repeated['point'])
        self.assertEqual(repeated['move_seconds'], 0)
        renderer = self.renderer(scene)
        before, before_receipt = renderer.render(repeated['start'] + 0.05)
        after, after_receipt = renderer.render(repeated['start'] + 0.5)
        self.assertEqual(before.tobytes(), after.tobytes())
        self.assertEqual(before_receipt['focus']['phase'], 'dwell')
        self.assertEqual(after_receipt['focus']['phase'], 'dwell')
        self.assertEqual(renderer.stats['exact_static_cache_hits'], 1)

    def test_overlapping_independent_ink_requires_one_owner(self):
        self.plan['scenes'][0]['source_objects'][3] = {
            'id': 'duplicate', 'regions': [[820, 145, 1460, 400]],
            'reveal_sentence_id': 's3',
        }
        self.plan['scenes'][0]['teaching_actions'][1]['target_id'] = 'duplicate'
        with self.assertRaisesRegex(ValueError, 'SOURCE_OBJECT_OVERLAP'):
            self.compile()

    def test_child_cannot_escape_owner_or_reveal_independently(self):
        child = self.plan['scenes'][0]['source_objects'][3]
        child['regions'] = [[800, 175, 1210, 280]]
        with self.assertRaisesRegex(ValueError, 'REVEAL_OWNER_BOUNDS'):
            self.compile()
        child['regions'] = [[1040, 175, 1210, 280]]
        child['reveal_sentence_id'] = 's3'
        with self.assertRaisesRegex(ValueError, 'REVEAL_OWNER'):
            self.compile()

    def test_reveal_owner_cycle_is_rejected(self):
        diagram = self.plan['scenes'][0]['source_objects'][2]
        diagram.pop('reveal_sentence_id')
        diagram['reveal_with'] = 'resistor'
        with self.assertRaisesRegex(ValueError, 'REVEAL_OWNER: cycle'):
            self.compile()

    def test_pointer_requires_nearby_clear_space_and_never_covers_source_ink(self):
        scene = self.compile()
        rendered = np.asarray(self.renderer(scene).page_frame(2.4, annotations=True, tint=False))
        ink = np.any(self.original != 255, axis=2)
        np.testing.assert_array_equal(rendered[ink], self.original[ink])
        self.plan['scenes'][0]['source_objects'][1]['focus_point'] = [50, 580]
        with self.assertRaisesRegex(ValueError, 'POINTER_LAYOUT_UNSAT'):
            self.compile()
        self.plan['scenes'][0]['source_objects'][1]['focus_point'] = [132, 221]
        with self.assertRaisesRegex(ValueError, 'POINTER_LAYOUT_UNSAT'):
            self.compile()

    def test_full_formal_captions_wrap_without_summary_and_are_in_separate_band(self):
        scene = self.compile()
        self.assertEqual(scene['caption_coverage']['status'], 'PASS')
        self.assertEqual([c['text'] for c in scene['captions']],
                         [n['text'] for n in self.plan['formal_master']])
        for caption in scene['captions']:
            self.assertEqual(''.join(caption['lines']), caption['text'])
            self.assertEqual(caption['source_range'], [0, len(caption['text'])])
        image, receipt = self.renderer(scene).render(3.5)
        self.assertEqual(receipt['caption_text'], self.plan['formal_master'][2]['text'])
        self.assertTrue(receipt['caption_complete'])
        self.assertTrue(receipt['caption_within_band'])
        self.assertGreater(image.height, self.original.shape[0])
        text = '完整中文字幕保留符号、条件和结论。' * 4
        font = ImageFont.truetype(scene['caption_font'], self.profile['caption_font_size'])
        lines = self.adapter._wrap(text, font, 1520, 2)
        self.assertEqual(''.join(lines), text)
        self.assertEqual(len(lines), 2)
        with self.assertRaisesRegex(ValueError, 'CAPTION_LAYOUT_UNSAT'):
            self.adapter._wrap(text * 2, font, 1520, 2)

    def test_caption_reading_budget_and_focus_dwell_are_hard_failures(self):
        self.plan['formal_master'][0]['text'] = '不能删减的完整正式字幕内容必须保留全部条件与结论。'
        self.receipt['raw_sentences'][0]['formal_text'] = self.plan['formal_master'][0]['text']
        with self.assertRaisesRegex(ValueError, 'TIMING_UNSAT'):
            self.compile()
        self.plan['formal_master'][0]['text'] = '先看公式。'
        self.receipt['raw_sentences'][0]['formal_text'] = '先看公式。'
        self.plan['layout']['presentation'] = {'minimum_dwell_seconds': 2.0}
        with self.assertRaisesRegex(ValueError, 'TIMING_UNSAT'):
            self.compile()

    def test_focus_cannot_slip_into_a_later_sentence_while_waiting_for_reveal(self):
        actions = self.plan['scenes'][0]['teaching_actions']
        actions[0]['target_id'] = 'diagram'  # s1 asks for an object revealed in s2.
        self.plan['scenes'][0]['teaching_actions'] = [actions[0], actions[2]]
        with self.assertRaisesRegex(ValueError, 'TIMING_UNSAT: reveal/move/dwell'):
            self.compile()

    def test_reveal_cannot_overflow_its_own_short_anchor_sentence(self):
        self.plan['formal_master'][0]['text'] = '看。'
        self.receipt['raw_sentences'][0]['formal_text'] = '看。'
        self.receipt['caption_windows'][0]['end'] = 0.4
        self.receipt['caption_windows'][1]['start'] = 0.4
        # The complete two-character caption fits 0.3 s at the normal 8 cps
        # limit, but the 0.5 s reveal must not silently continue into s2.
        with self.assertRaisesRegex(ValueError, 'TIMING_UNSAT: reveal exceeds its anchor sentence'):
            self.compile()

    def test_stationary_focus_may_hold_after_its_anchor_sentence(self):
        self.plan['scenes'][0]['teaching_actions'] = self.plan['scenes'][0]['teaching_actions'][:1]
        scene = self.compile()
        cue = scene['focus_cues'][0]
        self.assertEqual(cue['anchor_sentence_end'], 1.4)
        self.assertEqual(cue['end'], 4.0)
        _, receipt = self.renderer(scene).render(3.8)
        self.assertEqual(receipt['focus']['phase'], 'dwell')
        self.assertEqual(receipt['focus']['target_id'], 'page.formula')

    def test_visual_only_coverage_keeps_static_items_without_fabricated_speech(self):
        original_master = copy.deepcopy(self.plan['formal_master'])
        for visual in ('page.heading', 'page.source_page'):
            with self.subTest(visual=visual):
                plan = copy.deepcopy(self.plan)
                plan['coverage'].append({
                    'source_page': 1, 'source_item': 'Static source citation retained visually',
                    'formal_sentence_ids': [], 'visual_object_ids': [visual],
                })
                cv.validate_plan(plan, self.source)
                self.assertEqual(plan['formal_master'], original_master)
                self.assertEqual(plan['coverage'][-1]['formal_sentence_ids'], [])
        self.plan['coverage'][0]['formal_sentence_ids'].remove('s3')
        self.plan['coverage'].append({
            'source_page': 1, 'source_item': 'Visual page retention is not spoken coverage',
            'formal_sentence_ids': [], 'visual_object_ids': ['page.source_page'],
        })
        with self.assertRaisesRegex(ValueError, 'COVERAGE_SENTENCES'):
            cv.validate_plan(self.plan, self.source)

    def test_visual_only_coverage_rejects_wrong_page_references(self):
        # This is a plan-schema check. Source PDF/raster integrity is exercised
        # separately through the real CLI fixture and source-tamper regression.
        self.source['selected_pages'] = [1, 2]
        self.plan['selected_pages'] = [1, 2]
        self.plan['formal_master'].append({
            'id': 's4', 'text': '另页内容。', 'source_pages': [2], 'scene_id': 'second',
        })
        self.plan['scenes'].append({
            'id': 'second', 'title': '第二合成页', 'source_page': 2, 'source_pages': [2],
            'sentence_ids': ['s4'], 'teaching_actions': [],
            'source_objects': [{'id': 'heading', 'regions': [[40, 35, 900, 100]],
                                'reveal_sentence_id': None}],
        })
        self.plan['layout']['scenes']['second'] = copy.deepcopy(self.plan['layout']['scenes']['page'])
        self.plan['coverage'].append({
            'source_page': 2, 'source_item': 'Second page statement',
            'formal_sentence_ids': ['s4'], 'visual_object_ids': ['second.heading'],
        })
        cv.validate_plan(self.plan, self.source)
        for visual in ('second.heading', 'second.source_page'):
            with self.subTest(visual=visual):
                plan = copy.deepcopy(self.plan)
                plan['coverage'].append({
                    'source_page': 1, 'source_item': 'Incorrect cross-page visual citation',
                    'formal_sentence_ids': [], 'visual_object_ids': [visual],
                })
                with self.assertRaisesRegex(ValueError, 'COVERAGE_SOURCE: unrelated visual page'):
                    cv.validate_plan(plan, self.source)

    def test_reserved_source_page_object_id_is_rejected(self):
        self.plan['scenes'][0]['source_objects'].append({
            'id': 'source_page', 'regions': [[40, 35, 900, 100]], 'reveal_sentence_id': None,
        })
        with self.assertRaisesRegex(ValueError, 'OBJECT_IDS: duplicate or reserved source_page'):
            cv.validate_plan(self.plan, self.source)

    def test_original_geometry_and_sixty_fps_are_mandatory(self):
        self.profile['fps'] = 30
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_SLIDE_FPS'):
            self.compile()
        self.profile['fps'] = 60
        self.profile['width'] = 1280
        with self.assertRaisesRegex(ValueError, 'SOURCE_GEOMETRY'):
            self.compile()
        self.profile['width'] = 1600
        scene = self.compile()
        with self.assertRaisesRegex(ValueError, 'SOURCE_GEOMETRY'):
            self.adapter.OriginalSlideRenderer(scene, width=1280, fps=60)
        with self.assertRaisesRegex(ValueError, 'SOURCE_GEOMETRY'):
            self.adapter.OriginalSlideRenderer(scene, width=1600, fps=30)

    def test_exact_static_cache_does_not_freeze_pointer_motion(self):
        scene = self.compile()
        renderer = self.renderer(scene)
        first, first_receipt = renderer.render(2.3)
        second, second_receipt = renderer.render(2.5)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(renderer.stats['exact_static_cache_hits'], 1)
        self.assertEqual(first_receipt['time'], 2.3)
        self.assertEqual(second_receipt['time'], 2.5)
        moving_first, _ = renderer.render(2.83)
        moving_second, _ = renderer.render(2.95)
        self.assertNotEqual(moving_first.tobytes(), moving_second.tobytes())
        self.assertEqual(renderer.stats['exact_static_cache_hits'], 1)

    def test_source_and_compiled_caption_tampering_are_rejected(self):
        scene = self.compile()
        self.page_path.write_bytes(b'not the original source raster')
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            self.adapter.verify_scene(scene)
        Image.fromarray(self.original).save(self.page_path)
        # Preserve the identical original PNG representation for the next check.
        with fitz.open(self.pdf) as document:
            document[0].get_pixmap(alpha=False).save(self.page_path)
        for field in ('text', 'lines'):
            modified = copy.deepcopy(scene)
            modified['captions'][0][field] = ['摘要'] if field == 'lines' else '摘要'
            modified.pop('scene_digest')
            modified['scene_digest'] = cv.digest(modified)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'CAPTION'):
                self.adapter.verify_scene(modified)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required for synthetic encode')
class OriginalSlideCliTests(SyntheticOriginalSlideFixture):
    def test_real_offline_cli_sixty_fps_encode_cache_and_failed_attempt(self):
        project = self.base / 'cli-project'
        prepared = self.call_cli(project, 'prepare', '--source', str(self.pdf), '--pages', '1',
                                 '--presentation', 'original-slide')
        self.assertEqual(prepared['status'], 'SUCCESS')
        plan_path = write_json(self.base / 'plan.json', self.plan)
        self.call_cli(project, 'ingest', '--plan', str(plan_path))
        voice = self.call_cli(project, 'voice-input')
        from voice_adapter import plan_from_lesson
        voice_plan = plan_from_lesson(cv.read(voice['voice_input']))
        raw = self.base / 'synthetic-raw'
        (raw / 'audio').mkdir(parents=True)
        mp3 = raw / 'audio/narration.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(self.audio), str(mp3)], check=True)
        request = {'text': ''.join(beat['spoken_text'] for beat in voice_plan['beats']), **voice_plan['voice']}
        events = [{'type': 'SentenceBoundary', 'text': beat['spoken_text'],
                   'offset': int(start * 1e7), 'duration': int(0.7 * 1e7)}
                  for beat, start in zip(voice_plan['beats'], (0.1, 1.4, 2.8))]
        write_json(raw / 'audio/provider_events.json', {
            'provider': 'edge_tts', 'paragraph_requests': 1, 'request': request,
            'request_sha256': cv.digest(request), 'events': events,
            'mp3_sha256': cv.sha(mp3),
            'fixture_only': 'SYNTHETIC_TONE_AND_BOUNDARIES_NOT_PROVIDER_EXECUTION',
        })
        self.call_cli(project, 'bind-voice', '--raw-run', str(raw))
        rendered = self.call_cli(project, 'render')
        self.assertFalse(rendered['cache_reused'])
        video = Path(rendered['preview_path'])
        self.assertTrue(video.is_file())
        probe = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', str(video)]))
        stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        self.assertEqual(stream['r_frame_rate'], '60/1')
        self.assertEqual(stream['width'], 1600)
        self.assertEqual(stream['height'], 730)
        scene = cv.read(rendered['scene_path'])
        self.assertEqual(int(stream['nb_read_frames']), math.ceil(scene['duration'] * 60))
        self.assertGreater(rendered['static_frame_cache']['exact_static_cache_hits'], 0)
        receipts = [json.loads(line) for line in
                    (Path(rendered['output_dir']) / 'receipts.jsonl').read_text().splitlines()]
        self.assertEqual(len(receipts), int(stream['nb_read_frames']))
        self.assertTrue(all(r['caption_complete'] and r['caption_within_band'] for r in receipts))
        again = self.call_cli(project, 'render')
        self.assertTrue(again['cache_reused'])
        self.assertEqual(rendered['media_sha256'], again['media_sha256'])
        self.call_cli(project, 'qa')
        self.plan['scenes'][0]['source_objects'][1]['regions'][0][2] = 1601
        write_json(plan_path, self.plan)
        self.call_cli(project, 'ingest', '--plan', str(plan_path))
        failure = self.call_cli(project, 'render', '--samples-only', ok=False)
        self.assertIn('SOURCE_REGION_BOUNDS', failure['error'])
        latest = cv.read(project / 'attempts/latest.json')
        self.assertEqual(latest['status'], 'FAILED')
        self.assertNotIn('preview_path', latest)
        self.assertTrue((project / 'attempts/latest_success.json').exists())


if __name__ == '__main__':
    unittest.main()
