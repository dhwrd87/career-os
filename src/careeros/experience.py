"""User workflows over the existing engines and separated workspace roots.

All outputs are local derivatives. Recorded events describe human-reported
activity; these commands never submit, send, schedule or purchase anything.
"""
from __future__ import annotations
import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config
from careeros.core.io import atomic_write_json, read_json, sha256_file, sha256_value
from careeros.workspace import require_current_workspace, utc_now
from careeros.presentation import label as display_label, gap_advice


def context(workspace: Path):
    require_current_workspace(workspace)
    return load_config(workspace / 'careeros.yaml').roots


def records(folder: Path) -> list[dict]:
    return [read_json(p) for p in sorted(folder.glob('*.json'))] if folder.is_dir() else []


def selected(folder: Path, key: str, value: str) -> dict:
    for record in records(folder):
        if record.get(key) == value:
            return record
    raise ValueError(f'Unknown {key}: {value}')


def job_context(roots, opportunity_id: str):
    # Resolve IDs against persisted records rather than interpolate user paths.
    opp = next((read_json(p) for p in sorted((roots.state_root / 'opportunities').glob('*/opportunity.json')) if read_json(p).get('opportunity_id') == opportunity_id), None)
    if not opp:
        raise ValueError('Unknown opportunity ID')
    folder = next(p.parent for p in (roots.state_root / 'opportunities').glob('*/opportunity.json') if read_json(p).get('opportunity_id') == opportunity_id)
    qualification = selected(roots.state_root / 'qualifications', 'opportunity_id', opportunity_id)
    snapshot = read_json(folder / 'jd-snapshot.json')
    return opp, snapshot, qualification


def _write(roots, relative: str, text: str) -> Path:
    target = roots.assert_write_allowed(roots.output_root / relative, 'output')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    return target


def _table(headers, rows):
    def cell(v):
        return str(v if v is not None else 'Unknown').replace('|', '/').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(map(cell, headers)) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |', *['| ' + ' | '.join(map(cell, r)) + ' |' for r in rows]]) + '\n'


def _report_pdf(title: str, paragraphs: list[str], path: Path, *, keep_subsections: bool = False, compact: bool = False):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('ReportBody', fontName='Helvetica', fontSize=10, leading=13 if compact else 14, spaceAfter=5 if compact else 8))
    if compact:
        styles['Heading2'].fontSize=12
        styles['Heading2'].leading=15
        styles['Heading2'].spaceBefore=8
        styles['Heading2'].spaceAfter=4
    story = [Paragraph(html.escape(title), styles['Title']), Spacer(1, 12)]
    block=[];pending=[]
    if keep_subsections:styles['Heading2'].keepWithNext=True
    for text in paragraphs:
        if not text:
            continue
        if text.startswith('#'):
            if block:story.append(KeepTogether(block));block=[]
            paragraph=Paragraph(html.escape(text.lstrip('# ')), styles['Heading2'])
            if keep_subsections and text.startswith('###'):
                block.extend(pending);pending=[];block.append(paragraph)
            elif keep_subsections:
                story.extend(pending);pending=[paragraph]
            else:story.append(paragraph)
        else:
            paragraph=Paragraph(html.escape(text).replace('\n', '<br/>'), styles['ReportBody'])
            if block:block.append(paragraph)
            elif pending:story.append(KeepTogether([*pending,paragraph]));pending=[]
            else:story.append(paragraph)
    if block:story.append(KeepTogether(block))
    story.extend(pending)
    path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(path), pagesize=(612,792), leftMargin=44.64, rightMargin=44.64, topMargin=36, bottomMargin=36, title=title, author='', creator='Career OS', pageCompression=1).build(story)


def export_resume(workspace: Path, build_id: str) -> dict:
    from careeros.document_exports import render_docx
    from careeros.updates import require_derivative_current
    roots = context(workspace)
    build = next((p for p in (roots.state_root / 'resume-builds').glob('*/build.json') if read_json(p).get('build_id') == build_id), None)
    if not build:
        raise ValueError('Unknown resume build')
    require_derivative_current(roots, 'RESUME_BUILD', build_id)
    validation = read_json(build.parent / 'validation.json')
    if validation['status'] != 'PASS':
        raise PermissionError('Resume export requires passing PDF validation')
    content, artifact = read_json(build.parent / 'content.json'), read_json(build.parent / 'artifact.json')
    target = roots.assert_write_allowed(roots.output_root / 'editable' / (Path(artifact['path']).stem + '.docx'), 'output')
    result = render_docx(content, target)
    result['source_build_id'] = build_id
    result['source_content_sha256'] = sha256_file(build.parent / 'content.json')
    result['path'] = str(target.relative_to(roots.output_root))
    atomic_write_json(roots.assert_write_allowed(build.parent / 'docx-export.json', 'state'), result)
    return result


def cover_letter(workspace: Path, opportunity_id: str, build_id: str) -> dict:
    from careeros.updates import require_derivative_current
    roots = context(workspace)
    opp, snapshot, qual = job_context(roots, opportunity_id)
    build = next((p for p in (roots.state_root / 'resume-builds').glob('*/build.json') if read_json(p).get('build_id') == build_id), None)
    if not build or read_json(build).get('opportunity_id') != opportunity_id:
        raise ValueError('Build must belong to the selected opportunity')
    require_derivative_current(roots, 'RESUME_BUILD', build_id)
    require_derivative_current(roots, 'QUALIFICATION', qual['qualification_id'])
    if qual['decision'] != 'QUALIFIED' or read_json(build.parent / 'validation.json')['status'] != 'PASS':
        raise PermissionError('Cover letter requires qualification and a validated resume')
    content = read_json(build.parent / 'content.json')
    evidence = [b for s in [*content.get('employment', []), *content.get('projects', [])] for b in s['bullets'] if b.get('evidence_ids')][:3]
    if not evidence:
        raise ValueError('No supported evidence available for a cover letter')
    # Explain two relevant connections rather than turn the whole resume into
    # prose. Employer needs guide selection; all claims still come from the
    # validated resume's evidence-bearing bullets.
    need_ids={key for need in content.get('employer_need_trace',{}).get('needs',[])[:3] for key in need.get('candidate_evidence_ids',[])}
    examples=[(section,b) for section in [*content.get('employment',[]),*content.get('projects',[])] for b in section['bullets'] if b.get('evidence_ids')]
    examples.sort(key=lambda row:(not bool(set(row[1]['evidence_ids']) & need_ids),not bool(row[0].get('employer'))))
    chosen=[];seen=set()
    for section,bullet in examples:
        if set(bullet['evidence_ids']) & seen:continue
        chosen.append((section,bullet));seen.update(bullet['evidence_ids'])
        if len(chosen)==2:break
    evidence=[b for _,b in chosen]
    requirement=next((v['capability'] for v in opp.get('requirements',[]) if v.get('requirement_class')=='REQUIRED'),None)
    need_text=requirement if requirement and (requirement.isupper() or requirement in {'Python','Linux','JavaScript','Splunk','Wireshark','Salesforce'}) else (requirement.lower() if requirement else None)
    opening=(f"Your {opp['role_title']} opening at {opp['employer_name']} calls for {need_text}." if requirement else f"I am applying for the {opp['role_title']} role at {opp['employer_name']}.")
    paragraphs=[f"Dear {opp['employer_name']} hiring team,",opening]
    previous_section=None
    for section,bullet in chosen:
        from careeros.recruiter_conversion import first_person_fact
        claim=first_person_fact(bullet['text'])
        claim=claim if claim.startswith('I ') else claim[:1].lower()+claim[1:]
        if section.get('employer'):
            letter_context=f"As {section['actual_title']} at {section['employer']}"
        else:letter_context=f"In the {section['name']} project"
        if section is previous_section:paragraphs[-1]+=' '+(claim.replace('I ','I also ',1) if claim.startswith('I ') else claim[:1].upper()+claim[1:])
        elif len(paragraphs)==2:paragraphs[-1]+=' '+letter_context+', '+claim
        else:paragraphs.append(letter_context+', '+claim)
        previous_section=section
    paragraphs+=['I can discuss this work and the results in more detail.','Sincerely,\n'+content['candidate']['public_name']]
    key = sha256_value([opportunity_id, build_id])[:16]
    path = _write(roots, f'applications/{key}/cover-letter.md', '# Cover letter\n\n' + '\n\n'.join(paragraphs) + '\n')
    pdf = roots.assert_write_allowed(path.with_suffix('.pdf'), 'output')
    _report_pdf(content['candidate']['public_name'] + ' Cover Letter', paragraphs, pdf)
    from docx import Document
    from docx.shared import Inches, Pt
    docx_path=roots.assert_write_allowed(path.with_suffix('.docx'),'output')
    document=Document();section=document.sections[0]
    section.page_width,section.page_height=Inches(8.5),Inches(11)
    section.left_margin=section.right_margin=Inches(.72)
    section.top_margin=section.bottom_margin=Inches(.6)
    normal=document.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(11)
    normal.paragraph_format.space_after=Pt(10)
    for paragraph in paragraphs:document.add_paragraph(paragraph)
    document.core_properties.title=content['candidate']['public_name']+' Cover Letter'
    document.core_properties.author=content['candidate']['public_name'];document.core_properties.last_modified_by='';document.core_properties.comments=''
    document.save(docx_path)
    if [p.text for p in Document(docx_path).paragraphs]!=paragraphs:raise ValueError('Cover letter DOCX lost paragraph content.')
    result = {'schema': 'careeros.cover-letter-export.v1', 'opportunity_id': opportunity_id, 'build_id': build_id, 'status': 'REVIEW_REQUIRED', 'evidence_ids': sorted({e for b in evidence for e in b['evidence_ids']}), 'source_content_sha256': sha256_file(build.parent / 'content.json'), 'job_snapshot_hash': snapshot['content_hash'], 'artifacts': [{'path': str(p.relative_to(roots.output_root)), 'sha256': sha256_file(p)} for p in (path, pdf, docx_path)], 'external_actions': 0}
    atomic_write_json(roots.assert_write_allowed(roots.state_root / 'cover-letters' / f'{key}.json', 'state'), result)
    return result


def record_event(workspace: Path, application_id: str, payload: dict, *, timestamp=None) -> dict:
    from careeros.application_state import make_application_event, record_application_event, build_submission_event
    roots = context(workspace)
    state = selected(roots.state_root / 'applications', 'application_id', application_id)
    if payload.get('human_confirmed') is not True:
        raise PermissionError('Recording activity requires explicit human confirmation')
    if payload['event_type'] == 'SUBMITTED':
        opp, snapshot, qual = job_context(roots, state['opportunity_id'])
        packet = selected(roots.state_root / 'application-packets', 'packet_id', state['packet_id'])
        if packet.get('document_manifest'):
            from careeros.application_documents import verify_packet
            verify_packet(roots,packet)
        artifact = next((read_json(p) for p in (roots.state_root / 'resume-builds').glob('*/artifact.json') if read_json(p)['artifact_id'] == state['resume_artifact_id']), None)
        artifact_path = (roots.output_root / artifact['path']).resolve() if artifact else None
        if not artifact_path or not artifact_path.is_relative_to(roots.output_root.resolve()) or not artifact_path.is_file() or sha256_file(artifact_path) != packet['resume_sha256']:
            raise PermissionError('Submitted artifact is missing or differs from the prepared packet')
        event = build_submission_event(state, resume_sha256=packet['resume_sha256'], job_snapshot_hash=packet['jd_snapshot']['content_hash'], actor=payload['actor'], occurred_at=payload['occurred_at'], external_ref=payload.get('external_ref'))
    else:
        event = make_application_event(application_id, payload['event_type'], previous_state=state['current_state'], actor=payload['actor'], source='HUMAN_REPORTED_ACTIVITY', occurred_at=payload['occurred_at'], recorded_at=timestamp or payload['occurred_at'], notes=payload.get('notes'), evidence_refs=payload.get('evidence_refs', []), human_confirmed=True, supersedes_event_id=payload.get('supersedes_event_id'), correction_state=payload.get('correction_state'))
    result = record_application_event(roots.state_root, state, event)
    return result


def follow_up(workspace: Path, application_id: str, *, due_at: str, channel: str) -> dict:
    from careeros.application_state import build_follow_up
    datetime.fromisoformat(due_at.replace('Z', '+00:00'))
    roots = context(workspace)
    state = selected(roots.state_root / 'applications', 'application_id', application_id)
    opp, _, _ = job_context(roots, state['opportunity_id'])
    key = sha256_value([application_id, due_at, channel])[:16]
    draft = _write(roots, f'applications/{key}/follow-up.md', f"# Follow up draft\n\nHello {opp['employer_name']} hiring team,\n\nI’m following up on my application for {opp['role_title']}. I remain interested and would appreciate any update on next steps. Thank you for your time.\n\nReview before sending. No message has been sent.\n")
    result = build_follow_up(application_id, due_at=due_at, channel=channel, draft_artifact=str(draft.relative_to(roots.output_root)))
    atomic_write_json(roots.assert_write_allowed(roots.state_root / 'follow-ups' / f'{key}.json', 'state'), result)
    return result


def interview(workspace: Path, opportunity_id: str, *, stage='RECRUITER_SCREEN', timestamp=None) -> dict:
    from careeros.interview_prep import build_interview_evidence_pack
    from careeros.career_conversion import build_employer_need_trace
    from careeros.job_intelligence import analyze_job_description, build_job_evidence_matrix
    from careeros.updates import require_derivative_current
    roots = context(workspace)
    opp, snapshot, qual = job_context(roots, opportunity_id)
    require_derivative_current(roots, 'QUALIFICATION', qual['qualification_id'])
    profile = read_json(roots.state_root / 'profile/career-profile.json')
    intelligence = analyze_job_description(opp, snapshot)
    matrix = build_job_evidence_matrix(profile, intelligence)
    trace = build_employer_need_trace(intelligence, matrix, snapshot)
    app = next((a for a in records(roots.state_root / 'applications') if a['opportunity_id'] == opportunity_id), None)
    if not app:
        raise ValueError('Prepare an application packet before interview preparation')
    key = sha256_value([opportunity_id, stage])[:16]
    pack, stories, boundaries = build_interview_evidence_pack(profile=profile, opportunity=opp, snapshot=snapshot, qualification=qual, employer_need_trace=trace, application_id=app['application_id'], interview_id='interview:' + key, stage=stage, timestamp=timestamp)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / 'interview-packs' / f'{key}.json', 'state'), pack)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / 'interview-packs' / f'{key}-stories.json', 'state'), stories)
    paragraphs = [f"{opp['role_title']} at {opp['employer_name']}", 'Your interview: ' + display_label(stage)]
    paragraphs += ['What the employer needs: ' + n['statement'] for n in pack['employer_need_summary']]
    for index, outline in enumerate(pack['answer_outlines'], 1):
        paragraphs.append(f'## Example {index} · ' + ('STAR: situation, task, action, result' if outline['format']=='STAR' else display_label(outline['format'])))
        for label, value in outline['fields'].items():
            if not value:
                continue
            if isinstance(value, list):
                value = '; '.join(str(v.get('value', v)) if isinstance(v, dict) else str(v) for v in value)
            paragraphs.append(label.replace('_',' ').capitalize() + ': ' + str(value))
        paragraphs.append('Keep your answer accurate: ' + ' '.join(outline['prohibited_inferences']))
    for walkthrough in pack['technical_walkthroughs']:
        paragraphs.append('## Technical walkthrough')
        for label in ('OBJECTIVE', 'ENVIRONMENT', 'TOOLS', 'WHAT_I_DID', 'WHAT_I_OBSERVED', 'RESULT'):
            value = walkthrough[label]
            if value:
                paragraphs.append(label.replace('_', ' ').title() + ': ' + ('; '.join(map(str, value)) if isinstance(value, list) else (display_label(value) if label=='ENVIRONMENT' else str(value))))
    paragraphs += ['Question to ask: ' + str(q.get('question') or q) for q in pack['candidate_questions']]
    paragraphs += pack['prep_checklist']
    md = _write(roots, f'interviews/{key}/interview-preparation.md', '# Interview preparation\n\n' + '\n\n'.join(paragraphs) + '\n')
    _report_pdf('Interview Preparation', paragraphs, md.with_suffix('.pdf'))
    return {'pack_id': pack['pack_id'], 'status': pack['pack_status'], 'qa': pack['qa_gates'], 'path': str(md.relative_to(roots.output_root)), 'external_actions': 0}


def analytics(workspace: Path, *, window_start='2000-01-01T00:00:00Z', window_end=None, timestamp=None) -> dict:
    from careeros.application_state import read_event_log
    from careeros.conversion_learning import build_conversion_learning_bundle
    roots = context(workspace)
    profile = read_json(roots.state_root / 'profile/career-profile.json')
    apps = records(roots.state_root / 'applications')
    logs = {a['application_id']: read_event_log(roots.state_root / 'application-events' / (a['application_id'].split(':')[-1] + '.jsonl')) for a in apps}
    bundle = build_conversion_learning_bundle(candidate_profile_id=profile['profile_id'], opportunities=[read_json(p) for p in (roots.state_root / 'opportunities').glob('*/opportunity.json')], applications=apps, event_logs=logs, qualifications=records(roots.state_root / 'qualifications'), resume_variants=[read_json(p) for p in (roots.state_root / 'resume-builds').glob('*/build.json')], employer_need_traces=[read_json(p) for p in (roots.state_root / 'resume-builds').glob('*/employer-need-trace.json')], development_actions=[], course_options=[], window_start=window_start, window_end=window_end or utc_now(timestamp), timestamp=timestamp)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / 'reports/conversion-learning.json', 'state'), bundle)
    lines = ['# Career progress\n', 'Recorded applications: ' + str(bundle['cohort']['sample_count']), 'What these results can tell you: ' + display_label(bundle['cohort']['maturity_state']), 'These results describe the applications you recorded here. They cannot tell us what caused an employer to respond.', '## How your applications are progressing']
    for label, rate in bundle['conversion_metrics']['rates'].items():
        value = 'No observations' if rate['rate'] is None else f"{rate['numerator']} / {rate['denominator']} ({rate['rate']:.0%})"
        lines.append(label.replace('_', ' ').title() + ': ' + value)
    lines.append('## Development gaps')
    lines += [g['capability'] + ': ' + str(g['job_count']) + ' observed jobs; ' + g['classification'].replace('_', ' ').lower() for g in bundle['gap_recurrence']['gaps']]
    if not bundle['gap_recurrence']['gaps']:
        lines.append('We have not found gaps in the jobs checked so far. A wider search may reveal other requirements.')
    lines.append('## Strengths you can build on')
    lines.append('Keep records of similar jobs and their outcomes. With more results, it becomes easier to see what is working.')
    _write(roots, 'reports/career-progress.md', '\n\n'.join(lines))
    _report_pdf('Career Progress', lines[1:], roots.assert_write_allowed(roots.output_root / 'reports/career-progress.pdf', 'output'))
    return bundle


def discovery(workspace: Path, source: Path, *, limit=25, timestamp=None) -> dict:
    from careeros import opportunity, opportunity_registry
    roots = context(workspace)
    payload = read_json(source)
    if isinstance(payload, dict) and payload.get('schema') == 'careeros.discovery-source-proposal.v1':
        if payload.get('requirement_review_status') != 'REVIEWED' or any(not j.get('requirements') for j in payload['opportunities']):
            raise PermissionError('Review source-grounded job requirements before discovery ingestion')
    jobs = payload if isinstance(payload, list) else payload['opportunities']
    if not 1 <= limit <= 100:
        raise ValueError('Discovery limit must be between 1 and 100')
    result = opportunity_registry.reconcile_workspace_discovery(workspace, jobs[:limit], timestamp=timestamp)
    imported = []
    # Ingest through the real validation/qualification pipeline, not registry-only success.
    for job, decision in zip(jobs[:limit], result['results']):
        if decision['classification'] not in {'NEW', 'KNOWN_UPDATED', 'REPOST'}:
            continue
        cached = roots.assert_write_allowed(roots.cache_root / 'discovery-input.json', 'cache')
        atomic_write_json(cached, job)
        item, _ = opportunity.ingest(workspace, cached, timestamp=timestamp)
        qual = opportunity.qualify(workspace, item['opportunity_id'], timestamp=timestamp)
        imported.append({'opportunity_id': item['opportunity_id'], 'qualification': qual['decision']})
    result['imported'] = imported
    result['source_sha256'] = sha256_file(source)
    result['source_mode'] = 'USER_SUPPLIED_CATALOG'
    result['network_requests'] = 0
    result['truncated'] = len(jobs) > limit
    opportunity_registry.build_persistent_registry(roots.state_root, timestamp=timestamp)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / 'discovery/latest.json', 'state'), result)
    return result


def dashboard(workspace: Path) -> dict:
    roots = context(workspace)
    from careeros.learning_workflow import ensure_entry
    ensure_entry(workspace)
    profile_path = roots.state_root / 'profile/career-profile.json'
    profile = read_json(profile_path) if profile_path.is_file() else {}
    candidate = profile.get('candidate', {})
    name = candidate.get('public_name', 'Your Career OS')
    opportunities = [read_json(p) for p in sorted((roots.state_root / 'opportunities').glob('*/opportunity.json'))]
    qualifications = {q['opportunity_id']: q for q in records(roots.state_root / 'qualifications')}
    priorities = prioritize(workspace)
    journey_view=None
    family_path=roots.state_root/'role-families/active.json'
    if profile and family_path.is_file() and read_json(family_path)['approval_state']=='APPROVED':
        from careeros.journey import overview
        journey_view=overview(workspace)
    categories={j['opportunity_id']:j['category'] for j in journey_view['jobs']} if journey_view else {}
    order = {r['opportunity_id']: i for i, r in enumerate(priorities['rankings'])}
    opportunities.sort(key=lambda o: order[o['opportunity_id']])
    applications = records(roots.state_root / 'applications')
    follows = records(roots.state_root / 'follow-ups')
    rows = [[o['role_title'], o['employer_name'], categories.get(o['opportunity_id'],display_label(qualifications.get(o['opportunity_id'], {}).get('decision', 'NOT_EVALUATED'))), display_label(next((a['current_state'] for a in applications if a['opportunity_id'] == o['opportunity_id']), 'NOT_PREPARED'))] for o in opportunities]
    profile_md = '# Career profile\n\n' + name + '\n\n## Professional experience\n\n'
    employment = sorted(profile.get('employment', []), key=lambda r: (r.get('end_year') is None, int(r.get('start_year') or 0)), reverse=True)
    for role in employment:
        from careeros.resume_ats import format_public_date
        profile_md += f"### {role['actual_title']}\n\n{role['employer']} · {format_public_date(role)}\n\n"
        profile_md += '\n'.join('- ' + e['summary'] for e in profile.get('evidence', []) if role['record_id'] in e.get('employment_ids', [])) + '\n\n'
    for key in ('skills', 'credentials', 'education', 'projects', 'evidence'):
        profile_md += f'## {dict(evidence="Examples of your work",credentials="Qualifications and awards").get(key,key.title())}\n\n' + '\n'.join('- ' + str(i.get('name') or i.get('title') or i.get('institution') or i.get('summary') or i.get('statement') or 'Details need review') for i in profile.get(key, [])) + '\n\n'
    _write(roots, 'profile/career-profile.md', profile_md)
    _report_pdf(name + ' Career Profile', [line for line in profile_md.split('\n\n') if line], roots.assert_write_allowed(roots.output_root / 'profile/career-profile.pdf', 'output'))
    for opp in opportunities:
        qual = qualifications.get(opp['opportunity_id'], {})
        paragraphs = [opp['role_title'] + ' at ' + opp['employer_name'], 'Your fit: ' + display_label(qual.get('decision', 'NOT_EVALUATED'))]
        paragraphs += ['Requirement: ' + r['capability'] + ' (' + display_label(r.get('requirement_class', 'UNKNOWN')) + ')' for r in opp['requirements']]
        evidence_index = {e['record_id']: e for e in profile.get('evidence', [])}
        for match in qual.get('evidence', []):
            sources = [evidence_index[r]['summary'] for r in match.get('record_ids', []) if r in evidence_index]
            if sources:
                paragraphs.append('Your experience with ' + match['capability'] + ': ' + ' '.join(sources))
        paragraphs += ['To address: ' + g.get('capability', 'Unknown') + '. ' + gap_advice(g) for g in qual.get('gaps', [])]
        key = sha256_value(opp['opportunity_id'])[:16]
        _write(roots, f'opportunities/{key}/opportunity-report.md', '# Opportunity report\n\n' + '\n\n'.join(paragraphs) + '\n')
        _report_pdf('Opportunity Report', paragraphs, roots.assert_write_allowed(roots.output_root / f'opportunities/{key}/opportunity-report.pdf', 'output'))
    tracker = '# Application tracker\n\n' + _table(['Job', 'Employer', 'Where it fits', 'Application progress'], rows)
    _write(roots, 'applications/application-tracker.md', tracker)
    follow_md = '# Follow ups\n\n' + _table(['Application', 'Due', 'How to follow up', 'Progress'], [[next((o['role_title']+' at '+o['employer_name'] for o in opportunities if any(a['application_id']==f['application_id'] and a['opportunity_id']==o['opportunity_id'] for a in applications)),'Application'), f['due_at'], display_label(f['channel']), display_label(f['disposition'])] for f in follows])
    _write(roots, 'applications/follow-ups.md', follow_md)
    # Relative, browser-safe links to generated artifacts only; no third-party assets.
    links = []
    for p in sorted(roots.output_root.rglob('*')):
        if not p.is_file() or p.suffix not in {'.md', '.pdf', '.docx'} or p.name == 'HOME.md':
            continue
        relative = p.relative_to(roots.output_root)
        title = {'career-profile':'Your career profile','learning-roadmap':'Your learning plan','career-progress':'Your career progress','application-tracker':'Your applications','follow-ups':'Your follow-ups','opportunity-priorities':'Jobs to consider first','other-roles':'Other roles to explore','your-next-move':'Your next career move'}.get(p.stem,p.stem.replace('-', ' ').title())
        if relative.parts[0] == 'opportunities':
            match = next((o for o in opportunities if sha256_value(o['opportunity_id'])[:16] == relative.parts[1]), None)
            if match:
                title = match['role_title'] + ' · ' + match['employer_name']
        elif relative.parts[0] == 'packets':
            title = 'Application documents · ' + ('Review checklist' if p.stem == 'README' else 'Resume')
        links.append((str(relative), title + ' · ' + {'.md':'Text','.pdf':'PDF','.docx':'Editable DOCX'}[p.suffix]))
    md = f'# {name}\n\nCareer OS workspace\n\n## Overview\n\n{len(opportunities)} opportunities · {len(applications)} application packets · {len(follows)} follow ups\n\n## Opportunities\n\n' + _table(['Job', 'Employer', 'Where it fits', 'Application progress'], rows) + '\n## Documents\n\n' + '\n'.join(f'- [{title}]({path.replace(" ", "%20")})' for path, title in links) + '\n'
    _write(roots, 'HOME.md', md)
    def esc(v): return html.escape(str(v), quote=True)
    table = '<table><thead><tr>' + ''.join('<th>' + esc(h) + '</th>' for h in ['Role','Employer','Fit','Stage']) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + esc(c) + '</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table>'
    cards = ''.join(f'<article><strong>{v}</strong><span>{label}</span></article>' for v, label in [(len(opportunities),'Opportunities'),(len(applications),'Applications'),(len(follows),'Follow ups')])
    nav = ''.join(f'<a href="{esc(path.replace(" ", "%20"))}">{esc(title)}</a>' for path, title in links)
    nav = '<a href="learning/index.html">Your learning plan</a>' + nav if (roots.output_root / 'learning/index.html').exists() else nav
    if journey_view:
        nav='<a href="job-search/index.html">Ready Now, Stretch Roles and Dream Roles</a>'+nav
        cards=''.join(f'<article><strong>{journey_view["categories"][category]}</strong><span>{category}</span></article>' for category in ('Ready Now','Stretch Roles','Dream Roles'))
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(name)} Career OS</title><style>
body{{margin:0;background:#f2f5f8;color:#15233a;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1120px;margin:56px auto;padding:0 28px}}header{{border-bottom:1px solid #c7d2df;padding-bottom:24px}}small{{text-transform:uppercase;letter-spacing:.15em;color:#1f4f78}}h1{{font-size:42px;margin:10px 0}}h2{{font-size:22px;margin-top:32px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:28px 0}}article{{background:white;padding:22px;border:1px solid #dce3eb;border-radius:12px}}strong{{display:block;font-size:32px}}span{{color:#526171}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{text-align:left;padding:14px;border-bottom:1px solid #dce3eb}}th{{font-size:12px;text-transform:uppercase;color:#526171}}nav{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}a{{color:#1f4f78;text-decoration:none;background:white;padding:12px;border:1px solid #dce3eb;border-radius:6px;overflow-wrap:anywhere}}a:hover,a:focus{{outline:2px solid #1f4f78}}@media(max-width:700px){{main{{margin:24px auto}}h1{{font-size:30px}}.cards,nav{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}@media print{{body{{background:white}}main{{margin:0}}}}</style><main><header><small>Your career, in one place</small><h1>{esc(name)}</h1><p>Build on what you know. Find work that fits you, and plan your next step.</p></header><section class="cards" aria-label="Workspace totals">{cards}</section><h2>Jobs to consider</h2>{table}<h2>Your documents</h2><nav aria-label="Generated documents">{nav}</nav><p>These drafts use the career details you have reviewed. Check them before you share or send them.</p></main></html>'''
    _write(roots, 'index.html', page)
    return {'home': 'index.html', 'markdown': 'HOME.md', 'documents': len(links), 'opportunities': len(opportunities), 'applications': len(applications), 'external_actions': 0}


def learning(workspace: Path, catalog: Path, *, timestamp=None) -> dict:
    from careeros.learning_workflow import build
    return build(workspace, catalog, timestamp=timestamp)


def queue_audit(workspace: Path) -> dict:
    from careeros.document_quality import inspect_pdf
    from careeros.recruiter_conversion import cross_summary_templates
    roots = context(workspace)
    findings, checked = [], []
    for path in sorted((roots.state_root / 'resume-builds').glob('*/artifact.json')):
        artifact = read_json(path)
        pdf = (roots.output_root / artifact['path']).resolve()
        if not pdf.is_relative_to(roots.output_root.resolve()) or not pdf.is_file():
            findings.append({'artifact_id': artifact['artifact_id'], 'issue': 'MISSING_OR_OUTSIDE_OUTPUT_ROOT'})
            continue
        if sha256_file(pdf) != artifact['sha256']:
            findings.append({'artifact_id': artifact['artifact_id'], 'issue': 'HASH_MISMATCH'})
        quality = inspect_pdf(pdf)
        if quality['status'] != 'PASS':
            findings.append({'artifact_id': artifact['artifact_id'], 'issue': 'PDF_PREFLIGHT', 'details': quality['findings']})
        checked.append({'artifact_id': artifact['artifact_id'], 'status': quality['status'], 'accessibility': quality['accessibility']})
    from careeros.application_documents import verify_packet
    for packet in records(roots.state_root/'application-packets'):
        if packet.get('document_manifest'):
            try:verify_packet(roots,packet)
            except PermissionError as exc:findings.append({'packet_id':packet['packet_id'],'error':str(exc)})
    profile_path = roots.state_root / 'profile/career-profile.json'
    summary_review = cross_summary_templates([read_json(p) for p in sorted((roots.state_root / 'resume-builds').glob('*/content.json'))], read_json(profile_path) if profile_path.is_file() else {})
    return {'status': 'FAIL' if findings else summary_review['status'], 'artifacts_checked': len(checked), 'artifacts': checked, 'findings': findings, 'summary_batch_review': summary_review}


def packet_view(workspace: Path, packet: dict, artifact: dict) -> dict:
    from careeros.application_documents import packet_view as complete_packet
    return complete_packet(workspace,packet,artifact)


def prioritize(workspace: Path, assumptions: dict | None = None) -> dict:
    from careeros.prioritization import rank_opportunities
    roots = context(workspace)
    result = rank_opportunities([read_json(p) for p in (roots.state_root / 'opportunities').glob('*/opportunity.json')], records(roots.state_root / 'qualifications'), assumptions=assumptions)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / 'reports/opportunity-priorities.json', 'state'), result)
    _write(roots, 'reports/opportunity-priorities.md', '# Jobs to consider first\n\n' + 'Start with jobs where your experience supports the requirements. Check missing details before deciding. These comparisons are not hiring predictions.' + '\n\n' + _table(['Job','Employer','Your fit','Requirements supported','Your value estimate'], [[r['role_title'],r['employer_name'],display_label(r['qualification']),str(r['supported_fit_percent'])+'%',r['assumed_expected_value'] if r['assumed_expected_value'] is not None else 'Not estimated'] for r in result['rankings']]))
    return result
