"""Public original fixtures only. No lecture, image, private hash, or network."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'fixtures'))
from source_model_gate import GateError, validate, export_formal, digest, sha
from build_original_fixture import bind_master, make
FIX=ROOT/'fixtures'

def load(name):return json.loads((FIX/name).read_text())
def mutate(p,edits):
    for edit in edits:
        target=p
        for segment in edit['path'][:-1]: target=target[segment]
        key=edit['path'][-1]
        if edit.get('remove'): del target[key]
        else: target[key]=edit['value']
    return p

class SourceModelGateTests(unittest.TestCase):
    def test_original_parallel_rc(self):
        r=validate(load('original_rc.json'),FIX)
        self.assertEqual(r['status'],'MACHINE_CHECKS_PASSED_REVIEW_REQUIRED')
        self.assertEqual([f['residual'] for f in r['checks']['formulas']],['0','0'])
        self.assertFalse(r['downstream']['scientific_approval'])
        self.assertFalse(r['downstream']['publication_allowed'])

    def test_original_noise_projection(self):
        r=validate(load('original_noise_projection.json'),FIX)
        self.assertEqual(r['checks']['formulas'][0]['noise_evidence_scope'],'Projection algebra under adopted PSD laws')

    def test_exact_formal_export(self):
        p=load('original_rc.json'); out=export_formal(p,FIX)
        self.assertEqual([n['text'] for n in out['narration']],[s['text'] for s in p['master']['sentences']])
        self.assertEqual([c['text'] for c in out['gate_report']['resolved_captions']],[s['text'] for s in p['master']['sentences']])
        self.assertEqual(out['gate_report']['package_sha256'],digest(p))

    def test_negative_fixtures_block_export(self):
        for spec in load('negative_cases.json'):
            with self.subTest(spec['id']):
                p=mutate(load(spec['base']),spec['edits'])
                if spec.get('edit_master'): bind_master(p)
                with self.assertRaises(GateError) as ctx:export_formal(p,FIX)
                self.assertEqual(ctx.exception.code,spec['expected'],str(ctx.exception))
                self.assertTrue(ctx.exception.location)

    def test_excitation_dependent_component_rejected(self):
        p=load('original_rc.json');m=p['models'][0]
        m['parameters'].append(dict(id='I0',unit='A',domain='positive',sample=.001,meaning='Reference current'))
        m['components'][0]['value']='R*(1+(iin/I0)**2)'
        with self.assertRaises(GateError) as ctx:export_formal(p,FIX)
        self.assertEqual(ctx.exception.code,'NONLINEAR_MODEL')

    def test_no_excitation_substitution(self):
        p=load('original_rc.json');p['models'][0]['formulas'][0]['derivation']['substitute']={'iin':'0'}
        with self.assertRaises(GateError) as ctx:export_formal(p,FIX)
        self.assertEqual(ctx.exception.code,'SCHEMA')

    def test_source_path_cannot_escape_root(self):
        p=load('original_rc.json');p['sources'][0]['path']='../scripts/source_model_gate.py'
        with self.assertRaises(GateError) as ctx:validate(p,FIX)
        self.assertEqual(ctx.exception.code,'SOURCE_PATH')

    def test_unrelated_sentence_knowledge_rejected(self):
        p=load('original_rc.json');p['master']['sentences'][1]['knowledge_refs']=['setup'];bind_master(p)
        with self.assertRaises(GateError) as ctx:validate(p,FIX)
        self.assertEqual(ctx.exception.code,'REFERENCE_MISMATCH')

    def test_numerical_spot_label_does_not_claim_simulation(self):
        r=validate(load('original_rc.json'),FIX)
        self.assertTrue(all(f['numeric_evidence_kind']=='SPOT_EVALUATION_NOT_INDEPENDENT_CIRCUIT_SIMULATION' for f in r['checks']['formulas']))

    def test_parameter_domain_hole_cannot_cancel(self):
        p=load('original_rc.json');m=p['models'][0]
        m['parameters'].append(dict(id='x',unit='1',domain='nonnegative',sample=1,meaning='May equal zero'))
        m['components'][0]['value']='R*x/x'
        with self.assertRaises(GateError) as ctx:validate(p,FIX)
        self.assertEqual(ctx.exception.code,'EXPRESSION_DOMAIN')

    def test_original_text_cannot_use_unrelated_artifact(self):
        p=load('original_rc.json');r=p['regions'][0]
        r['artifact_path']='original_rc.json';r['artifact_sha256']=sha(FIX/'original_rc.json')
        with self.assertRaises(GateError) as ctx:validate(p,FIX)
        self.assertEqual(ctx.exception.code,'SOURCE_ARTIFACT_MISMATCH')

    def test_nonlinear_declaration_cannot_opt_out_of_linear_role(self):
        p=load('original_rc.json');p['assumptions'][0]['value']=False
        for f in p['models'][0]['formulas']:f['requirements']['linear_small_signal']=False
        with self.assertRaises(GateError) as ctx:validate(p,FIX)
        self.assertEqual(ctx.exception.code,'ASSUMPTION_CONFLICT')

    def test_natural_angular_frequency_cannot_be_hz(self):
        p=load('original_rc.json');f=p['models'][0]['formulas'][0]
        f['expression']='1/(R*C)';f['unit']='Hz';f['derivation']={'operation':'second_order_omega0','node':'n'}
        with self.assertRaises(GateError) as ctx:validate(p,FIX)
        self.assertEqual(ctx.exception.code,'FREQUENCY_CONVENTION')

    def test_cli_failure_emits_no_formal_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=load('original_rc.json');p['sources'][0]['path']='absent.txt'
            (root/'bad.json').write_text(json.dumps(p))
            result=subprocess.run([sys.executable,str(ROOT/'scripts/source_model_gate.py'),str(root/'bad.json'),'--export-formal'],capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            out=json.loads(result.stdout)
            self.assertEqual(out['status'],'BLOCKED');self.assertNotIn('narration',out)
            self.assertFalse(out['downstream']['technical_formal_export_allowed'])
            self.assertEqual(out['error']['code'],'SOURCE_MISSING')

if __name__=='__main__':unittest.main()
