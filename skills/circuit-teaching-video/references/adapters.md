# Optional adapters and exact integration boundaries

## Default five-node production adapter

For raw lecture-to-film work use `scripts/course_video.py` and [its contract](../authoring/CONTRACT.md). It prepares complete selected pages, preserves a fresh native author's single formal master, derives speech and full captions, and compiles actual provider evidence into the existing renderer. CourseProject keeps source, lesson, timeline and build evidence together. The old routes below remain optional/lower-level, not additional mandatory stages.

The Edge-specific `scripts/edge_display.py` revalidates raw request/events/MP3 and fresh PCM, then uses strictly increasing sentence onsets for exclusive display windows. Raw interval overlaps are retained, not falsely called nonoverlapping acoustic measurements. The final display window ends at the full measured PCM duration. Explicit equal-length whitespace-to-ASCII-comma projection is disclosed character by character; lexical changes, ambiguous/missing/additional events and reordered mappings reject. No exact word alignment, universal provider behavior or spoken-content certification is implied. A transport may split a sentence at a request-byte boundary; the current route stops instead of fabricating events.

Only `course_video.py synthesize --allow-network` or an explicit standalone `--synthesize` command sends derived narration to Edge. Verify applicable authorization first. Offline `bind-voice` never calls TTS. Preserve complete returned raw evidence on adapter failure and use the narrow offline path if valid, rather than repeating the external call. Layout-only rework reuses validated audio and invalidates media/reviews. No mandatory user listening step is imposed.

PDF preparation requires external PyMuPDF. Keep projects outside the public checkout: they contain original source bytes, page images/text, audio and extracted installed fonts. Current basic text extraction can miss complex layouts; use original-page evidence for the affected item. An external replacement parser must preserve original source hashes, full physical scope, reading order, block types/boxes, text/math, figure references and explicit defects. It must not convert OCR into a topology claim. The [optional MinerU 4.0.12 basic adapter](external-parser.md) writes a separate extraction SourcePackage with explicit original source base and project/input hashes. Its external package/models are not bundled or auto-installed. The author uses that exact sidecar plus original images; it never becomes another master or a scientific certificate.

The local `run_workflow.py` adapter accepts `circuit-content-package-1`, preserves its model/object IDs, and generates `circuit-lesson-1` only after its synthetic sentence-evidence timeline is SAT. Read [executable workflow](executable-workflow.md). This narrow adapter is not a generic converter for the independent planning schema and does not accept live provider events.

## Core world-canvas adapter

Input: `circuit-lesson-1` as shown in the original resistor-divider example. Compiler output: `circuit-compiled-scene-1`. Supported kinds: text, formula, rect, line and verified white-background PDF asset. Objects persist through the scene; camera visits can pan, zoom and return. Required capability names are checked. Captions remain in screen coordinates and derive only from the complete formal manuscript. See the [caption/voice source contract](caption-workflow.md) for the authored schema and migration from legacy independent text fields.

The compiler measures actual fonts/formulas, freezes geometry and hashes renderer code, registry and font files. The renderer rejects stale bindings. Width is a positive multiple of 32 for the current 16:9 encoder. Its output remains a technical preview until the requested visual/audio review has occurred.

## Local source PDF crops

Optional dependency: PyMuPDF; review its AGPL/commercial terms in `THIRD_PARTY_NOTICES.md` before use. No PDF is bundled.

A lesson can add `source_catalog` with `sources` and `assets` dictionaries. Source records include `id`, project-relative `path`, `sha256`, one-based `page`, `pdf_rotation` and `redistribution_basis`. Asset records include `source_id`, `crop_version`, normalized `[left, top, right, bottom]` crop and `white_matte_safe: true`. An object of kind `asset` references `asset_id`, authored bounds, `start`, `end` and reveal `duration`. Paths must stay inside the project directory.

The catalog rasterizer reuses the production source-PDF clipping implementation. It verifies source hashes and samples at target density. An embedded raster retains its original detail limit. `white_matte_safe` is an authored assertion that must be inspected: do not use this underlay path on photographs, colored backgrounds or meaningful white-filled symbols. Source rights are not established merely by writing a label.

## Optional speech

Install `edge-tts` only if that service fits the authorized task. It is a third-party client, not a guaranteed service contract. A lesson may add `voice: {name, rate}`. Its complete `narration: [{id, text, speech_adaptations?}]` is the same formal master used by captions. The adapter deterministically derives spoken input and source↔spoken span maps; it rejects independent `spoken_text`/`display_text` overrides. Timed rendering additionally requires narration and caption `start`/`end` windows.

```sh
python scripts/voice_adapter.py /path/to/lesson.json --output /path/to/voice-output --synthesize
```

This explicit command sends spoken text and selected voice settings to the service accessed by edge-tts. There is no automatic call during planning, compilation, testing or core rendering. Confirm the user's authorization and service terms first. Credentials are not stored or requested by this repository.

The adapter keeps request hashes, actual provider sentence events, MP3/WAV/PCM identity and measured PCM duration. Every run regenerates a temporary 24 kHz mono 16-bit PCM WAV from the verified MP3, validates finite ordered sentence bounds against the decoded PCM, and only then replaces the output. A preexisting WAV is never trusted independently. It refuses stale cached text or mismatched boundary text/count instead of inventing timing. It does not promise sentence events will be returned by every provider version. Overlapping provider sentence events are explicitly unsupported and rejected; this adapter does not silently trim them or call estimated boundaries measured. Its strict validation remains unchanged; the five-node composition above has separate real-provider evidence, not a guarantee for all provider versions.

Lower-level direct-route boundary: review the receipt, then place actual measured times into the authoritative lesson and recompile. The default five-node route performs this sentence-level adaptation automatically. The public pipeline does not automatically compile every semantic action from provider events, perform forced word alignment, synthesize pronunciations, or certify full listening review. `bind-audio` explicitly binds supplied audio bytes to formal text, derived speech, voice and timing identities; `--audio` rejects missing or stale bindings and checks duration. This prevents stale version reuse, but does not prove acoustic transcript agreement, subtitle synchronization or action synchronization.

## Planning and standalone audit helpers

The preserved `plan_knowledge.py`/`workflow.py` schema normalizes knowledge graphs, local boards and visits. It is a planning artifact, not the renderer schema. The semantic pointer/video decision/media helpers retain their own audit formats; they are available for explicit integration, not falsely presented as automatically executed by the main pipeline.

Unsupported features remain explicit gaps: automatic source-lecture coverage extraction, unrestricted model/PDK simulation, arbitrary image matte inference, automatic optimal layout, provider-independent action alignment, and independent pedagogical certification.
