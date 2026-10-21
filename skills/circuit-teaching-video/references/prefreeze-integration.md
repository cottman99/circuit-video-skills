# P1 evidence gate integrated with P0 production

## Run the implemented chain

Install the normal rendering dependencies and the optional bounded gate dependencies
from the repository root: `python -m pip install -r requirements.txt -r requirements-p1.txt`.
The full regression suite, including the gate, requires both files. Legacy rendering
alone still uses the normal dependencies.

From the repository root:

```sh
python -B skills/circuit-teaching-video/scripts/prefreeze_gate.py skills/circuit-teaching-video/examples/rc-evidence/content-package.json
python -B skills/circuit-teaching-video/scripts/run_workflow.py skills/circuit-teaching-video/examples/rc-evidence/content-package.json --output output/rc-evidence --synthetic-audio-fixture --video --width 640 --fps 5
python -B -m unittest discover -s skills/circuit-teaching-video/tests -v
```

The original public RC fixture produces a 14-second technical preview with test
tones, not TTS speech. No network, upload or publication occurs. The diagram is
explicitly authored from stable declared model IDs, not inferred from prose.

## Typed nodes and artifact contracts

| Node | Inputs | Outputs | Block conditions |
| --- | --- | --- | --- |
| Evidence validation | Versioned `source-model-script-1`, actual source/region bytes, assumptions, declared linear models, knowledge, complete master and caption references | Source/model checks and exact full formal export | Missing/tampered source, invalid algebra/units/assumptions, dangling references, prerequisite/coverage failures |
| Independent pre-freeze bridge | `circuit-content-package-2`, inline `source_model_evidence`, explicit source root, full formal/caption records, semantic model and visual expressions | `prefreeze-formal-artifact-1`: export plus version/code/input/output binding | Missing gate, master/caption mismatch, changed model links, unsupported model composition or different displayed formula |
| Voice and caption derivation | Validated formal source; separate typed pronunciation adaptations and voice settings | Full written subtitle source and separate phonetic derivative | Partial/independent captions, whole-sentence phonetic override |
| Audio/timing | Explicit synthetic PCM fixture/events, validated text/PCM identities, visual/read constraints and font measurements | Validated synthetic evidence; SAT timeline or UNSAT diagnostics | Cached audio/event drift; insufficient reading or layout capacity |
| Freeze/render | SAT timeline, explicit semantic/visual plan, gate binding, exact audio and runtime | Derived lesson, frozen scene, technical preview and receipts | Missing capabilities, invalid geometry, runtime/media failures |

The bridge currently supports **one complete declared model**, preserving all
component, net, assumption and formula IDs. Its P0 knowledge graph is the exact
projection of checked knowledge goals, prerequisites and source references.
Each formula object must equal canonical SymPy LaTeX for the validated expression;
put equation names or narrative labels in separate objects. Component object links
and directed terminals are checked. Diagram geometry, prose faithfulness, model
adequacy and learning quality still require review.

## Version and failure semantics

Version 2 requires inline evidence and cannot fall back to legacy rendering when
it is absent or invalid. File CLI paths resolve source references relative to the
content package. Python callers must pass an explicit `source_root`.

`prefreeze_gate.prepare` calls the mathematical/source gate again on every
invocation and accepts no saved PASS report. It writes no files itself. The
runner persists its full formal export only after the gate and existing package
validation both pass, before audio/timing/render. A gate failure records a new
FAILED attempt at `pre_freeze_gate` with a localized error, no export and no new
downstream artifacts. An old historical success/export is not the latest attempt
and is never inherited as current evidence. Later timing/render failures do not
retroactively make a successful formal-content check scientific approval.

The frozen scene, derived lesson and preview carry the exact binding:

- Gate and bridge versions; implementation/schema hashes and actual gate dependency versions.
- Current gate input hash and evidence-package hash, including source/model/master references.
- Master identity and formal-export output hash.
- `MACHINE_CHECKS_PASSED_REVIEW_REQUIRED`, with scientific, audiovisual and publication flags false.

The gate implementation/schema also enter runtime bindings, so code changes make
old frozen scenes stale. A frozen artifact records a checked **input snapshot**;
it is not live source authentication. To assess changed upstream files, invoke
the version-2 content workflow again. The gate reopens and validates those files
before it may reuse audio or proceed downstream.

Changes to valid source/model evidence invalidate formal export, timing, frozen
scene and preview. Exact written text may remain unchanged. Audio may be reused
only if its separate speech/fixture/PCM binding still validates, and only after
the new gate passes. Layout-only changes do not regenerate audio. Voice changes
invalidate audio/timing/media but not the formal manuscript or gate export.
Reviews are never inherited. This is dependency validation, not approval transfer.

## Legacy and low-level routes

- `circuit-content-package-1` remains compatible and explicitly reports
  `UNGATED_LEGACY_PREVIEW`. It cannot supply a P1 evidence field or inherit an old gate.
- Direct `pipeline.py compile` does not trust a caller-supplied gate/status field;
  its scene is ungated. Direct low-level rendering reports
  `NOT_REVALIDATED_LOW_LEVEL_RENDER`, even when replaying a frozen snapshot.
- Only the version-2 orchestrator, after executing its gate, attaches the fresh
  machine-check binding to its preview manifest. None of these statuses means
  production acceptance, scientific review or authorized publication.

## Deliberately unfinished whole-skill stages

This is not automatic source research/extraction, arbitrary planning-to-scene
conversion, nonlinear/device-model verification, general multi-model storyboard
composition, complex multi-board cinematography, real speech/word alignment,
complete audiovisual review, hash-bound independent approval or authorized
delivery. See the [whole-workflow node ledger](workflow-node-coverage.json) and
[bounded gate mathematics](source-model-gate.md). Local previews do not require a
new human approval at every render; publication still needs applicable authority.
