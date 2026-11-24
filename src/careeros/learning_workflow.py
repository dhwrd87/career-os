"""Connect Learning Path Intelligence V1 contracts to workspace workflows.

Scoring, course classification, ROI, evidence planning and impact use the
existing learning_path engine. This module owns persistence and lifecycle.
"""
from __future__ import annotations
import copy
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from careeros import learning_path as engine
from careeros.config.loader import load_config
from careeros.core.io import append_jsonl, atomic_write_json, read_json, sha256_file, sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import require_current_workspace, schema_dir, utc_now


def roots_for(workspace):
    require_current_workspace(workspace)
    return load_config(workspace/'careeros.yaml').roots


def _save(roots, relative, value):
    path=roots.assert_write_allowed(roots.state_root/'learning'/relative,'state')
    atomic_write_json(path,value)
    return path


def _completions(roots):
    """Replay the progress journal; projections may be interrupted or absent."""
    path=roots.state_root/'learning/progress-events.jsonl';latest={}
    if not path.exists():return []
    allowed={'NOT_STARTED':'IN_PROGRESS','IN_PROGRESS':'COMPLETED','COMPLETED':'VERIFIED'}
    for line in path.read_text().splitlines():
        event=json.loads(line);previous=latest.get(event['step_id'],{}).get('state','NOT_STARTED')
        if event['prior_state']!=previous or event['state']!=allowed.get(previous):raise ValueError('Learning progress journal has an invalid transition')
        latest[event['step_id']]=event
    return list(latest.values())


def preferences(workspace: Path, values: dict | None = None) -> dict:
    roots=roots_for(workspace);path=roots.state_root/'learning/preferences.json'
    if values is None:return read_json(path) if path.exists() else {}
    allowed={'budget','currency','weekly_hours','weeks_available','max_duration_hours','subscriptions_owned','preferred_providers','learning_styles','self_paced_preference','credential_preference','candidate_level','knowledge_levels','current_knowledge','satisfied_prerequisites','urgency','project_hours','available_tools'}
    if set(values)-allowed:raise ValueError('Unsupported learning preference: '+', '.join(sorted(set(values)-allowed)))
    for key in ('budget','weekly_hours','weeks_available','max_duration_hours','urgency','project_hours'):
        if key in values and (isinstance(values[key],bool) or not isinstance(values[key],(int,float)) or not math.isfinite(values[key]) or values[key]<0 or (key in {'weekly_hours','weeks_available','project_hours'} and values[key]==0)):
            raise ValueError(key+' must be a finite valid number')
    for key in ('subscriptions_owned','preferred_providers','learning_styles','current_knowledge','satisfied_prerequisites','available_tools'):
        if key in values and (not isinstance(values[key],list) or any(not isinstance(v,str) for v in values[key])):raise ValueError(key+' must contain text values')
    if 'currency' in values and (not isinstance(values['currency'],str) or len(values['currency'])!=3):raise ValueError('Use an ISO currency code')
    if values.get('candidate_level') and values['candidate_level'] not in {'BEGINNER','FOUNDATIONAL','INTERMEDIATE','ADVANCED'}:raise ValueError('Invalid candidate level')
    if not isinstance(values.get('knowledge_levels',{}),dict) or any(not isinstance(k,str) or v not in {'BEGINNER','FOUNDATIONAL','INTERMEDIATE','ADVANCED'} for k,v in values.get('knowledge_levels',{}).items()):raise ValueError('knowledge_levels must map capabilities to valid levels')
    if 'self_paced_preference' in values and not isinstance(values['self_paced_preference'],bool):raise ValueError('self_paced_preference must be true or false')
    if values.get('credential_preference','NEUTRAL') not in {'NEUTRAL','PREFERRED','HIGH'}:raise ValueError('Invalid credential preference')
    _save(roots,'preferences.json',values)
    return values


def analyze_gaps(workspace: Path, *, opportunity_ids=None, include_profile_gaps=True, timestamp=None) -> dict:
    roots=roots_for(workspace);profile=read_json(roots.state_root/'profile/career-profile.json');family=read_json(roots.state_root/'role-families/active.json');prefs=preferences(workspace)
    from careeros.updates import require_derivative_current
    require_derivative_current(roots,'CAREER_PROFILE',profile['profile_id'])
    require_derivative_current(roots,'ROLE_FAMILY',family['role_family_id'])
    qualifications=[read_json(p) for p in sorted((roots.state_root/'qualifications').glob('*.json'))]
    qualifications=[q for q in qualifications if q.get('role_family_id')==family['role_family_id'] and (opportunity_ids is None or q['opportunity_id'] in opportunity_ids)]
    for q in qualifications:require_derivative_current(roots,'QUALIFICATION',q['qualification_id'])
    grouped={}
    subtype={'EXPERIENCE':'EXPERIENCE','CREDENTIAL':'CREDENTIAL','EDUCATION':'KNOWLEDGE','TOOL':'TOOL','SKILL':'PRACTICAL_SKILL'}
    for q in qualifications:
        if q.get('role_family_id')!=family['role_family_id']:continue
        opportunity=read_json(roots.state_root/'opportunities'/q['opportunity_id']/'opportunity.json')
        requirements={r['capability'].casefold():r for r in opportunity['requirements']}
        for gap in q.get('gaps',[]):
            capability=gap.get('capability','').strip()
            if not capability or capability=='Job requirements need review':continue
            req=requirements.get(capability.casefold(),{})
            kind=gap.get('gap_type') or subtype.get(gap.get('requirement_subtype') or req.get('requirement_subtype'),'PRACTICAL_SKILL')
            key=(capability.casefold(),kind)
            row=grouped.setdefault(key,{'gap_type':kind,'gap_statement':capability,'source_gap_ids':[],'recurrence_count':0,'hard_gap_frequency':0,'preferred_gap_frequency':0,'provenance':[],'opportunity_ids':[],'requirement_importance':0})
            if q['opportunity_id'] in row['opportunity_ids']:continue
            row['recurrence_count']+=1;row['opportunity_ids'].append(q['opportunity_id']);row['source_gap_ids'].append(q['qualification_id'])
            required=req.get('requirement_class')=='REQUIRED'
            row['hard_gap_frequency']+=int(required and (kind in {'EXPERIENCE','CREDENTIAL'} or gap.get('match')=='HARD_GAP'))
            row['preferred_gap_frequency']+=int(not required)
            row['requirement_importance']=max(row['requirement_importance'],5 if required else 2.5)
            row['provenance'].append({'type':'OBSERVED_JOB_REQUIREMENT','ref':q['qualification_id'],'opportunity_id':q['opportunity_id'],'requirement':capability,'requirement_class':req.get('requirement_class','UNKNOWN')})
    for g in (profile.get('preferences',{}).get('career_gaps',[]) if include_profile_gaps else []):
        statement=g.get('gap_statement') or g.get('capability') or g.get('description')
        if not statement:continue
        kind=str(g.get('gap_type') or 'KNOWLEDGE').upper()
        if kind=='SKILL':kind='PRACTICAL_SKILL'
        grouped.setdefault((statement.casefold(),kind),{**g,'gap_type':kind,'gap_statement':statement,'source_gap_ids':[profile['preferences']['record_id']],'recurrence_count':0,'provenance':[{'type':'APPROVED_CAREER_PREFERENCE','ref':profile['preferences']['record_id']}],'opportunity_ids':[]})
    for skill in (profile.get('skills',[]) if include_profile_gaps else []):
        if not skill.get('evidence_ids'):
            grouped.setdefault((skill['name'].casefold(),'EVIDENCE'),{'gap_type':'EVIDENCE','gap_statement':skill['name'],'source_gap_ids':[skill['record_id']],'recurrence_count':0,'provenance':[{'type':'CANONICAL_SKILL_WITHOUT_EVIDENCE','ref':skill['record_id']}],'opportunity_ids':[]})
    rows=[];source_count=max(1,len(qualifications))
    for row in grouped.values():
        row['job_frequency']=min(5,5*row['recurrence_count']/source_count)
        known=any(row['gap_statement'].casefold()==s['name'].casefold() for s in profile.get('skills',[])) or row['gap_statement'].casefold() in {v.casefold() for v in prefs.get('current_knowledge',[])}
        row.update({'candidate_proximity':3 if known else 1,'current_evidence_strength':2 if known else 0,'career_breadth':min(5,len(family.get('target_titles',[]))), 'market_relevance':row['job_frequency'],'urgency':prefs.get('urgency',2),'estimated_learning_effort':4 if row['gap_type']=='EXPERIENCE' else 2,'evidence_creation_potential':1 if row['gap_type']=='EXPERIENCE' else 4})
        rows.append(row)
    priorities=engine.prioritize_career_gaps(candidate_profile_id=profile['profile_id'],role_family_id=family['role_family_id'],gaps=rows,timestamp=timestamp)
    source_index={r['gap_statement']:r for r in rows}
    result={'schema':'careeros.learning-gap-analysis.v1','profile_hash':sha256_value(profile),'role_family_id':family['role_family_id'],'market_as_of':utc_now(timestamp),'source_qualification_ids':[q['qualification_id'] for q in qualifications],'gap_priorities':priorities,'source_details':source_index,'boundary':'Observed job requirements and approved career preferences; this sample is not the entire labor market.'}
    _save(roots,'gaps.json',result);return result


def build(workspace: Path, catalog: Path, *, opportunity_ids=None, include_profile_gaps=True, timestamp=None) -> dict:
    roots=roots_for(workspace);profile=read_json(roots.state_root/'profile/career-profile.json');family=read_json(roots.state_root/'role-families/active.json');prefs=preferences(workspace);analysis=analyze_gaps(workspace,opportunity_ids=opportunity_ids,include_profile_gaps=include_profile_gaps,timestamp=timestamp)
    gaps=analysis['gap_priorities'];raw=read_json(catalog);raw=raw if isinstance(raw,list) else raw.get('courses',[])
    candidates=[engine.build_course_candidate(c,timestamp=timestamp) for c in raw]
    completed=[]
    for item in _completions(roots):
        if item.get('state')=='VERIFIED':completed+=item.get('learning_topics',[])
    existing={'canonical_skills':[s['name'] for s in profile.get('skills',[])]+prefs.get('current_knowledge',[]),'projects':[p['name'] for p in profile.get('projects',[])],'credentials':[c['title'] for c in profile.get('credentials',[])],'prior_coursework':completed,'evidence':[e.get('summary','') for e in profile.get('evidence',[])]}
    objectives=[];evaluations=[];redundancies=[];rois=[];impacts=[]
    for gap in gaps:
        statement=gap['gap_statement'];kind=gap['gap_type']
        objective=engine.build_learning_objective(gap,objective_statement='Develop and verify '+statement,target_competency=statement,starting_state='Observed '+kind.lower()+' gap',desired_state='Reviewed evidence appropriate to the requirement',completion_evidence=['Inspectable artifact and separate human review'],lane_impact=[family['role_family_id']],job_impact=['POTENTIAL_QUALIFICATION_IMPACT'],timestamp=timestamp)
        objectives.append(objective);impacts.append(engine.qualification_impact(gap))
        if kind=='EXPERIENCE':continue
        for candidate in candidates:
            level=prefs.get('knowledge_levels',{}).get(statement,prefs.get('candidate_level','BEGINNER'))
            evaluation,redundancy=engine.evaluate_course(candidate,objective=objective,gap=gap,existing_evidence=existing,candidate_level=level,satisfied_prerequisites=prefs.get('satisfied_prerequisites',[]),market_required_credential=kind in {'CREDENTIAL','CERTIFICATION'},employer_terms=[statement],preferences={**prefs,'as_of':utc_now(timestamp)})
            evaluations.append(evaluation);redundancies.append(redundancy)
            rois.append(engine.build_learning_roi(evaluation,gap,jobs_currently_blocked=gap['hard_gap_frequency'],jobs_partially_affected=gap['preferred_gap_frequency']))
    def factory(step,objective):
        gap=next(g for g in gaps if g['gap_id']==objective['gap_id'])
        return engine.build_evidence_creation_plan(learning_step_id=step['learning_step_id'],target_evidence=gap['gap_statement']+' demonstration',project_type='KNOWLEDGE_REVIEW' if gap['gap_type']=='KNOWLEDGE' else 'PRACTICAL_PROJECT',objective=objective['objective_statement'],required_tools=prefs.get('available_tools',[]),expected_actions=['Choose a small task','Make a piece of work of your own','Check the result and keep notes'],expected_artifacts=['Your work sample','Notes from testing or review'],verification_method=['Keep the original files','Ask someone to review the work against your goal'])
    # Reserve practical work within the time budget before selecting education.
    project_hours=prefs.get('project_hours',2);needs_project=[g for g in gaps if g['gap_type'] in {'PRACTICAL_SKILL','TOOL','PLATFORM','PROTOCOL','EVIDENCE','PORTFOLIO'}]
    max_hours=prefs.get('max_duration_hours')
    if max_hours is None and prefs.get('weekly_hours') and prefs.get('weeks_available'):max_hours=prefs['weekly_hours']*prefs['weeks_available']
    project_count=min(len(needs_project),int(max_hours//project_hours)) if max_hours is not None else len(needs_project)
    project_gaps=needs_project[:project_count];effective={**prefs,'as_of':utc_now(timestamp)}
    if max_hours is not None:effective['max_duration_hours']=max(0,max_hours-project_count*project_hours)
    target_titles=[read_json(roots.state_root/'opportunities'/key/'opportunity.json')['role_title'] for key in opportunity_ids] if opportunity_ids is not None else family.get('target_titles',[])
    path,steps,plans=engine.optimize_minimal_path(candidate_profile_id=profile['profile_id'],role_family_id=family['role_family_id'],target_role_ids=target_titles,objectives=objectives,candidates=candidates,evaluations=evaluations,evidence_plan_factory=factory,preferences=effective,timestamp=timestamp)
    for gap in project_gaps:
        objective=next(o for o in objectives if o['gap_id']==gap['gap_id']);step_id='learning-step:'+sha256_value([path['learning_path_id'],gap['gap_id'],'project'])[:24]
        step={'schema':'careeros.learning-step.v1','schema_version':'1.0.0','learning_step_id':step_id,'sequence':len(steps)+1,'step_type':'PROJECT','objective_ids':[objective['objective_id']],'course_candidate_id':None,'title':'Create an original '+gap['gap_statement']+' work sample','completion_condition':'Keep your original work and check the result with someone who can review it. Describe it as project work, not employment.','prerequisites':[],'estimated_time':str(project_hours)+' hours','estimated_cost':'Use available tools; verify any additional expense','status':'PROPOSED'}
        step['prerequisites']=[s['learning_step_id'] for s in steps if objective['objective_id'] in s['objective_ids']]
        SchemaRegistry(schema_dir()).validate('urn:careeros:schema:learning-step:v1',step);steps.append(step);plans.append(factory(step,objective))
    path['steps']=[s['learning_step_id'] for s in steps]
    path['expected_gap_coverage']=sorted(set(path['expected_gap_coverage']+[g['gap_id'] for g in project_gaps]))
    impact=engine.build_learning_path_impact(learning_path_id=path['learning_path_id'],lanes={family['role_family_id']:['EVIDENCE_EXPANSION'] if steps else ['NO_EXPECTED_CHANGE']},qualification_impacts=impacts)
    qa=engine.learning_path_qa(gaps=gaps,objectives=objectives,candidates=candidates,evaluations=evaluations,path=path,evidence_plans=plans,qualification_impacts=impacts)
    chosen={s['course_candidate_id'] for s in steps if s.get('course_candidate_id')};costs=[engine.learning_cost(c,effective) for c in candidates if c['course_candidate_id'] in chosen];hours=[engine.learning_hours(c) for c in candidates if c['course_candidate_id'] in chosen]
    total_hours=sum(h for h in hours if h is not None)+len(project_gaps)*project_hours
    total_cost=sum(c for c in costs if c is not None)
    path['estimated_total_time']=(str(total_hours)+' hours'+(' + unknown education time' if None in hours else ''))
    path['estimated_total_cost']=(str(total_cost)+' '+prefs.get('currency','currency unspecified')+(' + unknown costs' if None in costs else '')+'; practical materials not priced')
    run_id=sha256_value([profile,prefs,analysis,raw])[:24]
    result={'schema':'careeros.learning-workflow.v1','run_id':run_id,'target_opportunity_ids':opportunity_ids,'created_at':utc_now(timestamp),'path':path,'steps':steps,'evidence_plans':plans,'gap_priorities':gaps,'gap_analysis':analysis,'objectives':objectives,'course_candidates':candidates,'course_evaluations':evaluations,'redundancy':redundancies,'learning_roi':rois,'impact':impact,'provider_comparison':engine.compare_provider_options(evaluations,candidates),'preferences':prefs,'personalization_state':'READY_FOR_REVIEW' if prefs else 'PREFERENCES_NOT_SUPPLIED','qa':qa,'catalog_sha256':sha256_file(catalog),'source_profile_hash':sha256_value(profile),'experience_actions':[{'gap_id':g['gap_id'],'capability':g['gap_statement'],'action':'Seek actual supervised professional work; training does not satisfy this requirement.','requirement_state':'UNSATISFIED'} for g in gaps if g['gap_type']=='EXPERIENCE'],'uncovered_gap_ids':[g['gap_id'] for g in gaps if g['gap_id'] not in path['expected_gap_coverage']],'canonical_mutations':0,'external_actions':0}
    _save(roots,'runs/'+run_id+'.json',result);_save(roots,'latest.json',result);render(workspace,result);return result


def status(workspace: Path, *, timestamp=None) -> dict:
    roots=roots_for(workspace);path=roots.state_root/'learning/latest.json'
    if not path.exists():return {'status':'NOT_STARTED','canonical_mutations':0}
    result=read_json(path);current=read_json(roots.state_root/'profile/career-profile.json');result['freshness']='CURRENT' if result['source_profile_hash']==sha256_value(current) and result['preferences']==preferences(workspace) else 'STALE_REBUILD_REQUIRED'
    active=read_json(roots.state_root/'role-families/active.json')
    if active['role_family_id']!=result['path']['role_family_id']:result['freshness']='STALE_REBUILD_REQUIRED'
    selected={s.get('course_candidate_id') for s in result['steps']}
    result['source_freshness']={}
    for course in result['course_candidates']:
        if course['course_candidate_id'] not in selected:continue
        assessed=engine.assess_course_freshness(course_candidate_id=course['course_candidate_id'],last_verified_at=course['last_verified_at'],availability='AVAILABLE',as_of=utc_now(timestamp))
        result['source_freshness'][course['course_candidate_id']]=assessed['freshness_state']
        if assessed['freshness_state']!='CURRENT' or (result['preferences'].get('budget') is not None and engine.learning_cost(course,{**result['preferences'],'as_of':utc_now(timestamp)}) is None):result['freshness']='STALE_REBUILD_REQUIRED'
    from careeros.updates import require_derivative_current
    try:require_derivative_current(roots,'CAREER_PROFILE',current['profile_id'])
    except PermissionError:result['freshness']='STALE_REBUILD_REQUIRED'
    result['completions']=_completions(roots)
    for completion in result['completions']:
        completion['artifact_integrity']='PASS'
        for artifact in completion.get('artifacts',[]):
            file=(workspace/artifact['path']).resolve()
            if not file.is_relative_to(workspace.resolve()) or not file.is_file() or sha256_file(file)!=artifact['sha256']:completion['artifact_integrity']='REVIEW_REQUIRED'
    return result


def ensure_entry(workspace: Path):
    """Expose a real gap-review entry before a user supplies a course catalog."""
    bundle=status(workspace)
    if bundle.get('status')=='NOT_STARTED':
        roots=roots_for(workspace)
        try:analysis=analyze_gaps(workspace) if (roots.state_root/'role-families/active.json').exists() else {}
        except PermissionError:analysis={}
        bundle={'gap_priorities':analysis.get('gap_priorities',[]),'preferences':preferences(workspace),'path':{'estimated_total_cost':'Not planned','estimated_total_time':'Not planned'},'steps':[],'qa':{},'freshness':'NOT_STARTED'}
    render(workspace,bundle)


def record_progress(workspace: Path, payload: dict, *, timestamp=None) -> dict:
    roots=roots_for(workspace);bundle=status(workspace)
    step=next((s for s in bundle.get('steps',[]) if s['learning_step_id']==payload.get('step_id')),None)
    if not step:raise ValueError('Unknown learning step')
    state=payload['state'];actor=payload.get('actor')
    if state not in {'IN_PROGRESS','COMPLETED','VERIFIED'} or not isinstance(actor,str) or not actor.strip():raise ValueError('State and actor are required')
    key=sha256_value(step['learning_step_id'])[:24];previous=next((e for e in _completions(roots) if e['step_id']==step['learning_step_id']),{'state':'NOT_STARTED'})
    if state not in {'NOT_STARTED':{'IN_PROGRESS'},'IN_PROGRESS':{'COMPLETED'},'COMPLETED':{'VERIFIED'},'VERIFIED':set()}[previous['state']]:raise ValueError('Invalid training transition: '+previous['state']+' -> '+state)
    artifacts=[]
    for value in payload.get('artifacts',[]):
        file=(workspace/value).resolve()
        if not file.is_relative_to(workspace.resolve()) or not file.is_file():raise ValueError('Completion artifact must be a local workspace file')
        artifacts.append({'path':str(file.relative_to(workspace.resolve())),'sha256':sha256_file(file)})
    if state=='VERIFIED' and (payload.get('human_confirmed') is not True or not artifacts):raise PermissionError('Verification requires human confirmation and inspectable artifacts')
    event={'schema':'careeros.learning-progress-event.v1','step_id':step['learning_step_id'],'path_id':bundle['path']['learning_path_id'],'prior_state':previous['state'],'state':state,'actor':actor,'occurred_at':utc_now(timestamp),'source':payload.get('source','USER_REPORT'),'verification_class':'HUMAN_REVIEWED_ARTIFACT' if state=='VERIFIED' else 'SELF_REPORT','artifacts':artifacts or previous.get('artifacts',[]),'learning_topics':[o['target_competency'] for o in bundle['objectives'] if o['objective_id'] in step['objective_ids']],'affected_canonical_ids':[],'canonical_mutations':0}
    append_jsonl(roots.assert_write_allowed(roots.state_root/'learning/progress-events.jsonl','state'),event);_save(roots,'completions/'+key+'.json',event)
    bundle['completions']=_completions(roots);render(workspace,bundle);return event


def propose_profile_update(workspace: Path, payload: dict, *, timestamp=None) -> dict:
    from careeros import updates
    roots=roots_for(workspace);bundle=status(workspace);step=next((s for s in bundle['steps'] if s['learning_step_id']==payload['step_id']),None)
    if not step:raise ValueError('Unknown learning step')
    completion=next((e for e in _completions(roots) if e['step_id']==step['learning_step_id']),{'state':'NOT_STARTED'})
    if completion['state']!='VERIFIED':raise PermissionError('Evidence must be verified before proposing canonical use')
    for a in completion['artifacts']:
        file=(workspace/a['path']).resolve()
        if not file.is_relative_to(workspace.resolve()) or not file.is_file() or sha256_file(file)!=a['sha256']:raise PermissionError('Completion evidence changed after review')
    if not payload.get('summary') or not payload.get('actions'):raise ValueError('Provide the reviewed summary and actual actions; course topics are not demonstrated skills')
    now=utc_now(timestamp);evidence_id='evidence:learning-'+sha256_value([completion,payload])[:20]
    provenance=[{'source_id':'source:'+sha256_value(a)[:20],'source_type':'DOCUMENT','source_reference':a['path'],'source_hash':a['sha256'],'captured_at':now} for a in completion['artifacts']]
    project=step['step_type'] in {'PROJECT','LAB','PORTFOLIO_ARTIFACT','PRACTICE'}
    base={'schema_version':'1.0.0','created_at':now,'updated_at':now,'provenance':provenance,'verification_state':'VERIFIED','confidence':'HIGH','visibility':'INTERNAL','status':'ACTIVE'}
    evidence={**base,'schema':'careeros.evidence-record.v1','record_id':evidence_id,'evidence_type':'PROJECT' if project else 'TRAINING','summary':payload['summary'],'context':'PROJECT' if project else 'COURSEWORK','actions':payload['actions'],'outcomes':payload.get('outcomes',[]),'skill_ids':[],'employment_ids':[],'project_ids':[],'metric_boundaries':['No metrics are implied by completion.'],'claim_boundaries':['Training/project evidence is not professional employment.']}
    changes=[{'operation':'ADD_EVIDENCE','record_type':'evidence','record_id':None,'field_path':None,'before':None,'after':evidence,'source_refs':[a['path'] for a in completion['artifacts']],'confidence':'HIGH','visibility_impact':'NONE','verification_impact':'NONE','reason':'Reviewed original learning artifact; no employment claim.'}]
    profile=read_json(roots.state_root/'profile/career-profile.json')
    for claim in payload.get('skill_claims',[]):
        if not claim.get('name') or claim.get('proficiency') not in {'AWARENESS','FOUNDATIONAL','PRACTICED'}:raise ValueError('Only explicitly reviewed, bounded skill claims are supported')
        existing=next((s for s in profile.get('skills',[]) if s['name'].casefold()==claim['name'].casefold()),None)
        if existing:
            changes.append({'operation':'CORRECT_FACT','record_type':'skills','record_id':existing['record_id'],'field_path':'evidence_ids','before':existing['evidence_ids'],'after':sorted(set(existing['evidence_ids']+[evidence_id])),'source_refs':[a['path'] for a in completion['artifacts']],'confidence':'HIGH','visibility_impact':'NONE','verification_impact':'NONE','reason':'Link only the explicitly reviewed artifact; do not upgrade proficiency automatically.'})
            evidence['skill_ids'].append(existing['record_id'])
        else:
            skill_id='skill:learning-'+sha256_value(claim['name'].casefold())[:20];skill={**base,'schema':'careeros.skill-record.v1','record_id':skill_id,'name':claim['name'],'category':'LEARNING','proficiency':claim['proficiency'],'evidence_ids':[evidence_id],'contexts':['PROJECT' if project else 'COURSEWORK'],'claim_boundaries':['No professional experience is implied.']};evidence['skill_ids'].append(skill_id)
            changes.append({'operation':'ADD_RECORD','record_type':'skills','record_id':None,'field_path':None,'before':None,'after':skill,'source_refs':[a['path'] for a in completion['artifacts']],'confidence':'HIGH','visibility_impact':'NONE','verification_impact':'NONE','reason':'Explicitly reviewed competency claim from an artifact.'})
    award=payload.get('credential')
    if award:
        if not isinstance(award,dict) or not all(award.get(k) for k in ('title','issuer','issued_date')) or award.get('award_confirmed') is not True:raise ValueError('An awarded credential requires reviewed title, issuer, issue date and award confirmation')
        kind=award.get('kind')
        if kind not in {'COMPLETION_CERTIFICATE','INDUSTRY_CERTIFICATION'}:raise ValueError('Distinguish completion certificates from industry certifications')
        if kind=='INDUSTRY_CERTIFICATION' and step['step_type']!='CERTIFICATION_ATTEMPT':raise ValueError('Preparation or course completion cannot award an industry certification; verify the certification attempt separately')
        credential={**base,'schema':'careeros.credential-record.v1','record_id':'credential:learning-'+sha256_value([award,completion])[:20],'title':award['title'],'issuer':award['issuer'],'issued_date':award['issued_date'],'credential_state':'COMPLETED','claim_boundaries':[kind+'; artifact-backed award only. No professional experience is implied.']}
        for key in ('expiration_date','credential_identifier','credential_url'):
            if key in award:credential[key]=award[key]
        changes.append({'operation':'ADD_RECORD','record_type':'credentials','record_id':None,'field_path':None,'before':None,'after':credential,'source_refs':[a['path'] for a in completion['artifacts']],'confidence':'HIGH','visibility_impact':'NONE','verification_impact':'NONE','reason':'Separately reviewed actual award; not inferred from course topics or preparation.'})
    input_path=_save(roots,'promotion-input.json',{'created_by':payload.get('actor','user'),'reason':'Learning evidence review; requires explicit canonical approval.','source':{'type':'DOCUMENT','references':[a['path'] for a in completion['artifacts']]},'proposed_changes':changes})
    result=updates.propose(workspace,input_path,timestamp=timestamp);_save(roots,'promotion.json',{'changeset_id':result['changeset_id'],'step_id':step['learning_step_id'],'canonical_mutations':0});return result


def reassess(workspace: Path, *, timestamp=None) -> dict:
    from careeros import profile as profile_api, opportunity
    roots=roots_for(workspace);old=read_json(roots.state_root/'role-families/active.json');before={read_json(p)['opportunity_id']:read_json(p) for p in (roots.state_root/'qualifications').glob('*.json')}
    compiled,_=profile_api.build_profile(workspace,timestamp=timestamp);intents=compiled['preferences'].get('target_role_intents',[]);index=next((i for i,v in enumerate(intents) if v['display_name']==old['display_name']),None)
    if index is None:raise ValueError('The selected role changed; review role selection before reassessment')
    family=profile_api.build_role_family(workspace,intent_index=index,approve=old['approval_state']=='APPROVED',timestamp=timestamp)
    results=[]
    for p in sorted((roots.state_root/'opportunities').glob('*/opportunity.json')):
        opp=read_json(p);q=opportunity.qualify(workspace,opp['opportunity_id'],timestamp=timestamp);previous=before.get(opp['opportunity_id'],{})
        results.append({'opportunity_id':opp['opportunity_id'],'role_title':opp['role_title'],'before':previous.get('decision','NOT_EVALUATED'),'after':q['decision'],'remaining_gaps':[g['capability'] for g in q['gaps']]})
    result={'schema':'careeros.learning-reassessment.v1','role_family_id':family['role_family_id'],'results':results,'canonical_mutations':0,'boundary':'Reassessment uses only currently approved canonical evidence. Completion alone changes no eligibility.'};_save(roots,'reassessment.json',result);render(workspace,status(workspace));return result


def render(workspace: Path, bundle: dict):
    from careeros.experience import _write, _report_pdf
    from careeros.presentation import label
    from html import escape
    roots=roots_for(workspace);prefs=bundle.get('preferences',{})
    lines=['# Your learning plan','Choose a useful next step, try it, and keep an example of what you can do.']
    if bundle.get('created_at'):lines.append('Plan checked on: '+bundle['created_at'])
    if bundle.get('freshness')=='STALE_REBUILD_REQUIRED':lines.append('Update this plan before you start. Some profile or course details have changed or are out of date. Check the sources and make a new plan.')
    lines+=['## What fits your life',f"Budget: {prefs.get('budget','Not set')} {prefs.get('currency','')}. Time each week: {prefs.get('weekly_hours','Not set')} hours. Planning ahead: {prefs.get('weeks_available','Not set')} weeks.",'Subscriptions you already have: '+(', '.join(v.replace('_',' ').title() for v in prefs.get('subscriptions_owned',[])) or 'None recorded')]
    candidates={c['course_candidate_id']:c for c in bundle.get('course_candidates',[])}
    if candidates and all(any(r.get('type')=='SYNTHETIC' for r in c.get('source_refs',[])) for c in candidates.values()):lines.insert(2,'Fictional example: these courses, subscriptions and prices are for demonstration only.')
    lines.append('## Where to focus')
    for g in bundle.get('gap_priorities',[]):
        count=g['recurrence_count'];lines.append(g['gap_statement']+' — '+label(g['gap_type'])+'. Found in '+str(count)+(' job we checked.' if count==1 else ' jobs we checked.'))
    lines.append('## Your next steps')
    if not bundle.get('steps'):lines.append('We do not yet have a learning option that fits. Set your time, budget and starting skills, then check current course details. We will not fill the plan with guessed recommendations.')
    completion={c['step_id']:c for c in bundle.get('completions',[])}
    for step in bundle.get('steps',[]):
        state=completion.get(step['learning_step_id'],{});course=candidates.get(step.get('course_candidate_id'))
        lines+=['### '+str(step['sequence'])+'. '+step['title'],label(step['step_type'])+' · '+label(state.get('state','NOT_STARTED'))+' · '+step['estimated_time'],step['completion_condition']]
        if state.get('artifact_integrity')=='REVIEW_REQUIRED':lines.append('A file has changed since it was checked. Review the work again before using it as support for a career claim.')
        if course:lines.append('Resource: '+course['url'])
    lines.append('## Turn learning into work you can show')
    numbers={step['learning_step_id']:step['sequence'] for step in bundle.get('steps',[])}
    for evidence in bundle.get('evidence_plans',[]):lines+=['### Step '+str(numbers.get(evidence['learning_step_id'],'?'))+' · '+evidence['target_evidence'],'Keep: '+', '.join(evidence['expected_artifacts']),'Check your work: '+', '.join(evidence['verification_method'])]
    lines.append('## How this may help your career')
    selected={(step.get('course_candidate_id'),o) for step in bundle.get('steps',[]) for o in step['objective_ids']}
    evaluations=bundle.get('course_evaluations',[]);chosen={e['course_evaluation_id'] for e in evaluations if e['ranking_eligible'] and (e['course_candidate_id'],e['objective_id']) in selected}
    for roi in bundle.get('learning_roi',[]):
        if roi['course_evaluation_id'] not in chosen:continue
        gap=next(g for g in bundle['gap_priorities'] if g['gap_id']==roi['gap_id']);lines.append(gap['gap_statement']+': '+label(roi['roi_class']).lower()+' estimated learning value. This is a comparison aid, not a promise of a job or higher pay.')
    path=bundle.get('path',{});lines+=['Planned learning cost: '+path.get('estimated_total_cost','Not yet known').replace('; practical materials not priced',' for selected resources; check any extra project costs').replace('currency unspecified','(currency not set)').replace('+ unknown costs','plus costs still to check')+'.','Planned learning time: '+path.get('estimated_total_time','Not yet known')+'.']
    for action in bundle.get('experience_actions',[]):lines.append(action['capability']+': Look for supervised work where you can carry out this responsibility. Keep a record of what you actually did. Courses and practice projects do not replace required professional experience.')
    reassessment=roots.state_root/'learning/reassessment.json'
    if reassessment.exists():
        lines.append('## Check your fit again')
        rows=[row for row in read_json(reassessment)['results'] if bundle.get('target_opportunity_ids') is None or row['opportunity_id'] in bundle['target_opportunity_ids']]
        if not rows:lines.append('This role has not been reassessed yet. After you approve new career information, compare its requirements again.')
        for row in rows:
            lines.append(row['role_title']+': '+label(row['after'])+'. Still to address: '+(', '.join(row['remaining_gaps']) or 'No gaps in the requirements we checked.'))
    if bundle.get('uncovered_gap_ids'):lines.append('Some requirements still have no suitable learning step. Check missing course details, costs and entry rules before adding more training.')
    lines+=['A completed course does not prove professional experience. Review any new skill or actual award before adding it to your career profile.','Affiliate links never change which resources we recommend.']
    comparisons=[]
    for key in candidates:
        options=[e for e in evaluations if e['course_candidate_id']==key];relevant=[e for e in options if e['dimensions']['GAP_COVERAGE']>0];comparisons.extend(relevant or sorted(options,key=lambda e:-e['overall_routing_score'])[:1])
    if comparisons:lines+=['## Compare your learning options','The four scores below are out of five. They compare learning content, the award, job relevance and work you could show.']
    for e in sorted(comparisons,key=lambda e:-e['overall_routing_score'])[:24]:
        course=candidates[e['course_candidate_id']];gap=next(g for g in bundle['gap_priorities'] if g['gap_id']==e['gap_id']);reasons=list(e.get('preference_alignment',{}).get('reasons',[]))
        if course['freshness_state']!='CURRENT':reasons.append('CATALOG_'+course['freshness_state'])
        if e['redundancy_class']=='HIGHLY_REDUNDANT':reasons.append('HIGHLY_REDUNDANT')
        if e['candidate_level_match'] in {'TOO_ADVANCED','PREREQUISITE_MISSING'}:reasons.append(e['candidate_level_match'])
        value=e['four_value_model'];lines+=['### '+course['title']+' · '+gap['gap_statement'],label(course['course_type'])+' · '+course['provider'].replace('_',' ')+' · '+('Could fit this plan' if e['ranking_eligible'] else 'Not a fit right now'),'Learning: '+str(value['LearningValue'])+'/5. Award: '+str(value['CredentialSignal'])+'/5. Job relevance: '+str(value['EmployerRelevance'])+'/5. Work you can show: '+str(value['EvidenceCreationValue'])+'/5.','Starting level: '+label(e['candidate_level_match'])+'. Familiar material: '+label(e['redundancy_class'])+'.','Why: '+('; '.join(label(reason) for reason in reasons) or 'Addresses a requirement in the jobs we checked.')]
    _write(roots,'learning/learning-roadmap.md','\n\n'.join(lines)+'\n');_write(roots,'reports/learning-path.md','[Open your learning plan](../learning/index.html)\n')
    _report_pdf('Your Learning Plan',lines[1:],roots.assert_write_allowed(roots.output_root/'learning/learning-roadmap.pdf','output'),keep_subsections=True)
    parts=[]
    for line in lines:
        if line.startswith('#'):
            level=len(line)-len(line.lstrip('#'));parts.append(f'<h{level}>'+escape(line.lstrip('# '))+f'</h{level}>')
        elif line.startswith('Resource: https://'):
            url=line[len('Resource: '):];parts.append('<p>Resource: <a rel="noreferrer" href="'+escape(url,quote=True)+'">'+escape(url)+'</a></p>')
        else:parts.append('<p>'+escape(line)+'</p>')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Your learning plan</title><style>body{margin:0;background:#f2f5f8;color:#15233a;font:16px/1.6 system-ui}main{max-width:980px;margin:36px auto;padding:30px;background:white}h1{font-size:38px}h2{color:#1f4f78;margin-top:36px;border-top:1px solid #dce3eb;padding-top:18px}h3{margin-top:26px}p{overflow-wrap:anywhere}nav a{color:#1f4f78;margin-right:18px}@media(max-width:600px){main{margin:0;padding:22px}h1{font-size:29px}}</style><main><nav><a href="../index.html">Your career home</a><a href="learning-roadmap.pdf">Download your plan</a><a href="learning-roadmap.md">Text version</a></nav>'+''.join(parts)+'</main></html>'
    _write(roots,'learning/index.html',page)
