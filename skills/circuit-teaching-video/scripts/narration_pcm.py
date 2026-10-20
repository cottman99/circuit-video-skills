#!/usr/bin/env python3
"""Offline TTS completeness evidence and bounded-memory PCM assembly; no service calls."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import wave

MAX_CHUNK_BYTES = 1024 * 1024


def scan_pcm(path, consume=None, *, chunk_frames=65536):
    """Read actual PCM bytes, not just the WAV header; memory is bounded per chunk."""
    if type(chunk_frames) is not int or chunk_frames <= 0:
        raise ValueError('chunk_frames must be a positive integer')
    digest = hashlib.sha256()
    with wave.open(str(path), 'rb') as source:
        channels, width, rate, frames, compression, _ = source.getparams()
        if compression != 'NONE' or not frames:
            raise ValueError('Expected nonempty uncompressed PCM WAV')
        frame_bytes = channels * width
        bounded_frames = min(chunk_frames, max(1, MAX_CHUNK_BYTES // frame_bytes))
        total = 0
        while block := source.readframes(bounded_frames):
            if len(block) % frame_bytes:
                raise ValueError('Incomplete PCM sample frame')
            total += len(block)
            digest.update(block)
            if consume is not None:
                consume(block)
        if total != frames * frame_bytes:
            raise ValueError('PCM data shorter than declared WAV length')
    return {'channels': channels, 'sample_width': width, 'sample_rate': rate,
            'frames': frames, 'duration_s': frames / rate, 'pcm_sha256': digest.hexdigest()}


def audit_narration(text, sentences, pcm, *, minimum_duration_s):
    """Metadata coverage and measured-duration sanity, never proof of spoken content."""
    minimum = Fraction(str(minimum_duration_s))
    if isinstance(minimum_duration_s, bool) or minimum < 0:
        raise ValueError('A nonnegative, project-chosen duration floor is required')
    errors = []
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Nonempty requested text required')
    valid = (isinstance(sentences, list) and bool(sentences) and
             all(isinstance(row, dict) and isinstance(row.get('text'), str) and
                 row['text'].strip() for row in sentences))
    normalize = lambda value: re.sub(r'\s+', '', value)
    covered = valid and normalize(''.join(row['text'] for row in sentences)) == normalize(text)
    if not valid:
        errors.append('Nonempty provider sentence transcript required')
    if not covered:
        errors.append('Provider transcript does not exactly cover requested text after whitespace removal')
    measured = scan_pcm(pcm)
    if Fraction(measured['frames'], measured['sample_rate']) < minimum:
        errors.append('Measured PCM is shorter than the project-chosen duration floor')
    return {'passed': not errors, 'errors': errors, 'pcm': measured,
            'minimum_duration_s': float(minimum), 'normalized_transcript_exact': bool(covered),
            'scope': 'Provider metadata coverage and PCM duration only; no ASR, listening, alignment or naturalness certification'}


def assemble_pcm(parts, output, *, chunk_frames=65536):
    """Stream cached PCM and integer-frame pauses to a NEW WAV, without float arrays."""
    if not isinstance(parts, list) or not parts:
        raise ValueError('Nonempty list of {pcm, pause_s} records required')
    prepared = []
    format_ = None
    total_frames = 0
    for part in parts:
        info = scan_pcm(part['pcm'], chunk_frames=chunk_frames)
        current = tuple(info[key] for key in ('channels', 'sample_width', 'sample_rate'))
        if format_ is not None and current != format_:
            raise ValueError('PCM formats differ; explicitly convert inputs before assembly')
        format_ = current
        pause = Fraction(str(part.get('pause_s', 0)))
        if isinstance(part.get('pause_s'), bool) or pause < 0:
            raise ValueError('pause_s must be finite and nonnegative')
        pause_frames = round(pause * info['sample_rate'])
        prepared.append((part, info, pause_frames))
        total_frames += info['frames'] + pause_frames
    channels, width, rate = format_
    frame_bytes = channels * width
    if total_frames * frame_bytes > 0xFFFFFFFF - 36:
        raise ValueError('Master exceeds WAV RIFF size limit; split it or use a suitable container')
    timeline = []
    cursor = 0
    # Exclusive creation prevents an accidental overwrite of cached or released audio.
    with Path(output).open('xb') as target, wave.open(target, 'wb') as master:
        master.setnchannels(channels); master.setsampwidth(width); master.setframerate(rate)
        master.setnframes(total_frames)
        bounded_frames = min(chunk_frames, max(1, MAX_CHUNK_BYTES // frame_bytes))
        for part, expected, pause_frames in prepared:
            actual = scan_pcm(part['pcm'], master.writeframesraw, chunk_frames=chunk_frames)
            if actual != expected:
                raise ValueError('Input PCM changed during assembly; output is incomplete/untrusted')
            audio_end = cursor + actual['frames']
            end = audio_end + pause_frames
            remaining = pause_frames
            # Allocate only when needed; a large channel count must not multiply
            # the frame-count setting into an unbounded silence buffer.
            silence_frames = min(remaining, bounded_frames)
            silence = (b'\x80' if width == 1 else b'\0' * width) * channels * silence_frames
            while remaining:
                count = min(remaining, silence_frames)
                master.writeframesraw(silence[:count * frame_bytes]); remaining -= count
            timeline.append({'pcm': str(part['pcm']), 'start_frame': cursor,
                             'audio_end_frame': audio_end, 'end_frame': end})
            cursor = end
    return {'pcm': scan_pcm(output, chunk_frames=chunk_frames), 'paragraphs': timeline,
            'scope': 'Byte-preserving PCM concatenation with quantized pauses; no normalization or content review'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    audit = sub.add_parser('audit')
    audit.add_argument('--text', required=True, help='UTF-8 requested narration text')
    audit.add_argument('--sentences', required=True, help='JSON list of provider records with text')
    audit.add_argument('--pcm', required=True)
    audit.add_argument('--minimum-duration-s', required=True, type=float)
    merge = sub.add_parser('assemble')
    merge.add_argument('--parts', required=True, help='JSON list; PCM paths relative to this file')
    merge.add_argument('--output', required=True, help='New WAV path; never overwrite')
    args = parser.parse_args()
    try:
        if args.command == 'audit':
            report = audit_narration(Path(args.text).read_text(encoding='utf-8'),
                json.loads(Path(args.sentences).read_text(encoding='utf-8')), args.pcm,
                minimum_duration_s=args.minimum_duration_s)
        else:
            path = Path(args.parts).resolve()
            parts = json.loads(path.read_text(encoding='utf-8'))
            parts = [{**part, 'pcm': path.parent / part['pcm']} for part in parts]
            report = assemble_pcm(parts, args.output)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(not report.get('passed', True))
    except (OSError, ValueError, TypeError, KeyError, wave.Error) as error:
        parser.exit(1, str(error) + '\n')
