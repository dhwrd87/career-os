#!/usr/bin/env python3
"""Show the connected job-search journeys using fictional records only."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
from careeros import experience, journey
from careeros.core.io import atomic_write_json, read_json
ROOT=Path(__file__).resolve().parents[1]
NOW='2026-10-02T12:00:00Z'

def build(target):
    fixture=ROOT/'fixtures/synthetic'
    strong=read_json(fixture/'career-changer/opportunity/strong.json')
    other=copy.deepcopy(strong)
    other.update(opportunity_id='example-training-coordinator',role_title='Training Coordinator',employer_name='Example Learning Services',job_description='Example Learning Services seeks a Training Coordinator. Required: Process Mapping, Training and Data Cleanup.')
    dream=read_json(fixture/'learning/job.json')
    dream.update(opportunity_id='example-dream-role',role_title='Data Operations Lead',job_description=dream['job_description'].replace('Implementation Analyst','Data Operations Lead'))
    atomic_write_json(target/'sources/job-search.json',[strong,other,read_json(fixture/'career-changer/opportunity/borderline.json'),dream])
    found=journey.find_jobs(target,{'catalog':'sources/job-search.json','locations':['Remote US'],'dream_roles':['Data Operations Lead'],'prepare_top':2},timestamp=NOW)
    roles=journey.suggest_roles(target,timestamp=NOW)
    goal=journey.plan(target,'example-dream-role',catalog=target/'sources/learning-courses.json',timestamp=NOW)
    for draft in found['resume_batch']['results']:
        if draft.get('build_id'):experience.export_resume(target,draft['build_id'])
    experience.dashboard(target)
    return {'categories':found['categories'],'resumes_prepared':found['resume_batch']['prepared'],'other_role_ideas':len(roles['lanes']),'dream_plan':goal['path'],'canonical_mutations':0,'external_actions':0,'synthetic_only':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True,type=Path)
    print(json.dumps(build(parser.parse_args().workspace),indent=2))
