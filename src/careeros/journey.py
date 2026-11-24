"""Connect existing career engines into a job seeker's day-to-day workflows."""
from __future__ import annotations
import copy
import html
import math
from pathlib import Path
from careeros import experience, opportunity, resume
from careeros.application_state import build_opportunity_freshness
from careeros.career_outputs import discover_lanes
from careeros.core.io import atomic_write_json, read_json, sha256_value
from careeros.presentation import label, gap_advice
from careeros.updates import require_derivative_current
from careeros.workspace import utc_now

CATEGORIES=('Ready Now','Stretch Roles','Dream Roles')


def _context(workspace):
    roots=experience.context(workspace)
    path=roots.state_root/'profile/career-profile.json'
    if not path.is_file():raise ValueError('Start by adding and reviewing your career history. Then we can look for jobs that fit you.')
    profile=read_json(path);family=read_json(roots.state_root/'role-families/active.json')
    require_derivative_current(roots,'CAREER_PROFILE',profile['profile_id'])
    require_derivative_current(roots,'ROLE_FAMILY',family['role_family_id'])
    if family['approval_state']!='APPROVED':raise PermissionError('Review your suggested career direction first. We will use that choice to compare jobs and prepare your resumes.')
    return roots,profile,family


def _save(roots,name,value):
    path=roots.assert_write_allowed(roots.state_root/'job-search'/name,'state');atomic_write_json(path,value);return path


def _normalized(text):
    import re
    text=str(text or '').casefold()
    text=re.sub(r'\b(u\.?s\.?a?\.?|united states of america)\b','united states',text)
    return ' '.join(re.findall(r'[a-z0-9]+',text))


def _preference_check(job,preferences):
    location=_normalized(job.get('location'));wanted=preferences.get('locations',[])
    if wanted and not location:return ['The posting does not give a location.'],False
    if wanted and not any(set(_normalized(v).split()).issubset(set(location.split())) for v in wanted):return ['The location does not match your search.'],True
    modes=preferences.get('work_modes',[])
    if modes and len(modes)<3:
        mode=next((m for m in ('REMOTE','HYBRID','ONSITE') if m.casefold() in location.replace('on site','onsite')),None)
        if mode and mode not in modes:return ['The working arrangement does not match your search.'],True
        if not mode:return ['Check whether the working arrangement suits you.'],False
    return [],False


def overview(workspace:Path, *, request:dict|None=None,timestamp=None) -> dict:
    roots,profile,family=_context(workspace)
    saved=roots.state_root/'job-search/request.json';request=request if request is not None else (read_json(saved) if saved.exists() else {})
    dreams={_normalized(v) for v in request.get('dream_roles',[])}
    preferences={'locations':request.get('locations',profile['preferences'].get('location_preferences',[])), 'work_modes':[v.upper() for v in request.get('work_modes',profile['preferences'].get('work_modes',[]))]}
    for path in sorted((roots.state_root/'opportunities').glob('*/opportunity.json')):
        opportunity.qualify(workspace,read_json(path)['opportunity_id'],timestamp=timestamp)
    ranked=experience.prioritize(workspace)['rankings'];jobs=[];excluded=[]
    for rank in ranked:
        key=rank['opportunity_id'];folder=roots.state_root/'opportunities'/key
        opp=read_json(folder/'opportunity.json');snapshot=read_json(folder/'jd-snapshot.json')
        q=read_json(roots.state_root/'qualifications'/(key+'.json'))
        fresh=build_opportunity_freshness(opp,snapshot,timestamp=timestamp)
        atomic_write_json(roots.assert_write_allowed(folder/'freshness.json','state'),fresh)
        preference_notes,mismatch=_preference_check(opp,preferences)
        if opp['employer_name'].casefold() in {v.casefold() for v in request.get('exclude_employers',[])}:mismatch=True;preference_notes=['You asked to leave this employer out.']
        if mismatch or fresh['freshness_state'] in {'CLOSED','EXPIRED','SUPERSEDED'}:
            excluded.append({'opportunity_id':key,'role_title':opp['role_title'],'reason':preference_notes or ['This posting is no longer current.']});continue
        ready=q['decision']=='QUALIFIED' and fresh['freshness_state']=='FRESH' and not preference_notes
        dream=_normalized(opp['role_title']) in dreams
        category='Ready Now' if ready else 'Dream Roles' if dream else 'Stretch Roles'
        matches=[e['capability'] for e in q['evidence'] if e['match'] in {'SUPPORTED_MATCH','TRANSFERABLE_MATCH'}]
        checks=list(preference_notes)
        if fresh['freshness_state']!='FRESH':checks.append('Check that this job is still open before preparing an application.')
        if not opp.get('requirements'):checks.append('Review the job requirements before we judge your fit.')
        jobs.append({**rank,'qualification':q['decision'],'category':category,'dream_goal':dream,'eligible_for_preparation':ready,'location':opp.get('location'),'source_url':opp.get('source_url'),'last_verified_at':fresh['last_verified_at'],'freshness':fresh['freshness_state'],'matches':list(dict.fromkeys(matches)),'gaps':q['gaps'],'checks':checks,'requirements':opp['requirements'],'why':('Your recorded experience supports the requirements we checked.' if ready else ('You have useful starting points, but some requirements or details need work.' if matches else 'Let us check your background and the main requirements to find a realistic starting point.')),'qualification_id':q['qualification_id']})
    jobs.sort(key=lambda j:(CATEGORIES.index(j['category']),-j['supported_fit_percent'],j['opportunity_id']))
    result={'schema':'careeros.career-journey.v1','created_at':utc_now(timestamp),'profile_hash':sha256_value(profile),'role_family_id':family['role_family_id'],'preferences':preferences,'dream_roles':request.get('dream_roles',[]),'jobs':jobs,'excluded':excluded,'categories':{c:sum(j['category']==c for j in jobs) for c in CATEGORIES},'message':f"We compared {len(jobs)} saved openings with your career profile. Review the matches and any details still to check.",'canonical_mutations':0,'external_actions':0}
    previous=roots.state_root/'job-search/latest.json'
    if previous.exists():result['resumes']=read_json(previous).get('resumes',[])
    _save(roots,'latest.json',result);render(workspace,result);return result


def find_jobs(workspace:Path,request:dict,*,approved=False,timestamp=None,fetcher=None) -> dict:
    roots,profile,family=_context(workspace)
    allowed={'catalog','boards','titles','locations','work_modes','dream_roles','exclude_employers','prepare_top','selected_ids'}
    if set(request)-allowed:raise ValueError('Some search settings are not supported. Use job titles, locations, working arrangements, employer boards or reviewed job postings.')
    for field in ('titles','locations','work_modes','dream_roles','exclude_employers','selected_ids'):
        if field in request and (not isinstance(request[field],list) or any(not isinstance(v,str) or not v.strip() for v in request[field])):raise ValueError(f'{field} must be a list of names.')
    if any(v.upper() not in {'REMOTE','HYBRID','ONSITE'} for v in request.get('work_modes',[])):raise ValueError('Choose remote, hybrid or onsite work.')
    top=request.get('prepare_top',3)
    if isinstance(top,bool) or not isinstance(top,int) or not 0<=top<=10:raise ValueError('Choose between zero and ten resumes to prepare at once.')
    _save(roots,'request.json',request)
    proposals=[];failures=[]
    if request.get('boards'):
        if approved is not True:raise PermissionError('Searching employer boards needs your permission to read public job pages. Your career profile stays in your workspace.')
        if not isinstance(request['boards'],list) or len(request['boards'])>3:raise ValueError('Search up to three employer boards at a time.')
        if any(not isinstance(source,dict) or not isinstance(source.get('board'),str) or not isinstance(source.get('employer'),str) for source in request['boards']):raise ValueError('Each employer source needs its verified name and board identifier.')
        from careeros.discovery_sources import fetch_greenhouse
        fetch=fetcher or fetch_greenhouse
        titles=request.get('titles') or family['target_titles']
        for source in request['boards']:
            try:
                proposal=fetch(board=source['board'],employer=source['employer'],approved=True,limit=100,query=titles,timestamp=timestamp)
                path=_save(roots,'sources/'+sha256_value(source)[:16]+'.json',proposal)
                proposals.append({'path':str(path),'jobs':proposal['selected_posts'],'provider':proposal['provider'],'status':'REQUIREMENT_REVIEW_REQUIRED'})
            except (ValueError,OSError,KeyError) as exc:failures.append({'employer':source.get('employer','Unknown employer'),'message':str(exc)})
    imported=None
    if request.get('catalog'):
        source=Path(request['catalog']);source=source if source.is_absolute() else workspace/source
        payload=read_json(source)
        # Assistant-produced results must carry a source URL and verification
        # evidence; arbitrary pasted lists do not become verified live openings.
        jobs=payload if isinstance(payload,list) else payload.get('opportunities',[])
        if not jobs:raise ValueError('This search file has no job postings. Add current employer links or search an employer board.')
        for job in jobs:
            from urllib.parse import urlsplit
            if job.get('source_type')!='SYNTHETIC':
                url=urlsplit(str(job.get('source_url') or ''))
                if url.scheme!='https' or not url.hostname or url.username or url.password:raise ValueError('Use a public HTTPS employer link without embedded sign-in details.')
            if job.get('source_type')!='SYNTHETIC' and (not job.get('source_url') or not job.get('last_verified_at') or not job.get('job_description')):raise ValueError('Each real opening needs its employer link, posting text and the date it was checked.')
        imported=experience.discovery(workspace,source,limit=100,timestamp=timestamp)
    result=overview(workspace,request=request,timestamp=timestamp);result.update({'source_proposals':proposals,'source_failures':failures,'discovery':imported,'network_requests':len(proposals),'status':'REQUIREMENT_REVIEW_REQUIRED' if proposals else 'REVIEW_READY'})
    if proposals:
        if sum(p['jobs'] for p in proposals):result['message']='We found public postings. Review the employer requirements in the saved search results, then compare the jobs and prepare the best-fitting resumes.'
        else:result['status']='NO_MATCHES';result['message']='There were no matching postings in these employer sources. Try other titles or employers; this was not a search of every job board.'
    elif failures and not imported:result['status']='SOURCE_UNAVAILABLE';result['message']='We could not check these sources. Existing saved results are still available; try again or use another employer posting.'
    elif not imported and not result['jobs']:result['message']='There are no openings to compare yet. Search an employer board or bring in current postings found by your assistant.'
    if imported and (top or request.get('selected_ids')):
        result['resume_batch']=prepare(workspace,top=top,selected_ids=request.get('selected_ids'),timestamp=timestamp)
        result['resumes']=result['resume_batch']['results']
    render(workspace,result)
    _save(roots,'latest-search.json',result);return result


def suggest_roles(workspace:Path,*,timestamp=None) -> dict:
    roots,profile,_=_context(workspace)
    current=overview(workspace,timestamp=timestamp)
    opportunities=[read_json(p) for p in (roots.state_root/'opportunities').glob('*/opportunity.json')]
    lanes=discover_lanes(profile,market_opportunities=opportunities,timestamp=timestamp)
    rows=lanes['lanes'];lines=['# Other roles worth exploring','Your skills may be useful in more than one kind of job. These are ideas to explore, not promises of a job or a new qualification.']
    for row in rows:lines+=['## '+row['display_name'],row['why'],'Titles to explore: '+', '.join(row['example_titles'])]
    lines+=['Next, check a current posting for each title that interests you. We can compare its requirements with your experience before you decide.']
    from careeros.experience import _write,_report_pdf
    _write(roots,'career/other-roles.md','\n\n'.join(lines)+'\n');_report_pdf('Other Roles Worth Exploring',lines[1:],roots.assert_write_allowed(roots.output_root/'career/other-roles.pdf','output'))
    result={**lanes,'message':'Here are career directions supported by your history and the openings we have checked. Choose any you would like to explore.','path':'career/other-roles.md','canonical_mutations':0};_save(roots,'role-ideas.json',result);return result


def prepare(workspace:Path,*,top=3,selected_ids=None,timestamp=None) -> dict:
    roots,_,_=_context(workspace)
    if isinstance(top,bool) or not isinstance(top,int) or not 0<=top<=10:raise ValueError('Choose between zero and ten resumes at a time.')
    current=overview(workspace,timestamp=timestamp);index={j['opportunity_id']:j for j in current['jobs']}
    if selected_ids and any(key not in index for key in selected_ids):raise ValueError('One of the selected jobs is missing, closed or outside your search. Refresh the list before preparing it.')
    chosen=[index[key] for key in dict.fromkeys(selected_ids)] if selected_ids else [j for j in current['jobs'] if j['eligible_for_preparation']][:top]
    if len(chosen)>10:raise ValueError('Select no more than ten jobs at a time.')
    results=[]
    for job in chosen:
        row={'opportunity_id':job['opportunity_id'],'role_title':job['role_title'],'employer_name':job['employer_name']}
        if not job['eligible_for_preparation']:
            results.append({**row,'status':'NEEDS_REVIEW','message':'We have held this resume while required qualifications or job details need checking.','gaps':job['gaps']});continue
        try:
            build,content,artifact=resume.build(workspace,job['opportunity_id'],timestamp=timestamp)
            checked,_=resume.validate(workspace,build['build_id'])
            if checked['status']!='PASS':
                results.append({**row,'status':'QA_FAILED','message':'This draft needs a layout or content fix before you use it.','validation':checked});continue
            results.append({**row,'status':'REVIEW_REQUIRED','message':'Your tailored resume is ready to review. Nothing has been sent.','build_id':build['build_id'],'path':artifact['path'],'sha256':artifact['sha256'],'evidence_ids':build['selected_evidence_ids']})
        except (ValueError,PermissionError,FileExistsError) as exc:results.append({**row,'status':'NEEDS_REVIEW','message':str(exc)})
    current['resumes']=results;_save(roots,'latest.json',current);render(workspace,current)
    result={'schema':'careeros.resume-batch.v1','results':results,'prepared':sum(r['status']=='REVIEW_REQUIRED' for r in results),'message':('Review each draft for the right employer, job title, contact details and examples before applying.' if results else 'There are no suitable jobs to prepare yet. Review the gaps or add current postings.'),'canonical_mutations':0,'external_actions':0};_save(roots,'resume-batch.json',result);return result


def plan(workspace:Path,opportunity_id:str,*,catalog:Path|None=None,timestamp=None) -> dict:
    from careeros import learning_workflow
    roots,profile,_=_context(workspace)
    current=overview(workspace,timestamp=timestamp);job=next((j for j in current['jobs'] if j['opportunity_id']==opportunity_id),None)
    if not job:raise ValueError('Choose a saved job that represents the role you want. We need its actual requirements to build a useful plan.')
    if catalog is None:catalog=_save(roots,'empty-learning-catalog.json',[])
    learning=learning_workflow.build(workspace,catalog,opportunity_ids=[opportunity_id],include_profile_gaps=False,timestamp=timestamp)
    prefs=learning['preferences']
    lines=['# Your plan for '+job['role_title'],f"Target: {job['role_title']} at {job['employer_name']}",'This plan uses the posting and your career profile. It guides your next steps; it does not promise a job.','## What you can bring already']
    lines+=job['matches'] or ['Add clear examples of your work so we can see your starting strengths.']
    lines+=['## What to work on next']
    actions=[]
    for gap in job['gaps']:
        action={'capability':gap['capability'],'type':gap.get('requirement_subtype','SKILL'),'next_step':gap_advice(gap)};actions.append(action);lines+=['### '+gap['capability'],action['next_step']]
    lines+=['## A pace that fits your life',f"Weekly study time: {prefs.get('weekly_hours','Not set')} hours. Budget: {prefs.get('budget','Not set')} {prefs.get('currency','')}.",'Learning time in the selected plan: '+learning['path']['estimated_total_time']+'.','Learning cost: '+learning['path']['estimated_total_cost'].replace('practical materials not priced','check the cost of project materials').replace('currency unspecified','currency needs checking')+'.','## Your next steps']
    for step in learning['steps']:lines+=['### '+str(step['sequence'])+'. '+step['title'],'Allow '+step['estimated_time']+'. '+(step['completion_condition'] if step['step_type']=='PROJECT' else 'Finish the resource and keep notes on what you can now do.')]
    if not learning['steps']:lines.append('No verified learning option fits the details we have. Check your time and budget, then add current resources. We will not fill the list with guessed courses.')
    lines+=['## Check your progress','Keep your work and review what it shows. Courses do not count as professional experience. Confirm any credential award separately.','After you approve new career information, compare the role again. Update your resume and interview examples as needed.']
    from careeros.experience import _write,_report_pdf
    key=sha256_value(opportunity_id)[:16];path=f'career/plans/{key}/career-plan.md'
    _write(roots,path,'\n\n'.join(lines)+'\n');_report_pdf('Your Career Development Plan',lines[1:],roots.assert_write_allowed(roots.output_root/Path(path).with_suffix('.pdf'),'output'),keep_subsections=True,compact=True)
    import shutil
    learning_snapshot='career/plans/'+key+'/learning-plan.pdf'
    shutil.copyfile(roots.output_root/'learning/learning-roadmap.pdf',roots.assert_write_allowed(roots.output_root/learning_snapshot,'output'))
    result={'schema':'careeros.target-career-plan.v1','opportunity_id':opportunity_id,'target_role':job['role_title'],'category':job['category'],'actions':actions,'learning_path_id':learning['path']['learning_path_id'],'path':path,'learning_report':learning_snapshot,'message':('Start with the gaps that matter for this role. Review the learning steps and work samples against your time and budget.' if learning['steps'] else 'Review the gaps and practical next steps. We have not found a verified learning option that fits your current details.' if actions else 'Your recorded background covers the requirements we checked. More training may not be needed for this role.'),'canonical_mutations':0,'external_actions':0};_save(roots,'plans/'+key+'.json',result);return result


def render(workspace:Path,bundle:dict):
    from careeros.experience import _write,_report_pdf
    roots=experience.context(workspace);lines=['# Your next career move',bundle['message'],'Ready Now: your recorded experience fits the requirements we checked. Stretch Roles: some gaps or details need work. Dream Roles: roles you chose as longer-term goals. None of these labels guarantees a job.']
    parts=['<h1>Your next career move</h1><p>Find work that fits you now, explore a step up, and plan for the role you want next.</p>']
    for category in CATEGORIES:
        lines.append('## '+category);parts.append('<section><h2>'+category+'</h2>')
        jobs=[j for j in bundle['jobs'] if j['category']==category]
        if not jobs:parts.append('<p>No jobs in this group yet.</p>');lines.append('No jobs in this group yet.')
        for j in jobs:
            lines+=['### '+j['role_title']+' at '+j['employer_name'],j['why']]
            if j['matches']:lines.append('You can draw on: '+', '.join(j['matches'])+'.')
            lines += ['To work on: '+g['capability']+'. '+gap_advice(g) for g in j['gaps']]
            lines += j['checks']
            parts.append('<article><h3>'+html.escape(j['role_title'])+'</h3><p>'+html.escape(j['employer_name']+' · '+str(j.get('location') or 'Location to check'))+'</p><p>'+html.escape(j['why'])+'</p>')
            if j['matches']:parts.append('<p><b>Your strengths:</b> '+html.escape(', '.join(j['matches']))+'</p>')
            for g in j['gaps']:parts.append('<p><b>'+html.escape(g['capability'])+':</b> '+html.escape(gap_advice(g))+'</p>')
            for note in j['checks']:parts.append('<p>'+html.escape(note)+'</p>')
            if str(j.get('source_url') or '').startswith('https://'):parts.append('<a rel="noreferrer" href="'+html.escape(j['source_url'],quote=True)+'">Read the employer posting</a>');lines.append('Employer posting: '+j['source_url'])
            parts.append('</article>')
        parts.append('</section>')
    if bundle.get('excluded'):
        note='We left out '+str(len(bundle['excluded']))+' postings that were closed or did not fit your search preferences.'
        lines.append(note);parts.append('<p>'+note+'</p>')
    for failure in bundle.get('source_failures',[]):
        note='We could not check '+failure['employer']+'. Try that source again or use another employer posting.'
        lines.append(note);parts.append('<p>'+html.escape(note)+'</p>')
    parts.append('<section><h2>Your resume drafts</h2>');lines.append('## Your resume drafts')
    for row in bundle.get('resumes',[]):
        lines.append(row['role_title']+' at '+row['employer_name']+': '+row['message'])
        if row.get('path'):parts.append('<p><a href="../'+html.escape(row['path'],quote=True)+'">'+html.escape(row['role_title']+' · '+row['employer_name'])+' — review resume</a></p>')
        else:parts.append('<p>'+html.escape(row['role_title']+': '+row['message'])+'</p>')
    parts.append('</section><p>Your profile has not been changed. Nothing has been sent.</p>')
    _write(roots,'job-search/your-next-move.md','\n\n'.join(lines)+'\n');_report_pdf('Your Next Career Move',lines[1:],roots.assert_write_allowed(roots.output_root/'job-search/your-next-move.pdf','output'),keep_subsections=True)
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Your next career move</title><style>body{margin:0;background:#f2f5f8;color:#15233a;font:16px/1.6 system-ui}main{max-width:1040px;margin:36px auto;padding:30px}h1{font-size:38px}h2{color:#1f4f78;margin-top:36px}article{background:white;border:1px solid #dce3eb;border-radius:10px;padding:22px;margin:16px 0}h3{margin-top:0}a{color:#1f4f78;overflow-wrap:anywhere}@media(max-width:600px){main{margin:0;padding:20px}h1{font-size:29px}}</style><main><nav><a href="../index.html">Your career home</a> · <a href="your-next-move.pdf">Download this report</a> · <a href="../learning/index.html">Your learning plan</a></nav>'+''.join(parts)+'</main></html>'
    _write(roots,'job-search/index.html',page)
