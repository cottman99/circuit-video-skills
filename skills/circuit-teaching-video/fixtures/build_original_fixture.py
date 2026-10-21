"""Build only original public mathematical fixtures, no private-source dependencies."""
import copy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'scripts'))
from source_model_gate import digest,sha

def bind_master(p):
    m=p['master']; m['paragraphs']=[{'id':'derivation','sentence_ids':[s['id'] for s in m['sentences']]}]
    m['sha256']=digest({k:v for k,v in m.items() if k!='sha256'})
    p['caption_refs']=[{'id':'cap-'+s['id'],'span_id':s['id'],'source_range':[0,len(s['text'])],'master_sha256':m['sha256'],'slice_sha256':hashlib.sha256(s['text'].encode()).hexdigest()} for s in m['sentences']]
    return p

def make():
    sourcehash=sha(ROOT/'original_rc_source.txt')
    claim=lambda id,text,fs:dict(id=id,text=text,kind='derived_result' if fs else 'source_statement',region_refs=['r-source'],model_refs=['rc'],formula_refs=fs,coverage_status='scripted',coverage_note='Covered in the original complete formal derivation.',review_status='not_professionally_reviewed')
    assumption={'id':'a-linear','fact':'linear_small_signal','value':True,'statement':'Positive constant R and C; linear time-invariant, zero initial conditions.','origin':'original_fixture','region_refs':['r-source']}
    formula=lambda id,exp,method:dict(id=id,expression=exp,unit='ohm',requirements={'linear_small_signal':True},derivation=method,steps=['Stamp currents through R and C from n to ground.','Equate their sum to injected current and solve.'],claim_refs=['c-'+id])
    p={'schema_version':'source-model-script-1','scope':{'title':'Original RC current-driven fixture','pages':[1],'not_full_course':True,'rights':'Original public fixture.'},
       'sources':[dict(id='source',path='original_rc_source.txt',sha256=sourcehash,page_count=1,media_type='text/plain',authority='Original authored ideal-model fixture.',rights='original_public_fixture')],
       'regions':[dict(id='r-source',source_ref='source',page=1,bbox=[0,0,1,1],coordinate_system='original_text_whole_document',artifact_path='original_rc_source.txt',artifact_sha256=sourcehash,render_recipe='not_applicable',description='Complete original text, no external source or image.',inspection=dict(status='original_text_inspected',method='Author inspected original text and model.',limitation='No independent physical validation.'))],
       'claims':[claim('c-model','R and C connect the excited node to ground.',[]),claim('c-impedance','Z=R/(1+sRC).',['impedance']),claim('c-dc','DC impedance is R.',['dc'])],
       'assumptions':[assumption],
       'models':[dict(id='rc',role='linear_circuit',description='Original ideal parallel RC.',nodes=['gnd','n'],reference_node='gnd',components=[{'id':'r','kind':'R','from':'n','to':'gnd','value':'R'},{'id':'c','kind':'C','from':'n','to':'gnd','value':'C'}],parameters=[dict(id='R',unit='ohm',domain='positive',sample=1200,meaning='Resistance'),dict(id='C',unit='F',domain='positive',sample=3e-9,meaning='Capacitance')],excitation={'symbol':'iin','from':'gnd','to':'n','unit':'A'},assumption_refs=['a-linear'],source_region_refs=['r-source'],topology_review=dict(status='agent_transcribed_requires_professional_review',notes='Original declared topology, not reconstructed from third-party content.'),formulas=[formula('impedance','R/(1+s*R*C)',{'operation':'mna_transfer','node':'n'}),formula('dc','R',{'operation':'mna_transfer','node':'n','substitute':{'s':'0'}})])],
       'knowledge':[dict(id='kcl',goal='Apply KCL.',prerequisite_ids=[],claim_refs=[],formula_refs=[],assumed_prerequisite=True),dict(id='setup',goal='Identify node and current direction.',prerequisite_ids=['kcl'],claim_refs=['c-model'],formula_refs=[],assumed_prerequisite=False),dict(id='derive',goal='Solve the RC impedance.',prerequisite_ids=['setup'],claim_refs=['c-impedance'],formula_refs=['impedance'],assumed_prerequisite=False),dict(id='limit',goal='Check the DC boundary.',prerequisite_ids=['derive'],claim_refs=['c-dc'],formula_refs=['dc'],assumed_prerequisite=False)],
       'master':{'revision':'original-rc-r1','sentences':[dict(id='s-setup',text='Let current i enter node n, with positive constant R and C connected from n to ground; v is the node voltage.',knowledge_refs=['setup'],claim_refs=['c-model'],formula_refs=[]),dict(id='s-derive',text='KCL gives i = v/R + s C v; dividing by v and then inverting yields Z = v/i = R/(1+s R C).',knowledge_refs=['derive'],claim_refs=['c-impedance'],formula_refs=['impedance']),dict(id='s-limit',text='At s = 0, the capacitor carries no current in this ideal zero-initial-condition model and Z(0) = R.',knowledge_refs=['limit'],claim_refs=['c-dc'],formula_refs=['dc'])]},
       'caption_refs':[],'coverage':dict(required_claim_ids=['c-model','c-impedance','c-dc'],required_formula_ids=['impedance','dc'],required_knowledge_ids=['setup','derive','limit'],excluded_scope=['Physical measurements, speech, rendering, scientific review and publication authorization.'])}
    return bind_master(p)

def noise():
    p=make(); m=p['models'][0]; m['role']='unilateral_noise_null_network'; m['description']='Original abstract unilateral-noise-null RC fixture.'
    facts=['one_sided_per_hz_psd','unilateral_voltage_noise_projection','classical_white_noise_laws','uncorrelated_sources']
    for fact in facts:
        aid='a-'+fact
        p['assumptions'].append(dict(id=aid,fact=fact,value=True,statement='Declared synthetic test assumption: '+fact,origin='original_fixture',region_refs=['r-source']))
        m['assumption_refs'].append(aid)
    m['parameters'] += [dict(id='g',unit='S',domain='positive',sample=.02,meaning='Synthetic transconductance'),dict(id='P',unit='A2/Hz',domain='positive',sample=1e-24,meaning='Synthetic constant source PSD'),dict(id='f',unit='Hz',domain='nonnegative',sample=1e5,meaning='Frequency in Hz')]
    m['formulas']=[dict(id='noise',expression='P*(1+(2*pi*f*R*C)**2)/(g*R)**2',unit='A2/Hz',requirements={f:True for f in facts},derivation=dict(operation='noise_projection',node='n',transconductance='g',intrinsic_psd='P',frequency='f'),steps=['Find the null-network impedance by MNA.','Invert g times impedance and use the squared magnitude at j2pi f.','Multiply by adopted synthetic PSD P, not a device noise-law verification.'],claim_refs=['c-noise'])]
    p['claims']=[dict(id='c-noise',text='The declared null-network projection gives P(1+(2pi fRC)^2)/(gR)^2.',kind='derived_result',region_refs=['r-source'],model_refs=['rc'],formula_refs=['noise'],coverage_status='scripted',coverage_note='Only abstract projection algebra is tested.',review_status='not_professionally_reviewed')]
    p['knowledge']=[dict(id='projection',goal='Check a declared synthetic noise projection.',prerequisite_ids=[],claim_refs=['c-noise'],formula_refs=['noise'],assumed_prerequisite=False)]
    p['master']={'revision':'original-noise-r1','sentences':[dict(id='s-noise',text='For the declared abstract unilateral model, the null-network impedance is R/(1+sRC); the inverse of g times this impedance, squared in magnitude at s=j2pi f, multiplies the positive synthetic PSD P.',knowledge_refs=['projection'],claim_refs=['c-noise'],formula_refs=['noise'])]}
    p['coverage']=dict(required_claim_ids=['c-noise'],required_formula_ids=['noise'],required_knowledge_ids=['projection'],excluded_scope=['No physical source-noise law or device topology is certified.'])
    return bind_master(p)

if __name__=='__main__':
    for name,fn in [('original_rc.json',make),('original_noise_projection.json',noise)]:
        (ROOT/name).write_text(json.dumps(fn(),ensure_ascii=False,indent=2)+'\n')
