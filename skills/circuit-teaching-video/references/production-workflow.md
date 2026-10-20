# Single-source production and evidence authority

The authored lesson owns canonical formulas, visible text, assumptions, IDs, source references, narration intent and camera/attention decisions. The compiler derives measured geometry; the renderer consumes the frozen scene without rewriting source. Review reads the scene and actual artifact receipts, not a second manually maintained timing/formula table.

## Research → explain → render → verify

1. Inventory source claims and figures. Record source locators, rights, assumptions and evidence strength. Identify meaningful omissions rather than copying every decorative page element.
2. Organize a knowledge graph, local reasoning boards and a camera route. Use a sufficient circuit model and explain approximations at the point they matter. Preserve dependencies without turning all content into a rigid tree.
3. Author semantic objects and intent. Formula writing is followed by an explicit fully-visible reading window. Attention targets reference object IDs; no arbitrary pointer, zoom or chapter quota.
4. If speech is requested, map canonical display and spoken text to real provider/recording evidence. Cache keys include text, voice and rate; preserve actual PCM hashes and timings. Sentence evidence stays sentence evidence.
5. Compile. Validate IDs, capabilities, input/runtime/font fingerprints, graph cycles, layout boundaries, cumulative retention and declared read windows. Missing fields or unsupported capabilities stop production.
6. Render full preview and inspect actual visuals/audio. A full silent render can test timing/geometry, but cannot fulfill an audiovisual listening gate. Short native-density samples establish small-text/math clarity better than upscaled previews.
7. Encode the selected output profile. Verify exact decoded frame count, tail, complete decode and internal transitions. Bind the final review to the actual final media hash. Keep scientific, structural, pixel, listening, delivery and learning-effect findings separate.

## Current public implementation

`pipeline.py compile` binds one `circuit-lesson-1` JSON, selected fonts and runtime files. `pipeline.py render` checks that binding before rendering. It emits geometry/pointer/caption state for every encoded frame and validates exact decoded frames. Camera interpolation uses world coordinates once; captions stay screen-fixed. The example's seconds are authored animation timing, not measured narration.

Optional `voice_adapter.py` produces real sentence receipts from the same lesson's `narration` records. This release does not automatically retime every authored action from arbitrary provider events. Review and integrate measured timings into the authoritative lesson, then recompile. Do not copy the spoken transcript into a second edited source. The synthesis helper has not been live-provider tested in this release.

The generic `workflow.py`/`plan_knowledge.py` planning schema is an independent storyboard gate, not an automatic converter into production scene schema. An adapter that transforms planning artifacts must preserve IDs, source coverage and actual capabilities.

## Change invalidation

- Narration text, voice or rate: invalidate affected audio cache, timing, scene and downstream media/review.
- Font, notation, size or layout: remeasure all affected geometry, reveal groups, pointer clearance and final media.
- Source crop or PDF: reverify file hashes, crop geometry, rights and source fidelity.
- Encoder/profile: invalidate encoded-media evidence and final-file review, not necessarily canonical content.

A review document stating PASS is not an executed gate. Never fabricate a human watch/listen record or transform technical success into scientific or learning certification.
