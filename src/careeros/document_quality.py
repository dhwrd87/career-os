"""Object-level PDF preflight and explicit geometry regression signatures."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any


def normalize_text(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip()


def inspect_pdf(path: Path) -> dict[str, Any]:
    import pdfplumber
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    reader = PdfReader(path)
    findings, fonts, geometry = [], [], []
    if reader.is_encrypted:
        return {'status': 'FAIL', 'findings': ['ENCRYPTED'], 'fonts': [], 'geometry': []}
    if reader.get_fields():
        findings.append('INTERACTIVE_FORM')
    root = reader.trailer['/Root']
    if root.get('/OpenAction') or root.get('/AA'):
        findings.append('ACTIVE_DOCUMENT_ACTION')
    names = root.get('/Names')
    if names and any(key in names.get_object() for key in ('/JavaScript', '/EmbeddedFiles')):
        findings.append('ACTIVE_OR_EMBEDDED_PAYLOAD')
    for i, page in enumerate(reader.pages, 1):
        resources = page.get('/Resources', {}).get_object()
        for ref in resources.get('/Font', {}).values():
            font = ref.get_object()
            name = str(font.get('/BaseFont', ''))
            descriptor = font.get('/FontDescriptor')
            descriptor = descriptor.get_object() if descriptor else {}
            embedded = any(k in descriptor for k in ('/FontFile', '/FontFile2', '/FontFile3'))
            core = name.lstrip('/') in {'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique', 'Helvetica-BoldOblique'}
            fonts.append({'name': name, 'embedded': embedded, 'unicode_map': '/ToUnicode' in font, 'core_font': core})
            if not embedded and not core:
                findings.append(f'UNEMBEDDED_FONT_PAGE_{i}')
            if not core and '/ToUnicode' not in font:
                findings.append(f'MISSING_UNICODE_MAP_PAGE_{i}')
        for ref in resources.get('/ExtGState', {}).values():
            state = ref.get_object()
            if any(float(state.get(key, 1)) < 1 for key in ('/ca', '/CA')):
                findings.append(f'TRANSPARENT_CONTENT_PAGE_{i}')
        for ref in resources.get('/XObject', {}).values():
            if ref.get_object().get('/Subtype') == '/Image':
                findings.append(f'RASTER_CONTENT_PAGE_{i}')
        stream = ContentStream(page.get_contents(), reader)
        for operands, operator in stream.operations:
            if operator == b'Tr' and operands and operands[0] in (3, 7):
                findings.append(f'HIDDEN_TEXT_PAGE_{i}')
        for annotation in page.get('/Annots', []):
            action = annotation.get_object().get('/A')
            action = action.get_object() if action else None
            if action and action.get('/S') not in ('/URI', '/GoTo'):
                findings.append(f'UNSAFE_ANNOTATION_PAGE_{i}')
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            if any(char.get('non_stroking_color') in ((1, 1, 1), 1) for char in page.chars if char.get('text', '').strip()):
                findings.append(f'WHITE_TEXT_PAGE_{i}')
            words = page.extract_words()
            if not words:
                findings.append(f'EMPTY_PAGE_{i}')
            if any(w['x0'] < 25 or w['x1'] > page.width - 25 or w['top'] < 20 or w['bottom'] > page.height - 20 for w in words):
                findings.append(f'UNSAFE_BOUNDS_PAGE_{i}')
            geometry.append({'page': i, 'width': page.width, 'height': page.height, 'words': [{'text': w['text'], 'x0': round(w['x0'], 1), 'top': round(w['top'], 1), 'x1': round(w['x1'], 1), 'bottom': round(w['bottom'], 1)} for w in words]})
    return {'status': 'FAIL' if findings else 'PASS', 'findings': findings, 'fonts': fonts, 'geometry': geometry,
            'accessibility': {'selectable_text': all(p['words'] for p in geometry), 'tagged_pdf': bool(root.get('/StructTreeRoot')), 'pdf_ua_certified': False},
            'font_policy': 'Standard PDF core Helvetica fonts allowed; embedded fonts required for other families.'}


def compare_geometry(actual: dict, golden: dict, tolerance: float = .8) -> dict:
    findings = []
    if len(actual['geometry']) != len(golden['geometry']):
        findings.append('PAGE_COUNT_CHANGED')
    for a, b in zip(actual['geometry'], golden['geometry']):
        if len(a['words']) != len(b['words']):
            findings.append('WORD_COUNT_CHANGED')
        for x, y in zip(a['words'], b['words']):
            if x['text'] != y['text'] or any(abs(x[k] - y[k]) > tolerance for k in ('x0', 'top', 'x1', 'bottom')):
                findings.append(f"GEOMETRY_CHANGED_PAGE_{a['page']}")
                break
    return {'status': 'FAIL' if findings else 'PASS', 'findings': findings, 'tolerance_pt': tolerance}
