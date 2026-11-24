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


def _report_pdf(title: str, paragraphs: list[str], path: Path, *, keep_subsections: bool = False):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('ReportBody', fontName='Helvetica', fontSize=10, leading=14, spaceAfter=8))
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
    paragraphs = [f"Dear {opp['employer_name']} hiring team,", f"I am applying for the {opp['role_title']} role. {content['summary']}"]
    # Preserve the exact approved evidence wording and its employment/project context.
    for section in [*content.get('employment', []), *content.get('projects', [])]:
        chosen = [b for b in section['bullets'] if b in evidence]
        if chosen:
            label = f"At {section['employer']}" if section.get('employer') else f"In my {section['name']} project"
            paragraphs.append(label + ': ' + ' '.join(b['text'] for b in chosen))
    paragraphs += ['I would welcome a conversation about how this experience could support your team.', 'Sincerely,\n' + content['candidate']['public_name']]
    key = sha256_value([opportunity_id, build_id])[:16]
    path = _write(roots, f'applications/{key}/cover-letter.md', '# Cover letter\n\n' + '\n\n'.join(paragraphs) + '\n')
    pdf = roots.assert_write_allowed(path.with_suffix('.pdf'), 'output')
    _report_pdf(content['candidate']['public_name'] + ' Cover Letter', paragraphs, pdf)
    result = {'schema': 'careeros.cover-letter-export.v1', 'opportunity_id': opportunity_id, 'build_id': build_id, 'status': 'REVIEW_REQUIRED', 'evidence_ids': sorted({e for b in evidence for e in b['evidence_ids']}), 'source_content_sha256': sha256_file(build.parent / 'content.json'), 'job_snapshot_hash': snapshot['content_hash'], 'artifacts': [{'path': str(p.relative_to(roots.output_root)), 'sha256': sha256_file(p)} for p in (path, pdf)], 'external_actions': 0}
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
    paragraphs = [f"{opp['role_title']} at {opp['employer_name']}", 'Stage: ' + stage]
    paragraphs += ['Employer need: ' + n['statement'] for n in pack['employer_need_summary']]
    for index, outline in enumerate(pack['answer_outlines'], 1):
        paragraphs.append(f'## Story {index} · ' + outline['format'].replace('_', ' ').title())
        for label, value in outline['fields'].items():
            if not value:
                continue
            if isinstance(value, list):
                value = '; '.join(str(v.get('value', v)) if isinstance(v, dict) else str(v) for v in value)
            paragraphs.append(label.title() + ': ' + str(value))
        paragraphs.append('Answer boundaries: ' + ' '.join(outline['prohibited_inferences']))
    for walkthrough in pack['technical_walkthroughs']:
        paragraphs.append('## Technical walkthrough')
        for label in ('OBJECTIVE', 'ENVIRONMENT', 'TOOLS', 'WHAT_I_DID', 'WHAT_I_OBSERVED', 'RESULT'):
            value = walkthrough[label]
            if value:
                paragraphs.append(label.replace('_', ' ').title() + ': ' + ('; '.join(map(str, value)) if isinstance(value, list) else str(value)))
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
    lines = ['# Career progress\n', 'Recorded applications: ' + str(bundle['cohort']['sample_count']), 'Sample maturity: ' + bundle['cohort']['maturity_state'], 'These observations describe this workspace. They do not establish causation.', '## Observed conversion']
    for label, rate in bundle['conversion_metrics']['rates'].items():
        value = 'No observations' if rate['rate'] is None else f"{rate['numerator']} / {rate['denominator']} ({rate['rate']:.0%})"
        lines.append(label.replace('_', ' ').title() + ': ' + value)
    lines.append('## Development gaps')
    lines += [g['capability'] + ': ' + str(g['job_count']) + ' observed jobs; ' + g['classification'].replace('_', ' ').lower() for g in bundle['gap_recurrence']['gaps']]
    if not bundle['gap_recurrence']['gaps']:
        lines.append('No gaps recorded in evaluated opportunities. This does not establish broad market readiness.')
    lines.append('## Career capital')
    lines.append('Signals describe the observed opportunity cohort. Build a larger, comparable outcome sample before changing strategy.')
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
    order = {r['opportunity_id']: i for i, r in enumerate(priorities['rankings'])}
    opportunities.sort(key=lambda o: order[o['opportunity_id']])
    applications = records(roots.state_root / 'applications')
    follows = records(roots.state_root / 'follow-ups')
    rows = [[o['role_title'], o['employer_name'], qualifications.get(o['opportunity_id'], {}).get('decision', 'NOT_EVALUATED'), next((a['current_state'] for a in applications if a['opportunity_id'] == o['opportunity_id']), 'NOT_PREPARED')] for o in opportunities]
    profile_md = '# Career profile\n\n' + name + '\n\n## Professional experience\n\n'
    employment = sorted(profile.get('employment', []), key=lambda r: (r.get('end_year') is None, int(r.get('start_year') or 0)), reverse=True)
    for role in employment:
        from careeros.resume_ats import format_public_date
        profile_md += f"### {role['actual_title']}\n\n{role['employer']} · {format_public_date(role)}\n\n"
        profile_md += '\n'.join('- ' + e['summary'] for e in profile.get('evidence', []) if role['record_id'] in e.get('employment_ids', [])) + '\n\n'
    for key in ('skills', 'credentials', 'education', 'projects', 'evidence'):
        profile_md += f'## {key.title()}\n\n' + '\n'.join('- ' + str(i.get('name') or i.get('title') or i.get('institution') or i.get('summary') or i.get('statement') or 'Details need review') for i in profile.get(key, [])) + '\n\n'
    _write(roots, 'profile/career-profile.md', profile_md)
    _report_pdf(name + ' Career Profile', [line for line in profile_md.split('\n\n') if line], roots.assert_write_allowed(roots.output_root / 'profile/career-profile.pdf', 'output'))
    for opp in opportunities:
        qual = qualifications.get(opp['opportunity_id'], {})
        paragraphs = [opp['role_title'] + ' at ' + opp['employer_name'], 'Qualification: ' + qual.get('decision', 'NOT_EVALUATED')]
        paragraphs += ['Requirement: ' + r['capability'] + ' (' + r.get('requirement_class', 'UNKNOWN') + ')' for r in opp['requirements']]
        evidence_index = {e['record_id']: e for e in profile.get('evidence', [])}
        for match in qual.get('evidence', []):
            sources = [evidence_index[r]['summary'] for r in match.get('record_ids', []) if r in evidence_index]
            if sources:
                paragraphs.append('Evidence for ' + match['capability'] + ': ' + ' '.join(sources))
        paragraphs += ['Gap: ' + g.get('capability', 'Unknown') + ' — ' + g.get('match', 'UNKNOWN') for g in qual.get('gaps', [])]
        key = sha256_value(opp['opportunity_id'])[:16]
        _write(roots, f'opportunities/{key}/opportunity-report.md', '# Opportunity report\n\n' + '\n\n'.join(paragraphs) + '\n')
        _report_pdf('Opportunity Report', paragraphs, roots.assert_write_allowed(roots.output_root / f'opportunities/{key}/opportunity-report.pdf', 'output'))
    tracker = '# Application tracker\n\n' + _table(['Role', 'Employer', 'Qualification', 'Application state'], rows)
    _write(roots, 'applications/application-tracker.md', tracker)
    follow_md = '# Follow ups\n\n' + _table(['Application', 'Due', 'Channel', 'Disposition'], [[f['application_id'], f['due_at'], f['channel'], f['disposition']] for f in follows])
    _write(roots, 'applications/follow-ups.md', follow_md)
    # Relative, browser-safe links to generated artifacts only; no third-party assets.
    links = []
    for p in sorted(roots.output_root.rglob('*')):
        if not p.is_file() or p.suffix not in {'.md', '.pdf', '.docx'} or p.name == 'HOME.md':
            continue
        relative = p.relative_to(roots.output_root)
        title = p.stem.replace('-', ' ').title()
        if relative.parts[0] == 'opportunities':
            match = next((o for o in opportunities if sha256_value(o['opportunity_id'])[:16] == relative.parts[1]), None)
            if match:
                title = match['role_title'] + ' · ' + match['employer_name']
        elif relative.parts[0] == 'packets':
            title = 'Application packet · ' + ('Review checklist' if p.stem == 'README' else 'Resume')
        links.append((str(relative), title + ' · ' + p.suffix[1:].upper()))
    md = f'# {name}\n\nCareer OS workspace\n\n## Overview\n\n{len(opportunities)} opportunities · {len(applications)} application packets · {len(follows)} follow ups\n\n## Opportunities\n\n' + _table(['Role', 'Employer', 'Qualification', 'Application state'], rows) + '\n## Documents\n\n' + '\n'.join(f'- [{title}]({path.replace(" ", "%20")})' for path, title in links) + '\n'
    _write(roots, 'HOME.md', md)
    def esc(v): return html.escape(str(v), quote=True)
    table = '<table><thead><tr>' + ''.join('<th>' + esc(h) + '</th>' for h in ['Role','Employer','Fit','Stage']) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + esc(c) + '</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table>'
    cards = ''.join(f'<article><strong>{v}</strong><span>{label}</span></article>' for v, label in [(len(opportunities),'Opportunities'),(len(applications),'Applications'),(len(follows),'Follow ups')])
    nav = ''.join(f'<a href="{esc(path.replace(" ", "%20"))}">{esc(title)}</a>' for path, title in links)
    nav = '<a href="learning/index.html">Learning and development · Roadmap</a>' + nav if (roots.output_root / 'learning/index.html').exists() else nav
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(name)} Career OS</title><style>
body{{margin:0;background:#f2f5f8;color:#15233a;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1120px;margin:56px auto;padding:0 28px}}header{{border-bottom:1px solid #c7d2df;padding-bottom:24px}}small{{text-transform:uppercase;letter-spacing:.15em;color:#1f4f78}}h1{{font-size:42px;margin:10px 0}}h2{{font-size:22px;margin-top:32px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:28px 0}}article{{background:white;padding:22px;border:1px solid #dce3eb;border-radius:12px}}strong{{display:block;font-size:32px}}span{{color:#526171}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{text-align:left;padding:14px;border-bottom:1px solid #dce3eb}}th{{font-size:12px;text-transform:uppercase;color:#526171}}nav{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}a{{color:#1f4f78;text-decoration:none;background:white;padding:12px;border:1px solid #dce3eb;border-radius:6px;overflow-wrap:anywhere}}a:hover,a:focus{{outline:2px solid #1f4f78}}@media(max-width:700px){{main{{margin:24px auto}}h1{{font-size:30px}}.cards,nav{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}@media print{{body{{background:white}}main{{margin:0}}}}</style><main><header><small>Career OS · private workspace</small><h1>{esc(name)}</h1><p>Evidence, opportunities and your next career move.</p></header><section class="cards" aria-label="Workspace totals">{cards}</section><h2>Opportunity pipeline</h2>{table}<h2>Your documents</h2><nav aria-label="Generated documents">{nav}</nav><p>Generated from your workspace. Review drafts before using them externally.</p></main></html>'''
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
    profile_path = roots.state_root / 'profile/career-profile.json'
    summary_review = cross_summary_templates([read_json(p) for p in sorted((roots.state_root / 'resume-builds').glob('*/content.json'))], read_json(profile_path) if profile_path.is_file() else {})
    return {'status': 'FAIL' if findings else summary_review['status'], 'artifacts_checked': len(checked), 'artifacts': checked, 'findings': findings, 'summary_batch_review': summary_review}


def packet_view(workspace: Path, packet: dict, artifact: dict) -> dict:
    import shutil
    roots = context(workspace)
    key = packet['packet_id'].split(':')[-1]
    folder = roots.assert_write_allowed(roots.output_root / 'packets' / key, 'output')
    folder.mkdir(parents=True, exist_ok=True)
    source = roots.output_root / artifact['path']
    target = roots.assert_write_allowed(folder / source.name, 'output')
    shutil.copyfile(source, target)
    manifest = {'packet_id': packet['packet_id'], 'opportunity_id': packet['opportunity_id'], 'review_state': packet['human_review_state'], 'resume': {'filename': target.name, 'sha256': sha256_file(target)}, 'jd_snapshot_hash': packet['jd_snapshot']['content_hash'], 'external_actions': 0}
    atomic_write_json(folder / 'manifest.json', manifest)
    _write(roots, f'packets/{key}/README.md', '# Application packet\n\nReview required. No application has been submitted.\n\n' + f'- [Resume]({target.name.replace(" ", "%20")})\n- [Artifact lineage](manifest.json)\n\n' + 'Check contact details, evidence, employer and role, job freshness, and application answers before applying.\n')
    return manifest


def prioritize(workspace: Path, assumptions: dict | None = None) -> dict:
    from careeros.prioritization import rank_opportunities
    roots = context(workspace)
    result = rank_opportunities([read_json(p) for p in (roots.state_root / 'opportunities').glob('*/opportunity.json')], records(roots.state_root / 'qualifications'), assumptions=assumptions)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / 'reports/opportunity-priorities.json', 'state'), result)
    _write(roots, 'reports/opportunity-priorities.md', '# Opportunity priorities\n\n' + result['boundary'] + '\n\n' + _table(['Role','Employer','Qualification','Supported fit','Assumed value'], [[r['role_title'],r['employer_name'],r['qualification'],str(r['supported_fit_percent'])+'%',r['assumed_expected_value'] if r['assumed_expected_value'] is not None else 'Not estimated'] for r in result['rankings']]))
    return result
