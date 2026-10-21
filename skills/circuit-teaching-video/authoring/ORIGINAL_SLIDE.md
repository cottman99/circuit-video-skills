# Original-slide presentation contract

This is the presentation-specific branch of steps 4–6. It does not replace the single formal manuscript, source inventory, pronunciation or review contracts. Use it when SourcePackage.presentation_mode is `original-slide`.

## Input → output

Read every original selected page image, its source text and the brief. Return the same AUTHOR_RESPONSE lesson fields, but use `layout.schema: "original-slide-layout-1"` and one scene per complete original page, in selected-page order. The renderer retains the raster's original language, aspect, positions, connections, labels, curves and mathematical notation. It neither translates nor re-typesets the page. Full Chinese captions occupy a separate band below it. Explain source notation through its contextual quantity or relationship in the single master, not mechanical recitation of subscript syntax. Pronunciation remains a local typed derivative, never a second editable script. Do not reflow source objects, redraw diagrams, remove marks or replace a formula with newly generated LaTeX.

Each scene has `id`, `title`, `source_page`, `source_pages:[source_page]`, `sentence_ids`, `source_objects` and `teaching_actions`. No source_crops/formula_objects are needed in this mode. The ordinary formal_master records and exact full-caption references remain unchanged.

A reveal owner is a complete semantic object, not a convenient rectangular slice: for example a connected circuit with all its wires and labels, a complete equation or a plot with axes and legend. Give it `id`, `regions:[[left,top,right,bottom],...]` in the supplied page image's **integer pixels**, and `reveal_sentence_id`. Rectangle right/bottom are exclusive. Use null for marks visible at page entry. The owner appears cumulatively and remains visible for the rest of the page. Include clear background margin around its complete ink; a two-pixel exposed union-boundary check catches clipping through ink, not semantic omissions. Internal seams between rectangles are not object boundaries. The physical source-image edge is exempt because no new clipping is introduced there. For inspected faint compression/background speckles only, an owner may declare edge_background_tolerance (integer 0–10 in 8-bit channel values) and a nonempty edge_tolerance_reason; default is exact background (0). This affects boundary validation only, never source pixels or masking. It cannot clear dark ink or certify that a pale meaningful mark is irrelevant. Preserve source defects and inspect the complete region.

A focus subobject has `id`, `regions` and `reveal_with:"owner_id"`, but no separate reveal_sentence_id. Its regions must lie within its reveal owner's regions. Use this for input/feedback/output parts of an already visible circuit. It is never independently masked or recolored. Different reveal owners must not share ink. Multiple regions can preserve separated lines of one semantic object without covering unrelated content.

An action is `{sentence_id,target_id,action:"focus"}`. Local target IDs identify the exact semantic referent; coverage.visual_object_ids uses scene-qualified IDs. The same cue drives the target's underlay and pointer. Default timing uses the returned provider sentence onset, delayed explicitly until its target is fully revealed. After a short move the pointer holds still; it does not drift throughout the sentence. A long sentence may use an explicitly authored `{timing_basis:"estimated_text_position",text_range:[start,end]}` on its **formal text**, only when that span names the target. This is a text-position estimate, not a measured word/phoneme boundary. Do not partition a sentence equally among unrelated objects. Preserve real event receipts and estimated-cue labels. Impossible reveal/move/dwell windows fail, not truncate.

The renderer chooses nearby clear whitespace for a focus point. If that fails, supply a source-pixel `focus_point:[x,y]` associated with that object; it must have clear space around it. Do not put the pointer on a symbol, wire or curve. The glow and underlay preserve original ink, including original colored curves/legends.

`layout.scenes[scene_id]` is exactly `{background_rgb:[r,g,b],mask_policy:"uniform-background"}`. Declare this only after inspecting the regions. This adapter supports semantic regions on a known uniform background; it does not erase complex backgrounds, photos or meaningful white foreground as if they were blank. Such objects need an alpha/background adapter and are currently unsupported. Unmasked source content remains present. The complete original page must be visible before its scene ends.

Optional `layout.semantic_colors` maps meaningful role names to RGB values, and a reveal owner may declare `ink_role` from that map. Use roles for dark neutral notation on a light uniform background, never arbitrary object-index colors or photos. Original chromatic pixels are unchanged. Omit colors when they add no instructional meaning. Layout can also set positive `presentation.reveal_seconds`, `move_seconds`, `minimum_dwell_seconds`, `minimum_complete_page_seconds`; these are presentation parameters, not physical laws. Defaults are 0.5-second reveal, 0.28-second move, 0.25-second minimum dwell and 0.5-second complete-page ending. Output is 60 fps and preserves the imported 1600-pixel page width.

## Minimal shape (illustrative IDs and bounds, not a source answer)

```json
{
  "scenes":[{
    "id":"page_a","title":"Original page","source_page":1,"source_pages":[1],
    "sentence_ids":["sentence_a","sentence_b"],
    "source_objects":[
      {"id":"connected_diagram","regions":[[100,200,1200,600]],"reveal_sentence_id":"sentence_a"},
      {"id":"output_branch","regions":[[900,260,1180,500]],"reveal_with":"connected_diagram"},
      {"id":"equation","regions":[[100,650,1200,760]],"reveal_sentence_id":"sentence_b","ink_role":"derived_result"}
    ],
    "teaching_actions":[
      {"sentence_id":"sentence_a","target_id":"output_branch","action":"focus"},
      {"sentence_id":"sentence_b","target_id":"equation","action":"focus"}
    ]
  }],
  "layout":{
    "schema":"original-slide-layout-1",
    "semantic_colors":{"derived_result":[35,104,170]},
    "scenes":{"page_a":{"background_rgb":[255,255,255],"mask_policy":"uniform-background"}}
  }
}
```

Static titles, citations and other marks can remain unmasked. The reserved visual reference `scene_id.source_page` identifies the complete authoritative raster; no source object may use that local ID. A coverage item conveyed visually may have `formal_sentence_ids:[]` and a nonempty same-page visual reference, so do not invent spoken links for a static mark. Every formal sentence still needs a genuine source treatment row, and every selected page remains in the coverage inventory.

Coverage links would be `page_a.connected_diagram`, `page_a.output_branch`, `page_a.equation`. Use actual source-measured bounds, complete scope and actual sentence IDs, not these placeholders. Source coverage and referent correctness still require real source inspection; a rectangle check is not a scientific or semantic certificate.
