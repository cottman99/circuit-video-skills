"""Author the original RC demonstration from explicit IDs, never from prose."""
from pathlib import Path
import copy
import json
import shutil
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from prefreeze_gate import projected_sources, projected_knowledge, formula_latex

def build():
    evidence = json.loads((ROOT/'fixtures/original_rc.json').read_text())
    model = evidence['models'][0]
    base = json.loads((ROOT/'examples/resistor-divider/content-package.json').read_text())
    objects = copy.deepcopy(base['visual']['objects'][:4])
    objects[1]['text'] = 'Original parallel RC model'
    objects[2]['text'] = 'Positive constant R, C; zero initial conditions'
    objects[3]['text'] = 'Original source; machine checks are not scientific review'
    def line(id, points):
        xs, ys = zip(*points)
        objects.append(dict(id='model.'+id,kind='line',points=points,
                            world_bounds=[min(xs),min(ys),max(1,max(xs)-min(xs)),max(1,max(ys)-min(ys))],stroke='#252a30',width=3))
    def text(id, value, x, y, size=30):
        objects.append(dict(id='model.'+id,kind='text',text=value,xy=[x,y],world_bounds=[x,y,1,1],size=size,typography_role='body'))
    line('top-bus',[[300,300],[700,300]])
    line('bottom-bus',[[400,650],[700,650]])
    line('r-top',[[400,300],[400,390]])
    objects.append(dict(id='model.r',kind='rect',world_bounds=[370,390,60,120],stroke='#252a30',width=3))
    line('r-bottom',[[400,510],[400,650]])
    line('c-top',[[700,300],[700,430]])
    line('c-plate1',[[660,430],[740,430]])
    line('c-plate2',[[660,465],[740,465]])
    line('c-bottom',[[700,465],[700,650]])
    line('input',[[160,300],[300,300]])
    line('input-arrow',[[280,285],[300,300],[280,315]])
    line('ground',[[550,650],[550,700]])
    line('ground-bar',[[520,700],[580,700]])
    text('input-label','i',190,245)
    text('node-label','n: v',430,240)
    text('r-label','R',455,430)
    text('c-label','C',760,430)
    text('ground-label','gnd',515,720)
    text('impedance-label','Impedance Z(s)',1000,280)
    text('dc-label','DC limit Z(0)',1000,560)
    for fid, y in [('impedance',350),('dc',630)]:
        formula = next(f for f in model['formulas'] if f['id']==fid)
        objects.append(dict(id='model.'+fid,kind='formula',latex=formula_latex(model,formula),world_bounds=[1000,y,1,1],font_size=46))
    ids = [o['id'] for o in objects]
    visual = copy.deepcopy(base['visual']);visual['objects']=objects;visual['required_object_ids']=ids;visual['boards'][0]['object_refs']=ids
    semantic={'id':model['id'],'assumptions':model['assumption_refs'],'nets':model['nodes'],
              'components':[dict(id=c['id'],kind=c['kind'],terminals={'from':c['from'],'to':c['to']},object_refs=(['model.r','model.r-label'] if c['id']=='r' else ['model.c-plate1','model.c-plate2','model.c-label'])) for c in model['components']],
              'formulas':[dict(id=f['id'],object_ref='model.'+f['id'],component_refs=['r','c'],knowledge_refs=[k['id'] for k in evidence['knowledge'] if f['id'] in k['formula_refs']]) for f in model['formulas']]}
    captions=[dict(id=c['id'],narration_id=c['span_id'],source_range=c['source_range']) for c in evidence['caption_refs']]
    narration=[dict(id=s['id'],text=s['text']) for s in evidence['master']['sentences']]
    actions=[dict(id='reveal-'+fid,target='model.'+fid,narration_id=sid,earliest_offset=.2,deadline_offset=0,min_reveal_seconds=.5,min_read_seconds=1.2,after=before) for fid,sid,before in [('impedance','s-derive',[]),('dc','s-limit',['reveal-impedance'])]]
    package={'schema_version':'circuit-content-package-2','title':'Original RC evidence-to-preview fixture',
             'source_model_evidence':evidence,'content':{'sources':projected_sources(evidence),'knowledge_graph':projected_knowledge(evidence),'semantic_model':semantic,'narration':narration},'visual':visual,'voice':base['voice'],'caption_refs':captions,
             'temporal':{'actions':actions,'caption_max_codepoints_per_second':30,'caption_min_seconds':.5},
             'synthetic_fixture':{'schema_version':'synthetic-sentence-fixture-1','sentences':[dict(narration_id=n['id'],duration_seconds=d,gap_before_seconds=.2) for n,d in zip(narration,[4.5,4,4.5])],'tail_seconds':.4}}
    return package

if __name__ == '__main__':
    target=ROOT/'examples/rc-evidence';target.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'fixtures/original_rc_source.txt',target/'original_rc_source.txt')
    (target/'content-package.json').write_text(json.dumps(build(),indent=2)+'\n')
