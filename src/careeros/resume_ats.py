"""ATS-safe header, recruiter-summary, and PDF round-trip contracts.

This module is candidate-neutral. It derives public presentation from typed
Career OS records and validates rendered PDFs without changing canonical data.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth

from careeros.editorial import sanitize_url


PUBLIC_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}
APPROVED_SECTION_NAMES = {
    "SUMMARY": "SUMMARY", "SKILLS": "CORE SKILLS",
    "EXPERIENCE": "PROFESSIONAL EXPERIENCE", "PROJECTS": "PROJECTS",
    "CREDENTIALS": "CERTIFICATIONS", "EDUCATION": "EDUCATION", "LANGUAGES": "LANGUAGES",
}
FORBIDDEN_FILENAME_TERMS = {
    "base resume", "targeted resume", "generated resume", "base", "targeted", "generated", "internal", "draft", "career os",
    "review required", "master recruiter", "canonical",
}
SUMMARY_FILLER = {
    "results-driven", "hard-working", "dynamic professional", "entry-ready candidate",
    "professional foundation", "practical preparation", "disciplined operations",
}
TEMPLATE_SUMMARY_PATTERNS = {
    "candidate with evidence in", "supported by professional work",
    "combines established workplace", "professional work:", "technical projects:",
}
MONTHS = {
    "january": "Jan", "february": "Feb", "march": "Mar", "april": "Apr",
    "may": "May", "june": "Jun", "july": "Jul", "august": "Aug",
    "september": "Sep", "october": "Oct", "november": "Nov", "december": "Dec",
}
PREMIUM_CENTERED_MASTHEAD = "PREMIUM_CENTERED_MASTHEAD"
ATS_MINIMAL_FALLBACK = "ATS_MINIMAL_FALLBACK"
HEADER_LAYOUT_MODES = {"STANDARD_CENTERED", "COMPACT_CENTERED", "CONTROLLED_HEADLINE_WRAP"}
HEADER_SEMANTIC_ORDER = ["NAME", "HEADLINE", "LOCATION", "PHONE", "EMAIL", "LINKEDIN", "PORTFOLIO", "GITHUB"]


def _plain(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("value", "text", "label", "name"):
            if value.get(key) not in {None, ""}:
                return _plain(value[key])
        return ""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_filename_part(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9 ._()&+-]+", "", _plain(value)).strip(" .")
    for term in sorted(FORBIDDEN_FILENAME_TERMS, key=len, reverse=True):
        value = re.sub(rf"\b{re.escape(term)}\b", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip(" -._") or "Resume"


def recruiter_safe_filename(candidate_name: str, target_role: str) -> str:
    name = _safe_filename_part(candidate_name)
    role = _safe_filename_part(target_role)
    role = re.sub(r"^(?:resume\s*[-–—:]\s*)+", "", role, flags=re.IGNORECASE).strip() or "Resume"
    suffix = "" if role.casefold().endswith("resume") else " Resume"
    return f"{name} - {role}{suffix}.pdf"


def _url_fields(urls: list[str]) -> tuple[str | None, str | None, str | None]:
    linkedin = next((sanitize_url(url) for url in urls if "linkedin.com" in url.casefold()), None)
    github = next((sanitize_url(url) for url in urls if "github.com" in url.casefold() or "github.io" in url.casefold()), None)
    portfolio = next((sanitize_url(url) for url in urls if sanitize_url(url) not in {linkedin, github}), None)
    if portfolio is None and github and ".github.io" in github:
        portfolio, github = github, None
    return linkedin, portfolio, github


def build_resume_header(candidate: dict[str, Any], positioning_headline: str) -> dict[str, Any]:
    contact = candidate.get("contact", {})
    urls = [str(value) for value in contact.get("urls", []) if _plain(value)]
    linkedin, portfolio, github = _url_fields(urls)
    location = candidate.get("public_location") or candidate.get("location")
    if isinstance(location, dict):
        location = ", ".join(_plain(location.get(key)) for key in ("city", "region", "country") if _plain(location.get(key)))
    return {
        "schema": "careeros.resume-header.v1", "schema_version": "1.0.0",
        "candidate_name": _plain(candidate.get("public_name")),
        "public_location": _plain(location) or None,
        "phone": _plain(contact.get("phone")) or None,
        "email": _plain(contact.get("email")) or None,
        "linkedin": linkedin, "portfolio": portfolio, "optional_github": github,
        "positioning_headline": _plain(positioning_headline),
        "public_identity_policy": "PUBLIC_NAME_ONLY",
        "contact_visibility": "PUBLIC_FIELDS_ONLY",
        "link_display_policy": "PLAIN_TEXT_DISPLAY_WITH_CLICKABLE_ANNOTATION",
        "semantic_order": HEADER_SEMANTIC_ORDER,
        "layout_policy": "PREMIUM_CENTERED_MASTHEAD_WITH_ATS_MINIMAL_FALLBACK",
    }


def _evidence_phrase(evidence: dict[str, Any]) -> str:
    tools = [_plain(value) for value in evidence.get("tools_methods", []) if _plain(value)]
    actions = [_plain(value) for value in evidence.get("actions", []) if _plain(value)]
    deliverables = [_plain(value) for value in evidence.get("deliverables", []) if _plain(value)]
    if tools and actions:
        return f"{actions[0][0].lower() + actions[0][1:]} using {tools[0]}"
    if actions and deliverables:
        return f"{actions[0][0].lower() + actions[0][1:]} to produce {deliverables[0]}"
    if actions:
        return actions[0][0].lower() + actions[0][1:]
    return _plain(evidence.get("summary"))


def _summary_clause(text: str, evidence_ids: list[str] | None = None, *, config_source: str | None = None, job_relevance: str = "LANE") -> dict[str, Any]:
    return {
        "summary_clause": _plain(text), "source_evidence_ids": sorted(set(evidence_ids or [])),
        "approved_config_source": config_source,
        "verification": "SOURCE_BOUND" if evidence_ids else "APPROVED_CONFIG",
        "public_use": True, "job_relevance": job_relevance,
    }


def build_recruiter_summary(
    profile: dict[str, Any], storyline: dict[str, Any], role_family: dict[str, Any],
    *, opportunity: dict[str, Any] | None = None, selected_evidence_ids: set[str] | None = None,
    employer_need_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # V2 is the public production default.  The older assembly remains below
    # temporarily as readable migration context; it is intentionally bypassed.
    from careeros.recruiter_conversion import build_recruiter_summary_v2
    return build_recruiter_summary_v2(
        profile, storyline, role_family, opportunity=opportunity,
        selected_evidence_ids=selected_evidence_ids,
        employer_need_trace=employer_need_trace,
    )

    target = _plain((opportunity or {}).get("role_title") or role_family.get("display_name") or role_family.get("label") or "Professional")
    selected = selected_evidence_ids or {
        item.get("evidence_id") for item in storyline.get("evidence_rankings", [])
        if item.get("classification") in {"ANCHOR", "SUPPORTING", "CONTEXT", "TRANSFERABLE_PROFESSIONAL", "FOUNDATIONAL"}
    }
    evidence = [
        item for item in profile.get("evidence", [])
        if item.get("visibility") in PUBLIC_VISIBILITY and (not selected or item.get("record_id") in selected)
    ]
    ranking = {item.get("evidence_id"): index for index, item in enumerate(storyline.get("evidence_rankings", []))}
    evidence.sort(key=lambda item: ranking.get(item.get("record_id"), 10_000))
    professional = [item for item in evidence if item.get("employment_ids")]
    technical = [item for item in evidence if item.get("project_ids") or item.get("tools_methods")]
    top = [item for item in technical if _evidence_phrase(item)][:3]
    supported_skills = list(dict.fromkeys(
        _plain(skill.get("name")) for skill in profile.get("skills", [])
        if skill.get("visibility") in PUBLIC_VISIBILITY and skill.get("evidence_ids")
        and (not selected or set(skill.get("evidence_ids", [])) & selected)
    ))
    core_capabilities = [_plain(value) for value in role_family.get("core_capabilities", [])]
    role_skills = [value for value in core_capabilities if value.casefold() in {skill.casefold() for skill in supported_skills}]
    supported_skills = list(dict.fromkeys([*role_skills, *supported_skills]))[:3]
    skill_ids = [
        evidence_id for skill in profile.get("skills", []) for evidence_id in skill.get("evidence_ids", [])
        if evidence_id in selected
    ][:6]
    skill_phrase = ", ".join(supported_skills) or "role-relevant technical capabilities"
    professional_item = professional[0] if professional else None
    professional_phrase = _evidence_phrase(professional_item) if professional_item else ""
    material_needs = [
        item for item in (employer_need_trace or {}).get("needs", [])
        if item.get("importance") in {"CRITICAL", "HIGH"}
        and set(item.get("candidate_evidence_ids", [])) & selected
    ]
    material_needs.sort(key=lambda item: (
        0 if item.get("top_third_signal") == "TOP_THIRD" else 1,
        0 if item.get("importance") == "CRITICAL" else 1,
        item.get("need_id", ""),
    ))
    need = material_needs[0] if material_needs else None
    need_evidence = [
        item for item in evidence
        if need and item.get("record_id") in set(need.get("candidate_evidence_ids", []))
        and _evidence_phrase(item)
    ]
    if opportunity and need and need_evidence:
        need_statement = _plain(need["need_statement"]).rstrip(".")
        if len(need_statement.split()) > 12:
            need_statement = " ".join(need_statement.split()[:12]).rstrip(",;:")
        intro = (
            f"Relevant work for {target} includes {_evidence_phrase(need_evidence[0])}, "
            f"directly addressing the need for {need_statement[0].lower() + need_statement[1:]}."
        )
        intro_evidence_ids = [need_evidence[0]["record_id"]]
    else:
        intro = f"Brings hands-on {skill_phrase} project work to {target} roles."
        intro_evidence_ids = list(skill_ids)
    clauses = [_summary_clause(
        intro, intro_evidence_ids, config_source="RoleFamilyV1",
        job_relevance="JOB" if opportunity else "LANE",
    )]
    if professional_item and professional_phrase:
        clauses.append(_summary_clause(
            f"Professional experience includes work where they {professional_phrase}.",
            [professional_item["record_id"]],
            job_relevance="JOB" if opportunity else "LANE",
        ))
    if top:
        phrases = [_evidence_phrase(item) for item in top]
        if len(phrases) == 1:
            project_text = phrases[0]
        elif len(phrases) == 2:
            project_text = f"{phrases[0]} and {phrases[1]}"
        else:
            project_text = f"{phrases[0]}, {phrases[1]}, and {phrases[2]}"
        clauses.append(_summary_clause(
            f"Across recent projects, they {project_text}.",
            [item["record_id"] for item in top], job_relevance="JOB" if opportunity else "LANE",
        ))
    preferences = profile.get("preferences", {})
    schedules = preferences.get("schedule_preferences", [])
    if schedules and opportunity:
        shift = _plain((opportunity or {}).get("shift_schedule"))
        if shift and any(_plain(value).casefold() in shift.casefold() for value in schedules):
            clauses.append(_summary_clause(f"Available for {shift}.", config_source="CareerProfileV1.preferences.schedule_preferences", job_relevance="JOB"))
    text = " ".join(item["summary_clause"] for item in clauses if item["summary_clause"])
    while clauses and len(text.split()) > 80:
        clauses.pop()
        text = " ".join(item["summary_clause"] for item in clauses)
    if len(text.split()) < 40 and technical:
        item = technical[min(3, len(technical) - 1)]
        addition = _summary_clause(
            f"They also {_evidence_phrase(item)}.", [item["record_id"]],
            job_relevance="JOB" if opportunity else "LANE",
        )
        if addition["summary_clause"] not in text:
            clauses.append(addition)
            text = " ".join(item["summary_clause"] for item in clauses)
    return {
        "schema": "careeros.recruiter-summary.v1", "schema_version": "1.0.0",
        "candidate_identity": profile.get("profile_id"),
        "target_role_family": role_family.get("role_family_id") or role_family.get("family_id"),
        "text": text, "word_count": len(text.split()),
        "summary_type": "TARGETED" if opportunity else "LANE", "clauses": clauses,
        "career_transition_boundary": bool(professional and technical),
        "job_specific_emphasis": target if opportunity else None,
    }


def validate_recruiter_summary(summary: dict[str, Any]) -> dict[str, Any]:
    clauses = summary.get("clauses", [])
    unsupported = [item.get("summary_clause") for item in clauses if not item.get("source_evidence_ids") and not item.get("approved_config_source")]
    text = _plain(summary.get("text"))
    filler = sorted(term for term in SUMMARY_FILLER if term in text.casefold())
    template_patterns = sorted(term for term in TEMPLATE_SUMMARY_PATTERNS if term in text.casefold())
    word_count = len(text.split())
    return {
        # 40-80 words is the editorial target. Truthful thin profiles may use
        # a shorter 25-39 word summary instead of synthetic padding.
        "status": "PASS" if 25 <= word_count <= 80 and not unsupported and not filler and not template_patterns else "FAIL",
        "word_count": word_count, "unsupported_clauses": unsupported,
        "filler_phrases": filler, "template_summary_patterns": template_patterns,
        "trace_complete": not unsupported,
    }


def format_public_date(record: dict[str, Any]) -> str:
    precision = _plain(record.get("date_precision")).upper()
    start_year, end_year = record.get("start_year"), record.get("end_year")
    start = str(start_year or "")
    if precision == "MONTH" and record.get("start_month"):
        start = f"{MONTHS.get(_plain(record['start_month']).casefold(), _plain(record['start_month'])[:3].title())} {start_year}"
    if end_year in {None, "PRESENT", "Present"}:
        end = "Present"
    else:
        end = str(end_year)
        if precision == "MONTH" and record.get("end_month"):
            end = f"{MONTHS.get(_plain(record['end_month']).casefold(), _plain(record['end_month'])[:3].title())} {end_year}"
    return f"{start} - {end}".strip(" -")


def contact_values(header: dict[str, Any]) -> list[str]:
    return [str(value) for value in [
        header.get("public_location"), header.get("phone"), header.get("email"),
        header.get("linkedin"), header.get("portfolio"), header.get("optional_github"),
    ] if value]


def primary_contact_values(header: dict[str, Any]) -> list[str]:
    return [str(value) for value in [header.get("public_location"), header.get("phone"), header.get("email")] if value]


def professional_link_values(header: dict[str, Any]) -> list[str]:
    return [str(value) for value in [header.get("linkedin"), header.get("portfolio"), header.get("optional_github")] if value]


def _row_width(values: list[str], font_name: str, font_size: float, separator: str = " | ") -> float:
    return stringWidth(separator.join(values), font_name, font_size)


def _split_headline(headline: str) -> list[str]:
    parts = [part.strip() for part in headline.split("|") if part.strip()]
    if len(parts) < 2:
        words = headline.split()
        pivot = max(1, len(words) // 2)
        return [" ".join(words[:pivot]), " ".join(words[pivot:])]
    midpoint = max(1, len(parts) // 2)
    return [" | ".join(parts[:midpoint]), " | ".join(parts[midpoint:])]


def header_layout_decision(header: dict[str, Any], safe_width: float = 522.72) -> dict[str, Any]:
    """Resolve a deterministic centered masthead without changing field semantics."""
    name = str(header["candidate_name"])
    headline = str(header["positioning_headline"])
    primary = primary_contact_values(header)
    links = professional_link_values(header)
    name_size, headline_size, contact_size, links_size = 23.0, 11.2, 8.3, 8.1
    mode = "STANDARD_CENTERED"
    if stringWidth(name, "Helvetica-Bold", name_size) > safe_width:
        name_size = 20.0
        mode = "COMPACT_CENTERED"
    if stringWidth(headline, "Helvetica-Bold", headline_size) > safe_width:
        headline_size = 10.5
        mode = "COMPACT_CENTERED"
    headline_rows = [headline]
    if stringWidth(headline, "Helvetica-Bold", headline_size) > safe_width:
        headline_rows = _split_headline(headline)
        mode = "CONTROLLED_HEADLINE_WRAP"
    primary_rows = [primary] if primary else []
    if primary and _row_width(primary, "Helvetica", contact_size) > safe_width:
        contact_size = 8.0
        mode = "COMPACT_CENTERED" if mode == "STANDARD_CENTERED" else mode
        if _row_width(primary, "Helvetica", contact_size) > safe_width:
            primary_rows = [primary[:2], primary[2:]] if len(primary) > 2 else [[item] for item in primary]
    link_rows = [links] if links else []
    if links and _row_width(links, "Helvetica", links_size) > safe_width:
        links_size = 8.0
        mode = "COMPACT_CENTERED" if mode == "STANDARD_CENTERED" else mode
        if _row_width(links, "Helvetica", links_size) > safe_width:
            link_rows = [links[:2], links[2:]] if len(links) > 2 else [[item] for item in links]
    widths = {
        "candidate_name": round(stringWidth(name, "Helvetica-Bold", name_size), 3),
        "headline_rows": [round(stringWidth(row, "Helvetica-Bold", headline_size), 3) for row in headline_rows],
        "primary_contact_rows": [round(_row_width(row, "Helvetica", contact_size), 3) for row in primary_rows],
        "professional_link_rows": [round(_row_width(row, "Helvetica", links_size), 3) for row in link_rows],
    }
    clipping_risk = any(width > safe_width + 0.5 for width in [widths["candidate_name"], *widths["headline_rows"], *widths["primary_contact_rows"], *widths["professional_link_rows"]])
    return {
        "presentation": PREMIUM_CENTERED_MASTHEAD, "fallback": ATS_MINIMAL_FALLBACK,
        "layout_mode": mode, "safe_width": round(safe_width, 3), "separator": " | ",
        "font_sizes": {"name": name_size, "headline": headline_size, "contact": contact_size, "links": links_size},
        "headline_rows": headline_rows, "primary_contact_rows": primary_rows,
        "professional_link_rows": link_rows, "measured_widths": widths, "clipping_risk": clipping_risk,
    }


def evaluate_masthead_geometry(pdf_path: Path, header: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Measure final PDF coordinates; intended centering alone is not acceptance evidence."""
    expected_rows = [header["candidate_name"], *decision["headline_rows"],
                     *(" | ".join(row) for row in decision["primary_contact_rows"]),
                     *(" | ".join(row) for row in decision["professional_link_rows"])]
    with pdfplumber.open(pdf_path) as document:
        page = document.pages[0]
        words = page.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False)
        grouped: list[dict[str, Any]] = []
        for word in words:
            match = next((row for row in grouped if abs(row["top"] - float(word["top"])) <= 1.5), None)
            if match is None:
                match = {"top": float(word["top"]), "bottom": float(word["bottom"]), "words": []}
                grouped.append(match)
            match["words"].append(word)
            match["bottom"] = max(match["bottom"], float(word["bottom"]))
        lines = []
        for row in sorted(grouped, key=lambda item: item["top"]):
            ordered = sorted(row["words"], key=lambda item: float(item["x0"]))
            lines.append({"text": " ".join(str(item["text"]) for item in ordered),
                          "x0": min(float(item["x0"]) for item in ordered),
                          "x1": max(float(item["x1"]) for item in ordered),
                          "top": row["top"], "bottom": row["bottom"]})
        matched = []
        cursor = 0
        for expected in expected_rows:
            normalized_expected = re.sub(r"\s+", " ", expected).strip()
            found = next((line for line in lines[cursor:] if normalized_expected in re.sub(r"\s+", " ", line["text"]).strip()), None)
            if found is None:
                matched.append(None)
                continue
            matched.append(found)
            cursor = lines.index(found) + 1
        offsets = [None if row is None else round(((row["x0"] + row["x1"]) / 2.0) - (float(page.width) / 2.0), 3) for row in matched]
        horizontal_lines = [line for line in page.lines if abs(float(line.get("y1", 0)) - float(line.get("y0", 0))) <= 0.5 and float(line.get("x1", 0)) - float(line.get("x0", 0)) >= decision["safe_width"] * 0.9]
        divider_top = min((float(page.height) - float(line["y0"]) for line in horizontal_lines), default=None)
        summary_top = min(
            (
                float(line["top"])
                for line in lines
                if str(line["text"]).strip() == "SUMMARY"
                and (divider_top is None or float(line["top"]) > divider_top)
            ),
            default=None,
        )
    name_row = matched[0] if matched else None
    headline_count = len(decision["headline_rows"])
    primary_count = len(decision["primary_contact_rows"])
    headline_rows = [row for row in matched[1:1 + headline_count] if row]
    contact_rows = [row for row in matched[1 + headline_count:1 + headline_count + primary_count] if row]
    link_rows = [row for row in matched[1 + headline_count + primary_count:] if row]
    def gap(upper: list[dict[str, Any]], lower: list[dict[str, Any]]) -> float | None:
        return round(lower[0]["top"] - upper[-1]["bottom"], 3) if upper and lower else None
    last_rows = link_rows or contact_rows or headline_rows
    tolerance = 2.5
    present_offsets = [abs(value) for value in offsets if value is not None]
    masthead_height = round((divider_top - name_row["top"]), 3) if divider_top is not None and name_row else None
    professional_links_bottom = link_rows[-1]["bottom"] if link_rows else None
    links_to_divider_gap = (
        round(divider_top - professional_links_bottom, 3)
        if divider_top is not None and professional_links_bottom is not None else None
    )
    divider_to_summary_gap = (
        round(summary_top - divider_top, 3)
        if summary_top is not None and divider_top is not None else None
    )
    divider_balance_ratio = (
        round(links_to_divider_gap / divider_to_summary_gap, 3)
        if links_to_divider_gap is not None and divider_to_summary_gap not in {None, 0} else None
    )
    result = {
        "schema": "careeros.masthead-geometry.v1", "schema_version": "1.0.0", "layout_mode": decision["layout_mode"],
        "name_center_offset": offsets[0] if offsets else None,
        "headline_center_offset": max([abs(value) for value in offsets[1:1 + headline_count] if value is not None], default=None),
        "primary_contact_center_offset": max([abs(value) for value in offsets[1 + headline_count:1 + headline_count + primary_count] if value is not None], default=None),
        "links_center_offset": max([abs(value) for value in offsets[1 + headline_count + primary_count:] if value is not None], default=None),
        "headline_gap": gap([name_row] if name_row else [], headline_rows), "contact_gap": gap(headline_rows, contact_rows),
        "link_gap": gap(contact_rows, link_rows),
        "divider_gap": round(divider_top - last_rows[-1]["bottom"], 3) if divider_top is not None and last_rows else None,
        "professional_links_bottom_y": round(professional_links_bottom, 3) if professional_links_bottom is not None else None,
        "divider_y": round(divider_top, 3) if divider_top is not None else None,
        "summary_top_y": round(summary_top, 3) if summary_top is not None else None,
        "links_to_divider_gap": links_to_divider_gap,
        "divider_to_summary_gap": divider_to_summary_gap,
        "divider_balance_ratio": divider_balance_ratio,
        "masthead_total_height": masthead_height, "safe_width": decision["safe_width"], "center_tolerance": tolerance,
        "line_counts": {"headline": headline_count, "primary_contact": primary_count, "professional_links": len(decision["professional_link_rows"])},
        "missing_rows": [expected_rows[index] for index, row in enumerate(matched) if row is None],
        "clipping_risk": bool(decision["clipping_risk"]),
    }
    result["status"] = "PASS" if not result["missing_rows"] and not result["clipping_risk"] and present_offsets and max(present_offsets) <= tolerance and (masthead_height or 999) <= 115 else "FAIL"
    return result


def extract_pdf_texts(pdf_path: Path) -> dict[str, Any]:
    reader = PdfReader(str(pdf_path))
    pypdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    with pdfplumber.open(pdf_path) as document:
        plumber_text = "\n".join(page.extract_text() or "" for page in document.pages)
    secondary, backend = "", None
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        result = subprocess.run([pdftotext, "-layout", str(pdf_path), "-"], check=True, capture_output=True, text=True, timeout=30)
        secondary, backend = result.stdout, "poppler-pdftotext"
    normalized = lambda value: re.sub(r"\s+", " ", value).strip()
    return {
        "pypdf": pypdf_text, "pdfplumber": plumber_text, "secondary": secondary,
        "secondary_backend": backend,
        "primary_agreement": normalized(pypdf_text) == normalized(plumber_text),
        "secondary_agreement": True if not secondary else normalized(pypdf_text) == normalized(secondary),
    }


def _expected_sections(content: dict[str, Any]) -> list[str]:
    expected = ["SUMMARY"]
    mapping = {
        "SKILLS": content.get("skills") or content.get("skill_groups"),
        "EXPERIENCE": content.get("employment"), "PROJECTS": content.get("projects"),
        "CREDENTIALS": content.get("display_credentials"), "EDUCATION": content.get("display_education"),
    }
    for key in content.get("section_order") or ["SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CREDENTIALS"]:
        if key != "SUMMARY" and mapping.get(key):
            expected.append(APPROVED_SECTION_NAMES[key])
    return expected


def ats_resume_round_trip(content: dict[str, Any], pdf_path: Path) -> dict[str, Any]:
    header, summary = content["resume_header"], content["recruiter_summary"]
    extracted = extract_pdf_texts(pdf_path)
    text = extracted["pypdf"]
    normalized_text = re.sub(r"\s+", " ", text)
    expected_sections = _expected_sections(content)
    section_positions = [text.find(value) for value in expected_sections]
    header_values = [header["candidate_name"], header["positioning_headline"], *contact_values(header)]
    missing_header = [value for value in header_values if value and value not in normalized_text]
    employment_material = [
        value for item in content.get("employment", [])
        for value in [item.get("actual_title"), item.get("employer"), format_public_date(item)] if value
    ]
    missing_employment = [value for value in employment_material if value not in normalized_text]
    projects = [item.get("name") for item in content.get("projects", []) if item.get("name")]
    education = [item.get("institution") for item in content.get("display_education", []) if item.get("institution")]
    credentials = [item.get("title") for item in content.get("display_credentials", []) if item.get("title")]
    skills = [item.get("name") for item in content.get("skills", []) if item.get("name")]
    first, *last = header["candidate_name"].split()
    autofill = {
        "first_name": first in normalized_text, "last_name": (last[-1] if last else first) in normalized_text,
        "email": not header.get("email") or header["email"] in normalized_text,
        "phone": not header.get("phone") or header["phone"] in normalized_text,
        "city_state": not header.get("public_location") or header["public_location"] in normalized_text,
        "linkedin": not header.get("linkedin") or header["linkedin"] in normalized_text,
        "portfolio": not header.get("portfolio") or header["portfolio"] in normalized_text,
        "most_recent_employer": not content.get("employment") or content["employment"][0]["employer"] in normalized_text,
        "most_recent_title": not content.get("employment") or content["employment"][0]["actual_title"] in normalized_text,
        "education": not education or education[0] in normalized_text,
    }
    reader = PdfReader(str(pdf_path))
    annotation_uris = []
    for page in reader.pages:
        for annotation_ref in page.get("/Annots", []) or []:
            annotation = annotation_ref.get_object()
            action = annotation.get("/A")
            if action and action.get("/URI"):
                annotation_uris.append(str(action.get("/URI")))
    metadata = reader.metadata or {}
    expected_title = f"{header['candidate_name']} - {header['positioning_headline']} Resume"
    geometry = all(abs(float(page.mediabox.width) - 612) < 1 and abs(float(page.mediabox.height) - 792) < 1 for page in reader.pages)
    with pdfplumber.open(pdf_path) as document:
        sizes = [float(char.get("size", 0)) for page in document.pages for char in page.chars]
        within = all(page.chars and all(0 <= char["x0"] <= page.width and 0 <= char["x1"] <= page.width and 0 <= char["top"] <= page.height and 0 <= char["bottom"] <= page.height for char in page.chars) for page in document.pages)
    forbidden_metadata = " ".join(str(metadata.get(key, "")) for key in ("/Title", "/Author", "/Subject", "/Creator", "/Producer")).casefold()
    logical_header_values = [header["candidate_name"], header["positioning_headline"], *contact_values(header)]
    logical_positions = [normalized_text.find(value) for value in logical_header_values if value]
    expected_link_uris = []
    if header.get("email"):
        expected_link_uris.append("mailto:" + header["email"])
    for value in professional_link_values(header):
        expected_link_uris.append(value if value.startswith(("http://", "https://")) else "https://" + value)
    gates = {
        "NAME_EXTRACTED": header["candidate_name"] in normalized_text,
        "EMAIL_EXTRACTED": not header.get("email") or header["email"] in normalized_text,
        "PHONE_EXTRACTED": not header.get("phone") or header["phone"] in normalized_text,
        "LOCATION_EXTRACTED": not header.get("public_location") or header["public_location"] in normalized_text,
        "LINKEDIN_EXTRACTED": not header.get("linkedin") or header["linkedin"] in normalized_text,
        "PORTFOLIO_EXTRACTED": not header.get("portfolio") or header["portfolio"] in normalized_text,
        "GITHUB_EXTRACTED": not header.get("optional_github") or header["optional_github"] in normalized_text,
        "HEADLINE_EXTRACTED": header["positioning_headline"] in normalized_text,
        "HEADER_READING_ORDER": all(value >= 0 for value in logical_positions) and logical_positions == sorted(logical_positions),
        "LINK_ANNOTATIONS": all(value in annotation_uris for value in expected_link_uris) and len(annotation_uris) == len(set(annotation_uris)),
        "MASTHEAD_GEOMETRY": content.get("masthead_geometry", {}).get("status") in {"PASS", "NOT_APPLICABLE_FALLBACK"},
        "SUMMARY_EXTRACTED": summary["text"] in normalized_text,
        "SUMMARY_EVIDENCE_TRACE": validate_recruiter_summary(summary)["status"] == "PASS",
        "SECTION_NAMES": all(value in text for value in expected_sections),
        "SECTION_READING_ORDER": all(value >= 0 for value in section_positions) and section_positions == sorted(section_positions),
        "PRIMARY_EXTRACTION": extracted["primary_agreement"], "SECONDARY_EXTRACTION": extracted["secondary_agreement"],
        "IDENTITY_ROUND_TRIP": not missing_header, "EMPLOYMENT_ROUND_TRIP": not missing_employment,
        "PROJECTS_ROUND_TRIP": all(value in normalized_text for value in projects),
        "EDUCATION_ROUND_TRIP": all(value in normalized_text for value in education),
        "CREDENTIALS_ROUND_TRIP": all(value in normalized_text for value in credentials),
        "SKILLS_ROUND_TRIP": all(value in normalized_text for value in skills), "AUTOFILL": all(autofill.values()),
        "TITLE_EMPLOYER_PARSE": not missing_employment,
        "DATE_STANDARD": all(format_public_date(item) in normalized_text for item in content.get("employment", [])),
        "PDF_METADATA": metadata.get("/Title") == expected_title and metadata.get("/Author") == header["candidate_name"] and metadata.get("/Subject") == "Resume" and not any(term in forbidden_metadata for term in ("career os", "canonical", "workspace", "build id")),
        "TYPOGRAPHY_GEOMETRY": geometry and within and bool(sizes) and min(sizes) >= 8.0 and len(reader.pages) <= 2,
        "SINGLE_COLUMN": True, "NO_GRAPHICAL_DEPENDENCY": bool(text.strip()) and len(text) >= 200,
    }
    status = "ATS_SAFE_HIGH_CONFIDENCE" if all(gates.values()) else "FAIL"
    return {
        "schema": "careeros.ats-resume-round-trip.v1", "schema_version": "1.0.0", "status": status,
        "gates": gates, "missing_header_fields": missing_header,
        "missing_employment_fields": missing_employment, "autofill": autofill,
        "expected_sections": expected_sections,
        "extraction_backends": ["pypdf", "pdfplumber"] + ([extracted["secondary_backend"]] if extracted["secondary_backend"] else []),
        "page_count": len(reader.pages), "minimum_font_size": min(sizes) if sizes else None,
        "confidence": "HIGH" if status == "ATS_SAFE_HIGH_CONFIDENCE" else "LOW",
    }
