# Executable content-to-preview P0

This is an implemented vertical slice, **not completion of whole-skill workflow
optimization**. It replaces manual copying of sentence times for one deliberately
bounded example. The larger node inventory and remaining acceptance work are in
[workflow-node-coverage.json](workflow-node-coverage.json).

## Run it offline

From the repository root:

```sh
python skills/circuit-teaching-video/scripts/run_workflow.py \
  skills/circuit-teaching-video/examples/resistor-divider/content-package.json \
  --output /tmp/circuit-workflow-demo --synthetic-audio-fixture --video
python -m unittest discover -s skills/circuit-teaching-video/tests -q
```

The explicit fixture option produces low-volume test tones, not TTS. No network
service is used. Its PCM duration is measured from the actual generated WAV;
sentence boundaries are constructed test inputs bound to that PCM, **not measured
speech, forced alignment, word timestamps or evidence of correct pronunciation**.
The resulting preview is technical and unreviewed. No approval is required merely
to render this local example; rendering never authorizes publication.

Exit 0 records `SUCCESS` with `technical_status: TECHNICAL_PREVIEW_UNREVIEWED`;
exit 2 records `UNSAT` with diagnostics; exit 1 records `FAILED` for invalid input
or an operation failure. A success exit does not mean that a human has reviewed
the audio or science. CLI errors before a usable output directory is known, or an
unwritable directory, cannot promise a persisted record.

## Authored input and stage contracts

`circuit-content-package-1` contains:

- `content`: source records, knowledge graph, semantic circuit model, full formal
  `narration`. The semantic model explicitly links stable component/net/formula
  IDs to visual objects. It is not inferred back from narration.
- `visual`: untimed objects and board layout, complete object universe, renderer
  capabilities and one fixed native-size camera. No authored seconds are allowed.
- `voice`: voice configuration used by the dedicated phonetic derivation.
- `caption_refs`: source spans only, no independently authored subtitle text.
- `temporal`: reveal/read dependency DAG and explicit minimum reading policy.
- `synthetic_fixture`: explicit test durations/gaps per sentence, not production
  voice evidence.

The source package is never mutated. Generated `lesson-derived.json` is an adapter
output, not a second editing surface.

| Executed node | Inputs | Output | Failure boundary |
| --- | --- | --- | --- |
| Formal caption source | Full formal manuscript, caption source references | Exact full text and source-span artifact | Missing/repeated text, independent display text, unsupported finer cue spans |
| Phonetic voice | Same formal manuscript, typed local pronunciation spans, voice | Dedicated spoken derivative and full formal↔spoken span map | Whole-sentence override, deletion, stale or unsupported span |
| Synthetic audio fixture | Derived speech identity, fixture specification | Actual PCM WAV and sentence event receipt | Unknown fixture schema or bad timing |
| Audio/event validation | Receipt, speech plan, exact WAV, fixture | Revalidated PCM hash/count, event coverage and text/map binding | Stale/missing/overlapping/out-of-range events, changed bytes |
| Joint timeline | Validated sentence windows, full-caption refs, actual fonts/layout, reading/reveal constraints | SAT timeline with exact cues or UNSAT conflict list | Insufficient time or subtitle width/height; no shrinking/summary fallback |
| Lesson adapter + freeze | SAT timeline, original semantic content and untimed visual objects | Derived `circuit-lesson-1`, frozen scene with dependency hashes | Missing capability/model/object links, geometry failure |
| Preview | Frozen scene, exact audio, output profile | Samples or MP4, frame receipts, decode/frame-count report | Stale code/fonts/audio, geometry or encoding failure |

The text/voice branches are independently keyed. Voice or pronunciation changes
leave the formal caption artifact unchanged, but rebuild audio, timeline, scene
and preview. Layout changes reuse audio only after revalidating it; they recompute
caption layout/timeline and scene/media. Changing the implementation conservatively
changes node identities. The frozen scene also binds current workflow/renderer
code and fonts. Every run records `review: NOT_PERFORMED`; an old approval is not inherited.
A new attempt record is allocated before input validation, including when the
input is malformed JSON or environment capture fails.

## Exact supported timing/layout subset

- One stationary 1920×1080 board with cumulative objects and existing renderer.
- Exactly one full caption per narration sentence. Native font measurement chooses
  line wrapping after sentence windows are known. If full text will not fit, UNSAT
  instructs obtaining finer evidence or changing layout. It does not fabricate
  word times or shorten text.
- Every formula has exactly one action with a positive reveal and read duration,
  a sentence window, offsets and zero or more `after` predecessors.
- The solver computes earliest starts in this DAG. For these lower-bound
  dependencies and fixed deadlines, an earliest finish beyond the deadline is an
  actual conflict. It reports the target, earliest finish, deadline and shortfall.
  Cycles/malformed constraints are invalid input, not a claimed solved schedule.
- Caption reading rate is a configurable engineering constraint, not a measured
  accessibility or comprehension result.
- Semantic links and unchanged circuit/formula content are checked/preserved;
  this does not prove that the authored circuit topology or physics is correct.

## Inspectable artifacts

Each invocation has a unique `run_id` and monotonically allocated `run_sequence`.
`runs/<run_id>/attempt.json` is written as `RUNNING` before input validation. It
records the exact raw CLI input hash (or canonical Python-input hash), stage,
start/update/end timestamps, environment fingerprint and new/reused artifact
flags. An unreadable input has an explicit null hash, not an invented identity.
Environment capture starts after the initial record; if capture fails, the failed
attempt states that the fingerprint was unavailable rather than inheriting one.

- `latest.json` is the newest-started **attempt**, including RUNNING, UNSAT and
  FAILED. A failed record contains no prior preview path, media hash, scene path
  or scene digest. It may reference `previous_success_run_id` as history only.
- `latest_success.json` is the newest-started successful attempt, not current
  approval or evidence that the latest attempt succeeded.
- Terminal statuses are `SUCCESS`, `UNSAT`, `FAILED`. Records include `stage` and
  `error_code`; success has no error, and UNSAT identifies constraint failure.
- All attempt records and pointers use temporary-file replacement plus fsync.
  POSIX advisory locks serialize sequence allocation/pointer changes. Older runs
  completing later cannot overwrite a newer attempt or newer successful attempt.
  These are atomic individual JSON snapshots, not a multi-file database
  transaction; compare run IDs when reading multiple files.
- A process killed without a catchable exception leaves RUNNING, not false
  SUCCESS. RUNNING is not proof that the process is still alive. This slice does
  not add automatic crash recovery, leases or unattended retries.

Content-keyed node artifacts remain under `nodes/`. Audio is the only cached
execution stage and uses a per-key lock while generating/revalidating text,
boundaries and PCM. Each attempt has its own media subdirectory, so concurrent
encodes cannot overwrite one another. New/reused flags describe this attempt's
artifacts, not review approval. Other stages are recomputed; a stable node key
does not mean execution was skipped. Corrupt cached evidence fails closed.

The preview manifest and attempt bind Python, dependency specification hashes and
actual installed versions, renderer code/fonts, FFmpeg/FFprobe executable hashes
and version output, platform and output/encoder profile. The preview key includes
this environment fingerprint. Compare scene, decoded frames/duration and actual
media identity when repeating a run. Equal scene digests across different encoder
or runtime environments do **not** promise byte-identical MP4s. Same-environment
repeat behavior is regression-tested, not extrapolated to all machines.

The preview is reproducible from the frozen scene and exact bound WAV within the
recorded environment limits. Samples/MP4s remain local. No publishing/delivery
adapter runs. Reviews must bind exact scene/media versions separately; technical
SUCCESS is never review approval.

## Explicit remaining gaps

The integrated version-2 route adds the [P1 pre-freeze evidence gate](prefreeze-integration.md): selected source bytes, bounded declared linear-model algebra, knowledge prerequisites and full formal/caption coverage are checked before downstream execution. Version-1 remains explicitly ungated. This does not convert arbitrary `workflow.py` storyboard output, perform source research, establish scientific adequacy, optimize pedagogy or automatically design visuals. It does not integrate live provider receipts, do word-level alignment,
solve general temporal networks, retime multi-board camera/attention tracks,
optimize subtitle splits, or implement delivery/approval policy. Existing
`voice_adapter.py` remains an optional separately authorized provider path; its
output is not silently accepted as this synthetic fixture schema. Production
support requires a separate validated evidence adapter and its tests.

The next changes should follow independent whole-skill review, with bounded
acceptance checks for each node, rather than presenting this P0 as final approval.

Version-2 inputs and gate artifacts are specified in [prefreeze integration](prefreeze-integration.md). Missing/invalid evidence is FAILED, never a fallback to version-1.
