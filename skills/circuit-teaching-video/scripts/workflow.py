#!/usr/bin/env python3
"""Mandatory transformation entrypoint for knowledge-canvas storyboard plans.
Legacy rendering remains in its existing compiler; this command never renders.
"""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
from plan_knowledge import normalize, canonical

def run(mode, plan):
    if mode!='knowledge-canvas': raise ValueError('Unsupported workflow mode')
    normalized=normalize(plan)  # No pass-through or skip-validation option.
    return {'schema_version':'1.0','mode':mode,'status':'storyboard_plan_only',
            'normalized_plan':normalized,
            'completed_nodes':['knowledge_structure_normalization','local_board_preservation_plan','camera_visit_resolution'],
            'pending':['expert_semantic_review','adapter_mapping_and_capability_check','measured_audio_timing_if_requested','actual_render_and_review_if_requested'],
            'scope':'No media, TTS, source verification, or global-camera renderer produced'}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',required=True,choices=['knowledge-canvas']);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:
        result=run(a.mode,json.loads(a.plan.read_text()))
        if a.output.resolve()==a.plan.resolve(): raise ValueError('Output must not overwrite author input')
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(canonical(result))
        print(json.dumps({'passed':True,'output':str(a.output),'status':result['status']}));return 0
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as e:
        print(json.dumps({'passed':False,'errors':[str(e)]}));return 1
if __name__=='__main__': sys.exit(main())
