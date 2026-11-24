#!/usr/bin/env python3
"""Render all recruiter surfaces from an existing synthetic persona matrix.

Uses the same approved profile and posting in each run. It makes no external
requests. Scores and preferences are internal observations, not human feedback.
"""
from __future__ import annotations
import argparse,json,shutil
from pathlib import Path
from careeros import career_outputs,experience,lane_base,opportunity,resume,workspace
from careeros.core.io import read_json,atomic_write_json,sha256_value


def run(matrix_root:Path,output:Path,jobs:list[dict]):
    rows=[]
    for sample in jobs:
        persona=sample['persona'];source=matrix_root/persona/'workspace';target=output/persona/'workspace'
        if not target.exists():shutil.copytree(source,target,ignore=shutil.ignore_patterns('.cache','__pycache__'))
        before=workspace.canonical_state_hash(target)
        master=career_outputs.build_master_resume(target,timestamp='2026-10-03T21:00:00Z')
        base=lane_base.build_lane_base(target,accept=True,actor='synthetic-review',timestamp='2026-10-03T21:00:00Z')
        atomic_write_json(target/'sources/copy-review-job.json',sample['job'])
        job,_=opportunity.ingest(target,target/'sources/copy-review-job.json',timestamp='2026-10-03T21:00:00Z')
        opportunity.qualify(target,job['opportunity_id'],timestamp='2026-10-03T21:00:00Z')
        build,content,artifact=resume.build(target,job['opportunity_id'],timestamp='2026-10-03T21:00:00Z');validation,_=resume.validate(target,build['build_id'])
        letter=experience.cover_letter(target,job['opportunity_id'],build['build_id']) if validation['status']=='PASS' else None
        docx=experience.export_resume(target,build['build_id']) if validation['status']=='PASS' else None
        assert workspace.canonical_state_hash(target)==before
        profile=read_json(target/'state/profile/career-profile.json')
        rows.append({'persona':persona,'target':job['role_title'],'profile_hash':sha256_value(profile),'master':master['path'],'master_validation':master['qa']['status'],'cover_letter_status':letter['status'] if letter else 'HELD','lane':base['artifact']['path'],'lane_validation':base['validation']['status'],'tailored':artifact['path'],'tailored_validation':validation['status'],'failed_gates':[g['gate'] for g in validation['gates'] if g['status']=='FAIL'],'build_id':build['build_id'],'docx':docx['path'] if docx else None,'cover_letter':letter['artifacts'][0]['path'] if letter else None,'summary':content['summary'],'copy_quality':content['recruiter_copy_quality_v2'],'canonical_mutations':0,'external_actions':0})
    result={'schema':'careeros.synthetic-copy-review.v1','personas':rows,'status':'PASS' if all(r['master_validation']=='PASS' and r['lane_validation']=='PASS' and r['tailored_validation']=='PASS' and r['cover_letter'] for r in rows) else 'REVIEW_REQUIRED','assessment_basis':'Internal executable checks; not independent human feedback or competitor preference.'}
    output.mkdir(parents=True,exist_ok=True);atomic_write_json(output/'review-results.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--matrix-root',type=Path,required=True);p.add_argument('--jobs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.matrix_root,a.output,read_json(a.jobs));print(json.dumps({'status':r['status'],'personas':len(r['personas']),'failed':[{k:v[k] for k in ('persona','failed_gates')} for v in r['personas'] if v['failed_gates']]},indent=2))
