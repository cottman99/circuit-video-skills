"""Retained layout-only phrase wrapping from the verified TIA transfer adapter.

Never edits display/spoken text, splits cues, synthesizes audio, or invents timing.
"""
import logical_scene as native

def subtitle_rows(text):
    rows=native.wrapped(text,34,1780)
    punctuation='，。；：！？、,.!?;: '
    if len(rows)>1 and any(len(row.strip(punctuation))<=1 for row in rows):
        font=native.font(34)
        cuts=[i+1 for i,c in enumerate(text[:-1]) if c in '，；：,;:']
        candidates=[(text[:i],text[i:]) for i in cuts if font.getlength(text[:i])<=1780 and font.getlength(text[i:])<=1780]
        if not candidates:raise ValueError('Subtitle has an orphan line; reauthor its phrase layout')
        rows=list(min(candidates,key=lambda r:abs(font.getlength(r[0])-font.getlength(r[1]))))
    if not all(row.strip(punctuation) for row in rows):raise ValueError('Punctuation-only subtitle line')
    if len(rows)>2:raise ValueError('Subtitle exceeds two native-layout lines')
    if ''.join(rows)!=text:raise ValueError('Subtitle layout altered exact display text')
    return rows
