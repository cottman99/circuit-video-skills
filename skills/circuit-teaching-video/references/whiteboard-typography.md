# Whiteboard typography, safe zones and layering

Use real font faces and measure with the same face used to draw. The portable Latin example uses DejaVu Sans Regular and authentic Bold from Matplotlib. For Chinese production choose Noto Sans CJK SC Regular and Medium through `CIRCUIT_FONT_REGULAR` and `CIRCUIT_FONT_HEADING`. Missing glyphs or mismatched families fail; there is no faux bold or invisible fallback. Source fonts remain separate dependencies.

The current 1920×1080 logical profile keeps titles left, assumptions/source notes in a top-right header, reasoning in the body and captions in a screen-fixed bottom internal strip. Output scaling changes density, not logical layout. The world fills the screen; it is not shrunk to create an external subtitle margin. Local source-note and body-note floors differ. Explicit project requirements may call for another profile, which requires a supported adapter and fresh checks.

Font or weight changes require remeasurement. Wrapping preserves exact text. Overflow is rejected, not silently shrunk below readable floors. Keep font roles separate from mathematical identities and attention styling. Do not dim or weaken an unchanged teacher pointer as a side effect of typography cleanup.

Layer order is whiteboard → pale optional attention underlay → original content ink → glyph-safe frame/glow/pointer/arrow → captions and shell. The exact-white matte retains every nonwhite pixel, including antialiasing. It is not a universal background remover: photographs, colored backgrounds or meaningful white fills need an explicit authored matte or another adapter.

Inspect early and accumulated frames from each board at native density. Check subscripts, negative signs, source references, small assumptions, pointer clearance and caption placement. A miniaturized final overview preserves the map but does not establish full local reading size. A static image review is not motion or listening review.
