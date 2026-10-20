#!/usr/bin/env python3
"""Read actual encoded streams/frames; no network, TTS, rendering or quality claim."""
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import wave
sys.dont_write_bytecode = True
from validation_common import referenced_file
from narration_pcm import scan_pcm


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(args):
    return subprocess.run(args, capture_output=True, check=True).stdout


def positive_fraction(value):
    if isinstance(value, bool):
        raise ValueError('Expected positive finite number')
    result = Fraction(str(value))
    if result <= 0:
        raise ValueError('Expected positive finite number')
    return result


def pcm_duration(path):
    measured = scan_pcm(path)
    return Fraction(measured['frames'], measured['sample_rate'])


def frame_rgb(path, index, roi, *, reference=False):
    # Select the actual video explicitly; a larger attached cover is not the scene.
    probe = json.loads(run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                            '-show_streams', '-of', 'json', str(path)]))
    streams = [s for s in probe['streams'] if s['codec_type'] == 'video' and
               not s.get('disposition', {}).get('attached_pic')]
    if len(streams) != 1:
        raise ValueError('Exactly one non-attached video/reference stream required')
    stream_index = streams[0]['index']
    x, y, w, h = roi
    prefix = [] if reference else [f'select=eq(n\\,{index})']
    filters = ','.join(prefix + [f'crop={w}:{h}:{x}:{y}', 'format=rgb24'])
    raw = run(['ffmpeg', '-v', 'error', '-xerror', '-protocol_whitelist', 'file,pipe', '-i', str(path),
               '-map', f'0:{stream_index}', '-vf', filters, '-frames:v', '1', '-threads', '1', '-f', 'rawvideo', '-'])
    if len(raw) != w * h * 3:
        raise ValueError('Requested encoded/reference frame or ROI did not decode')
    return raw


def inspect(path, duration, fps='12/1', *, max_bytes=None, full_decode=True):
    """CFR checker. Duration should come from final PCM, not format.duration."""
    expected = positive_fraction(duration)
    rate = positive_fraction(fps)
    count = math.ceil(expected * rate)
    result = {'passed': False, 'checks': {}, 'errors': [],
              'expected_PCM_s': float(expected), 'fps': str(rate), 'expected_frames': count,
              'scope': 'Encoded stream/frame integrity only; not internal alignment or perceptual review'}
    try:
        path = Path(path)
        result['sha256'] = sha256(path)
        probe = json.loads(run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-count_frames', '-show_streams',
                                '-show_format', '-of', 'json', str(path)]))
        videos = [s for s in probe['streams'] if s['codec_type'] == 'video' and
                  not s.get('disposition', {}).get('attached_pic')]
        audios = [s for s in probe['streams'] if s['codec_type'] == 'audio']
        if len(videos) != 1 or len(audios) != 1:
            raise ValueError('Exactly one video stream and one audio stream required')
        v, a = videos[0], audios[0]
        vd, ad = Fraction(v['duration']), Fraction(a['duration'])
        actual_count = int(v['nb_read_frames'])
        result.update(video_s=float(vd), audio_s=float(ad), video_frames=actual_count,
                      container_s=float(probe['format']['duration']), bytes=path.stat().st_size)
        checks = result['checks']
        checks['video_duration_matches_frame_grid'] = abs(vd - Fraction(count, 1) / rate) <= Fraction(1, 10000)
        # AAC/other compressed audio timestamps can be quantized to a sample or packet.
        checks['audio_matches_PCM_duration'] = abs(ad - expected) <= Fraction(1, 20)
        checks['exact_decoded_frame_count'] = actual_count == count
        checks['header_frame_count_matches_decode'] = ('nb_frames' not in v or int(v['nb_frames']) == actual_count)
        checks['fixed_frame_rate'] = Fraction(v['avg_frame_rate']) == rate and Fraction(v['r_frame_rate']) == rate
        checks['streams_start_at_zero'] = all(abs(Fraction(s.get('start_time', '0'))) <= Fraction(1, 10000) for s in (v, a))
        # Seek into the expected final displayed frame, not merely near the file's actual end.
        tail_at = float(max(Fraction(0), Fraction(count - 1, 1) / rate - Fraction(1, 1000000)))
        tail = run(['ffmpeg', '-v', 'error', '-xerror', '-protocol_whitelist', 'file,pipe', '-ss', f'{tail_at:.9f}', '-i', str(path),
                    '-map', f'0:{v["index"]}', '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-threads', '1', '-'])
        checks['expected_tail_frame_decodes'] = tail.startswith(b'\x89PNG\r\n\x1a\n')
        result['tail_sample_s'] = tail_at
        if max_bytes is not None:
            if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
                raise ValueError('max_bytes must be a positive integer')
            checks['within_delivery_size_limit'] = path.stat().st_size <= max_bytes
        if full_decode:
            run(['ffmpeg', '-v', 'error', '-xerror', '-protocol_whitelist', 'file,pipe', '-i', str(path), '-map', f'0:{v["index"]}',
                 '-map', f'0:{a["index"]}', '-f', 'null', '-'])
            checks['full_decode'] = True
        result['passed'] = all(checks.values())
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError, subprocess.CalledProcessError) as exc:
        result['errors'].append(str(exc))
    return result


def check_boundaries(path, boundaries, fps, duration, base, root):
    """Compare decoded samples on BOTH sides of each declared internal transition.

    References are lossless PNGs of expected rendered states. ROI must cover the
    changing object, not an unchanged corner. Geometry/meaning require review.
    """
    errors, observations = [], []
    rate, length = positive_fraction(fps), positive_fraction(duration)
    if not isinstance(boundaries, list):
        return ['boundaries must be a list'], observations
    seen = set()
    for b in boundaries:
        try:
            name = b['id']
            if not isinstance(name, str) or not name or name in seen:
                raise ValueError('unique boundary id required')
            seen.add(name)
            at = positive_fraction(b['time_s'])
            if at >= length:
                raise ValueError('boundary must be internal')
            # One frame of sampling margin accommodates CFR time quantization.
            before_i, after_i = math.floor(at * rate) - 1, math.ceil(at * rate) + 1
            if before_i < 0 or after_i >= math.ceil(length * rate):
                raise ValueError('boundary too close to end; explicitly review edge transition')
            decoded, refs = [], []
            tolerance = float(b.get('max_mean_error', 12))
            if not math.isfinite(tolerance) or not 0 <= tolerance <= 20:
                raise ValueError('pixel tolerance must be between 0 and 20 out of 255')
            roi = b['roi']
            if not isinstance(roi, list) or len(roi) != 4 or any(type(n) is not int for n in roi) or min(roi[:2]) < 0 or min(roi[2:]) <= 0:
                raise ValueError('ROI must be integer x,y,width,height')
            for side, index in [('before', before_i), ('after', after_i)]:
                ref = b[side]
                ref_path = referenced_file(base, ref['path'], root, errors, name + ' reference')
                if ref_path is None:
                    raise ValueError('missing boundary reference')
                if sha256(ref_path) != ref['sha256']:
                    raise ValueError('boundary reference hash mismatch')
                expected = frame_rgb(ref_path, 0, roi, reference=True)
                actual = frame_rgb(path, index, roi)
                mae = sum(abs(x - y) for x, y in zip(actual, expected)) / len(expected)
                passed = mae <= tolerance
                observations.append({'id': name, 'side': side, 'frame': index, 'mean_error': mae, 'passed': passed})
                if not passed:
                    errors.append(f'{name}: encoded {side} state differs from reference')
                decoded.append(actual); refs.append(expected)
            reference_change = sum(abs(x-y) for x,y in zip(*refs)) / len(refs[0])
            transition = b.get('transition', 'changed')
            if transition == 'changed':
                # A nonchanging corner cannot establish a declared visual transition.
                if reference_change <= 2 * tolerance:
                    errors.append(f'{name}: reference ROI does not distinguish the two states above tolerance')
            elif transition == 'unchanged':
                # Adjacent clauses can retain one focus; never force artificial flicker.
                if not isinstance(b.get('reason'), str) or not b['reason'].strip():
                    errors.append(f'{name}: unchanged-state boundary needs a concrete reason')
                if reference_change > tolerance:
                    errors.append(f'{name}: unchanged-state reference images disagree')
            else:
                errors.append(f'{name}: transition must be changed or unchanged')
        except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError, subprocess.CalledProcessError) as exc:
            errors.append(f'boundary: {exc}')
    return errors, observations


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('media'); g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--pcm'); g.add_argument('--duration', help='Diagnostic only; final delivery requires hashed PCM')
    ap.add_argument('--fps', default='12/1'); ap.add_argument('--max-bytes', type=int)
    args = ap.parse_args()
    try:
        result = inspect(args.media, pcm_duration(args.pcm) if args.pcm else args.duration,
                         args.fps, max_bytes=args.max_bytes)
    except (OSError, ValueError, wave.Error) as exc:
        result = {'passed': False, 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2)); sys.exit(not result['passed'])
