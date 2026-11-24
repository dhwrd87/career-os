"""Local, explicitly approved answer reuse and source-bound screening drafts."""
from __future__ import annotations
import re
from pathlib import Path
from careeros.core.io import atomic_write_json, read_json, sha256_value
from careeros.workspace import utc_now


def question_key(text):
    return sha256_value(' '.join(str(text).casefold().split()))


def load_bank(roots):
    path=roots.state_root/'application-answers/bank.json'
    return read_json(path) if path.is_file() else {'schema':'careeros.application-answer-bank.v1','entries':[]}


def save_bank(workspace:Path,payload:dict,*,approved=False,actor=None,timestamp=None):
    from careeros.experience import context
    if approved is not True or not actor or not actor.strip():
        raise PermissionError('Review the answers and explicitly approve saving them with your name.')
    roots=context(workspace);profile=read_json(roots.state_root/'profile/career-profile.json');bank=load_bank(roots)
    entries=payload.get('entries')
    if not isinstance(entries,list) or not entries:raise ValueError('Supply at least one answer to save.')
    known={v['record_id'] for group in ('employment','evidence','skills','education','credentials','projects') for v in profile.get(group,[])}
    pending=[]
    for item in entries:
        if not isinstance(item,dict) or not all(isinstance(item.get(k),str) and item[k].strip() for k in ('question','answer')):
            raise ValueError('Each saved answer needs its exact question and approved answer.')
        ids=item.get('source_record_ids',[])
        if not isinstance(ids,list) or any(v not in known for v in ids):raise ValueError('Answer references must point to approved career records.')
        for field in ('employer_name','role_title','location'):
            if item.get(field) is not None and (not isinstance(item[field],str) or not item[field].strip()):raise ValueError('Answer scope must name the employer or role, or be null for exact-question reuse.')
        if CONSEQUENTIAL.search(item['question']) and any(not item.get(k) for k in ('employer_name','role_title','location')):
            raise ValueError('Personal declarations need explicit employer, role and location scope before saving for reuse.')
        entry={k:item.get(k) for k in ('question','answer','employer_name','role_title','location')}
        entry.update(question_key=question_key(item['question']),source_record_ids=ids,profile_source_hash=profile['source_snapshot_hash'],approved_by=actor,approved_at=utc_now(timestamp))
        pending.append(entry)
    for entry in pending:
        bank['entries']=[v for v in bank['entries'] if (v['question_key'],v.get('employer_name'),v.get('role_title'),v.get('location'))!=(entry['question_key'],entry.get('employer_name'),entry.get('role_title'),entry.get('location'))]+[entry]
    atomic_write_json(roots.assert_write_allowed(roots.state_root/'application-answers/bank.json','state'),bank)
    return {'status':'SAVED','entries':len(pending),'external_actions':0,'canonical_mutations':0}


CONSEQUENTIAL=re.compile(r'authoriz|sponsor|citizen|visa|salary|compensat|pay expect|availab|start date|relocat|travel|shift|schedule|legal|convict|felon|criminal|background check|disab|veteran|gender|race|ethnic|pronoun|consent|agree|certify|attest|opt.?in|opt.?out|acknowledg|conflict|non.?compete|\bage\b|date of birth|security clearance',re.I)


def prepare_answers(roots,opp,profile,content,*,cover_letter_available=False,timestamp=None):
    actual=opp.get('application_questions',[])
    provenance=opp.get('application_question_source')
    # Only a captured source can turn a proposed question into an employer question.
    if actual and (not provenance or not provenance.get('url') or not provenance.get('captured_at')):
        raise ValueError('Actual employer questions need their source URL and capture time.')
    questions=[{**v,'kind':'ACTUAL_EMPLOYER_QUESTION'} for v in actual]
    questions.append({'id':'anticipated-background','text':'Which examples of your work are relevant to this role?','required':False,'kind':'ANTICIPATED_PREPARATION','field_type':'text'})
    bank=load_bank(roots);rows=[]
    for q in questions:
        text=q['text'];answer=None;ids=[];basis=None
        candidates=[v for v in bank['entries'] if v['question_key']==question_key(text) and v.get('employer_name') in (None,opp['employer_name']) and v.get('role_title') in (None,opp['role_title']) and v.get('profile_source_hash')==profile['source_snapshot_hash'] and (not CONSEQUENTIAL.search(text) or v.get('location')==opp.get('location'))]
        candidates.sort(key=lambda v:(bool(v.get('employer_name')),bool(v.get('role_title')),v['approved_at']),reverse=True)
        if candidates:answer=candidates[0]['answer'];ids=candidates[0]['source_record_ids'];basis='USER_APPROVED_EXACT_QUESTION'
        field=q.get('field_type','text').lower()
        if answer is None and not CONSEQUENTIAL.search(text):
            candidate=content['candidate']
            contact={'first_name':candidate['public_name'].split()[0],'last_name':candidate['public_name'].split()[-1],'email':candidate.get('email'),'phone':candidate.get('phone'),'name':candidate['public_name']}
            key=q.get('field_name') or {'first name':'first_name','last name':'last_name','email':'email','phone':'phone','name':'name'}.get(text.strip(' *:').lower())
            if 'file' in field and re.search(r'resume|curriculum|\bcv\b',text,re.I):answer='Upload Resume.pdf, or Resume.docx if the form requests an editable document.';basis='PREPARED_DOCUMENT'
            elif 'file' in field and 'cover letter' in text.lower() and cover_letter_available:answer='Upload Cover Letter.pdf, or Cover Letter.docx if requested.';basis='PREPARED_DOCUMENT'
            elif key in contact and contact[key]:answer=contact[key];basis='APPROVED_PROFILE_CONTACT'
            elif re.search(r'current or previous (?:employer|job title)',text,re.I):
                roles=sorted(profile.get('employment',[]),key=lambda v:int(v.get('start_year') or 0),reverse=True)
                if roles:
                    record=roles[0];answer=record['actual_title'] if 'job title' in text.lower() else record['employer'];ids=[record['record_id']];basis='APPROVED_EMPLOYMENT_RECORD'
            elif field in {'text','textarea','input_text','input_textarea'} and re.search(r'experience|background|work example|examples? of your work|project|skill|qualification',text,re.I):
                examples=[(s,b) for s in [*content.get('employment',[]),*content.get('projects',[])] for b in s['bullets'] if b.get('evidence_ids')]
                selected=examples[:2]
                if selected:
                    pieces=[]
                    for section,bullet in selected:
                        context=f"As {section['actual_title']} at {section['employer']}" if section.get('employer') else f"In the {section['name']} project"
                        from careeros.recruiter_conversion import first_person_fact
                        claim=first_person_fact(bullet['text']);pieces.append(context+', '+(claim if claim.startswith('I ') else claim[:1].lower()+claim[1:]))
                        ids.extend(bullet['evidence_ids'])
                    answer=f"For the {opp['role_title']} role at {opp['employer_name']}, my relevant work includes the following. "+' '.join(pieces);basis='VALIDATED_RESUME_EVIDENCE'
        options=q.get('options',[])
        labels=[v.get('label') if isinstance(v,dict) else v for v in options]
        if answer is not None and labels and answer not in labels:answer=None;basis=None;ids=[]
        limit=q.get('max_length')
        if answer is not None and limit and len(answer)>limit:answer=None;basis=None;ids=[]
        rows.append({**q,'answer':answer,'source_record_ids':sorted(set(ids)),'basis':basis,'status':'DRAFT_REVIEW_REQUIRED' if answer is not None else 'NEEDS_YOUR_ANSWER','source':provenance if q['kind']=='ACTUAL_EMPLOYER_QUESTION' else None})
    unresolved=[{'id':v['id'],'question':v['text'],'required':v.get('required',False)} for v in rows if v['kind']=='ACTUAL_EMPLOYER_QUESTION' and v['answer'] is None]
    return {'schema':'careeros.application-answer-drafts.v1','opportunity_id':opp['opportunity_id'],'employer_name':opp['employer_name'],'role_title':opp['role_title'],'captured_question_state':('CAPTURED' if provenance.get('complete',True) else 'PARTIAL_OR_UNAVAILABLE') if provenance else 'NOT_ACCESSIBLE_OR_NOT_CAPTURED','questions':rows,'unanswered':unresolved,'material_questions':[v for v in unresolved if v['required']],'status':'REVIEW_REQUIRED','created_at':utc_now(timestamp),'external_actions':0}
