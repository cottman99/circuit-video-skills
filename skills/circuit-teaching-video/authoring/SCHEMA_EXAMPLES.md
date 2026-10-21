> Original-slide is the default. Its shape is in [ORIGINAL_SLIDE.md](ORIGINAL_SLIDE.md). The examples below describe the explicitly selected legacy whiteboard mode.

# Author response shape

This is schema documentation, not a runnable lesson, golden response or fallback. Angle-bracket values below must be replaced from the newly supplied source. No actual lecture, formula, crop coordinates or presentation positions are prescribed here. All selected physical PDF pages must be retained.

```json
{
  "title": "<source-backed lesson title>",
  "scope_source_sha256": "<SHA-256 of original PDF bytes>",
  "selected_pages": ["<integer physical PDF page number>"],
  "scope_statement": "<complete selected scope and explicit limits>",
  "formal_master": [
    {
      "id": "sentence_001",
      "text": "<complete formal sentence, not a caption summary>",
      "source_pages": ["<integer source page>"],
      "scene_id": "scene_001"
    }
  ],
  "scenes": [
    {
      "id": "scene_001",
      "title": "<source-backed scene title>",
      "sentence_ids": ["sentence_001"],
      "source_pages": ["<integer source page>"],
      "source_crops": [
        {
          "id": "crop_001",
          "page": "<integer source page>",
          "bbox_normalized": ["<left>", "<top>", "<right>", "<bottom>"],
          "description": "<source region, including material labels and relationships>",
          "white_matte_safe": true
        }
      ],
      "formula_objects": [
        {
          "id": "formula_001",
          "latex": "<complete source-faithful renderer-compatible expression>",
          "source_page": "<integer source page>",
          "meaning": "<meaning and conditions actually established by source>",
          "reveal_sentence_id": "sentence_001"
        }
      ],
      "teaching_actions": [
        {"sentence_id": "sentence_001", "target_id": "crop_001", "action": "frame"}
      ]
    }
  ],
  "coverage": [
    {
      "source_page": "<integer source page>",
      "source_item": "<precise location and source content, including quote or figure/region identity>",
      "formal_sentence_ids": ["sentence_001"],
      "visual_object_ids": ["scene_001.crop_001", "scene_001.formula_001"]
    }
  ],
  "unresolved_issues": [],
  "layout": {
    "schema": "course-layout-1",
    "measurement_policy": "Actual rendered bounds, preserved crop aspect, readable text and full captions",
    "scenes": {
      "scene_001": {
        "objects": {
          "crop_001": ["<x>", "<y>", "<width>", "<height>"],
          "formula_001": ["<x>", "<y>", "<font_size>"]
        },
        "labels": []
      }
    }
  },
  "pronunciation": {}
}
```

Repeat scenes, sentences and coverage rows as needed for complete material coverage; the single entries above are only shape illustrations. Source crop coordinates are normalized finite numbers between zero and one with positive extent. Layout coordinates and sizes are finite canvas-pixel numbers. Both are measured from this project, never copied from another lecture. white_matte_safe:true is an inspected precondition for the bounded white-backed line-art/notation adapter, not a universal default; incompatible photos/opaque-white semantics are unsupported by this adapter. Crop/formula IDs and layout targets are scene-local. Omit absent crop/formula objects using empty arrays. Unsupported mathematical notation stays an intact source crop. Do not emit formula_parts or latex_compatibility. A label uses {id,target,text,xy:[x,y],size}; its target resolves to an object and its wording is source-supported. Do not author a caption/spoken-text track or timings.

## Local pronunciation example

Coverage visual_object_ids use scene-qualified IDs (scene_id.object_id). Layout object keys, label targets and teaching-action target_id use local IDs within their scene. Optional voice is exactly {"name":"<nonempty voice name>","rate":"<nonempty rate string>"}; no text or other request fields are accepted.

For the purely illustrative formal sentence `The label is RMS.`, a local abbreviation reading is:

```json
{
  "pronunciation": {
    "sentence_001": [
      {"kind": "term", "source_range": [13, 16], "source_text": "RMS", "reading": "R M S"}
    ]
  }
}
```

This is a syntax example, not source content to include in a lesson. Offsets count Unicode code points, start inclusive/end exclusive. A notation span instead has exactly kind, source_range, source_text and meaning; it invokes the existing context-selected notation adapter. No span has a spoken_text field. The CLI derives the full speech string, complete formal-text hash and span map. Captions retain the entire original formal sentence byte-for-byte.

## Independent review report

```json
{
  "reviewer": "<identity of separate native review pass or evaluator>",
  "scope": "<exact inspected source pages and artifacts; identify source-only versus AV review>",
  "source_sha256": "<original PDF hash>",
  "plan_sha256": "<exact reviewed author-plan hash>",
  "media_sha256": null,
  "findings": [
    {
      "severity": "<CLI-supported severity>",
      "description": "<specific finding with source item, sentence/object and source location>",
      "affected_node": "<node containing the diagnosed fault>"
    }
  ]
}
```

Use null media_sha256 only for a review that did not inspect rendered media. Bind the actual media hash for an AV review; do not reuse a source-only report as AV evidence. Record inspected page images and source completeness in scope/findings. A review with no findings must be an actual comparison, not an author-created empty approval. The evaluator owns the acceptance decision; a report is evidence, not automatic certification.
