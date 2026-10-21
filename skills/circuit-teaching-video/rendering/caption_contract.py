"""Full formal-transcript subtitles, separate from board labels and visual annotations.

Cue text is a contiguous slice of the authoritative formal text, never a summary
or a fallback to display_text. This proves text/window coverage of declarations,
not that the declarations match the recorded voice or establish word alignment.
"""
import hashlib
import json
import math
from speech_text import speech_identity


def require(ok, message):
    if not ok:
        raise ValueError('Caption contract: ' + message)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def narration_identity(narration):
    return identity([{'id': n['id'], 'text': n['text']} for n in narration])


def timing_identity(narration, cues):
    return identity({'narration': [{k: n[k] for k in ('id', 'start', 'end')} for n in narration],
                     'captions': [{k: c[k] for k in ('id', 'narration_id', 'source_range', 'start', 'end')} for c in cues]})


def validate_audio_binding(binding, narration, cues, voice=None):
    require(binding.get('schema_version') == 'narration-audio-binding-1', 'unsupported audio binding')
    require(binding.get('narration_sha256') == narration_identity(narration),
            'narration changed; regenerate or explicitly rebind matching audio')
    require(binding.get('timing_sha256') == timing_identity(narration, cues),
            'timing changed; rederive timing and explicitly rebind audio')
    require(binding.get('voice_sha256') == identity(voice),
            'voice configuration changed; regenerate or explicitly rebind matching audio')
    require(binding.get('speech_sha256') == speech_identity(narration, voice),
            'speech adaptation changed; regenerate or explicitly rebind matching audio')
    value = binding.get('audio_sha256', '')
    require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
            'invalid bound audio hash')
    return True


def resolve_captions(narration, cues, duration, *, compiled=False):
    """Resolve exact slices and reject missing, repeated, reordered or extra text.

    source_range uses Python Unicode code-point offsets [start, end), not bytes.
    The intervals partition each declared narration window without gaps. Silence
    between narration records needs no subtitle. Timing remains authored evidence.
    """
    require(finite(duration) and duration > 0, 'invalid duration')
    require(isinstance(narration, list) and isinstance(cues, list), 'narration and captions must be lists')
    by_id = {}
    previous = 0
    for row in narration:
        nid = row.get('id')
        require(isinstance(nid, str) and nid and nid not in by_id, 'missing or duplicate narration ID')
        text = row.get('text')
        require(isinstance(text, str) and text.strip(), 'missing text: ' + nid)
        require(not any(ord(ch) < 32 for ch in text), 'split control characters/newlines into narration records: ' + nid)
        start, end = row.get('start'), row.get('end')
        require(finite(start) and finite(end) and previous <= start < end <= duration,
                'invalid or overlapping narration window: ' + nid)
        previous = end
        by_id[nid] = row
    resolved = []
    seen = set()
    previous = 0
    for cue in cues:
        cid = cue.get('id')
        require(isinstance(cid, str) and cid and cid not in seen, 'missing or duplicate caption ID')
        seen.add(cid)
        if not compiled:
            require(set(cue) <= {'id', 'narration_id', 'source_range', 'start', 'end'},
                    'authored captions contain references and times only; put visual annotations in world objects: ' + cid)
        nid = cue.get('narration_id')
        require(nid in by_id, 'caption must reference authoritative narration: ' + cid)
        span = cue.get('source_range')
        require(isinstance(span, list) and len(span) == 2 and
                all(isinstance(v, int) and not isinstance(v, bool) for v in span),
                'source_range must contain two integer code-point offsets: ' + cid)
        a, b = span
        source = by_id[nid]
        require(0 <= a < b <= len(source['text']), 'source_range outside narration: ' + cid)
        text = source['text'][a:b]
        require(text.strip(), 'empty caption slice: ' + cid)
        # Only the compiler can materialize subtitle text. There is deliberately
        # no display_text/text override in the authored caption schema.
        if compiled:
            require('display_text' not in cue and cue.get('text') == text,
                    'compiled text differs from full formal-text slice: ' + cid)
        start, end = cue.get('start'), cue.get('end')
        require(finite(start) and finite(end) and previous <= start < end <= duration,
                'invalid or overlapping caption window: ' + cid)
        require(source['start'] <= start < end <= source['end'],
                'caption outside its narration window: ' + cid)
        previous = end
        resolved.append({'id': cid, 'narration_id': nid, 'source_range': [a, b],
                         'start': start, 'end': end, 'text': text,
                         'text_sha256': text_hash(source['text'])})
    cursor = 0
    for source in narration:
        nid = source['id']
        linked = [cue for cue in resolved if cue['narration_id'] == nid]
        require(linked, 'narration has no full subtitles: ' + nid)
        require(resolved[cursor:cursor + len(linked)] == linked, 'caption/narration order differs: ' + nid)
        cursor += len(linked)
        offset = 0
        time = source['start']
        for cue in linked:
            require(cue['source_range'][0] == offset, 'omitted, duplicated or reordered formal text: ' + nid)
            require(abs(cue['start'] - time) <= 1e-8, 'gap in declared speech-window coverage: ' + nid)
            offset = cue['source_range'][1]
            time = cue['end']
        require(offset == len(source['text']), 'missing formal-text tail: ' + nid)
        require(abs(time - source['end']) <= 1e-8, 'missing declared speech-window tail: ' + nid)
        require(''.join(c['text'] for c in linked) == source['text'],
                'subtitles must reconstruct text exactly: ' + nid)
    report = {
        'policy': 'full_formal_text_exact',
        'status': 'PASS' if narration else 'NOT_APPLICABLE_NO_NARRATION',
        'narration_records': len(narration),
        'caption_cues': len(resolved),
        'formal_codepoints': sum(len(n['text']) for n in narration),
        'narration_sha256': {n['id']: text_hash(n['text']) for n in narration},
        'transcript_sha256': narration_identity(narration),
        'timing_sha256': timing_identity(narration, resolved),
        'text_evidence': 'exact_ordered_source_slices',
        'timing_evidence': 'declared_narration_windows_not_audio_alignment',
    }
    return resolved, report


def validate_compiled_captions(scene):
    resolved, report = resolve_captions(scene.get('narration', []), scene.get('captions', []), scene['duration'], compiled=True)
    require(scene.get('caption_coverage') == report, 'missing or stale full-text coverage receipt')
    for cue, expected in zip(scene.get('captions', []), resolved):
        require(cue.get('text') == expected['text'], 'compiled cue differs from text: ' + cue['id'])
        require(cue.get('text_sha256') == expected['text_sha256'], 'stale narration hash: ' + cue['id'])
        require(''.join(row['text'] for row in cue['rows']) == cue['text'], 'rows lost formal text: ' + cue['id'])
        require(''.join(unit['text'] for row in cue['rows'] for unit in row['units']) == cue['text'],
                'rendered units lost formal text: ' + cue['id'])
    require(scene.get('speech_sha256') == speech_identity(scene.get('narration', []), scene.get('voice')),
            'missing or stale derived speech identity')
    if scene.get('audio_binding') is not None:
        validate_audio_binding(scene['audio_binding'], scene.get('narration', []), scene.get('captions', []), scene.get('voice'))
    return report
