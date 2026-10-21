#!/usr/bin/env python3
"""Local P0: content package -> text/voice -> synthetic evidence -> solve -> preview.

No network calls, provider synthesis, publication, or acoustic/listening claim.
The supported solver is earliest scheduling of a reveal/read DAG within fixed
sentence windows. It does not stretch audio or invent internal word alignment.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import wave

from workflow_attempts import Attempt, atomic_write, file_lock, environment_fingerprint

import pipeline as p
from speech_text import build_speech_plan, speech_identity
from caption_contract import narration_identity, resolve_captions

VERSION = 'content-workflow-p1-1'


def require(ok, message):
    if not ok:
        raise ValueError('Workflow: ' + message)


def exact_keys(value, allowed, required, label):
    require(isinstance(value, dict) and set(value) <= set(allowed) and set(required) <= set(value),
            'unsupported or missing fields in ' + label)


def validate_package(package):
    exact_keys(package, ['schema_version', 'title', 'content', 'visual', 'voice', 'caption_refs',
                         'temporal', 'synthetic_fixture', 'source_model_evidence'],
               ['schema_version', 'title', 'content', 'visual', 'voice', 'caption_refs',
                'temporal', 'synthetic_fixture'], 'package')
    require(package['schema_version'] in ('circuit-content-package-1', 'circuit-content-package-2'), 'unsupported content package')
    require(('source_model_evidence' in package) == (package['schema_version'] == 'circuit-content-package-2'),
            'version 2 requires P1 evidence; legacy packages cannot carry a claimed gate')
    content = package['content']
    exact_keys(content, ['sources', 'knowledge_graph', 'semantic_model', 'narration'],
               ['sources', 'knowledge_graph', 'semantic_model', 'narration'], 'content')
    narration = content['narration']
    require(narration, 'empty formal manuscript')
    for row in narration:
        exact_keys(row, ['id', 'text', 'speech_adaptations'], ['id', 'text'], 'formal manuscript')
    # The existing typed derivation rejects whole-sentence overrides and stale spans.
    plan = build_speech_plan(narration, package['voice'])
    visual = package['visual']
    exact_keys(visual, ['boards', 'objects', 'layout_contract', 'required_object_ids',
                        'required_capabilities', 'camera_bounds'],
               ['boards', 'objects', 'layout_contract', 'required_object_ids',
                'required_capabilities', 'camera_bounds'], 'visual plan')
    require(len(visual['boards']) == 1, 'P0 supports one stationary board, not arbitrary camera visits')
    require(visual['camera_bounds'] == visual['boards'][0]['bounds'] == [0, 0, 1920, 1080],
            'P0 fixed camera must show the complete single native-size board')
    ids = [o['id'] for o in visual['objects']]
    require(len(ids) == len(set(ids)), 'duplicate visual object ID')
    require(set(ids) == set(visual['required_object_ids']), 'missing visual object coverage')
    for obj in visual['objects']:
        require(not set(obj) & {'start', 'end', 'duration', 'read_window'},
                'visual plan must be untimed: ' + obj['id'])
    # Preserve and validate explicit model links, never reconstruct a circuit from prose.
    model = content['semantic_model']
    exact_keys(model, ['id', 'assumptions', 'nets', 'components', 'formulas'],
               ['id', 'assumptions', 'nets', 'components', 'formulas'], 'semantic model')
    require(model['assumptions'] and model['nets'], 'model assumptions and nets required')
    require(len(model['nets']) == len(set(model['nets'])), 'duplicate net ID')
    semantic_ids = []
    for component in model['components']:
        exact_keys(component, ['id', 'kind', 'terminals', 'object_refs'],
                   ['id', 'kind', 'terminals', 'object_refs'], 'component')
        semantic_ids.append(component['id'])
        require(component['terminals'] and set(component['terminals'].values()) <= set(model['nets']),
                'dangling circuit terminal: ' + component['id'])
        require(component['object_refs'] and set(component['object_refs']) <= set(ids),
                'dangling component object: ' + component['id'])
    objects = {o['id']: o for o in visual['objects']}
    for formula in model['formulas']:
        exact_keys(formula, ['id', 'object_ref', 'component_refs', 'knowledge_refs'],
                   ['id', 'object_ref', 'component_refs', 'knowledge_refs'], 'formula')
        semantic_ids.append(formula['id'])
        require(formula['object_ref'] in objects and objects[formula['object_ref']]['kind'] == 'formula',
                'formula object must resolve without rewriting its expression')
        require(set(formula['component_refs']) <= {c['id'] for c in model['components']},
                'dangling formula component')
        require(set(formula['knowledge_refs']) <= {n['id'] for n in content['knowledge_graph']['nodes']},
                'dangling formula knowledge reference')
    require(len(semantic_ids) == len(set(semantic_ids)), 'duplicate semantic ID')
    require({f['object_ref'] for f in model['formulas']} ==
            {o['id'] for o in visual['objects'] if o['kind'] == 'formula'}, 'missing semantic formula coverage')
    # Reuse the canonical coverage validator with temporary ordinal windows only
    # to check source spans. These temporary windows are never timing evidence.
    dummy = [dict(n, start=i, end=i+1) for i, n in enumerate(narration)]
    refs = package['caption_refs']
    for ref in refs:
        exact_keys(ref, ['id', 'narration_id', 'source_range'],
                   ['id', 'narration_id', 'source_range'], 'caption source reference')
    byid = {n['id']: (i, n) for i, n in enumerate(narration)}
    require(all(c['narration_id'] in byid for c in refs), 'dangling caption narration ID')
    require(len(refs) == len(narration) and len({c['narration_id'] for c in refs}) == len(narration),
            'P0 requires exactly one full caption per sentence; finer cues need finer timing evidence')
    temporary = [dict(c, start=byid[c['narration_id']][0], end=byid[c['narration_id']][0]+1) for c in refs]
    resolved, _ = resolve_captions(dummy, temporary, len(narration))
    formal = {'schema_version': 'formal-caption-source-1',
              'narration': [{'id': n['id'], 'text': n['text']} for n in narration],
              'caption_refs': copy.deepcopy(refs), 'transcript_sha256': narration_identity(narration)}
    # Explicit source slices, no editable text route. Content here is derived.
    formal['derived_full_text'] = [{'id': c['id'], 'text': c['text']} for c in resolved]
    return formal, plan


def pcm_info(path):
    with wave.open(str(path), 'rb') as wav:
        params = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getcomptype())
        frames = wav.getnframes()
        pcm = wav.readframes(frames)
    require(params == (24000, 1, 2, 'NONE'), 'fixture audio must be 24 kHz mono 16-bit PCM')
    require(frames > 0 and len(pcm) == frames*2, 'empty or truncated PCM')
    return {'sha256': p.sha(path), 'pcm_sha256': hashlib.sha256(pcm).hexdigest(),
            'pcm_frames': frames, 'sample_rate': 24000, 'channels': 1,
            'sample_width_bytes': 2, 'duration': frames/24000}


def make_fixture(plan, spec, directory):
    """Write audible test tones, explicitly NOT synthesized speech or alignment."""
    exact_keys(spec, ['schema_version', 'sentences', 'tail_seconds'],
               ['schema_version', 'sentences', 'tail_seconds'], 'synthetic fixture')
    require(spec['schema_version'] == 'synthetic-sentence-fixture-1', 'unsupported fixture schema')
    require(len(spec['sentences']) == len(plan['beats']), 'fixture sentence coverage differs')
    directory.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    events = []
    frequency = 180 + int(p.digest(plan)[:4], 16) % 360
    for beat, row in zip(plan['beats'], spec['sentences']):
        exact_keys(row, ['narration_id', 'duration_seconds', 'gap_before_seconds'],
                   ['narration_id', 'duration_seconds', 'gap_before_seconds'], 'fixture sentence')
        require(row['narration_id'] == beat['id'], 'fixture sentence ID/order mismatch')
        gap, duration = row['gap_before_seconds'], row['duration_seconds']
        require(p.finite(gap) and gap >= 0 and p.finite(duration) and duration > 0,
                'invalid fixture timing')
        frames.extend(b'\x00\x00' * round(gap*24000))
        start = len(frames)//2
        count = round(duration*24000)
        require(count > 0, 'fixture sentence shorter than one sample')
        for i in range(count):
            # Low-volume pulsed tone. Its frequency depends on the speech input
            # so invalidation tests can also establish distinct audio byte identity.
            envelope = min(1, i/240, (count-i)/240)
            sample = round(1000*envelope*math.sin(2*math.pi*frequency*i/24000))
            frames.extend(struct.pack('<h', sample))
        events.append({'narration_id': beat['id'], 'start_frame': start,
                       'end_frame': len(frames)//2, 'spoken_text': beat['spoken_text'],
                       'formal_text_sha256': beat['formal_text_sha256'], 'span_map': beat['span_map']})
    tail = spec['tail_seconds']
    require(p.finite(tail) and tail >= 0, 'invalid fixture tail')
    frames.extend(b'\x00\x00' * round(tail*24000))
    audio = directory/'audio.wav'
    with wave.open(str(audio), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(frames)
    receipt = {'schema_version': 'synthetic-audio-events-1', 'evidence_kind': 'synthetic_test_tones_not_speech',
               'boundary_granularity': 'sentence', 'time_base': 'pcm_sample_frames',
               'speech_sha256': p.digest(plan), 'fixture_sha256': p.digest(spec),
               'audio': pcm_info(audio), 'events': events,
               'claims': {'real_tts': False, 'word_alignment': False, 'pronunciation_verified': False}}
    p.write(directory/'receipt.json', receipt)
    return receipt


def validate_events(plan, receipt, audio, spec):
    require(receipt.get('schema_version') == 'synthetic-audio-events-1' and
            receipt.get('evidence_kind') == 'synthetic_test_tones_not_speech',
            'this P0 adapter only accepts clearly labeled synthetic test evidence')
    require(receipt.get('time_base') == 'pcm_sample_frames' and
            receipt.get('boundary_granularity') == 'sentence', 'unsupported event time base/granularity')
    require(receipt.get('speech_sha256') == p.digest(plan), 'stale voice/phonetic event binding')
    require(receipt.get('fixture_sha256') == p.digest(spec), 'stale fixture specification')
    require(receipt.get('claims') == {'real_tts': False, 'word_alignment': False, 'pronunciation_verified': False},
            'synthetic evidence cannot claim speech verification')
    actual = pcm_info(audio)
    require(receipt.get('audio') == actual, 'audio bytes/PCM evidence changed')
    events = receipt.get('events', [])
    require(len(events) == len(plan['beats']), 'missing event coverage')
    previous = 0
    expected_frame = 0
    for beat, event, specification in zip(plan['beats'], events, spec['sentences']):
        require(event.get('narration_id') == beat['id'] and event.get('spoken_text') == beat['spoken_text'] and
                event.get('formal_text_sha256') == beat['formal_text_sha256'] and event.get('span_map') == beat['span_map'],
                'event text/span mapping mismatch: ' + beat['id'])
        start, end = event.get('start_frame'), event.get('end_frame')
        require(all(isinstance(v, int) and not isinstance(v, bool) for v in [start, end]) and
                previous <= start < end <= actual['pcm_frames'], 'invalid/overlapping/out-of-PCM event: ' + beat['id'])
        expected_frame += round(specification['gap_before_seconds']*24000)
        require(start == expected_frame, 'event start differs from declared synthetic fixture')
        expected_frame += round(specification['duration_seconds']*24000)
        require(end == expected_frame, 'event end differs from declared synthetic fixture')
        previous = end
    require(actual['pcm_frames'] == expected_frame+round(spec['tail_seconds']*24000),
            'PCM duration differs from declared synthetic fixture')
    return {'status': 'VALIDATED_SYNTHETIC_ONLY', 'audio_sha256': actual['sha256'],
            'event_count': len(events), 'receipt_sha256': p.digest(receipt),
            'limits': ['Sentence fixture boundaries are not measured speech or word alignment.',
                       'Hashes establish artifact identity, not acoustic transcript agreement.']}


def solve(package, receipt):
    """Earliest schedule is complete for this fixed-window, lower-bound DAG subset."""
    temporal = package['temporal']
    exact_keys(temporal, ['actions', 'caption_max_codepoints_per_second', 'caption_min_seconds'],
               ['actions', 'caption_max_codepoints_per_second', 'caption_min_seconds'], 'temporal constraints')
    rate, minimum = temporal['caption_max_codepoints_per_second'], temporal['caption_min_seconds']
    require(p.finite(rate) and rate > 0 and p.finite(minimum) and minimum > 0, 'invalid caption reading policy')
    windows = {e['narration_id']: [e['start_frame']/24000, e['end_frame']/24000] for e in receipt['events']}
    narration = [dict(n, start=windows[n['id']][0], end=windows[n['id']][1]) for n in package['content']['narration']]
    captions = [dict(c, start=windows[c['narration_id']][0], end=windows[c['narration_id']][1]) for c in package['caption_refs']]
    duration = receipt['audio']['duration']
    resolved, coverage = resolve_captions(narration, captions, duration)
    conflicts = []
    for cue in resolved:
        required = max(minimum, len(cue['text'])/rate)
        available = cue['end']-cue['start']
        if available+1e-8 < required:
            conflicts.append({'constraint': 'caption_reading_time', 'id': cue['id'],
                              'required_seconds': required, 'available_seconds': available,
                              'remedy': 'Change voice pace/pauses or revise the formal manuscript, never drop subtitle text.'})
    contract = copy.deepcopy(package['visual']['layout_contract'])
    contract['subtitles']['font_family'] = p.typography.FAMILY
    p.layout.validate_contract(contract, {'logical_width': 1920, 'logical_height': 1080})
    try:
        # Final wrapping uses the resolved native font and actual fixed windows.
        p.layout.compile_captions([dict(c, audio_end=c['end']) for c in resolved], contract, p.native)
    except ValueError as exc:
        conflicts.append({'constraint': 'caption_layout', 'reason': str(exc),
                          'remedy': 'Obtain finer timing evidence for full-text cue splits or change layout. No summary fallback.'})
    actions = temporal['actions']
    byid = {a['id']: a for a in actions}
    require(len(byid) == len(actions), 'duplicate temporal action ID')
    objects = {o['id']: o for o in package['visual']['objects']}
    require({a['target'] for a in actions} == {o['id'] for o in objects.values() if o['kind'] == 'formula'} and
            len({a['target'] for a in actions}) == len(actions), 'each formula needs exactly one reveal/read constraint')
    for action in actions:
        exact_keys(action, ['id', 'target', 'narration_id', 'earliest_offset', 'deadline_offset',
                            'min_reveal_seconds', 'min_read_seconds', 'after'],
                   ['id', 'target', 'narration_id', 'earliest_offset', 'deadline_offset',
                    'min_reveal_seconds', 'min_read_seconds', 'after'], 'temporal action')
        require(action['narration_id'] in windows and set(action['after']) <= set(byid), 'dangling action dependency')
        require(all(p.finite(action[k]) for k in ['earliest_offset', 'deadline_offset', 'min_reveal_seconds', 'min_read_seconds']) and
                action['earliest_offset'] >= 0 and action['deadline_offset'] <= 0 and
                action['min_reveal_seconds'] > 0 and action['min_read_seconds'] > 0, 'invalid temporal bounds')
    scheduled, visiting = {}, set()
    def visit(aid):
        require(aid not in visiting, 'cyclic temporal dependencies')
        if aid in scheduled:
            return scheduled[aid]
        visiting.add(aid)
        action = byid[aid]
        dependencies = [visit(dep) for dep in action['after']]
        start, end = windows[action['narration_id']]
        start = max([start+action['earliest_offset']] + [d['read_end'] for d in dependencies])
        reveal_end = start+action['min_reveal_seconds']
        read_end = reveal_end+action['min_read_seconds']
        deadline = end+action['deadline_offset']
        if read_end > deadline+1e-8:
            conflicts.append({'constraint': 'reveal_then_read_before_sentence_deadline', 'id': aid,
                              'target': action['target'], 'earliest_start': start, 'earliest_read_end': read_end,
                              'deadline': deadline, 'shortfall_seconds': read_end-deadline,
                              'after': action['after'],
                              'remedy': 'Change visual intent or obtain slower/paused audio; do not silently stretch evidence.'})
        result = {'id': aid, 'target': action['target'], 'start': start, 'reveal_end': reveal_end, 'read_end': read_end}
        scheduled[aid] = result
        visiting.remove(aid)
        return result
    for aid in byid:
        visit(aid)
    return {'schema_version': 'joint-timeline-p0-1', 'status': 'UNSAT' if conflicts else 'SAT',
            'duration': duration, 'narration': narration, 'captions': captions,
            'caption_coverage': coverage, 'actions': list(scheduled.values()), 'conflicts': conflicts,
            'evidence': 'validated_synthetic_sentence_windows_not_real_speech',
            'reading_policy': 'configured_codepoint_rate_and_minimum_not_comprehension_evidence'}


def to_lesson(package, timeline):
    require(timeline['status'] == 'SAT', 'UNSAT timeline cannot enter the renderer')
    content, visual = package['content'], copy.deepcopy(package['visual'])
    actions = {a['target']: a for a in timeline['actions']}
    for obj in visual['objects']:
        obj.update(start=0, end=timeline['duration'])
        if obj['id'] in actions:
            a = actions[obj['id']]
            obj.update(start=a['start'], duration=a['reveal_end']-a['start'],
                       read_window=[a['reveal_end'], a['read_end']])
    camera = visual.pop('camera_bounds')
    return {'schema_version': 'circuit-lesson-1', 'title': package['title'], 'duration': timeline['duration'],
            'sources': copy.deepcopy(content['sources']), 'knowledge_graph': copy.deepcopy(content['knowledge_graph']),
            **visual, 'narration': timeline['narration'], 'captions': timeline['captions'], 'voice': package['voice'],
            'camera_track': [{'start': 0, 'end': timeline['duration'], 'from': camera, 'to': camera}],
            'teacher_actions': []}


def execute(package, output, attempt, *, video=False, width=640, fps=5, source_root=None):
    """Every stage emits an inspectable artifact; only validated audio is cached."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    gate_artifact = None
    gate_status = {'status': 'UNGATED_LEGACY_PREVIEW', 'scientific_approval': False,
                   'audiovisual_approval': False, 'publication_allowed': False}
    if isinstance(package, dict) and package.get('schema_version') == 'circuit-content-package-2':
        attempt.stage('pre_freeze_gate')
        from prefreeze_gate import prepare
        gate_artifact = prepare(package, source_root)
        gate_status = gate_artifact['binding']
    attempt.stage('validate_package')
    formal, plan = validate_package(package)
    implementation = p.sha(__file__)
    key = lambda name, value: p.digest({'node': name, 'version': VERSION, 'implementation': implementation, 'inputs': value})
    keys = {'formal_captions': key('formal_captions', formal), 'phonetic_voice': key('phonetic_voice', plan)}
    if gate_artifact is not None:
        keys['formal_export'] = key('formal_export', gate_artifact)
        atomic_write(output/'nodes'/'formal_export'/keys['formal_export']/'artifact.json', gate_artifact)
        attempt.artifact('formal_export')
    keys['audio_events'] = key('audio_events', [keys['phonetic_voice'], package['synthetic_fixture']])
    audio_dir = output/'nodes'/'audio_events'/keys['audio_events']
    attempt.stage('audio_fixture')
    with file_lock(audio_dir/'.audio.lock'):
        reused = (audio_dir/'receipt.json').exists()
        receipt = json.loads((audio_dir/'receipt.json').read_text()) if reused else make_fixture(plan, package['synthetic_fixture'], audio_dir)
        attempt.artifact('audio_events', created=not reused)
        attempt.stage('validate_audio_events')
        validation = validate_events(plan, receipt, audio_dir/'audio.wav', package['synthetic_fixture'])
    runtime = p.runtime_bindings()
    keys['timeline'] = key('timeline', [keys['formal_captions'], keys['audio_events'], validation,
                                      package['temporal'], package['visual']['layout_contract'], runtime, gate_status])
    attempt.stage('solve_timeline')
    timeline = solve(package, receipt)
    for name, artifact in [('formal_captions', formal), ('phonetic_voice', plan), ('timeline', timeline)]:
        atomic_write(output/'nodes'/name/keys[name]/'artifact.json', artifact)
        attempt.artifact(name)
    atomic_write(audio_dir/'validation.json', validation)
    manifest = {'schema_version': 'workflow-run-1', 'status': timeline['status'], 'package_sha256': p.digest(package),
                'node_versions': keys, 'audio_cache': 'validated_reuse' if reused else 'built_synthetic_fixture',
                'review': {'status': 'NOT_PERFORMED', 'previous_reviews_reused': False},
                'evidence_kind': 'synthetic_test_tones_not_speech', 'network_calls': 0,
                'source_model_gate': gate_status,
                'conflicts': timeline['conflicts']}
    if timeline['status'] == 'SAT':
        attempt.stage('adapt_lesson')
        lesson = p.bind_audio(to_lesson(package, timeline), audio_dir/'audio.wav')
        lesson['source_model_gate'] = copy.deepcopy(gate_status)
        keys['frozen_scene'] = key('frozen_scene', [keys['timeline'], package['content']['semantic_model'], lesson, runtime])
        scene_dir = output/'nodes'/'frozen_scene'/keys['frozen_scene']
        atomic_write(scene_dir/'lesson-derived.json', lesson)
        attempt.stage('freeze_scene')
        scene = p.compile_data(lesson)
        scene.update(source_model_gate=copy.deepcopy(gate_status), semantic_model=copy.deepcopy(package['content']['semantic_model']),
                     timing_evidence=timeline['evidence'],
                     workflow_binding={'version': VERSION, 'package_sha256': p.digest(package),
                                       'node_versions': dict(keys), 'audio_events_sha256': p.digest(receipt),
                                       'source_model_gate': copy.deepcopy(gate_status)})
        scene.pop('scene_digest')
        scene['scene_digest'] = p.digest(scene)
        atomic_write(scene_dir/'scene.json', scene)
        attempt.artifact('frozen_scene')
        render_environment = environment_fingerprint(output_profile(video, width, fps), p.runtime_bindings())
        keys['preview'] = key('preview', [scene['scene_digest'], render_environment['sha256']])
        # Each attempt owns its media directory, including partial failed renders.
        preview_dir = output/'nodes'/'preview'/keys['preview']/attempt.run_id
        attempt.stage('render_preview')
        media = p.render(scene, preview_dir, width=width, fps=fps, video=video, audio=audio_dir/'audio.wav')
        media['audio'] = 'synthetic_test_tones_not_speech'
        media['workflow_node'] = keys['preview']
        media['review_status'] = 'not_audiovisually_reviewed'
        media['source_model_gate'] = copy.deepcopy(gate_status)
        media['run_id'] = attempt.run_id
        media['render_environment_fingerprint'] = render_environment
        atomic_write(preview_dir/'manifest.json', media)
        attempt.artifact('preview')
        manifest.update(scene_path=str(scene_dir/'scene.json'), preview_path=str(preview_dir),
                        scene_digest=scene['scene_digest'], media_sha256=media.get('media_sha256'),
                        status='SUCCESS', technical_status='TECHNICAL_PREVIEW_UNREVIEWED',
                        render_environment_fingerprint=render_environment)
    prior = attempt.previous_success
    oldkeys = prior.get('node_versions', {})
    manifest['invalidated_nodes'] = [name for name in sorted(set(keys) | set(oldkeys)) if oldkeys.get(name) != keys.get(name)]
    manifest['artifacts'] = {
        'formal_captions': str(output/'nodes'/'formal_captions'/keys['formal_captions']/'artifact.json'),
        'phonetic_voice': str(output/'nodes'/'phonetic_voice'/keys['phonetic_voice']/'artifact.json'),
        'audio_events': str(audio_dir/'receipt.json'), 'audio_validation': str(audio_dir/'validation.json'),
        'timeline': str(output/'nodes'/'timeline'/keys['timeline']/'artifact.json')}
    if gate_artifact is not None:
        manifest['artifacts']['formal_export'] = str(output/'nodes'/'formal_export'/keys['formal_export']/'artifact.json')
    return manifest


def output_profile(video, width, fps):
    return {'video': video, 'width': width, 'fps': fps,
            'renderer': 'pipeline.render', 'renderer_sha256': p.sha(p.__file__),
            'video_codec': 'libx264', 'preset': 'fast', 'crf': 22, 'pixel_format': 'yuv420p',
            'color_space': 'bt709', 'audio_codec': 'aac', 'audio_bitrate': '192k', 'audio_sample_rate': 48000}


def invoke(loader, output, *, input_sha256, input_encoding, video=False, width=640, fps=5, source_root=None):
    attempt = Attempt(output, input_sha256, input_encoding,
                      {'status': 'PENDING_CAPTURE', 'sha256': None})
    try:
        attempt.stage('capture_environment')
        environment = environment_fingerprint(output_profile(video, width, fps), p.runtime_bindings())
        attempt.environment(environment)
        attempt.stage('load_input')
        package = loader()
        result = execute(package, output, attempt, video=video, width=width, fps=fps, source_root=source_root)
        return attempt.finish(result['status'], result=result)
    except BaseException as exc:
        failed = attempt.finish('FAILED', error=exc)
        # Preserve the original exception type for callers and existing tests.
        exc.workflow_attempt = failed
        raise


def run(package, output, *, video=False, width=640, fps=5, source_root=None):
    """Python entrypoint: record an attempt before validating the supplied data."""
    try:
        raw = json.dumps(package, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        failure = None
    except (ValueError, TypeError) as exc:
        raw, failure = None, exc
    def load():
        if failure is not None:
            raise failure
        return package
    return invoke(load, output, input_sha256=hashlib.sha256(raw).hexdigest() if raw is not None else None,
                  input_encoding='canonical_python_json' if raw is not None else 'unserializable_python_input',
                  video=video, width=width, fps=fps, source_root=source_root)


def run_file(path, output, *, video=False, width=640, fps=5):
    """CLI input hash covers exact file bytes, including malformed JSON."""
    try:
        raw, failure = Path(path).read_bytes(), None
    except OSError as exc:
        raw, failure = None, exc
    def load():
        if failure is not None:
            raise failure
        return json.loads(raw)
    return invoke(load, output, input_sha256=hashlib.sha256(raw).hexdigest() if raw is not None else None,
                  input_encoding='raw_file_bytes' if raw is not None else 'unreadable_file',
                  video=video, width=width, fps=fps, source_root=Path(path).resolve().parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--synthetic-audio-fixture', action='store_true', required=True,
                        help='Explicitly generate test tones/events, not real TTS speech')
    parser.add_argument('--video', action='store_true')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--fps', type=int, default=5)
    args = parser.parse_args()
    try:
        result = run_file(args.package, args.output, video=args.video, width=args.width, fps=args.fps)
        print(json.dumps(result, ensure_ascii=False))
        return 2 if result['status'] == 'UNSAT' else 0
    except Exception as exc:
        print(json.dumps(getattr(exc, 'workflow_attempt', {'status': 'FAILED', 'error_code': 'ATTEMPT_SETUP_FAILED',
                                                         'reason': str(exc)}), ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
