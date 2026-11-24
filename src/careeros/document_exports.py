"""Editable exports from the same semantic content used by the PDF renderer."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def resume_paragraphs(content: dict[str, Any]) -> list[tuple[str, str]]:
    from careeros.resume_ats import format_public_date
    rows: list[tuple[str, str]] = []
    sections = {}
    sections['SUMMARY'] = [('section', 'SUMMARY'), ('body', content['summary'])]
    sections['SKILLS'] = [('section', 'CORE SKILLS')] + [('body', g['group'] + ': ' + ' | '.join(s['name'] for s in g['skills'])) for g in content.get('skill_groups', [])] if content.get('skill_groups') else []
    sections['EXPERIENCE'] = [('section', 'PROFESSIONAL EXPERIENCE')] if content.get('employment') else []
    for role in content.get('employment', []):
        sections['EXPERIENCE'] += [('role', role['actual_title']), ('secondary', ' | '.join(filter(None, [role['employer'], role.get('location'), format_public_date(role)])))]
        sections['EXPERIENCE'] += [('bullet', b['text']) for b in role['bullets']]
    sections['PROJECTS'] = [('section', 'FEATURED PROJECTS')] if content.get('projects') else []
    for item in content.get('projects', []):
        sections['PROJECTS'] += [('role', item['name'])]
        if item.get('contribution'):
            sections['PROJECTS'].append(('secondary', item['contribution']))
        sections['PROJECTS'] += [('bullet', b['text']) for b in item['bullets']]
    sections['EDUCATION'] = [('section', 'EDUCATION')] if content.get('display_education') else []
    for item in content.get('display_education', []):
        program = item.get('program') or 'Education'
        if item.get('field_of_study'):
            program += ' in ' + item['field_of_study']
        if item.get('display_status'):
            program += ' - ' + item['display_status']
        sections['EDUCATION'] += [('role', item['institution']), ('secondary', program)]
    sections['CREDENTIALS'] = [('section', 'CERTIFICATIONS AND PROFESSIONAL DEVELOPMENT')] if content.get('display_credentials') else []
    sections['CREDENTIALS'] += [('body', c['title'] + ' - ' + c['issuer']) for c in content.get('display_credentials', [])]
    for section in content.get('section_order') or ['SUMMARY', 'SKILLS', 'EXPERIENCE', 'PROJECTS', 'EDUCATION', 'CREDENTIALS']:
        rows.extend(sections.get(section, []))
    return rows


def render_docx(content: dict[str, Any], target: Path) -> dict[str, Any]:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor
    from careeros.core.io import sha256_file
    from careeros.resume_ats import build_resume_header, contact_values
    from careeros.document_quality import normalize_text
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.left_margin = section.right_margin = Inches(.62)
    section.top_margin = section.bottom_margin = Inches(.46)
    normal = doc.styles['Normal']
    normal.font.name, normal.font.size = 'Arial', Pt(9)
    normal.paragraph_format.line_spacing = Pt(11.4)
    normal.paragraph_format.space_after = Pt(2.5)
    header = content.get('resume_header') or build_resume_header(content['candidate'], content['target_role'])
    sizes = {'name': 23, 'headline': 11.2, 'contact': 8.3, 'section': 10.2, 'role': 9.6, 'secondary': 8.35, 'body': 9, 'bullet': 8.65}
    layout = content.get('header_layout_decision', {})
    header_rows = [('name', header['candidate_name'])]
    header_rows += [('headline', row) for row in layout.get('headline_rows', [header['positioning_headline']])]
    contacts = layout.get('primary_contact_rows', [contact_values(header)])
    header_rows += [('contact', ' | '.join(row)) for row in contacts]
    header_rows += [('contact', ' | '.join(row)) for row in layout.get('professional_link_rows', [])]
    expected = []
    for kind, text in [*header_rows, *resume_paragraphs(content)]:
        p = doc.add_paragraph()
        p.paragraph_format.widow_control = True
        p.paragraph_format.keep_with_next = kind in {'section', 'role', 'secondary', 'name', 'headline', 'contact'}
        if kind in {'name', 'headline', 'contact'}:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if kind == 'section':
            p.paragraph_format.space_before = Pt(6)
        if kind == 'bullet':
            p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Pt(11), Pt(-8)
        run = p.add_run(('- ' if kind == 'bullet' else '') + text)
        run.font.size = Pt(sizes[kind])
        run.bold = kind in {'name', 'headline', 'section', 'role'}
        run.font.color.rgb = RGBColor.from_string('1F4F78' if kind in {'section', 'headline'} else '15233A')
        expected.append(text)
    doc.core_properties.title = header['candidate_name'] + ' Resume'
    doc.core_properties.author = header['candidate_name']
    doc.core_properties.subject = 'Resume'
    doc.core_properties.last_modified_by = ''
    doc.core_properties.comments = ''
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(target)
    actual = '\n'.join(p.text for p in Document(target).paragraphs)
    missing = [t for t in expected if normalize_text(t) not in normalize_text(actual)]
    if missing:
        raise ValueError('DOCX semantic round trip lost content')
    return {'format': 'DOCX', 'path': target.name, 'sha256': sha256_file(target), 'semantic_round_trip': 'PASS', 'layout_review': 'RENDER_REQUIRED'}
