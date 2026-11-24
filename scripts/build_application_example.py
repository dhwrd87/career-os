#!/usr/bin/env python3
"""Exercise the complete local journey with existing fictional personas."""
import argparse,copy,json,sys
from pathlib import Path
from careeros import experience,journey,opportunity
from careeros.core.io import atomic_write_json,read_json
ROOT=Path(__file__).resolve().parents[1]
NOW='2026-11-24T12:00:00Z'


def build(output):
    if output.exists() and any(output.iterdir()):raise FileExistsError('Use an empty example folder.')
    output.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(ROOT/'tests/e2e'))
    from test_application_journey import fresh,job
    results=[]
    for persona in ['early-career','career-changer','experienced-multi-role']:
        target=output/persona;fixture,setup=fresh(target,persona,multiple=persona=='career-changer')
        directions=journey.career_directions(target,[0,1] if persona=='career-changer' else [0],approved=True,actor='fictional-example-owner',timestamp=NOW)
        catalog=[]
        for number in range(2 if persona=='career-changer' else 1):
            raw=job(target,fixture,key=f'{persona}-example-{number}',letter='REQUIRED' if number==0 else 'NOT_ACCEPTED')
            if number:raw['role_title']='Training Coordinator'
            if persona=='experienced-multi-role':
                raw['location']='Sacramento, CA (Hybrid)'
                raw['job_description']+=' This fictional position uses a hybrid schedule in Sacramento.'
            raw['source_url']='https://example.org/'
            raw.pop('application_url',None);raw.pop('application_url_source',None)
            # The source and form here are fictional. No sample URL is claimed
            # to be a verified real employer application.
            raw['application_question_source']['url']='https://example.org/'
            raw['application_question_source']['method']='SYNTHETIC_EXAMPLE'
            path=target/'sources/job.json';atomic_write_json(path,raw);opportunity.ingest(target,path,timestamp=NOW);catalog.append(raw)
        borderline=read_json(fixture/'opportunity/borderline.json');path=target/'sources/stretch.json';atomic_write_json(path,borderline);opportunity.ingest(target,path,timestamp=NOW)
        dream=copy.deepcopy(borderline);dream['opportunity_id']=persona+'-dream';dream['role_title']='Senior '+dream['role_title']
        if persona=='experienced-multi-role':
            for item in [borderline,dream]:item['location']='Sacramento, CA (Hybrid)'
            atomic_write_json(target/'sources/stretch.json',borderline);opportunity.ingest(target,target/'sources/stretch.json',timestamp=NOW)
        atomic_write_json(target/'sources/dream.json',dream);opportunity.ingest(target,target/'sources/dream.json',timestamp=NOW)
        request={'prepare_top':0,'dream_roles':[dream['role_title']]};journey.find_jobs(target,request,timestamp=NOW)
        batch=journey.prepare(target,top=5,timestamp=NOW)
        if batch['packages_prepared']!=len(catalog):raise AssertionError(batch)
        plans=[journey.plan(target,v['opportunity_id'],timestamp=NOW) for v in [borderline,dream]]
        first=batch['results'][0];interview=experience.interview(target,first['opportunity_id'],timestamp=NOW)
        # These are explicitly fictional reported events, not external actions.
        for event in ['SUBMITTED','INTERVIEW_INVITED','REJECTED']:
            experience.record_event(target,first['application_id'],{'event_type':event,'actor':'fictional-example-owner','occurred_at':NOW,'human_confirmed':True},timestamp=NOW)
        experience.analytics(target,timestamp=NOW);experience.dashboard(target)
        results.append({'persona':persona,'master':setup['outputs']['master_recruiter_resume'],'master_qa':directions['master']['qa'],'bases':directions['bases'],'packages':batch['results'],'development_plans':plans,'interview_qa':interview['qa'],'external_actions':0})
    result={'status':'PASS','personas':results,'synthetic_only':True,'external_actions':0};atomic_write_json(output/'journey-results.json',result);return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();result=build(args.output.resolve());print(json.dumps({'status':result['status'],'personas':len(result['personas']),'packages':sum(len(v['packages']) for v in result['personas']),'external_actions':0}))
