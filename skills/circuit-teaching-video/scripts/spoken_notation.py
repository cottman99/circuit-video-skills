"""Small context-selected notation readings for the one-pass TTS input layer.

The caller supplies the established meaning; this helper never infers a model,
changes display text, synthesizes speech, or certifies pronunciation.
"""
import re

SUPERSCRIPT = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻', '0123456789+-')
SUBSCRIPT = str.maketrans('₀₁₂₃₄₅₆₇₈₉₊₋', '0123456789+-')
PRIME_WORDS = {1: '撇', 2: '双撇', 3: '三撇'}


def _signed(value):
    value = value.replace('−', '-')
    return ('负 ' + value[1:]) if value.startswith('-') else ('正 ' + value[1:]) if value.startswith('+') else value


def _prime(value):
    value = value.replace('″', '′′').replace('‴', '′′′')
    match = re.fullmatch(r"(.+?)(['′]{1,3})", value)
    return (match[1], len(match[2])) if match else (value, 0)


def prepare_notation(display_text, meaning='literal'):
    """Return a display-preserving, explicitly typed reading for one notation span.

    Supported meanings: literal, identifier, subscript, power, signed_quantity,
    derivative. Unknown/ambiguous semantics should remain literal for review.
    No global replacements or independent pronunciation dictionary are needed.
    """
    if not isinstance(display_text, str) or not display_text:
        raise ValueError('A nonempty notation span is required')
    value = display_text.strip()
    base, primes = _prime(value)
    if meaning == 'literal':
        spoken = display_text
    elif meaning == 'identifier':
        if not re.fullmatch(r'[A-Za-z]+[0-9]*', base):
            raise ValueError('Use the established index/power meaning or keep unfamiliar notation literal')
        spoken = base + (' ' + PRIME_WORDS[primes] if primes else '')
    elif meaning == 'derivative':
        if not primes or not re.fullmatch(r'[A-Za-z]+', base):
            raise ValueError('A derivative reading requires an explicitly defined primed variable')
        spoken = base + ' 的' + {1: '一', 2: '二', 3: '三'}[primes] + '阶导数'
    elif meaning in ('subscript', 'power'):
        marker = '_' if meaning == 'subscript' else r'\^'
        match = re.fullmatch(r'([A-Za-z]+)(?:' + marker + r'(?:\{([^{}]+)\}|([+−\-]?[A-Za-z0-9]+)))', base)
        if match:
            name, index = match[1], match[2] or match[3]
        else:
            chars = '₀₁₂₃₄₅₆₇₈₉₊₋' if meaning == 'subscript' else '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻'
            match = re.fullmatch(r'([A-Za-z]+)([' + chars + r']+)', base)
            if not match:
                raise ValueError('Notation does not match the explicitly selected index/power meaning')
            name, index = match[1], match[2].translate(SUBSCRIPT if meaning == 'subscript' else SUPERSCRIPT)
        if not re.fullmatch(r'[+−\-]?[A-Za-z0-9]+', index):
            raise ValueError('Compound index/exponent needs a context-written spoken phrase')
        if meaning == 'subscript':
            spoken = name + ' 下标 ' + _signed(index)
        else:
            spoken = name + (' 的平方' if index == '2' else ' 的立方' if index == '3' else ' 的 ' + _signed(index) + ' 次方')
        if primes:
            spoken += ' ' + PRIME_WORDS[primes]
    elif meaning == 'signed_quantity':
        if not re.fullmatch(r'[+−\-][A-Za-z0-9.]+(?:\s*[A-Za-z]+)?', value):
            raise ValueError('Signed quantity reading requires a simple explicit sign and quantity')
        spoken = _signed(value)
    else:
        raise ValueError('Unsupported notation meaning: ' + str(meaning))
    return {'display_text': display_text, 'spoken_text': spoken, 'meaning': meaning,
            'verification': 'prepared_text_only; actual pronunciation unverified'}
