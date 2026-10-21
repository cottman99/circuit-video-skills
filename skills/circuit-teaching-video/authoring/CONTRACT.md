# Minimal native-author contract

The CLI prepares a source packet for a fresh native AI author; it does not author an unseen lesson by loading golden JSON. Inputs are the original PDF, complete selected physical-page scope, uniform brief, full extracted page text and page images. If an optional external parser sidecar is supplied, the host gives its exact path/hash and the author uses its reading order/text/math/figure locators with source_base; retain that extraction identity with the response. The original pages stay authoritative. The author actually inspects every selected image. An independent evaluator chooses the next source only after reusable code/prompt freeze.

## Presentation mode

The default is original-slide. Read [ORIGINAL_SLIDE.md](ORIGINAL_SLIDE.md) for its source_objects, reveal owners/focus children and original-pixel layout. Those fields replace the legacy source_crops/formula_objects/action/layout details below; common manuscript, source, coverage and voice contracts still apply. prepare records the chosen mode and original-slide projects reject whiteboard plans. Select `prepare --presentation whiteboard` explicitly for the legacy reflow route.

## One author response

SCHEMA_EXAMPLES.md documents the shape, using non-runnable placeholders. One AUTHOR_RESPONSE.json contains title, scope_statement, scope_source_sha256, selected_pages, formal_master, scenes, coverage, unresolved_issues, layout and pronunciation. Source hash and complete page list bind the declared scope.

- formal_master records have id, text, source_pages and scene_id. Concatenated scene sentence_ids must exactly equal the ordered master IDs. There is no second editable caption/narration track.
- In the explicit legacy whiteboard mode, scenes contain id, title, sentence_ids, source_pages, source_crops, formula_objects and teaching_actions. Crop boxes are whole-page normalized [left,top,right,bottom]. Each crop explicitly declares white_matte_safe:true only when inspected white-backed line art/notation is safe for that bounded adapter; photos or meaningful opaque-white content need another alpha adapter, not an assumption. Formulas contain id, latex, source_page, meaning and reveal_sentence_id. Preserve unsupported notation as a source crop.
- In the explicit legacy whiteboard mode, teaching_actions use only {sentence_id,target_id,action:"frame"}. Formula reveal/pointer is generic renderer behavior. Sequence comes from scene/sentence order, not another authored timing structure. Keep one frame cue per sentence and only a few reveals per measured interval; overlap or insufficient reading time is rejected, not truncated.
- coverage rows contain source_page, source_item, formal_sentence_ids and visual_object_ids. source_item identifies precise location/content, such as a quoted line or figure region with its material labels. These rows inventory all substantive source content and establish exact sentence/source links, not merely page presence. Scene and sentence IDs must be unique; crop/formula IDs are local within their scene. Coverage visual_object_ids must be scene-qualified as "scene_id.object_id", for example "scene_001.crop_001". Layout objects, label targets and teaching-action target_id remain scene-local, for example "crop_001".
- unresolved_issues disclose source_page, severity (info/warning/blocker), description and handling. Declared blocking issues must not be silently accepted.

Legacy whiteboard layout has schema="course-layout-1", measurement_policy and scenes keyed by scene ID. Each scene's objects map crop IDs to [x,y,width,height] and formula IDs to [x,y,font_size] in canvas pixels. Optional labels use {id,target,text,xy,size} and source-supported text. Do not emit latex_compatibility or formula_parts. Layout targets use local scene object IDs. Coordinates are project data, never per-lecture code; board gaps/camera panning use frozen generic configuration.

The compiler must measure actual rendered objects and complete captions, not trust declared boxes. Reject overflow, prohibited collisions, distorted crops and unreadable text. Readability thresholds/safe regions belong to shared configuration. For the legacy route, reflow/split authored scenes instead of ellipsizing captions or hiding source labels.

## Local voice API

The optional voice object contains exactly name and rate, both nonempty strings. Omit it to use the frozen defaults. No text or other transport/request fields are allowed; narration is derived only from the formal master and local pronunciation adaptations. Invalid voice configuration is rejected at ingest before transmission.

pronunciation maps each sentence ID to an ordered list inserted as speech_adaptations for the existing speech_text adapter:

- term: exactly kind="term", source_range=[start,end], source_text, reading.
- notation: exactly kind="notation", source_range, source_text, meaning, selecting an established context-supported adapter reading.

Offsets are zero-based/end-exclusive Unicode code points, ordered, non-overlapping and exact-matching. Term spans cover a whole 2–12 letter ASCII abbreviation/unit token, not prose. Omit identity adaptations. Do not use spoken_text inside adaptations. speech_text derives formal_text_sha256, the complete spoken string and the formal/spoken span map; no input hash is required inside spans. Captions retain complete unchanged master text. The existing notation adapter has limited language/notation coverage; report unsupported readings rather than inventing a second script.

## Evidence and revisions

Archive the exact first native response before ingestion. A separate native source comparison checks all selected page images/full text against coverage, master, crops and formulas. Mechanical reference checks cannot prove the inventory is complete. Preserve the review report with exact artifact hashes; it is evidence, not scientific certification. Missing review means technical-preview status. The held-out evaluator owns actual source/AV acceptance. No mandatory human listening is added.

Use diagnoses to drive at most two new revisions after the original, unless another bound is authorized. Record parent hashes, diagnosis and changes; preserve every snapshot. Re-run dependent nodes/reviews for changed content. Never repair source claims in generated subtitles, conceal failures with code exceptions or overwrite the original.

## Execute from the candidate root

PDF, PAGES and a fresh DIR are supplied after freeze. The author and review steps are real native AI work, not a fixture-loading shell command.

```sh
python scripts/course_video.py prepare --source "$PDF" --pages "$PAGES" --project "$DIR"
# Read generated author-request.md plus ALL scoped page images/text.
# Fresh author writes AUTHOR_RESPONSE; separate native pass compares it to source.
python scripts/course_video.py ingest --project "$DIR" --plan "$AUTHOR_RESPONSE"
python scripts/course_video.py voice-input --project "$DIR"
# Choose ONE audio path, subject to existing authorization:
python scripts/course_video.py synthesize --project "$DIR" --allow-network
# OR disclose reuse of existing offline audio:
python scripts/course_video.py bind-voice --project "$DIR" --raw-run "$RAW_RUN"
python scripts/course_video.py render --project "$DIR"
python scripts/course_video.py qa --project "$DIR" --review "$REVIEW"
```

prepare creates CourseProject.json, original/page PNG/text sources and author-request.md with the uniform brief. A fresh diagnosis-driven revision uses the same ingest command and a new response file. Network synthesis requires task authorization; a CLI flag does not grant it. Offline binding is not fresh synthesis. Use --allow-whitespace-comma-projection only when that limited projection is explicitly accepted, never for changed wording.

Bind REVIEW to the exact source/plan hashes reported by the CLI. Source-only review uses media_sha256=null; AV review binds the actual media hash. A stale or source-only report is not AV evidence. Local rendering/cached audio demonstrates integration, not source completeness, natural pronunciation or unseen-lecture generalization. Report unrun checks and remaining limitations honestly.
