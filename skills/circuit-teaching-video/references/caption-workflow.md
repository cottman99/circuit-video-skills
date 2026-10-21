# One full formal master, two derived presentations

The subtitle lane is a complete accessibility transcript, not a place for prompts,
board summaries or teaching keywords. Prevent the mistake at authoring time:

1. Author the **complete formal manuscript** in `narration[].text`, with a stable
   `id`. Keep normal written symbols, units, indices, primes and conditions.
2. Captions contain only `id`, `narration_id`, `source_range: [start, end)`,
   `start` and `end`. Offsets count Python Unicode code points. They contain **no
   text field**. The compiler slices the formal master and only wraps that text.
3. The voice adapter derives `spoken_text` from that same master. Optional local
   `speech_adaptations` reference an exact source span and `source_text`; the
   source check rejects shifted/stale overrides. They never alter the captions.
4. Put short labels and summaries in `objects` of `kind: "text"` on the board;
   put frames/arrows in `teacher_actions`. Those routes cannot supply subtitles.
5. Resolve measured voice timings into narration/cue windows, explicitly bind the
   chosen audio version, then compile and render. A transcript, pronunciation,
   voice/rate or timing change invalidates the previous binding.

## Minimal authored shape

```json
{
  "narration": [{
    "id": "s1",
    "text": "Keep x² explicit.",
    "start": 0,
    "end": 2,
    "speech_adaptations": [{
      "source_range": [5, 7],
      "source_text": "x²",
      "kind": "notation",
      "meaning": "power"
    }]
  }],
  "captions": [{
    "id": "c1",
    "narration_id": "s1",
    "source_range": [0, 17],
    "start": 0,
    "end": 2
  }]
}
```

This illustrates fields, not a complete renderer lesson. The full example lives
in `../examples/resistor-divider/lesson.json`. The caption reads `Keep x² explicit.`;
the derived voice input reads `Keep x 的平方 explicit.`. The formal↔spoken
code-point span map is emitted with the speech plan/receipt. It is a text mapping,
**not a word-timing alignment**.

`notation` adaptations reuse the existing typed `spoken_notation` readings:
identifier, subscript, power, signed_quantity and derivative. Each preserves its
selected notation meaning rather than dropping a prime, sign or index.
`term` adaptations have `reading` instead of `meaning`; they are limited to one
whole ASCII alphabetic abbreviation/unit token (2–12 letters) and a nonempty
local name. They cannot replace an entire sentence, signed expression or clause.
For example, a source-specific `Si` span may read `silicon` without globally
replacing `SI` or a mathematical subscript. The author remains responsible for
the expansion's scientific meaning. Unsupported compound notation fails;
there is no unrestricted prose-rewrite escape hatch.

## Timing, audio and version identity

Caption spans must partition every formal narration record exactly once, in order.
Cue intervals must partition its declared speech window without gaps or overlaps.
Silence between narration records need not have captions. Long sentences must be
split into consecutive reference spans, not shortened to fit two lines.

For an already obtained recording, explicitly associate the complete transcript,
derived pronunciation plan, voice configuration, timing and exact audio bytes:

```sh
python skills/circuit-teaching-video/scripts/pipeline.py bind-audio lesson.json --audio recording.wav --output lesson-bound.json
python skills/circuit-teaching-video/scripts/pipeline.py compile lesson-bound.json --output output/scene.json
python skills/circuit-teaching-video/scripts/pipeline.py render output/scene.json --output output/video --video --audio recording.wav
```

Continue from `lesson-bound.json` as the new authoritative version, not from two
independently edited copies. `bind-audio` records the explicitly selected pair; it
does **not** listen, verify the spoken transcript, or invent alignment. Integrate
actual recording/provider evidence before binding. The provider adapter supplies
sentence events, not arbitrary internal cue/word times. Internal estimated splits
must be labeled as estimates in the project's evidence, never measured words.

The scene and media manifest record formal-text coverage and the binding. Changing
formal text, an adaptation, voice/rate, a cue offset/window or audio bytes makes the
old binding fail. Fonts/runtime changes require recompilation. Technical hashes
prove identity, not correct pronunciation or factual content.

## Migration from independent display/spoken fields

Legacy `captions[].display_text` and independently authored `spoken_text` are
rejected, even if a boolean claims unchanged semantics. Recover the actual full
formal manuscript first; **do not rename a summary field to `text`**. Preserve all
clauses and conditions. Represent only proven pronunciation differences through
local source-span adaptations. If the formal source or mapping is uncertain,
stop that migration rather than reverse-normalizing the whole voice transcript.

Regression tests protect these boundaries, but the primary prevention is the
data flow: captions have no independent content-authoring route.
