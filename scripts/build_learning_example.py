#!/usr/bin/env python3
"""Add a source-traced synthetic learning module to a synthetic demo workspace."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
from careeros import experience, opportunity, learning_workflow as learning
from careeros.core.io import read_json,atomic_write_json
ROOT=Path(__file__).resolve().parents[1]
NOW='2026-10-02T12:00:00Z'

def build(target):
    source=ROOT/'fixtures/synthetic/learning'
    for name in ('job.json','courses.json','preferences.json'):
        shutil.copyfile(source/name,target/'sources'/('learning-'+name))
    opp,_=opportunity.ingest(target,target/'sources/learning-job.json',timestamp=NOW)
    opportunity.qualify(target,opp['opportunity_id'],timestamp=NOW)
    learning.preferences(target,read_json(target/'sources/learning-preferences.json'))
    result=learning.build(target,target/'sources/learning-courses.json',timestamp=NOW)
    step=next(s for s in result['steps'] if s['step_type']=='PROJECT' and 'Python' in s['title'])
    artifact=target/'sources/learning-project.txt'
    artifact.write_text('SYNTHETIC EXAMPLE ONLY\nPython exercise: read three fictional CSV rows, handled missing values, asserted row counts. This example records a learning project, not professional employment.\n')
    for state in ('IN_PROGRESS','COMPLETED','VERIFIED'):
        learning.record_progress(target,{'step_id':step['learning_step_id'],'state':state,'actor':'synthetic-human','source':'SYNTHETIC_DEMO','artifacts':['sources/learning-project.txt'],'human_confirmed':True},timestamp=NOW)
    changeset=learning.propose_profile_update(target,{'step_id':step['learning_step_id'],'actor':'synthetic-human','summary':'Completed a synthetic Python CSV exercise with missing-value and row-count tests.','actions':['Read fictional CSV rows','Tested missing values','Asserted row counts'],'skill_claims':[{'name':'Python','proficiency':'PRACTICED'}]},timestamp=NOW)
    learning.reassess(target,timestamp=NOW)
    experience.dashboard(target)
    return {'status':'PASS','gaps':len(result['gap_priorities']),'steps':len(result['steps']),'evidence_plans':len(result['evidence_plans']),'qa':result['qa'],'pending_changeset':changeset['changeset_id'],'canonical_mutations':0,'external_actions':0}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True);args=parser.parse_args();print(json.dumps(build(args.workspace),indent=2))
