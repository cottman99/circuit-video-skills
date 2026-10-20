---
name: circuit-teaching-video
description: Design and produce circuit teaching videos, knowledge-organized storyboards, persistent whiteboards, diagrams and narration edits, with source fidelity, real audio evidence and artifact-bound visual QA.
metadata:
  version: 0.1.0-public
---

# Circuit teaching video

Use the smallest requested route. A script edit ends at the script; a drawing edit ends at the drawing; a storyboard does not authorize synthesis or encoding. Research only what the requested explanation needs. Never infer permission to publish, upload source material, or send narration to a service from selecting this skill.

## Content before effects

Start from the question, system/module/circuit context and a sufficient model. Preserve device identity, conditions, units, sign conventions and source evidence. Prefer MOS for general device explanations, but do not relabel HBT evidence or erase a topic's actual device physics. Read [models and evidence](references/models-and-evidence.md) for research or substantial content changes.

For source adaptation, audit both source→video omissions and video→source unsupported additions. Keep the complete source coverage ledger separate from the visible board. Equations and diagrams need stable semantic IDs; animation must not change connectivity or mathematical meaning.

## Knowledge, board, camera

Keep the knowledge graph, local reasoning boards and camera route distinct. Only true prerequisites impose an acyclic order; electrical feedback is not a pedagogical prerequisite cycle. Choose a local board around one question, premises and conclusion. Keep formulas cumulative and a legible circuit/context view available. World retention is not viewport visibility.

Read [knowledge organization](references/knowledge-organization.md). The optional `scripts/workflow.py` normalizes planning schema 1.0; it does not render and its output is not interchangeable with `circuit-lesson-1`. The executable example's single `lesson.json` owns its content, IDs, geometry intent and timing. Do not independently edit generated scene content.

## Production

Read [production workflow](references/production-workflow.md) and [adapter contracts](references/adapters.md) before timed media work. The main entrypoint is `scripts/pipeline.py`:

1. Author or update one lesson source, including assumptions, source mapping, all visible content and IDs.
2. Resolve fonts, layout, reveal/read windows, camera and capabilities; compile to a frozen scene.
3. Render representative samples and the requested preview using that scene. For speech, use actual recording/provider evidence and label estimated timing honestly.
4. Review source/content, watch and listen to the complete audiovisual preview, then inspect short native-density samples before a long final encode.
5. Verify exact final artifact identity, decoded frames/tail and transitions, then complete final-file-bound visual/listening review. Only perform explicitly requested delivery or publication.

The scripts record technical evidence, not human approval. A silent example has no pronunciation or audio synchronization result. Text/voice/rate changes invalidate affected audio and all downstream timing/media; geometry/font changes invalidate affected renders. Rehashing an old review does not renew it.

## Visual invariants

Use a persistent full-screen whiteboard unless the user explicitly requests another presentation. Read [typography and layout](references/whiteboard-typography.md) for real weights, role floors and bottom internal subtitle safe zones. Render mathematical typography at output density, never merely upscale a low-resolution frame.

Read [math typography](references/math-typography.md) and [semantic identities](references/semantic-symbol-registry.md). Keep variable colors stable across formulas and plots; operators stay neutral. Attention red/glow is a separate removable layer, not a variable identity. Read [teacher pointer](references/teacher-pointer.md): follow the actual reveal front; frame a region; use arrows for relationships without implying a circuit wire.

A pale attention fill belongs behind content. Keep every nonwhite glyph/diagram pixel unchanged, then apply glyph-safe foreground attention and captions. The exact-white matte implementation only supports verified whiteboard content, not photographs or intentionally white-filled symbols.

## Speech, captions and honest review

Read [narration and visuals](references/narration-and-visuals.md), [technical speech](references/tts-pronunciation.zh-CN.md), and [subtitle guidance](references/subtitle-guidelines.zh-CN.md). Canonical display text and natural spoken text can differ only meaning-preservingly. Keep primes, indices, powers, units and signs explicit. Do not claim pronunciation repaired without listening.

Use measured voice timing where available; provider sentence boundaries are not forced word alignment. Finish important formula writing early enough for a full-read window, with content-driven holds rather than fixed gesture quotas. Metadata correctness does not certify scientific correctness, audiovisual quality or learning gains.

## Portability and limits

No private lecture assets, source fonts or vendor libraries ship in this skill. Optional network synthesis requires its explicit command and the user's authorization. Optional PDF input requires a recorded rights basis. Unsupported adapter capabilities fail rather than silently dropping content. See [public provenance and boundaries](references/public-scope.md) for precisely what was generalized and what remains external.
