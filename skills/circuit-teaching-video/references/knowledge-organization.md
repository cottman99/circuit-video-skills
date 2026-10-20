# Knowledge organization and local reasoning boards

## Three separate structures

`knowledge-canvas` is an opt-in storyboard/planning mode. It adds an executable normalization gate before a plan can be handed off. It does not replace the existing report, drawing, expression, teaching or video routes, and does not implement a moving-camera renderer.

Keep these structures distinct:

1. **Knowledge graph:** claims/concepts and explicitly typed relations. It records what is connected, including causal relations, contrast, composition and feedback. It is not automatically the lesson sequence or a visual tree.
2. **Local reasoning boards:** bounded teaching units answering a question from stated premises to a conclusion, with source references and stable retained objects. A board can draw on multiple graph branches and can be revisited.
3. **Camera visits:** an authored ordered route through those boards, with focus objects, a view rectangle and a reason for the transition. A route is not a graph traversal inferred from every edge.

Only edges typed `prerequisite` constrain a directed acyclic ordering. A prerequisite points from the earlier requirement to the dependent node. Feedback and other non-prerequisite relations may form cycles; an electrical feedback loop is not evidence of circular pedagogical prerequisites. Never change a physical relation into a prerequisite merely to force a sequence. The normalizer uses lexicographic stable-ID tie breaking for deterministic prerequisite ordering; this is not a claim that this order is uniquely best for learners.

## Core authoring rules

- Start with the question and enough system/module/circuit context to make the model meaningful. State assumptions and motivate any refinement. Use the smallest sufficient model; do not impose a universal tree or a prescribed number of levels.
- Each board states its question, nonempty premises, conclusion, knowledge and source references, object references, and retained objects. Claims remain attributable; a locator or a structurally valid graph does not prove the claim.
- Keep the circuit/context diagram in the left lane and formulas in the right lane. Formulas accumulate rather than replacing the previous step. Retain the circuit and every formula declared on that board. Names, notation and semantic colors must continue to identify the same objects across representations.
- Plan fast completion of new writing followed by a fully visible reading opportunity, with a semantic teacher pointer on a separate attention layer. Do not add a legend by default. The planner preserves these local defaults; the production compiler and actual-frame audit must establish their execution.
- Give each visit a transition purpose: what question requires moving attention, revisiting a premise or changing scale? No zoom, pointer or seconds quota applies. Keep the view stationary while reading; no arbitrary fixed duration is supplied by the planner.
- World persistence and viewport visibility differ. A later view may crop a retained object without deleting it. Return to it when the reasoning needs it. Normalization checks declared rectangles and focused-object containment, not actual text legibility or animation.

## Optional organization patterns

Choose these only when useful; none is a mandatory outline:

- **Concept map:** typed relations give an overview of a system or domain. Contrast and feedback links are welcome. The entire map need not be exposed at once.
- **Prerequisite DAG:** isolate the actual dependencies needed to understand a derivation. Multiple roots, converging branches and independent results are valid. A board may introduce prerequisites and their dependent result internally; its derived reasoning order follows the DAG.
- **Question route:** sequence local boards around questions and model refinements. A revisit can compare an earlier prediction with a new condition. Authored route order must not introduce a dependent board before its prerequisite knowledge is available.
- **Semantic zoom:** plan a view from system to module to circuit or from an equation to a meaningful term, preserving identity and context. In this release this is a storyboard view rectangle, not executable global camera motion.

## Executable plan schema 1.0

Run the compulsory mode dispatcher:

```sh
python -B scripts/workflow.py --mode knowledge-canvas --plan PLAN.json --output WORKFLOW.json
```

The underlying normalization node can be tested directly:

```sh
python -B scripts/plan_knowledge.py PLAN.json --output NORMALIZED.json
```

Paths are relative to this skill folder. The normalizer is an independent planning helper; the public renderer uses its own explicitly documented input schema. Store author and output files outside the skill package. Do not hand-edit generated fields to simulate a pass.

The plan is a JSON object. Required collections are nonempty except `knowledge_graph.edges`, which is required but may be empty. All record IDs match `^[a-z][a-z0-9_.-]*$` and are unique within their collection. Reference arrays contain unique existing IDs. Unless explicitly stated otherwise, reference arrays are nonempty. Required text is a nonempty string. Bounds use finite `[x, y, width, height]` values with positive width and height in one consistent authored coordinate space; they are not pixel measurements from a render.

- `schema_version`: exactly the string `"1.0"`
- `question`: overall question
- `sources`: records with `id`, `locator`, `basis`. Both locator and basis are nonempty text; basis is not an enumerated evidence certification. The planner does not fetch sources or inspect their contents
- `knowledge_graph.nodes`: records with `id`, `statement`, `source_refs`
- `knowledge_graph.edges`: records with `id`, `from`, `to`, `type`, `reason`. Type is one of `prerequisite`, `causal`, `contrast`, `part_of`, `feedback`, `related`. Endpoints reference knowledge nodes. Non-prerequisite loops are allowed; prerequisite self-loops and longer cycles fail
- `objects`: records with `id`, `kind`, `knowledge_refs`, `bounds`. Kind is `circuit`, `formula`, `text` or `plot`. These are planning objects, not the persistent-board renderer's asset/formula/text input schema; no renderer conversion is implied
- `boards`: records with `id`, `question`, `premises` (nonempty list of text), `conclusion`, `knowledge_refs`, `source_refs`, `object_refs`, `retained_objects`, `bounds`; optional `layout` and `local_policy` described below
- `camera_visits`: records in authored execution order with `id`, `board_id`, `transition_purpose`, `focus_objects`; optional `view_bounds` and `role` (`explain` by default, or `preview`). A board may have multiple visits. Every board must be visited and all knowledge nodes must be covered by visited boards

`layout` accepts only `left_fraction` and `gap_fraction`. Defaults are `0.48` and `0.04`; require `0 < left_fraction < 1`, `0 <= gap_fraction < 1`, and their sum less than 1. With board bounds `[x,y,w,h]`, circuits end at or before `x + w*left_fraction`; formulas start at or after `x + w*(left_fraction + gap_fraction)`. All declared objects must fit within the board, and object rectangles on the same board must not overlap with positive area (touching edges are allowed). Each board's `source_refs` must include every source referenced by its knowledge nodes and by its objects' knowledge nodes. Each board requires at least one `circuit` object. Text and plot objects have no lane restriction beyond board containment. Retained objects must be on that board, and include all its circuit and formula objects. There is no automatic packing, overlap solver, font measurement or resizing.

The normalizer fills absent local policy keys with:

```json
{"formula_retention":"cumulative","reveal":"fast_then_read","pointer":"semantic_teacher_pointer","legend":false}
```

Conflicting values for these four keys fail rather than silently weakening local behavior. Additional policy metadata is preserved but not implemented or certified by this node. `view_bounds` defaults to the visited board's bounds, must fit inside that board, and must fully contain every focus object. Focus objects must belong to that board. An `explain` visit may introduce a prerequisite and dependent node together on one board; otherwise each direct prerequisite must already have been introduced on an earlier explain visit. Object knowledge must be current or previously introduced. An explicit `preview` visit may reference future questions or results as an advance organizer; it earns no introduced-knowledge or prerequisite credit. Every knowledge node must eventually be covered by an explain visit.

The normalized output retains authored content and order, adds defaults and derived planning data, and replaces any input `derived` field. `derived.prerequisite_order` covers all knowledge nodes. `derived.board_reasoning_order` maps each board ID to its knowledge IDs in prerequisite order. `derived.visit_states` follows authored visit order; each record contains `visit_id`, `board_id`, `role`, `introduced_knowledge`, `reasoning_order`, `availability`, and `retained_world_objects` (the sorted cumulative union of retained objects from visited boards). `availability` explicitly says `planned retention after local reveal; not initially visible or audio-timed`. These are declared planning states, not measured render states. `derived.scope` states that checks cover declared structure and geometry only; `derived.renderer` names the existing persistent-board route and the absence of an automatic global-camera adapter. The dispatcher wraps this plan under `normalized_plan`, records completed and pending nodes, and sets `status: "storyboard_plan_only"`; its output is not the standalone node's direct-plan schema. The dispatcher envelope is described by its JSON output and workflow.py.

The standalone CLI prints a JSON result, exits 0 on success and 1 on validation/read/JSON failure. Without `--output`, success includes `normalized`; with it, success writes sorted-key, indented UTF-8-compatible JSON and reports `output` and the file's `sha256`. Failure reports `passed: false` and `errors`. A failed validation does not make an existing output file current: inspect the latest result and regenerate before using it.

## Handoff boundary

A normalized plan is a storyboard artifact. It is not measured narration, a rendered board, verified knowledge, a tested lesson or permission to synthesize/encode. Production continues through the existing semantic author inputs, compiler, source/audio identity checks, cumulative renderer, reveal/pointer audits and actual-frame review. Do not feed this JSON into the renderer as if the schemas were interchangeable. Unsupported global movement must remain planned or fail capability preflight; it must not silently replace cumulative local reasoning with independent slides.


For production capabilities and limits, read [adapter contracts](adapters.md).
