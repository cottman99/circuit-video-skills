# Optional external parser

Use MinerU 4.0.12 basic as a single primary extraction source when its separately prepared environment and license terms fit the task. The adapter adds no review stage and does not change the master, voice, caption, timeline or renderer contracts. PyMuPDF retains the original-page rendering/crop role. OCR yields candidate text/math and provenance, never a circuit netlist or scientific correction.

## Inputs and outputs

Input: original CourseProject.json (or SourcePackage stored at the original project root), original PDF, complete selected physical pages, external MinerU basic and a manifest of fully cached models. Output: a fresh SourcePackage.import.json sidecar preserving source fields and adding extraction evidence. It does not overwrite CourseProject or generate another master.

source_base explicitly locates the original project root for unchanged relative source/image paths; input_project records the original project path/hash. The sidecar is not a self-contained copy of those assets. Keep the source workspace with it; do not guess the source base from the import output directory.

Extraction retains ordered blocks, types, physical pages, normalized boxes, text/inline math, standalone LaTeX, original figure references/hashes, raw locators and explicit warnings. Keep headers/page numbers even when Markdown omits them. Do not re-sort by coordinates, invent confidence, silently fix equations or discard unsupported blocks. Missing assets/scope or changed source fails; invalid geometry/unsupported content remains a visible defect with an original-page reference.

## Execute once before authoring

```
EXTERNAL_PYTHON scripts/mineru_source.py --project PROJECT/CourseProject.json \
  --output FRESH_IMPORT --run-local --mineru-home EXISTING_HOME \
  --model-manifest EXISTING_MODEL_MANIFEST.json
```

Supply the exact sidecar path/hash to the author with all original page images. Keep that input identity with the original response. A revised extraction is new authoring evidence, not permission to reuse an old review. Only a diagnosed affected block falls back to its original page/crop; do not serially run every parser or add a blanket review sweep.

For contract tests, --raw PATH --raw-source-sha256 HASH explicitly records a host-supplied association. It is not fresh parser execution or independently proven source binding, and is not the normal fresh-import route.

## External installation, privacy and rights

No parser dependency code or weights are bundled, installed or fetched by this adapter. Use a separately, manually prepared environment. Before any MinerU/ORT import it disables telemetry, selects local/offline models and verifies the model-manifest files. Missing models fail. The main-process Python socket guard is additional protection; spawned workers inherit offline/telemetry environment settings, not that monkeypatch. This is not a network-layer guarantee. Use an offline-capable environment and do not start the optional service/daemon.

Each fresh output directory preserves its attempt and partial raw results. A failed import publishes no SourcePackage.import.json. Source/project changes during parsing reject before export.

MinerU code and individual models have their own version-specific terms. Do not claim complete-system MIT compatibility, infer deployment permission, redistribute weights or auto-install from this interface. Check the exact [upstream project](https://github.com/opendatalab/MinerU) and supplied model manifests for the intended deployment. This is not legal approval.

Measure useful end-to-end work: complete-unit import to usable single master, actual wall time, original defects, local repairs/interventions, omissions and first/final usability. Parser-only speed is not a complete production result.
