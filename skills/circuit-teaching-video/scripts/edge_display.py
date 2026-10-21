#!/usr/bin/env python3
"""Edge sentence-onset display adapter, not word/end-point alignment.

Offline: python edge_display.py lesson.json --source RAW_RUN --output NEW_RUN
Opt-in:  python edge_display.py lesson.json --output NEW_RUN --synthesize

The opt-in path uses the accepted voice_adapter transport unchanged. Only its
specific nonoverlap rejection is eligible for recovery, and only after the raw
request, exact sentence order/text, increasing onsets, raw intervals and freshly
decoded PCM all pass independent validation. No audio is trimmed or stretched.
Provider intervals remain raw evidence. caption_windows are exclusive DISPLAY
windows, ending at the next provider onset (last window: full PCM duration).
They are not measured sentence endings, word alignment or pronunciation proof.
An explicit offline-only --allow-whitespace-comma-projection additionally permits
equal-length requested-whitespace -> provider-ASCII-comma substitutions. Every
other code point must match in place; both texts and each difference are retained.
"""
from pathlib import Path
import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave


# Import the accepted implementation without creating bytecode in its tree.
sys.dont_write_bytecode = True
ADAPTER_PATH = Path(__file__).resolve().parents[1] / 'scripts/voice_adapter.py'
OVERLAP_ERROR = 'Provider sentence times must be positive, ordered and nonoverlapping'
DISPLAY_POLICY = {
    'start': 'exact provider SentenceBoundary onset',
    'end': 'next provider onset; final window ends at measured full PCM duration',
    'interval_convention': '[start, end)',
    'initial_silence': 'unassigned before first provider onset',
    'granularity': 'sentence only',
    'is_word_alignment': False,
    'is_measured_sentence_endpoint': False,
    'audio_trimmed_or_time_stretched': False,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')


def adapter():
    spec = importlib.util.spec_from_file_location('_accepted_edge_voice_adapter', ADAPTER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checked_events(plan, metadata, allow_whitespace_comma_projection=False):
    """Never sort, merge, fuzzy-match or invent an event to fix the mapping."""
    require(isinstance(metadata, dict), 'Raw provider metadata must be an object')
    require(metadata.get('provider') == 'edge_tts', 'Only recorded edge_tts receipts are supported')
    require(type(metadata.get('paragraph_requests')) is int and metadata['paragraph_requests'] == 1,
            'Expected one recorded paragraph request')
    require(isinstance(plan['voice'], dict), 'Lesson must provide the actual voice configuration')
    request = {'text': ''.join(beat['spoken_text'] for beat in plan['beats']), **plan['voice']}
    require('text' not in plan['voice'], 'Voice configuration cannot override the derived narration')
    require(metadata.get('request') == request, 'Cached request text/voice differs from derived speech plan')
    require(metadata.get('request_sha256') == digest(request), 'Raw request hash mismatch')
    all_events = metadata.get('events')
    require(isinstance(all_events, list) and all(isinstance(e, dict) for e in all_events),
            'Raw provider events must be a list of objects')
    events = [(i, e) for i, e in enumerate(all_events) if e.get('type') == 'SentenceBoundary']
    require(len(events) == len(plan['beats']) and bool(events),
            'Expected exactly one provider sentence event per formal narration record')
    previous_start = -1.0
    global_cursor = 0
    sentences = []
    for beat, (event_index, event) in zip(plan['beats'], events):
        requested_text, provider_text = beat['spoken_text'], event.get('text')
        require(isinstance(provider_text, str) and len(provider_text) == len(requested_text),
                'Provider sentence code-point length differs: ' + beat['sentence_id'])
        differences = []
        for position, (requested, provider) in enumerate(zip(requested_text, provider_text)):
            if requested == provider:
                continue
            require(allow_whitespace_comma_projection and requested.isspace() and provider == ',',
                    'Unpermitted provider sentence text/order difference at ' + beat['sentence_id'] +
                    ':' + str(position) + ' (' + repr(requested) + ' -> ' + repr(provider) + ')')
            differences.append({
                'sentence_id': beat['sentence_id'], 'provider_event_index': event_index,
                'sentence_codepoint_range': [position, position + 1],
                'requested_global_range': [global_cursor + position, global_cursor + position + 1],
                'provider_global_range': [global_cursor + position, global_cursor + position + 1],
                'operation': 'replace', 'requested_text': requested, 'provider_text': provider,
                'permitted_rule': 'one requested whitespace code point to one provider ASCII comma',
            })
        offset, duration = event.get('offset'), event.get('duration')
        require(all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in (offset, duration)), 'Provider timing must contain finite numeric ticks')
        start, end = offset / 10_000_000, (offset + duration) / 10_000_000
        require(0 <= start < end and math.isfinite(end), 'Provider raw interval must be finite and positive')
        require(start > previous_start, 'Provider sentence onsets must be strictly increasing, never reordered')
        previous_start = start
        sentences.append({
            'sentence_id': beat['sentence_id'],
            'formal_text': beat['formal_text'],
            'formal_text_sha256': beat['formal_text_sha256'],
            'spoken_text': beat['spoken_text'],
            'requested_text': requested_text, 'provider_text': provider_text,
            'exact_text_equal': not differences, 'text_differences': differences,
            'span_map': beat['span_map'],
            'adaptations_sha256': beat['adaptations_sha256'],
            'provider_event_index': event_index,
            'provider_offset_ticks': offset,
            'provider_duration_ticks': duration,
            'provider_onset_seconds': start,
            'raw_provider_interval_seconds': {'start': start, 'end': end, 'duration': duration / 10_000_000},
            'boundary_source': 'raw provider SentenceBoundary; interval unchanged',
        })
        global_cursor += len(requested_text)
    return sentences


def normalize(lesson_path, source, output, adapter_outcome=None, allow_whitespace_comma_projection=False):
    """Validate cached artifacts and write new artifacts without modifying input."""
    lesson_path, source, output = Path(lesson_path).resolve(), Path(source).resolve(), Path(output).resolve()
    require(source != output, 'Use a separate output directory; raw source evidence must not be overwritten')
    metadata_path, mp3_path = source / 'audio/provider_events.json', source / 'audio/narration.mp3'
    require(metadata_path.is_file() and mp3_path.is_file(), 'Complete provider_events.json and narration.mp3 are required')
    lesson_hash, metadata_hash, mp3_hash = sha(lesson_path), sha(metadata_path), sha(mp3_path)
    original = adapter()
    plan = original.plan_from_lesson(load(lesson_path))
    original.validate_spoken_policy(plan)
    metadata = load(metadata_path)
    sentences = checked_events(plan, metadata, allow_whitespace_comma_projection)
    differences = [difference for sentence in sentences for difference in sentence['text_differences']]
    requested_text = ''.join(sentence['requested_text'] for sentence in sentences)
    provider_text = ''.join(sentence['provider_text'] for sentence in sentences)
    require(metadata.get('mp3_sha256') == mp3_hash, 'Cached MP3 hash mismatch')
    overlaps = []
    for previous, current in zip(sentences, sentences[1:]):
        overlap_ticks = (previous['provider_offset_ticks'] + previous['provider_duration_ticks'] -
                         current['provider_offset_ticks'])
        if overlap_ticks > 0:
            overlaps.append({'preceding_sentence_id': previous['sentence_id'],
                             'following_sentence_id': current['sentence_id'],
                             'overlap_ticks': overlap_ticks, 'overlap_seconds': overlap_ticks / 10_000_000})
    if adapter_outcome and adapter_outcome.get('status') == 'overlap_rejection':
        require(bool(overlaps), 'Adapter overlap recovery requires a verified raw provider overlap')
    names = ('audio', 'speech_plan.json', 'voice_receipt.normalized.json', 'artifact_hashes.json')
    output.mkdir(parents=True, exist_ok=True)
    require(all(not (output / name).exists() for name in names),
            'Normalized output already exists; choose a fresh directory rather than overwrite evidence')
    with tempfile.TemporaryDirectory(prefix='.edge-normalize-', dir=output) as temporary:
        stage = Path(temporary)
        (stage / 'audio').mkdir()
        copied_metadata, copied_mp3 = stage / 'audio/provider_events.json', stage / 'audio/narration.mp3'
        shutil.copyfile(metadata_path, copied_metadata)
        shutil.copyfile(mp3_path, copied_mp3)
        require(sha(copied_metadata) == metadata_hash and sha(copied_mp3) == mp3_hash,
                'Raw provider artifacts changed while copying')
        decoded = stage / 'audio/narration.wav'
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(copied_mp3),
                        '-map', '0:a:0', '-vn', '-c:a', 'pcm_s16le', '-ar', '24000', '-ac', '1',
                        str(decoded)], check=True)
        with wave.open(str(decoded), 'rb') as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
            channels, width, compression = wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()
            pcm = wav.readframes(frames)
        require((rate, channels, width, compression) == (24000, 1, 2, 'NONE'),
                'Decoded audio must be 24 kHz mono 16-bit PCM')
        require(frames > 0 and len(pcm) == frames * channels * width,
                'Decoded PCM is empty or truncated')
        duration = frames / rate
        for sentence in sentences:
            require(sentence['provider_onset_seconds'] < duration and
                    sentence['raw_provider_interval_seconds']['end'] <= duration + 1 / rate,
                    'Provider raw interval extends beyond decoded PCM: ' + sentence['sentence_id'])
        caption_windows = []
        for index, sentence in enumerate(sentences):
            end = sentences[index + 1]['provider_onset_seconds'] if index + 1 < len(sentences) else duration
            caption_windows.append({
                'sentence_id': sentence['sentence_id'],
                'start': sentence['provider_onset_seconds'], 'end': end,
                'start_source': 'provider SentenceBoundary onset',
                'end_source': 'next provider onset' if index + 1 < len(sentences) else 'full decoded PCM duration',
                'timing_kind': 'exclusive display schedule, not measured sentence endpoint',
            })
        audio = {
            'path': 'audio/narration.wav', 'sha256': sha(decoded),
            'pcm_sha256': hashlib.sha256(pcm).hexdigest(), 'pcm_frames': frames,
            'sample_rate': rate, 'channels': channels, 'sample_width_bytes': width,
            'duration': duration, 'source_mp3_path': 'audio/narration.mp3',
            'source_mp3_sha256': mp3_hash,
            'decode_method': 'ffmpeg_pcm_s16le_24000hz_mono_fresh_decode_full_stream',
        }
        dump(stage / 'speech_plan.json', plan)
        receipt = {
            'schema_version': 1, 'receipt_kind': 'edge_sentence_onset_display_schedule_1',
            'provider': 'edge_tts', 'voice': plan['voice'],
            'speech_sha256': original.speech_digest(plan),
            'formal_narration_sha256': digest(plan['narration']),
            'speech_plan_path': 'speech_plan.json', 'speech_plan_sha256': sha(stage / 'speech_plan.json'),
            'provider_events_path': 'audio/provider_events.json', 'provider_events_sha256': metadata_hash,
            'source': {'lesson_path': str(lesson_path), 'lesson_sha256': lesson_hash,
                       'raw_run_path': str(source), 'request_sha256': metadata['request_sha256'],
                       'accepted_adapter_path': str(ADAPTER_PATH), 'accepted_adapter_sha256': sha(ADAPTER_PATH),
                       'accepted_speech_text_sha256': sha(ADAPTER_PATH.parent.parent / 'rendering/speech_text.py'),
                       'projection_adapter_sha256': sha(Path(__file__).resolve())},
            'adapter_outcome': adapter_outcome or {'status': 'not_invoked_offline_cached_normalization'},
            'text_binding': {
                'mode': 'whitespace_to_ascii_comma_projection' if differences else 'exact',
                'projection_explicitly_enabled': allow_whitespace_comma_projection,
                'exact_text_equal': requested_text == provider_text,
                'requested_text': requested_text, 'provider_text': provider_text,
                'requested_text_sha256': hashlib.sha256(requested_text.encode()).hexdigest(),
                'provider_text_sha256': hashlib.sha256(provider_text.encode()).hexdigest(),
                'requested_codepoints': len(requested_text), 'provider_codepoints': len(provider_text),
                'differences': differences, 'all_codepoints_validated_in_place': True,
                'insertion_deletion_or_reordering_allowed': False,
                'lexical_or_symbol_substitution_allowed': False,
            },
            'provider_validation': {
                'exact_sentence_text_and_order': not differences,
                'sentence_order_preserved': True, 'per_sentence_equal_codepoint_length': True,
                'whitespace_to_comma_projection_used': bool(differences),
                'whitespace_normalization_used': False, 'lexical_normalization_used': False,
                'strictly_increasing_onsets': True, 'raw_intervals_within_pcm': True,
                'raw_intervals_nonoverlapping': not overlaps,
                'raw_overlap_evidence': overlaps, 'boundary_granularity': 'sentence',
                'paragraph_requests': 1, 'asr_used': False, 'manual_word_timing_used': False,
                'cached_request_revalidated': True, 'pcm_rederived_from_verified_mp3': True,
            },
            'display_policy': DISPLAY_POLICY, 'display_policy_sha256': digest(DISPLAY_POLICY),
            'audio': audio, 'raw_sentences': sentences, 'caption_windows': caption_windows,
        }
        dump(stage / 'voice_receipt.normalized.json', receipt)
        hashes = {
            'schema_version': 1,
            'raw_provider_events_sha256': metadata_hash, 'raw_mp3_sha256': mp3_hash,
            'decoded_wav_sha256': audio['sha256'], 'decoded_pcm_sha256': audio['pcm_sha256'],
            'speech_plan_sha256': receipt['speech_plan_sha256'],
            'normalized_receipt_sha256': sha(stage / 'voice_receipt.normalized.json'),
            'original_lesson_sha256': lesson_hash,
        }
        dump(stage / 'artifact_hashes.json', hashes)
        require(sha(lesson_path) == lesson_hash and sha(metadata_path) == metadata_hash and sha(mp3_path) == mp3_hash,
                'Lesson or raw provider evidence changed during normalization')
        for name in names:
            require(not (output / name).exists(), 'Output changed concurrently; refusing to overwrite evidence')
        for name in names:
            (stage / name).rename(output / name)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lesson', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--source', type=Path, help='existing raw adapter run; offline normalization only')
    mode.add_argument('--synthesize', action='store_true',
                      help='explicitly authorize the original adapter to transmit derived speech to Edge')
    parser.add_argument('--allow-whitespace-comma-projection', action='store_true',
                        help='offline only: permit and disclose equal-length whitespace to ASCII comma differences')
    args = parser.parse_args()
    if args.synthesize and args.allow_whitespace_comma_projection:
        parser.error('Whitespace/comma projection is offline-only; use --source with preserved provider artifacts')
    outcome = None
    source = args.source
    if args.synthesize:
        # The original adapter retains its raw receipt (or failure) under this subdirectory.
        source = args.output / 'provider_raw'
        require(not source.exists(), 'Use a fresh output directory for a new authorized synthesis')
        require(all(not (args.output / name).exists() for name in
                    ('audio', 'speech_plan.json', 'voice_receipt.normalized.json', 'artifact_hashes.json')),
                'Use a fresh output directory before synthesis')
        source.mkdir(parents=True)
        original = adapter()
        plan = original.plan_from_lesson(load(args.lesson))
        # Validate the configuration before any transmission, as in offline mode.
        require(isinstance(plan['voice'], dict) and 'text' not in plan['voice'],
                'Voice configuration cannot override the derived narration')
        try:
            asyncio.run(original.synthesize(plan, source))
        except ValueError as error:
            if str(error) != OVERLAP_ERROR:
                raise
            outcome = {'status': 'overlap_rejection', 'exception': 'ValueError', 'message': str(error),
                       'recovery': 'strict cached validation; raw intervals preserved; display schedule only'}
            dump(source / 'adapter_overlap_rejection.json', outcome)
        else:
            outcome = {'status': 'accepted_original_receipt', 'path': 'provider_raw/voice_receipt.json',
                       'sha256': sha(source / 'voice_receipt.json')}
    receipt = normalize(args.lesson, source, args.output, outcome, args.allow_whitespace_comma_projection)
    print(json.dumps({'status': 'validated_sentence_onset_display_schedule',
                      'receipt': str(args.output / 'voice_receipt.normalized.json'),
                      'duration': receipt['audio']['duration'],
                      'exact_text_equal': receipt['text_binding']['exact_text_equal'],
                      'disclosed_text_difference_count': len(receipt['text_binding']['differences']),
                      'raw_interval_overlap_count': len(receipt['provider_validation']['raw_overlap_evidence']),
                      'word_alignment': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
