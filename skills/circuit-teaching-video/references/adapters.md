# Optional adapters and exact integration boundaries

## Core world-canvas adapter

Input: `circuit-lesson-1` as shown in the original resistor-divider example. Compiler output: `circuit-compiled-scene-1`. Supported kinds: text, formula, rect, line and verified white-background PDF asset. Objects persist through the scene; camera visits can pan, zoom and return. Required capability names are checked. Captions remain in screen coordinates.

The compiler measures actual fonts/formulas, freezes geometry and hashes renderer code, registry and font files. The renderer rejects stale bindings. Width is a positive multiple of 32 for the current 16:9 encoder. Its output remains a technical preview until the requested visual/audio review has occurred.

## Local source PDF crops

Optional dependency: PyMuPDF; review its AGPL/commercial terms in `THIRD_PARTY_NOTICES.md` before use. No PDF is bundled.

A lesson can add `source_catalog` with `sources` and `assets` dictionaries. Source records include `id`, project-relative `path`, `sha256`, one-based `page`, `pdf_rotation` and `redistribution_basis`. Asset records include `source_id`, `crop_version`, normalized `[left, top, right, bottom]` crop and `white_matte_safe: true`. An object of kind `asset` references `asset_id`, authored bounds, `start`, `end` and reveal `duration`. Paths must stay inside the project directory.

The catalog rasterizer reuses the production source-PDF clipping implementation. It verifies source hashes and samples at target density. An embedded raster retains its original detail limit. `white_matte_safe` is an authored assertion that must be inspected: do not use this underlay path on photographs, colored backgrounds or meaningful white-filled symbols. Source rights are not established merely by writing a label.

## Optional speech

Install `edge-tts` only if that service fits the authorized task. It is a third-party client, not a guaranteed service contract. A lesson may add `voice: {name, rate}` and `narration: [{id, display_text, spoken_text, semantics_unchanged: true}]`. The same lesson remains the authoring source.

```sh
python scripts/voice_adapter.py /path/to/lesson.json --output /path/to/voice-output --synthesize
```

This explicit command sends spoken text and selected voice settings to the service accessed by edge-tts. There is no automatic call during planning, compilation, testing or core rendering. Confirm the user's authorization and service terms first. Credentials are not stored or requested by this repository.

The adapter keeps request hashes, actual provider sentence events, MP3/WAV/PCM identity and measured PCM duration. Every run regenerates a temporary 24 kHz mono 16-bit PCM WAV from the verified MP3, validates finite ordered sentence bounds against the decoded PCM, and only then replaces the output. A preexisting WAV is never trusted independently. It refuses stale cached text or mismatched boundary text/count instead of inventing timing. It does not promise sentence events will be returned by every provider version. It was not live-provider tested for this release.

Integration boundary: review the receipt, then place actual measured times into the authoritative lesson and recompile. The public pipeline does not automatically compile every semantic action from provider events, perform forced word alignment, synthesize pronunciations, or certify full listening review. `--audio` only validates duration and binds the supplied audio bytes; it does not prove subtitle or action synchronization.

## Planning and standalone audit helpers

The preserved `plan_knowledge.py`/`workflow.py` schema normalizes knowledge graphs, local boards and visits. It is a planning artifact, not the renderer schema. The semantic pointer/video decision/media helpers retain their own audit formats; they are available for explicit integration, not falsely presented as automatically executed by the main pipeline.

Unsupported features remain explicit gaps: automatic source-lecture coverage extraction, unrestricted model/PDK simulation, arbitrary image matte inference, automatic optimal layout, provider-independent action alignment, and independent pedagogical certification.
