#!/usr/bin/env python3
"""Independent, fail-closed P1 -> P0 boundary; no renderer, TTS or publication.

This gate validates current evidence, never a previously saved PASS report.
The bounded bridge accepts one complete declared model. Visual geometry and
source/prose interpretation remain review obligations, not mathematical proofs.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import source_model_gate as gate

VERSION = 'p1-p0-prefreeze-1'
STATUS = 'MACHINE_CHECKS_PASSED_REVIEW_REQUIRED'
ROOT = Path(__file__).resolve().parents[1]


def need(condition, code, location, message):
    gate.need(condition, code, location, message)


def implementation_identity():
    files = {name: gate.sha(ROOT/name) for name in (
        'scripts/source_model_gate.py', 'scripts/prefreeze_gate.py',
        'schemas/source-model-script.schema.json')}
    return {'files': files, 'dependencies': {
        name: importlib.metadata.version(name) for name in ('sympy', 'jsonschema')}}


def projected_sources(evidence):
    return [{'id': s['id'], 'locator': s['path'], 'basis': s['rights'], 'sha256': s['sha256']}
            for s in evidence['sources']]


def projected_knowledge(evidence):
    # Source references are mechanically inherited, never invented from prose.
    claims = {c['id']: c for c in evidence['claims']}
    regions = {r['id']: r for r in evidence['regions']}
    nodes = []
    for k in evidence['knowledge']:
        sources = sorted({regions[r]['source_ref'] for c in k['claim_refs']
                          for r in claims[c]['region_refs']})
        nodes.append({'id': k['id'], 'statement': k['goal'], 'source_refs': sources})
    return {'nodes': nodes, 'edges': [{'from': before, 'to': k['id'], 'type': 'prerequisite'}
                                     for k in evidence['knowledge'] for before in k['prerequisite_ids']]}


def formula_latex(model, formula):
    expression, _ = gate.model_context(model, 'visual_formula')
    value, _ = expression.parse(formula['expression'], 'visual_formula.'+formula['id'])
    return gate.sp.latex(value)


def prepare(package, source_root):
    """Return an export + binding only after every P1/P0 relation passes.

    No files are written here. Failure returns no export and callers must stop.
    Voice adaptations/layout coordinates are not formal-content dependencies.
    """
    need(package.get('schema_version') == 'circuit-content-package-2', 'GATE_REQUIRED', '$',
         'This bridge requires evidence-gated content package version 2')
    need(source_root is not None, 'SOURCE_ROOT_REQUIRED', '$', 'An explicit source root is required')
    evidence = package.get('source_model_evidence')
    need(isinstance(evidence, dict), 'GATE_REQUIRED', 'source_model_evidence', 'Missing P1 evidence package')
    exported = gate.export_formal(evidence, Path(source_root))
    content = package['content']
    formal = [{'id': n['id'], 'text': n['text']} for n in content['narration']]
    need(formal == exported['narration'], 'FORMAL_EXPORT_MISMATCH', 'content.narration',
         'Formal IDs, full text and order must exactly match the validated master')
    need(package['caption_refs'] == exported['caption_refs'], 'CAPTION_EXPORT_MISMATCH', 'caption_refs',
         'Only the full ordered caption references from the validated master are allowed')
    need(content['sources'] == projected_sources(evidence), 'SOURCE_EXPORT_MISMATCH', 'content.sources',
         'Source identities must match the checked source ledger')
    need(content['knowledge_graph'] == projected_knowledge(evidence), 'KNOWLEDGE_EXPORT_MISMATCH',
         'content.knowledge_graph', 'Knowledge IDs, source links and prerequisites must match checked evidence')
    need(len(evidence['models']) == 1, 'BRIDGE_SCOPE', 'models',
         'The bounded visual bridge supports one complete model, not automatic multi-model composition')
    model = evidence['models'][0]
    semantic = content['semantic_model']
    need(semantic['id'] == model['id'] and semantic['nets'] == model['nodes'] and
         semantic['assumptions'] == model['assumption_refs'], 'MODEL_EXPORT_MISMATCH', 'content.semantic_model',
         'Stable model, net and assumption IDs must match the checked declaration')
    declared = {c['id']: c for c in model['components']}
    actual = {c['id']: c for c in semantic['components']}
    need(len(actual) == len(semantic['components']) and set(actual) == set(declared),
         'MODEL_EXPORT_MISMATCH', 'content.semantic_model.components', 'Complete component IDs required')
    for cid, component in declared.items():
        terminals = {key: component[key] for key in ('from', 'to', 'control_from', 'control_to') if key in component}
        need(actual[cid]['kind'] == component['kind'] and actual[cid]['terminals'] == terminals,
             'MODEL_EXPORT_MISMATCH', 'components.'+cid, 'Component kind and directed terminals changed')
    formulas = {f['id']: f for f in model['formulas']}
    links = {f['id']: f for f in semantic['formulas']}
    need(len(links) == len(semantic['formulas']) and set(links) == set(formulas),
         'FORMULA_EXPORT_MISMATCH', 'content.semantic_model.formulas', 'Complete formula IDs required')
    objects = {o['id']: o for o in package['visual']['objects']}
    for fid, formula in formulas.items():
        link = links[fid]
        expected_knowledge = sorted(k['id'] for k in evidence['knowledge'] if fid in k['formula_refs'])
        need(sorted(link['knowledge_refs']) == expected_knowledge and sorted(link['component_refs']) == sorted(declared),
             'FORMULA_EXPORT_MISMATCH', 'formulas.'+fid, 'Formula knowledge/model component links changed')
        obj = objects.get(link['object_ref'], {})
        need(obj.get('kind') == 'formula' and obj.get('latex') == formula_latex(model, formula),
             'FORMULA_VISUAL_MISMATCH', 'formulas.'+fid,
             'Displayed expression must be the canonical LaTeX of the checked expression; use a separate label')
    # This input identity binds content and visual semantic expressions, not
    # acoustic voice choices or positions. Those are independently bound by P0.
    inputs = {'content_version': package['schema_version'], 'evidence': evidence,
              'sources': content['sources'], 'knowledge_graph': content['knowledge_graph'],
              'semantic_model': semantic, 'formal_narration': formal, 'caption_refs': package['caption_refs'],
              'visual_semantics': [{k: o[k] for k in ('id', 'kind', 'latex') if k in o}
                                   for o in package['visual']['objects']]}
    binding = {'schema_version': 'prefreeze-evidence-binding-1', 'gate_version': gate.VERSION,
               'bridge_version': VERSION, 'implementation': implementation_identity(),
               'input_sha256': gate.digest(inputs), 'evidence_package_sha256': gate.digest(evidence),
               'master_sha256': exported['gate_report']['master_sha256'],
               'output_sha256': gate.digest(exported), 'status': STATUS,
               'scientific_approval': False, 'audiovisual_approval': False, 'publication_allowed': False,
               'validity_scope': 'checked_input_snapshot_revalidate_on_each_content_workflow_invocation'}
    return {'schema_version': 'prefreeze-formal-artifact-1', 'binding': binding, 'export': exported}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    try:
        result = prepare(json.loads(args.package.read_text()), args.package.parent)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        error = exc.record() if isinstance(exc, gate.GateError) else {'code': 'INVALID_PACKAGE', 'message': str(exc)}
        print(json.dumps({'status': 'BLOCKED', 'error': error, 'formal_export_allowed': False,
                          'scientific_approval': False, 'publication_allowed': False}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
