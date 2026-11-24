"""Self-contained, immutable local application folders over the existing writers."""
from __future__ import annotations
import html
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit
from careeros.core.io import atomic_write_json, read_json, sha256_file


def _public_url(value):
    p=urlsplit(str(value or ''))
    return p.scheme=='https' and bool(p.hostname) and not p.username and not p.password


def validate_application_details(opp):
    url=opp.get('application_url');source=opp.get('application_url_source')
    if opp.get('source_url') and not _public_url(opp['source_url']):raise ValueError('Use a public HTTPS employer posting link.')
    if url and (not _public_url(url) or not isinstance(source,dict) or not _public_url(source.get('url')) or not source.get('captured_at') or source.get('verified') is not True):
        raise ValueError('A direct application URL needs an observed HTTPS form, its source, capture date and verified=true. A listing alone is not a direct application link.')
    questions=opp.get('application_questions',[])
    if not isinstance(questions,list) or len(questions)>200:raise ValueError('Supply at most 200 actual application questions.')
    if questions:
        src=opp.get('application_question_source')
        if not isinstance(src,dict) or not _public_url(src.get('url')) or not src.get('captured_at'):raise ValueError('Employer questions need their source URL and capture time.')
        ids=set()
        for q in questions:
            if not isinstance(q,dict) or not isinstance(q.get('id'),str) or not q['id'] or q['id'] in ids or not isinstance(q.get('text'),str) or not q['text'].strip():raise ValueError('Each actual question needs a unique ID and exact text.')
            if 'required' in q and not isinstance(q['required'],bool):raise ValueError('Question required must be true or false.')
            if q.get('max_length') is not None and (not isinstance(q['max_length'],int) or isinstance(q['max_length'],bool) or q['max_length']<1):raise ValueError('Question length limits must be positive integers.')
            ids.add(q['id'])


def letter_decision(opp,snapshot,content,policy='AUTO'):
    if policy not in {'AUTO','REQUESTED','OMIT'}:raise ValueError('Choose AUTO, REQUESTED or OMIT for cover letters.')
    requirement=opp.get('cover_letter_requirement','UNKNOWN')
    actual=' '.join(q['text'] for q in opp.get('application_questions',[]) if q.get('required'))
    required=requirement=='REQUIRED' or bool(re.search(r'(?:cover letter|letter of interest)\s+(?:is\s+)?required|required\s+(?:cover letter|letter of interest)',snapshot['text'],re.I)) or bool(re.search('cover letter|letter of interest',actual,re.I))
    if required:return {'decision':'REQUIRED','generate':True,'reason':'The posting or captured form requires a cover letter.'}
    if policy=='OMIT' or requirement=='NOT_ACCEPTED':return {'decision':'NOT_NEEDED','generate':False,'reason':'Omitted by request or the form does not accept a cover letter.'}
    if policy=='REQUESTED':return {'decision':'REQUESTED','generate':True,'reason':'You requested a cover letter.'}
    strategy=content.get('recruiter_conversion_strategy_v2',{})
    transition=strategy.get('summary_archetype')=='PROFESSIONAL_TRANSITION'
    useful=any(re.search(r'why.*(?:role|company)|additional information|cover letter',q['text'],re.I) for q in opp.get('application_questions',[]))
    if transition or useful:return {'decision':'BENEFICIAL_OPTIONAL','generate':True,'reason':'A supported transition or an invitation to explain relevant work makes a short letter useful.'}
    return {'decision':'NOT_NEEDED','generate':False,'reason':'The posting does not require a letter; the resume and screening answers carry the application.'}


def verify_packet(roots,packet):
    manifest_path=roots.output_root/packet['document_manifest']
    if not manifest_path.is_relative_to(roots.output_root) or not manifest_path.is_file():raise PermissionError('The application manifest is missing.')
    if packet.get('document_manifest_sha256') and sha256_file(manifest_path)!=packet['document_manifest_sha256']:raise PermissionError('The application manifest has changed.')
    manifest=read_json(manifest_path)
    if manifest['packet_id']!=packet['packet_id'] or manifest['resume']['sha256']!=packet['resume_sha256']:raise PermissionError('The application manifest belongs to different documents.')
    for item in manifest['documents']:
        path=(manifest_path.parent/item['filename']).resolve()
        if not path.is_relative_to(manifest_path.parent.resolve()) or not path.is_file() or sha256_file(path)!=item['sha256']:
            raise PermissionError('An application document is missing or changed: '+item['filename'])
    return manifest


def packet_view(workspace,packet,artifact):
    from careeros import experience
    from careeros.presentation import label
    from careeros.career_conversion import build_employer_need_trace
    roots=experience.context(workspace);opp,snapshot,qualification=experience.job_context(roots,packet['opportunity_id'])
    if packet.get('document_manifest') and (roots.output_root/packet['document_manifest']).is_file():
        manifest=verify_packet(roots,packet);packet['document_manifest_sha256']=sha256_file(roots.output_root/packet['document_manifest']);return manifest
    folder=roots.assert_write_allowed(roots.output_root/'packets'/packet['packet_id'].split(':')[-1],'output');folder.parent.mkdir(parents=True,exist_ok=True)
    if folder.exists():raise PermissionError('An incomplete application folder exists; retain it for recovery before retrying.')
    build=next(p.parent for p in (roots.state_root/'resume-builds').glob('*/build.json') if read_json(p)['build_id']==packet['build_id'])
    content=read_json(build/'content.json');validation=read_json(build/'validation.json')
    exported=experience.export_resume(workspace,packet['build_id'])
    if exported['semantic_round_trip']!='PASS':raise PermissionError('The editable resume did not preserve its content.')
    if packet['cover_letter']['generate']:
        letter=experience.cover_letter(workspace,packet['opportunity_id'],packet['build_id'])
        packet['cover_letter']['export']=letter
    parent=roots.state_root/'opportunities'/opp['opportunity_id']
    intelligence=read_json(parent/'jd-intelligence.json');matrix=read_json(parent/'job-evidence-matrix.json');needs=build_employer_need_trace(intelligence,matrix,snapshot)
    with tempfile.TemporaryDirectory(prefix='.packet-draft-',dir=folder.parent) as temporary:
        stage=Path(temporary)
        shutil.copyfile(roots.output_root/artifact['path'],stage/'Resume.pdf')
        shutil.copyfile(roots.output_root/exported['path'],stage/'Resume.docx')
        if packet['cover_letter']['generate']:
            for item in packet['cover_letter']['export']['artifacts']:
                source=roots.output_root/item['path'];shutil.copyfile(source,stage/('Cover Letter'+source.suffix))
        (stage/'Job Description.md').write_text('# '+opp['role_title']+' at '+opp['employer_name']+'\n\n'+snapshot['text']+'\n')
        atomic_write_json(stage/'Job Description.json',snapshot)
        atomic_write_json(stage/'Opportunity.json',opp)
        atomic_write_json(stage/'Qualification.json',qualification)
        atomic_write_json(stage/'Employer Needs.json',needs)
        atomic_write_json(stage/'Application Answers.json',packet['application_answers'])
        atomic_write_json(stage/'Validation.json',{'resume':validation,'docx':exported,'cover_letter':packet['cover_letter'],'career_facts_unchanged':True,'human_review_required':True,'docx_visual_review':'RENDER_REQUIRED','resume_checks':{name:read_json(build/(name+'.json')) for name in ['job-specific-qa','ats-resume-round-trip','recruiter-copy-quality-v2','public-copy-boundary-v1','job-tailoring-trace','job-evidence-matrix','resume-completeness'] if (build/(name+'.json')).is_file()},'universal_ats_compatibility_claimed':False})
        answers=['# Application questions and draft answers','Actual questions come from the captured employer form. Anticipated questions are practice only. Review every draft before entering it in a form.']
        for q in packet['application_answers']['questions']:
            answers+=['## '+q['text'],'Employer question' if q['kind']=='ACTUAL_EMPLOYER_QUESTION' else 'Anticipated question — not confirmed on the employer form',('Required' if q.get('required') else 'Optional / practice'),q['answer'] or 'Your answer is still needed. Career OS has not guessed this information.']
        if packet['application_answers']['captured_question_state']!='CAPTURED':answers+=['## Check the application form','Its actual questions were not accessible or have not been captured. The practice question is not a complete screening form.']
        (stage/'Application Answers.md').write_text('\n\n'.join(answers)+'\n')
        notes=['# Qualification and employer needs',f"{opp['role_title']} at {opp['employer_name']}",'Qualification: '+label(qualification['decision']),'This compares the recorded requirements with approved career information. It is not a guarantee of interview selection.']
        notes += [f"{v['capability']}: {label(v['match'])}"+(f" — {v['reason']}" if v.get('reason') else '') for v in qualification['evidence']]
        notes += [f"Check {v['capability']}: {v.get('reason','')}" for v in qualification['gaps']]
        (stage/'Fit Assessment.md').write_text('\n\n'.join(notes)+'\n')
        direct=opp.get('application_url');listing=opp.get('source_url')
        links=[('Tailored resume PDF','Resume.pdf'),('Editable resume DOCX','Resume.docx'),('Original job description','Job Description.md'),('Qualification assessment','Fit Assessment.md'),('Employer needs and evidence','Employer Needs.json'),('Questions and draft answers','Application Answers.md'),('Validation details','Validation.json'),('Document manifest','manifest.json')]
        if packet['cover_letter']['generate']:links[2:2]=[('Cover letter PDF','Cover Letter.pdf'),('Editable cover letter DOCX','Cover Letter.docx')]
        unresolved=packet['application_answers']['material_questions']
        checks=['Confirm the employer and exact job title.','Open the employer form and check that the job is still open.','Review contact details, dates, qualifications and every work example.','Read the editable exports in your editor; formatting can vary.','Review the proposed answers and complete any missing answers.','Upload only the documents the employer requests; keep assessments and validation files private.','Read any consent or legal declaration yourself before accepting it.','Submit manually only when you are ready, then record the application and any follow-up date.']
        message=('Direct application: ['+opp['role_title']+' at '+opp['employer_name']+']('+direct+')' if direct else 'Direct application link: not verified. Open the employer posting and locate its application form; Career OS has not invented a link.')
        letter_label={'REQUIRED':'Required','REQUESTED':'Requested by you','BENEFICIAL_OPTIONAL':'Optional and recommended','NOT_NEEDED':'Not needed'}[packet['cover_letter']['decision']]
        source_note=f"Posting last checked: {packet['opportunity_freshness'].get('last_verified_at') or 'Unknown'}. Freshness at preparation: {label(packet['opportunity_freshness']['freshness_state'])}. Recheck before applying."
        fiction='Fictional example. This package does not represent a real vacancy or application portal.' if opp['source_type']=='SYNTHETIC' else ''
        lines=['# Start here',opp['role_title']+' at '+opp['employer_name'],fiction,'Your draft application documents are below. Nothing has been submitted.',message]
        if listing:lines+=['Employer posting / source: '+listing]
        lines += [source_note,'Cover letter: '+letter_label+'. '+packet['cover_letter']['reason'],'## Your files']+[f'- [{name}]({quote(path)})' for name,path in links]
        lines+=['## Questions still to answer']+([f"- {v['question']}" for v in unresolved] or ['No captured required question is unanswered. Check the live form for new or hidden questions.'])
        lines+=['## Application checklist']+['- [ ] '+v for v in checks]
        text='\n\n'.join(lines)+'\n';(stage/'Start Here.md').write_text(text);(stage/'README.md').write_text(text)
        parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Start Here — '+html.escape(opp['role_title'])+'</title><style>body{font:17px/1.6 system-ui,sans-serif;max-width:860px;margin:40px auto;padding:0 24px;color:#172b40}h1,h2{line-height:1.2}a{color:#185b90}li{margin:10px 0}.notice{background:#f0f5fa;padding:16px;border-radius:8px}a{overflow-wrap:anywhere}</style><h1>'+html.escape(opp['role_title'])+'</h1><p>'+html.escape(opp['employer_name'])+'</p><p class="notice">Drafts for your review. Nothing has been submitted.</p>']
        if fiction:parts+=['<p class="notice">'+html.escape(fiction)+'</p>']
        if direct:parts+=['<p><a rel="noreferrer" href="'+html.escape(direct,quote=True)+'">Open the employer’s application form</a></p>']
        else:parts+=['<p>Direct application link not verified. Find the form on the employer posting.</p>']
        if listing:parts+=['<p><a rel="noreferrer" href="'+html.escape(listing,quote=True)+'">Read the employer posting</a></p>']
        if opp.get('application_url_source'):parts+=['<p>Application-link source: '+html.escape(opp['application_url_source']['url'])+' · checked '+html.escape(opp['application_url_source']['captured_at'])+'</p>']
        parts+=['<p>'+html.escape(source_note)+'</p><p>Cover letter: '+html.escape(letter_label+'. '+packet['cover_letter']['reason'])+'</p><h2>Your files</h2><ul>']+[f'<li><a href="{quote(path)}">{html.escape(name)}</a></li>' for name,path in links]+['</ul><h2>Questions still to answer</h2><ul>']
        parts += ['<li>'+html.escape(v['question'])+'</li>' for v in unresolved] or ['<li>No captured required question is unanswered. Check the live form for new or hidden questions.</li>']
        if packet['application_answers']['captured_question_state']!='CAPTURED':parts+=['<li>The employer’s actual screening questions still need checking.</li>']
        parts+=['</ul><h2>Before you apply</h2><ol>']+['<li>'+html.escape(v)+'</li>' for v in checks]+['</ol></html>']
        (stage/'Start Here.html').write_text(''.join(parts))
        documents=[{'filename':p.name,'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in sorted(stage.iterdir()) if p.is_file()]
        manifest={'schema':'careeros.application-document-manifest.v1','packet_id':packet['packet_id'],'opportunity_id':opp['opportunity_id'],'employer_name':opp['employer_name'],'role_title':opp['role_title'],'review_state':'REVIEW_REQUIRED','resume':{'filename':'Resume.pdf','sha256':sha256_file(stage/'Resume.pdf')},'jd_snapshot_hash':snapshot['content_hash'],'application_url':direct,'listing_url':listing,'application_url_source':opp.get('application_url_source'),'opportunity_freshness':packet['opportunity_freshness'],'documents':documents,'external_actions':0}
        atomic_write_json(stage/'manifest.json',manifest)
        stage.rename(folder)
    packet['document_manifest']=str((folder/'manifest.json').relative_to(roots.output_root));packet['start_here']=str((folder/'Start Here.html').relative_to(roots.output_root))
    packet['completion_state']='DRAFT_NEEDS_ANSWERS' if unresolved or not direct or packet['application_answers']['captured_question_state']!='CAPTURED' else 'DRAFTS_PREPARED'
    packet['document_manifest_sha256']=sha256_file(folder/'manifest.json')
    return verify_packet(roots,packet)
