"""Derive TTS input from the complete formal transcript and local span readings.

The formal transcript is the only authored prose. No whole-sentence spoken_text
override exists. Notation readings reuse the typed notation adapter; term readings
are limited to one alphabetic abbreviation/unit token, never a prose sentence.
"""
from pathlib import Path
import hashlib
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from spoken_notation import prepare_notation


def require(ok, message):
    if not ok:
        raise ValueError('Speech derivation: ' + message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def derive_sentence(record):
    formal = record.get('text')
    require(isinstance(formal, str) and formal.strip(), 'a complete formal text is required')
    require('spoken_text' not in record and 'display_text' not in record,
            'independent spoken_text/display_text is not an authored transcript; migrate to full text plus span adaptations')
    require(not any(ord(ch) < 32 for ch in formal), 'formal text must be a single paragraph without control characters')
    adaptations = record.get('speech_adaptations', [])
    require(isinstance(adaptations, list), 'speech_adaptations must be a list')
    pieces, mapping = [], []
    source_cursor = spoken_cursor = 0

    def append(start, end, reading, kind):
        nonlocal spoken_cursor
        if start == end:
            return
        require(bool(reading) and (kind == 'identity' or reading.strip()), 'deletion/empty speech transforms are forbidden')
        pieces.append(reading)
        mapping.append({'formal_range': [start, end],
                        'spoken_range': [spoken_cursor, spoken_cursor + len(reading)],
                        'kind': kind})
        spoken_cursor += len(reading)

    for adaptation in adaptations:
        span = adaptation.get('source_range')
        require(isinstance(span, list) and len(span) == 2 and
                all(isinstance(v, int) and not isinstance(v, bool) for v in span),
                'adaptation source_range must be two integer code-point offsets')
        start, end = span
        require(source_cursor <= start < end <= len(formal), 'overlapping, unordered or invalid adaptation range')
        source = formal[start:end]
        require(adaptation.get('source_text') == source, 'stale adaptation source text/range')
        append(source_cursor, start, formal[source_cursor:start], 'identity')
        kind = adaptation.get('kind')
        if kind == 'notation':
            require(set(adaptation) == {'source_range', 'source_text', 'kind', 'meaning'},
                    'notation adaptations only select an established typed reading')
            require(adaptation['meaning'] != 'literal', 'omit identity notation adaptations')
            reading = prepare_notation(source, adaptation['meaning'])['spoken_text']
        elif kind == 'term':
            require(set(adaptation) == {'source_range', 'source_text', 'kind', 'reading'},
                    'term adaptations need exactly a source token and its reading')
            require(re.fullmatch(r'[A-Za-z]{2,12}', source) is not None,
                    'term adaptation must be one alphabetic abbreviation/unit token, not prose or signed notation')
            # Do not allow a substring of a longer word to masquerade as a token.
            require((start == 0 or not formal[start-1].isascii() or not formal[start-1].isalpha()) and
                    (end == len(formal) or not formal[end].isascii() or not formal[end].isalpha()),
                    'term adaptation must cover a whole token')
            reading = adaptation.get('reading')
            require(isinstance(reading, str) and 0 < len(reading.strip()) <= 80 and
                    not any(ch in reading for ch in '.。;；!?！？\r\n'),
                    'term reading must be a nonempty local name, not a replacement sentence')
        else:
            raise ValueError('Speech derivation: unsupported adaptation kind')
        append(start, end, reading, kind)
        source_cursor = end
    append(source_cursor, len(formal), formal[source_cursor:], 'identity')
    spoken = ''.join(pieces)
    require(spoken.strip(), 'derived speech cannot be empty')
    return {'id': record['id'], 'sentence_id': record['id'], 'formal_text': formal,
            'formal_text_sha256': hashlib.sha256(formal.encode()).hexdigest(),
            'spoken_text': spoken, 'span_map': mapping,
            'adaptations_sha256': digest(adaptations)}


def build_speech_plan(narration, voice=None):
    require(isinstance(narration, list), 'narration must be a list')
    seen = set()
    beats = []
    for record in narration:
        nid = record.get('id')
        require(isinstance(nid, str) and nid and nid not in seen, 'missing/duplicate narration ID')
        seen.add(nid)
        beats.append(derive_sentence(record))
    return {'voice': voice, 'beats': beats}


def speech_identity(narration, voice=None):
    return digest(build_speech_plan(narration, voice))
