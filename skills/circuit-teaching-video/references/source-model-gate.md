# Bounded source–model–formal-script gate

## Purpose and status

This optional P1 gate adds executable evidence contracts before audiovisual production. The version-2 content workflow now enforces it through an independent pre-freeze bridge. It does not replace the renderer or manufacture a general planning adapter; legacy version-1 routes remain explicitly ungated. Public fixtures are original ideal RC examples. No private lecture assets or lecture-derived script belong in this subtree.

A successful result is `MACHINE_CHECKS_PASSED_REVIEW_REQUIRED`, not scientific acceptance. The only supported downstream action is producing a hash-bound formal-text export. Scientific review, acoustic alignment, rendering review, and publication authorization remain false. The export function revalidates current inputs; it never accepts a caller-supplied PASS report.

## Reproduce

From this subtree, with Python 3.11 or later and requirements-p1.txt dependencies installed:

- `python scripts/source_model_gate.py fixtures/original_rc.json`
- `python scripts/source_model_gate.py fixtures/original_noise_projection.json`
- `python scripts/source_model_gate.py fixtures/original_rc.json --export-formal`
- `python -m unittest discover -s tests -v`

No command calls a network provider, synthesizes speech, changes an external service, or publishes. PDF cases additionally require Poppler `pdfinfo` and `pdftoppm` on PATH. A missing renderer blocks source validation. Rendering is temporary and read-only with respect to the original PDF.

## Node contracts

1. Source ledger: source file identities, rights boundary, declared page count, per-claim regions and coverage states. Source bytes and region artifacts are hash checked. A PDF page is freshly rendered with the declared recipe to verify the evidence image belongs to the declared source/page; the actual PDF page count is checked. Original text fixtures require exact source/artifact identity, one logical page, and whole-document coordinates. A successful byte/render check does not prove a claim interprets the region faithfully.
2. Model/derivation: named nodes, directed terminals, component values, parameter units/domains/sample values, explicit assumptions, formulas and derivation steps. Supported R, C, VCCS and VCVS primitives are stamped into MNA equations. The solver independently derives node-voltage/current transfer functions from those declarations. Formula checks compare algebraic residuals, not formula strings.
3. Knowledge organization: stable IDs, learning goals, acyclic prerequisite references, claim/formula links, and formal-span mappings. A knowledge node becomes complete only after all of its declared claims and formulas are covered; a later node cannot use a merely introduced prerequisite.
4. Formal master: versioned, ordered source spans with a content identity. Every caption refers to one entire master span, in order, by integer Unicode-code-point offsets and exact slice hash. There is no independent caption-text field or summary fallback. These are content references, not timed or display-ready captions.
5. Technical export: on success, emit canonical narration plus compatible full-span caption references and the identity-bound gate report. On any failure, emit a localized BLOCKED error and no narration export. The CLI exits 1 on failure.

## Mathematical validation boundaries

The supported model is a small linear homogeneous circuit with constant positive R/C parameters and rational controlled-source coefficients. Component values may not depend on the excitation. An AST parser constructs SymPy expressions without eval or arbitrary sympify. Parameter denominators must be provably nonzero before cancellation. Unknown symbols, unsupported syntax and operations, dimensionally inconsistent sums, invalid coefficient domains, nonunique circuits and nonzero formula residuals block export.

Supported derivation operations:

- `mna_transfer`: solve V(node)/I(input), optionally evaluate s=0 and/or negate for a positive magnitude definition.
- `mna_zero_limit`: explicitly take a positive model parameter to zero from above. It does not rewrite a finite model's assumptions or represent arbitrary substitutions.
- `second_order_omega0` and `second_order_Q`: derive parameters from the solved all-pole second-order denominator with positive coefficients. Natural angular frequency must be labeled rad/s, not Hz.
- `noise_projection`: only a two-node parallel R/C null network with explicit unilateral input-voltage-noise assumptions. A constant positive transconductance and separately nonnegative adopted white PSD laws are required. Frequency must be explicitly in Hz. This validates projection algebra under declared laws, not semiconductor noise physics or arbitrary transistor topologies.

The report distinguishes symbol structure, dimensional consistency, exact algebra, and numerical spot evaluation. The latter evaluates expressions at illustrative parameters; it is not an independent circuit simulator or measured evidence. Mandatory known-role assumptions are checked. Other assumption-to-hardware and source-to-topology compatibility remain review obligations.

General theorem proving, nonlinear circuits, arbitrary SPICE/device models, active source authentication, source rights ownership, physical process validity, prose truth, pedagogical quality and exhaustive source extraction are unsupported. A well-formed hash cannot prove those properties.

## Coverage and failures

The ledger uses `scripted`, `verified_model_only`, `source_only`, and `blocked`. A source-only or blocked claim cannot enter the formal script. Unscripted ledger items do not falsely count as teaching coverage. The scope is the explicitly selected claim set, not every assertion on a source page or every page in a document.

Errors include exact locations and distinguish missing/tampered sources, artifact/source mismatch, assumption conflicts, dangling or one-way links, unknown symbols, unit/convention failures, invalid algebra, unsupported noise models, prerequisite order, incomplete formal coverage and stale/partial caption references. Unsupported or invalid formulas stop the entire candidate export; unrelated source-only ledger entries remain reviewable without being silently promoted into content.

The public suite includes persisted negative cases for the four required categories (missing source, assumption conflict, dangling reference, and script coverage), plus false algebra with valid units, expression misuse, nonlinear coefficient injection, unsafe paths, stale masters, summary captions, reciprocal links, prerequisite completeness and restricted-noise guardrails.

## Integrated production seam

The version-2 content workflow calls `export_formal` through the independent
`scripts/prefreeze_gate.py` bridge before voice, timing or rendering. Read
[prefreeze integration](prefreeze-integration.md) for exact inputs/outputs,
canonical formula/semantic links, failure behavior, hash invalidation and legacy
labels. Source-only evidence runs still work with the standalone CLI.

No default bridge silently substitutes a script into an unrelated visual template.
The original RC integration fixture supplies an explicit, matching model/diagram.
The current one-model route is bounded and machine-checked, not whole-skill or
scientific acceptance. Private lecture evidence is never part of the public fixtures.
