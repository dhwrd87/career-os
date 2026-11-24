"""Candidate-neutral resume compiler, PDF renderer, and validation gates."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import pdfplumber
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
from reportlab.pdfgen.canvas import Canvas

from careeros.config.loader import load_config
from careeros.completeness import apply_actual_page_utilization, evaluate_resume_completeness
from careeros.career_conversion import build_career_conversion_trace, build_employer_need_trace, build_role_fact_set
from careeros.core.io import atomic_write_json, read_json, sha256_file, sha256_value
from careeros.versions import RENDERER_VERSION
from careeros.editorial import (
    build_bullet_candidates,
    default_public_display_policy,
    evaluate_editorial_quality,
    group_skills,
    plan_storyline,
    public_credentials,
    public_education,
    sanitize_url,
)
from careeros.job_intelligence import (
    adapt_storyline,
    build_tailoring_trace,
    evaluate_job_specific_qa,
    job_specific_summary,
    select_adaptive_bullets,
)
from careeros.resume_governance import (
    build_freshness_contract,
    compare_freshness,
    credential_opportunities,
    new_evidence_utilization,
    professional_history_sufficiency,
    public_label_leaks,
    recruiter_copy_specificity,
    targeted_resume_delta,
)
from careeros.resume_ats import (
    APPROVED_SECTION_NAMES,
    ATS_MINIMAL_FALLBACK,
    PREMIUM_CENTERED_MASTHEAD,
    ats_resume_round_trip,
    build_recruiter_summary,
    build_resume_header,
    contact_values,
    evaluate_masthead_geometry,
    format_public_date,
    header_layout_decision,
    recruiter_safe_filename,
    validate_recruiter_summary,
)
from careeros.resume_premium import apply_premium_presentation, evaluate_premium_quality, evaluate_visual_density
from careeros.recruiter_conversion import (
    build_recruiter_conversion_strategy,
    public_copy_boundary,
    recruiter_copy_quality_v2,
    targeted_editorial_regression,
)
from careeros.schemas.validation import SchemaRegistry
from careeros.versions import COMPILER_VERSION, FONT_PROFILE_VERSION, PRIVACY_POLICY_VERSION, TEMPLATE_VERSION, TRUTH_POLICY_VERSION
from careeros.workspace import require_current_workspace, schema_dir, update_last_build_versions, utc_now
from careeros.updates import mark_derivative_current, require_derivative_current


EMPLOYER_USABLE_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}


def _safe_token(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9 ._()-]+", "", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return value or "Resume"


def output_filename(pattern: str, public_name: str, target_role: str) -> str:
    rendered = pattern.format(public_name=_safe_token(public_name), target_role=_safe_token(target_role))
    return rendered if rendered.lower().endswith(".pdf") else rendered + ".pdf"


def _select_evidence(profile: dict[str, Any], opportunity: dict[str, Any], matrix: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    matrix_ids = {record_id for row in (matrix or {}).get("requirements", []) for record_id in row["candidate_evidence_ids"]}
    capability_names = {item["capability"].casefold() for item in opportunity["requirements"]}
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for evidence in profile["evidence"]:
        if evidence["visibility"] not in EMPLOYER_USABLE_VISIBILITY:
            excluded.append({"evidence_id": evidence["record_id"], "reason": "RESTRICTED_VISIBILITY"})
            continue
        skill_names = {skill["name"].casefold() for skill in profile["skills"] if skill["record_id"] in evidence.get("skill_ids", [])}
        matrix_selected = evidence["record_id"] in matrix_ids or bool(set(evidence.get("skill_ids", [])) & matrix_ids)
        compatibility_selected = bool(skill_names & capability_names or evidence.get("employment_ids") or evidence.get("project_ids"))
        if matrix_selected or compatibility_selected:
            selected.append(evidence)
        else:
            excluded.append({"evidence_id": evidence["record_id"], "reason": "LOW_ROLE_RELEVANCE"})
    return selected, excluded


def _content_contract(
    profile: dict[str, Any], family: dict[str, Any], opportunity: dict[str, Any], selected: list[dict[str, Any]],
    intelligence: dict[str, Any], matrix: dict[str, Any], qualification: dict[str, Any], snapshot: dict[str, Any] | None = None,
    lane_base_storyline: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    policy = default_public_display_policy()
    snapshot = snapshot or {
        "snapshot_id": str(intelligence.get("snapshot_id") or "snapshot:structured-requirements"),
        "text": "\n".join(str(item.get("requirement_text") or "") for item in matrix.get("requirements", [])),
    }
    # An accepted lane base is the governed default story. Job intelligence may
    # adapt its emphasis, never its truth or prohibited equivalence boundaries.
    base_storyline = lane_base_storyline or plan_storyline(profile, family, opportunity)
    storyline = adapt_storyline(base_storyline, profile, family, opportunity, intelligence, matrix)
    role_fact_set = build_role_fact_set(profile)
    preliminary_need_trace = build_employer_need_trace(intelligence, matrix, snapshot)
    selected_ids = {item["record_id"] for item in selected}
    base_candidates = [item for item in build_bullet_candidates(profile, storyline) if set(item["evidence_ids"]) & selected_ids]
    candidates, omitted_bullets = select_adaptive_bullets(
        base_candidates, matrix, storyline["job_story_signals"], storyline=storyline,
        employer_need_trace=preliminary_need_trace, role_fact_set=role_fact_set,
    )
    bullets_by_evidence = {item["evidence_ids"][0]: item for item in candidates}
    employment_sections = []
    evidence_index = {item["record_id"]: item for item in profile.get("evidence", [])}
    used_bullet_evidence: set[str] = set()
    for employment in sorted(
        profile["employment"],
        key=lambda item: (item.get("end_year") is None or str(item.get("end_year")).upper() == "PRESENT", int(item.get("start_year") or 0)),
        reverse=True,
    )[:6]:
        bullets = []
        for evidence_id in employment.get("evidence_ids", []):
            if evidence_id in used_bullet_evidence:
                continue
            candidate = bullets_by_evidence.get(evidence_id)
            if not candidate:
                continue
            bullets.append(candidate)
            used_bullet_evidence.update(candidate["evidence_ids"])
        bullets.sort(key=lambda item: (-float(item.get("selection_score", 0.0)), item["bullet_id"]))
        if not bullets:
            fallback = next((
                evidence_index.get(evidence_id)
                for evidence_id in employment.get("evidence_ids", [])
                if evidence_index.get(evidence_id, {}).get("visibility") in EMPLOYER_USABLE_VISIBILITY
                and str(evidence_index.get(evidence_id, {}).get("summary", "")).strip()
            ), None)
            if fallback:
                text = str(fallback["summary"]).strip().rstrip(".") + "."
                bullets.append({
                    "bullet_id": f"bullet:{fallback['record_id']}:minimal",
                    "evidence_ids": [fallback["record_id"]], "text": text,
                    "outcome": "", "metric_refs": [], "unsupported_metric_tokens": [],
                    "variant_mode": "MINIMAL_HISTORY",
                })
                used_bullet_evidence.add(fallback["record_id"])
        if not bullets and employment.get("visibility") not in set(policy["allowed_visibility"]):
            continue
        employment_sections.append({
            "employer": employment["employer"], "actual_title": employment["actual_title"],
            "public_title_alias": employment.get("public_title"), "display_title": employment["actual_title"],
            "start_year": employment.get("start_year"), "end_year": employment.get("end_year"), "bullets": bullets,
            "record_id": employment["record_id"], "display_mode": "FULL" if len(bullets) >= 2 else ("COMPACT" if bullets else "MINIMAL"),
        })
    project_sections = []
    project_rank = {item["evidence_id"]: index for index, item in enumerate(storyline.get("evidence_rankings", []))}
    projects = sorted(
        profile["projects"],
        key=lambda item: (
            -max([float(bullets_by_evidence.get(eid, {}).get("selection_score", 0.0)) for eid in item.get("evidence_ids", [])] or [0.0]),
            min([project_rank.get(eid, 10_000) for eid in item.get("evidence_ids", [])] or [10_000]),
        ),
    )
    for project in projects:
        if project["visibility"] not in EMPLOYER_USABLE_VISIBILITY:
            continue
        bullets = []
        for evidence_id in project.get("evidence_ids", []):
            if evidence_id in bullets_by_evidence and evidence_id not in used_bullet_evidence:
                bullets.append(bullets_by_evidence[evidence_id])
                used_bullet_evidence.update(bullets_by_evidence[evidence_id]["evidence_ids"])
        bullets.sort(key=lambda item: (-float(item.get("selection_score", 0.0)), item["bullet_id"]))
        if bullets:
            if len(project_sections) < 4:
                project_sections.append({
                    "name": project["name"], "date_range": project.get("date_range"),
                    "contribution": project["contribution"], "bullets": bullets,
                    "record_id": project["record_id"],
                    "selection_tier": "PRIMARY" if len(project_sections) < 2 else "SECONDARY",
                })
            else:
                omitted_bullets.extend({"bullet_id": bullet["bullet_id"], "reason": "SPACE", "evidence_ids": bullet["evidence_ids"]} for bullet in bullets)
    displayed_evidence_ids = {
        evidence_id
        for section in [*employment_sections, *project_sections]
        for bullet in section.get("bullets", [])
        for evidence_id in bullet.get("evidence_ids", [])
    }
    policy = default_public_display_policy()
    grouped_candidates = group_skills(profile, storyline, policy)
    skill_groups = [
        {
            "group": group["group"],
            "skills": [
                item for item in group["skills"]
                if group["group"] == "LANGUAGES" or bool(set(item.get("evidence_ids", [])) & displayed_evidence_ids)
            ],
        }
        for group in grouped_candidates
    ]
    skill_groups = [group for group in skill_groups if group["skills"]]
    skills = [item for group in skill_groups for item in group["skills"]]
    content = {
        "schema": "careeros.resume-content.v1",
        "candidate": profile["candidate"],
        "target_role": opportunity["role_title"],
        "role_family_id": family["role_family_id"],
        "summary": job_specific_summary(storyline, opportunity),
        "storyline": storyline,
        "public_display_policy": policy,
        "skills": [
            {
                "name": skill["name"], "record_id": skill["record_id"],
                "evidence_ids": skill.get("evidence_ids", []),
                **({"proficiency": skill.get("proficiency"), "claim_boundary": skill.get("claim_boundary")} if skill.get("claim_boundary") else {}),
            }
            for skill in skills
        ],
        "skill_groups": skill_groups,
        "employment": employment_sections,
        "projects": project_sections,
        "education": profile["education"],
        "display_education": public_education(profile, policy),
        "credentials": [item for item in profile["credentials"] if item["visibility"] in EMPLOYER_USABLE_VISIBILITY],
        "display_credentials": public_credentials(profile, policy),
        "section_order": storyline["section_order_adjustments"],
    }
    conversion_strategy = build_recruiter_conversion_strategy(
        profile, family, opportunity=opportunity,
        employer_need_trace=preliminary_need_trace,
        selected_evidence_ids=displayed_evidence_ids,
    )
    summary_contract = build_recruiter_summary(
        profile, storyline, family, opportunity=opportunity,
        selected_evidence_ids=displayed_evidence_ids,
        employer_need_trace=preliminary_need_trace,
    )
    content["recruiter_summary"] = summary_contract
    content["summary"] = summary_contract["text"]
    content["recruiter_conversion_strategy_v2"] = conversion_strategy
    content["resume_header"] = build_resume_header(profile["candidate"], opportunity["role_title"])
    content["resume_completeness"] = evaluate_resume_completeness(profile, content, omitted_bullets)
    content["editorial_quality"] = evaluate_editorial_quality(content)
    content["job_specific_qa"] = evaluate_job_specific_qa(content, intelligence, matrix, qualification)
    omission_reasons = {
        evidence_id: str(item.get("reason") or "OTHER")
        for item in omitted_bullets for evidence_id in item.get("evidence_ids", [])
    }
    final_need_trace = build_employer_need_trace(
        intelligence, matrix, snapshot, content=content, omission_reasons=omission_reasons,
    )
    conversion_trace = build_career_conversion_trace(
        profile, content, build_scope="TARGETED", employer_need_trace=final_need_trace,
        omission_reasons=omission_reasons,
    )
    content["employer_need_trace"] = final_need_trace
    content["role_fact_set"] = role_fact_set
    content["strongest_evidence_omission"] = conversion_trace["strongest_evidence_omission"]
    content["material_evidence_loss"] = conversion_trace["material_evidence_loss"]
    content["career_conversion_trace"] = conversion_trace
    content["public_copy_boundary_v1"] = public_copy_boundary(content)
    content["recruiter_copy_quality_v2"] = recruiter_copy_quality_v2(
        content, strategy=conversion_strategy, employer_need_trace=final_need_trace,
    )
    return content, omitted_bullets


def _styles(*, compact: bool = False):
    styles = getSampleStyleSheet()
    body_size = 8.5 if compact else 9.0
    body_leading = 10.5 if compact else 11.4
    bullet_size = 8.3 if compact else 8.65
    bullet_leading = 10.2 if compact else 11.2
    return {
        "name": ParagraphStyle("Name", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23 if not compact else 20, leading=25 if not compact else 22, textColor=colors.HexColor("#15233a"), spaceAfter=2),
        "headline": ParagraphStyle("Headline", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11.2 if not compact else 10.5, leading=13.5 if not compact else 12.5, textColor=colors.HexColor("#1f4f78"), spaceAfter=3),
        "contact": ParagraphStyle("Contact", parent=styles["Normal"], fontName="Helvetica", fontSize=8.3, leading=10, textColor=colors.HexColor("#526171"), spaceAfter=4),
        "links": ParagraphStyle("Links", parent=styles["Normal"], fontName="Helvetica", fontSize=8.1, leading=9.6, textColor=colors.HexColor("#647487"), spaceAfter=2),
        "section": ParagraphStyle("Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.2, leading=12.2, textColor=colors.HexColor("#1f4f78"), spaceBefore=6 if not compact else 5, spaceAfter=3, borderWidth=0, borderPadding=0),
        "subsection": ParagraphStyle("Subsection", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=8.4, leading=10, textColor=colors.HexColor("#647487"), spaceBefore=4, spaceAfter=2),
        "role": ParagraphStyle("Role", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.6, leading=11.4, textColor=colors.HexColor("#17233c"), spaceAfter=0.5),
        "secondary": ParagraphStyle("Secondary", parent=styles["Normal"], fontName="Helvetica", fontSize=8.35, leading=10, textColor=colors.HexColor("#526171"), spaceAfter=2),
        "body": ParagraphStyle("Body", parent=styles["Normal"], fontName="Helvetica", fontSize=body_size, leading=body_leading, alignment=TA_LEFT, spaceAfter=2.5),
        "bullet": ParagraphStyle("Bullet", parent=styles["Normal"], fontName="Helvetica", fontSize=bullet_size, leading=bullet_leading, leftIndent=11, firstLineIndent=-8, bulletIndent=0, spaceAfter=2),
        "compact_project": ParagraphStyle("CompactProject", parent=styles["Normal"], fontName="Helvetica", fontSize=8.45 if compact else 8.75, leading=10.4 if compact else 11, textColor=colors.HexColor("#26384b"), spaceAfter=2),
    }


class _InvariantCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)


def render_pdf(content: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    apply_premium_presentation(content)
    candidate = content["candidate"]
    header = content.get("resume_header") or build_resume_header(candidate, content["target_role"])
    header_presentation = content.get("header_presentation") or PREMIUM_CENTERED_MASTHEAD
    if header_presentation not in {PREMIUM_CENTERED_MASTHEAD, ATS_MINIMAL_FALLBACK}:
        raise ValueError(f"unsupported header presentation: {header_presentation}")
    total_bullets = sum(len(section.get("bullets", [])) for section in [*content.get("employment", []), *content.get("projects", [])])
    styles = _styles(compact=total_bullets > 24)
    for kind in ('section', 'subsection', 'role', 'secondary'):
        styles[kind].keepWithNext = True
    for style in styles.values():
        style.allowOrphans = 0
        style.allowWidows = 0
    layout = header_layout_decision(header, safe_width=LETTER[0] - (2 * 0.62 * inch))
    content["header_layout_decision"] = layout
    content["header_presentation"] = header_presentation
    if header_presentation == PREMIUM_CENTERED_MASTHEAD:
        for key in ("name", "headline", "contact", "links"):
            styles[key].alignment = TA_CENTER
        styles["name"].fontSize = layout["font_sizes"]["name"]
        styles["name"].leading = layout["font_sizes"]["name"] + 2
        styles["headline"].fontSize = layout["font_sizes"]["headline"]
        styles["headline"].leading = layout["font_sizes"]["headline"] + 2.1
        styles["contact"].fontSize = layout["font_sizes"]["contact"]
        styles["links"].fontSize = layout["font_sizes"]["links"]
    metadata_title = f"{header['candidate_name']} - {header['positioning_headline']} Resume"
    doc = SimpleDocTemplate(
        str(target), pagesize=LETTER, rightMargin=0.62 * inch, leftMargin=0.62 * inch,
        topMargin=0.46 * inch, bottomMargin=0.46 * inch, title=metadata_title,
        author=header["candidate_name"], subject="Resume", creator="", producer="",
    )
    def linked_markup(value: str) -> str:
        full_url = None
        if value in {header.get("linkedin"), header.get("portfolio"), header.get("optional_github")}:
            full_url = value if value.startswith(("http://", "https://")) else "https://" + value
        if header.get("email") == value:
            full_url = "mailto:" + value
        display = escape(value)
        return f'<link href="{escape(full_url, {chr(34): "&quot;"})}">{display}</link>' if full_url else display

    story: list[Any] = [Paragraph(escape(header["candidate_name"]), styles["name"])]
    if header_presentation == PREMIUM_CENTERED_MASTHEAD:
        for row in layout["headline_rows"]:
            story.append(Paragraph(escape(row), styles["headline"]))
        for row in layout["primary_contact_rows"]:
            story.append(Paragraph(layout["separator"].join(linked_markup(value) for value in row), styles["contact"]))
        for row in layout["professional_link_rows"]:
            story.append(Paragraph(layout["separator"].join(linked_markup(value) for value in row), styles["links"]))
        # The links row needs a modest optical buffer before the divider. Keep
        # the divider-to-body spacing and every other masthead token unchanged.
        story.append(HRFlowable(width="100%", thickness=0.45, color=colors.HexColor("#a9b7c4"), spaceBefore=4, spaceAfter=2))
    else:
        story.append(Paragraph(escape(header["positioning_headline"]), styles["headline"]))
        story.append(Paragraph(" | ".join(linked_markup(value) for value in contact_values(header)), styles["contact"]))
        story.append(HRFlowable(width="100%", thickness=0.55, color=colors.HexColor("#9aacbd"), spaceBefore=1, spaceAfter=2))
    sections: dict[str, list[Any]] = {
        "SUMMARY": [Paragraph("SUMMARY", styles["section"]), Paragraph(content["summary"], styles["body"])],
        "SKILLS": [], "EXPERIENCE": [], "PROJECTS": [], "EDUCATION": [], "CREDENTIALS": [],
    }
    if content.get("skill_groups"):
        sections["SKILLS"].append(Paragraph("CORE SKILLS", styles["section"]))
        for group in content["skill_groups"]:
            sections["SKILLS"].append(Paragraph(f"<b>{group['group']}:</b> " + " | ".join(item["name"] for item in group["skills"]), styles["body"]))
    if content["employment"]:
        sections["EXPERIENCE"].append(Paragraph(APPROVED_SECTION_NAMES["EXPERIENCE"], styles["section"]))
        for employment in content["employment"]:
            location = f" | {employment['location']}" if employment.get("location") else ""
            sections["EXPERIENCE"].append(Paragraph(employment["actual_title"], styles["role"]))
            sections["EXPERIENCE"].append(Paragraph(f"{employment['employer']}{location} | {format_public_date(employment)}", styles["secondary"]))
            for bullet in employment["bullets"]:
                sections["EXPERIENCE"].append(Paragraph("- " + bullet["text"], styles["bullet"]))
    if content["projects"]:
        sections["PROJECTS"].append(Paragraph("FEATURED PROJECTS", styles["section"]))
        additional_started = False
        for project in content["projects"]:
            if project.get("presentation_tier") == "ADDITIONAL":
                if not additional_started:
                    sections["PROJECTS"].append(Paragraph("ADDITIONAL PROJECTS", styles["subsection"]))
                    additional_started = True
                detail = project.get("bullets", [{}])[0].get("text") or project.get("contribution", "")
                sections["PROJECTS"].append(Paragraph(f"<b>{project['name']}</b> - {detail}", styles["compact_project"]))
                continue
            sections["PROJECTS"].append(Paragraph(project["name"], styles["role"]))
            if project.get("contribution"):
                sections["PROJECTS"].append(Paragraph(project["contribution"], styles["secondary"]))
            for bullet in project["bullets"]:
                sections["PROJECTS"].append(Paragraph("- " + bullet["text"], styles["bullet"]))
    if content.get("display_education"):
        sections["EDUCATION"].append(Paragraph("EDUCATION", styles["section"]))
        for education in content["display_education"]:
            degree = education.get("program") or "Education"
            if education.get("field_of_study"):
                degree += f" in {education['field_of_study']}"
            sections["EDUCATION"].append(Paragraph(education["institution"], styles["role"]))
            suffix = f" - {education['display_status']}" if education.get("display_status") else ""
            sections["EDUCATION"].append(Paragraph(f"{degree}{suffix}", styles["secondary"]))
    if content.get("display_credentials"):
        sections["CREDENTIALS"].append(Paragraph(APPROVED_SECTION_NAMES["CREDENTIALS"], styles["section"]))
        for credential in content["display_credentials"]:
            sections["CREDENTIALS"].append(Paragraph(f"{credential['title']} - {credential['issuer']}", styles["body"]))
    for section in content.get("section_order") or ["SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CREDENTIALS"]:
        story.extend(sections.get(section, []))
    doc.build(story, canvasmaker=_InvariantCanvas)
    reader = PdfReader(str(target))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({"/Title": metadata_title, "/Author": header["candidate_name"], "/Subject": "Resume"})
    temporary = target.with_suffix(".metadata.pdf")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(target)
    content["masthead_geometry"] = evaluate_masthead_geometry(target, header, layout) if header_presentation == PREMIUM_CENTERED_MASTHEAD else {
        "schema": "careeros.masthead-geometry.v1", "schema_version": "1.0.0", "layout_mode": "ATS_MINIMAL_FALLBACK",
        "name_center_offset": None, "headline_center_offset": None, "primary_contact_center_offset": None, "links_center_offset": None,
        "headline_gap": None, "contact_gap": None, "link_gap": None, "divider_gap": None,
        "professional_links_bottom_y": None, "divider_y": None, "summary_top_y": None,
        "links_to_divider_gap": None, "divider_to_summary_gap": None, "divider_balance_ratio": None,
        "masthead_total_height": None,
        "safe_width": layout["safe_width"], "center_tolerance": 2.5,
        "line_counts": {"headline": 1, "primary_contact": 1, "professional_links": 0},
        "missing_rows": [], "clipping_risk": False, "status": "NOT_APPLICABLE_FALLBACK",
    }
    content["resume_visual_density"] = evaluate_visual_density(content, target)
    content["premium_resume_quality"] = evaluate_premium_quality(content, content["resume_visual_density"])


def build(workspace: Path, opportunity_id: str, *, timestamp: str | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    require_current_workspace(workspace)
    validated = load_config(workspace / "careeros.yaml")
    roots = validated.roots
    profile = read_json(roots.state_root / "profile/career-profile.json")
    profile_manifest = read_json(roots.state_root / "profile/profile-build-manifest.json")
    family = read_json(roots.state_root / "role-families/active.json")
    opportunity_dir = roots.state_root / "opportunities" / opportunity_id
    opportunity = read_json(opportunity_dir / "opportunity.json")
    snapshot = read_json(opportunity_dir / "jd-snapshot.json")
    intelligence = read_json(opportunity_dir / "jd-intelligence.json")
    matrix = read_json(opportunity_dir / "job-evidence-matrix.json")
    qualification = read_json(roots.state_root / "qualifications" / f"{opportunity_id}.json")
    require_derivative_current(roots, "CAREER_PROFILE", profile["profile_id"])
    require_derivative_current(roots, "ROLE_FAMILY", family["role_family_id"])
    require_derivative_current(roots, "QUALIFICATION", qualification["qualification_id"])
    if qualification["decision"] != "QUALIFIED":
        raise PermissionError(f"resume build requires QUALIFIED; received {qualification['decision']}")
    from careeros.lane_base import _lane_content, load_current_for_role

    lane_base_dependency = load_current_for_role(workspace, family["role_family_id"])
    lane_base_record = lane_base_dependency[0] if lane_base_dependency else None
    lane_base_storyline = lane_base_dependency[1] if lane_base_dependency else None
    selected, excluded = _select_evidence(profile, opportunity, matrix)
    content, omitted_bullets = _content_contract(
        profile, family, opportunity, selected, intelligence, matrix, qualification, snapshot,
        lane_base_storyline=lane_base_storyline,
    )
    editorial_parent_content = None
    if lane_base_record:
        content["lane_base"] = {
            "lane_base_id": lane_base_record["lane_base_id"],
            "allowed_claims": lane_base_record["allowed_claims"],
            "prohibited_claims": lane_base_record["prohibited_claims"],
            "gap_assumptions": lane_base_record["gap_assumptions"],
        }
        base_content_path = roots.state_root / "lane-bases" / lane_base_record["lane_base_id"] / "content.json"
        if base_content_path.is_file():
            editorial_parent_content = read_json(base_content_path)
            content["targeted_resume_delta"] = targeted_resume_delta(editorial_parent_content, content)
    if "targeted_resume_delta" not in content:
        reference_storyline = plan_storyline(profile, family)
        reference_content, _ = _lane_content(profile, family, reference_storyline)
        editorial_parent_content = reference_content
        content["targeted_resume_delta"] = targeted_resume_delta(reference_content, content)
        content["targeted_resume_delta"]["reference"] = "APPROVED_ROLE_FAMILY_BASELINE"
    content["targeted_editorial_regression_v1"] = targeted_editorial_regression(
        editorial_parent_content or content, content,
    )
    created_at = utc_now(timestamp)
    workspace_manifest = read_json(workspace / "workspace-manifest.json")
    freshness = build_freshness_contract(
        profile, profile_manifest, family, content["storyline"],
        canonical_revision=int(workspace_manifest["canonical_head"]["revision"]),
        compiler_version=COMPILER_VERSION,
        editorial_policy_version=content["public_display_policy"]["policy_id"],
        build_timestamp=created_at,
        jd_snapshot=snapshot,
    )
    rendered_evidence = {
        evidence_id
        for section in [*content["employment"], *content["projects"]]
        for bullet in section.get("bullets", [])
        for evidence_id in bullet.get("evidence_ids", [])
    }
    omission_dispositions = {
        item["evidence_id"]: (
            "OMITTED_PRIVACY" if "RESTRICTED" in item["reason"] else "OMITTED_LOW_RELEVANCE"
        )
        for item in excluded
    }
    omission_dispositions.update({
        evidence_id: ("OMITTED_REDUNDANT" if item.get("reason") == "REDUNDANT" else "OMITTED_SPACE")
        for item in omitted_bullets for evidence_id in item.get("evidence_ids", [])
    })
    relevant_evidence = {
        evidence_id for row in matrix.get("requirements", []) for evidence_id in row.get("candidate_evidence_ids", [])
    }
    utilization = new_evidence_utilization(
        None, profile, rendered_evidence, omission_dispositions, relevant_evidence_ids=relevant_evidence,
    )
    history = professional_history_sufficiency(
        [item for item in profile.get("employment", []) if item.get("visibility") in EMPLOYER_USABLE_VISIBILITY],
        content["employment"],
    )
    content["canonical_evidence_freshness"] = freshness
    content["new_evidence_utilization"] = utilization
    content["professional_history_sufficiency"] = history
    content["recruiter_copy_specificity"] = recruiter_copy_specificity(content, profile)
    content["credential_opportunities"] = credential_opportunities(profile)
    build_key = f"{profile_manifest['profile_hash']}:{opportunity_id}:{snapshot['content_hash']}:{TEMPLATE_VERSION}:{COMPILER_VERSION}:{RENDERER_VERSION}:{sha256_value(content)}"
    build_id = f"resume-build:{uuid.uuid5(uuid.NAMESPACE_URL, build_key)}"
    existing_dir = roots.state_root / 'resume-builds' / build_id
    if existing_dir.exists():
        existing_artifact = read_json(existing_dir / 'artifact.json')
        existing_pdf = (roots.output_root / existing_artifact['path']).resolve()
        if not existing_pdf.is_relative_to(roots.output_root.resolve()) or not existing_pdf.is_file() or sha256_file(existing_pdf) != existing_artifact['sha256']:
            raise PermissionError('Existing resume artifact is missing or changed; preserve its record and resolve the integrity failure')
        return read_json(existing_dir / 'build.json'), read_json(existing_dir / 'content.json'), existing_artifact
    build_record = {
        "schema": "careeros.resume-build.v1", "schema_version": "1.0.0", "build_id": build_id,
        "profile_hash": profile_manifest["profile_hash"], "opportunity_id": opportunity_id,
        "jd_snapshot_hash": snapshot["content_hash"], "role_family_id": family["role_family_id"],
        "qualification_id": qualification["qualification_id"], "compiler_version": COMPILER_VERSION,
        "policy_versions": {"truth": TRUTH_POLICY_VERSION, "privacy": PRIVACY_POLICY_VERSION, "qualification": qualification["policy_version"]},
        "template_version": TEMPLATE_VERSION, "font_profile_version": FONT_PROFILE_VERSION,
        "input_evidence_ids": sorted(item["record_id"] for item in profile["evidence"]),
        "selected_evidence_ids": sorted(item["record_id"] for item in selected), "excluded_evidence": excluded,
        "gate_state": "BUILDING", "created_at": created_at,
        "lane_base_id": lane_base_record["lane_base_id"] if lane_base_record else None,
        "canonical_evidence_freshness": freshness,
    }
    registry = SchemaRegistry(schema_dir())
    registry.validate("urn:careeros:schema:job-description-intelligence:v1", intelligence)
    registry.validate("urn:careeros:schema:job-evidence-matrix:v1", matrix)
    registry.validate("urn:careeros:schema:canonical-evidence-freshness:v1", freshness)
    registry.validate("urn:careeros:schema:new-evidence-utilization:v1", utilization)
    registry.validate("urn:careeros:schema:professional-history-sufficiency:v1", history)
    registry.validate("urn:careeros:schema:targeted-resume-delta:v1", content["targeted_resume_delta"])
    registry.validate("urn:careeros:schema:recruiter-copy-specificity:v1", content["recruiter_copy_specificity"])
    registry.validate("urn:careeros:schema:resume-header:v1", content["resume_header"])
    registry.validate("urn:careeros:schema:recruiter-summary:v1", content["recruiter_summary"])
    registry.validate("urn:careeros:schema:employer-need-trace:v1", content["employer_need_trace"])
    registry.validate("urn:careeros:schema:strongest-evidence-omission:v1", content["strongest_evidence_omission"])
    registry.validate("urn:careeros:schema:role-fact-set:v1", content["role_fact_set"])
    registry.validate("urn:careeros:schema:material-evidence-loss:v1", content["material_evidence_loss"])
    registry.validate("urn:careeros:schema:career-conversion-trace:v1", content["career_conversion_trace"])
    registry.validate("urn:careeros:schema:recruiter-conversion-strategy:v2", content["recruiter_conversion_strategy_v2"])
    registry.validate("urn:careeros:schema:public-copy-boundary:v1", content["public_copy_boundary_v1"])
    registry.validate("urn:careeros:schema:recruiter-copy-quality:v2", content["recruiter_copy_quality_v2"])
    registry.validate("urn:careeros:schema:targeted-editorial-regression:v1", content["targeted_editorial_regression_v1"])
    registry.validate("urn:careeros:schema:resume-build:v1", build_record)
    filename = recruiter_safe_filename(profile["candidate"]["public_name"], content["resume_header"]["positioning_headline"])
    pdf_path = roots.output_root / "resumes" / filename
    if pdf_path.exists():
        pdf_path = pdf_path.with_name(f"{pdf_path.stem} - {build_id[-8:]}{pdf_path.suffix}")
        if pdf_path.exists():
            raise FileExistsError(f"refusing to overwrite existing resume artifact: {pdf_path.name}")
    render_pdf(content, roots.assert_write_allowed(pdf_path, "output"))
    ats_round_trip = ats_resume_round_trip(content, pdf_path)
    registry.validate("urn:careeros:schema:ats-resume-round-trip:v1", ats_round_trip)
    registry.validate("urn:careeros:schema:masthead-geometry:v1", content["masthead_geometry"])
    registry.validate("urn:careeros:schema:resume-visual-density:v1", content["resume_visual_density"])
    registry.validate("urn:careeros:schema:premium-resume-quality:v1", content["premium_resume_quality"])
    reader = PdfReader(str(pdf_path))
    artifact = {
        "schema": "careeros.resume-artifact.v1", "schema_version": "1.0.0",
        "artifact_id": f"artifact:{uuid.uuid5(uuid.NAMESPACE_URL, build_id + ':' + filename)}", "build_id": build_id,
        "media_type": "application/pdf", "path": str(pdf_path.relative_to(roots.output_root)), "sha256": sha256_file(pdf_path),
        "page_count": len(reader.pages), "metadata": {"title": f"{content['resume_header']['candidate_name']} - {content['resume_header']['positioning_headline']} Resume", "author": profile["candidate"]["public_name"], "subject": "Resume", "template": TEMPLATE_VERSION, "font_profile": FONT_PROFILE_VERSION},
        "status": "CANDIDATE", "accepted_at": None, "supersedes": None,
    }
    registry.validate("urn:careeros:schema:resume-artifact:v1", artifact)
    build_dir = roots.state_root / "resume-builds" / build_id
    trace = build_tailoring_trace(intelligence, matrix, content, omitted_bullets, qualification)
    registry.validate("urn:careeros:schema:job-tailoring-trace:v1", trace)
    registry.validate("urn:careeros:schema:resume-completeness:v1", content["resume_completeness"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "build.json", "state"), build_record)
    atomic_write_json(roots.assert_write_allowed(build_dir / "content.json", "state"), content)
    atomic_write_json(roots.assert_write_allowed(build_dir / "storyline.json", "state"), content["storyline"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "public-display-policy.json", "state"), content["public_display_policy"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "editorial-quality.json", "state"), content["editorial_quality"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "job-description-intelligence.json", "state"), intelligence)
    atomic_write_json(roots.assert_write_allowed(build_dir / "job-evidence-matrix.json", "state"), matrix)
    atomic_write_json(roots.assert_write_allowed(build_dir / "job-tailoring-trace.json", "state"), trace)
    atomic_write_json(roots.assert_write_allowed(build_dir / "job-specific-qa.json", "state"), content["job_specific_qa"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "resume-completeness.json", "state"), content["resume_completeness"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "canonical-evidence-freshness.json", "state"), freshness)
    atomic_write_json(roots.assert_write_allowed(build_dir / "new-evidence-utilization.json", "state"), utilization)
    atomic_write_json(roots.assert_write_allowed(build_dir / "professional-history-sufficiency.json", "state"), history)
    atomic_write_json(roots.assert_write_allowed(build_dir / "resume-header.json", "state"), content["resume_header"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "recruiter-summary.json", "state"), content["recruiter_summary"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "employer-need-trace.json", "state"), content["employer_need_trace"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "strongest-evidence-omission.json", "state"), content["strongest_evidence_omission"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "role-fact-set.json", "state"), content["role_fact_set"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "material-evidence-loss.json", "state"), content["material_evidence_loss"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "career-conversion-trace.json", "state"), content["career_conversion_trace"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "recruiter-conversion-strategy-v2.json", "state"), content["recruiter_conversion_strategy_v2"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "public-copy-boundary-v1.json", "state"), content["public_copy_boundary_v1"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "recruiter-copy-quality-v2.json", "state"), content["recruiter_copy_quality_v2"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "targeted-editorial-regression-v1.json", "state"), content["targeted_editorial_regression_v1"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "ats-resume-round-trip.json", "state"), ats_round_trip)
    atomic_write_json(roots.assert_write_allowed(build_dir / "resume-visual-density.json", "state"), content["resume_visual_density"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "premium-resume-quality.json", "state"), content["premium_resume_quality"])
    atomic_write_json(roots.assert_write_allowed(build_dir / "artifact.json", "state"), artifact)
    mark_derivative_current(roots, "RESUME_BUILD", build_id, timestamp=created_at, lineage_hash=artifact["sha256"])
    update_last_build_versions(workspace, timestamp=created_at)
    return build_record, content, artifact


def _gate(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {"gate": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def validate(workspace: Path, build_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    build_dir = roots.state_root / "resume-builds" / build_id
    build_record = read_json(build_dir / "build.json")
    content = read_json(build_dir / "content.json")
    artifact = read_json(build_dir / "artifact.json")
    pdf_path = roots.output_root / artifact["path"]
    profile = read_json(roots.state_root / "profile/career-profile.json")
    opportunity = read_json(roots.state_root / "opportunities" / build_record["opportunity_id"] / "opportunity.json")
    profile_manifest = read_json(roots.state_root / "profile/profile-build-manifest.json")
    family = read_json(roots.state_root / "role-families/active.json")
    snapshot = read_json(roots.state_root / "opportunities" / build_record["opportunity_id"] / "jd-snapshot.json")
    registry = SchemaRegistry(schema_dir())
    gates: list[dict[str, str]] = []
    from careeros.document_quality import inspect_pdf
    object_preflight = inspect_pdf(pdf_path)
    gates.append(_gate("PDF_OBJECT_PREFLIGHT", object_preflight['status'] == 'PASS', str(object_preflight['findings'])))
    try:
        registry.validate("urn:careeros:schema:resume-build:v1", build_record)
        registry.validate("urn:careeros:schema:resume-artifact:v1", artifact)
        schema_ok = True
    except Exception as exc:
        schema_ok = False
        schema_detail = str(exc)
    gates.append(_gate("SCHEMA", schema_ok, "typed build and artifact contracts" if schema_ok else schema_detail))
    workspace_manifest = read_json(workspace / "workspace-manifest.json")
    current_freshness = build_freshness_contract(
        profile, profile_manifest, family, content["storyline"],
        canonical_revision=int(workspace_manifest["canonical_head"]["revision"]),
        compiler_version=COMPILER_VERSION,
        editorial_policy_version=content["public_display_policy"]["policy_id"],
        build_timestamp=build_record["created_at"], jd_snapshot=snapshot,
    )
    freshness = compare_freshness(build_record["canonical_evidence_freshness"], current_freshness)
    gates.append(_gate("CANONICAL_EVIDENCE_FRESHNESS", freshness["acceptance_allowed"], freshness["status"]))
    round_trip = ats_resume_round_trip(content, pdf_path)
    registry.validate("urn:careeros:schema:resume-header:v1", content["resume_header"])
    registry.validate("urn:careeros:schema:recruiter-summary:v1", content["recruiter_summary"])
    registry.validate("urn:careeros:schema:ats-resume-round-trip:v1", round_trip)
    registry.validate("urn:careeros:schema:resume-visual-density:v1", content["resume_visual_density"])
    registry.validate("urn:careeros:schema:premium-resume-quality:v1", content["premium_resume_quality"])
    for gate_name, passed in round_trip["gates"].items():
        gates.append(_gate(gate_name, bool(passed), round_trip["status"]))
    gates.append(_gate("ATS_CONFIDENCE", round_trip["status"] == "ATS_SAFE_HIGH_CONFIDENCE", round_trip["confidence"]))
    gates.append(_gate("SUMMARY_QUALITY", validate_recruiter_summary(content["recruiter_summary"])["status"] == "PASS", str(validate_recruiter_summary(content["recruiter_summary"]))))
    premium = content["premium_resume_quality"]
    density = content["resume_visual_density"]
    gates.append(_gate("PREMIUM_RESUME_QUALITY", premium["status"] == "PASS", f"score={premium['score']}; flags={premium['flags']}"))
    gates.append(_gate("RESUME_VISUAL_DENSITY", density["status"] == "PASS", f"utilization={density['measurements']['average_page_utilization']:.0%}"))
    utilization = content.get("new_evidence_utilization", {})
    gates.append(_gate("NEW_EVIDENCE_UTILIZATION", utilization.get("status") == "PASS", f"silent_high_value={len(utilization.get('high_value_silent_omissions', []))}"))
    history = professional_history_sufficiency(
        [item for item in profile.get("employment", []) if item.get("visibility") in EMPLOYER_USABLE_VISIBILITY], content["employment"],
    )
    gates.append(_gate("PROFESSIONAL_HISTORY_SUFFICIENCY", history["status"] == "PASS", str(history["failures"])))
    gates.append(_gate("EMPTY_EXPERIENCE_ENTRY", not any(item["code"] == "EMPTY_EXPERIENCE_ENTRY" for item in history["failures"]), "every displayed role has supported content"))
    evidence_ids = {item["record_id"] for item in profile["evidence"]}
    bullet_evidence = [rid for section in [*content["employment"], *content["projects"]] for bullet in section["bullets"] for rid in bullet["evidence_ids"]]
    gates.append(_gate("TRUTH", set(bullet_evidence) <= evidence_ids, "all bullets trace to canonical evidence"))
    gates.append(_gate("PROVENANCE", all(rid in build_record["selected_evidence_ids"] for rid in bullet_evidence), "selected evidence IDs recorded"))
    chronology_keys = [
        (item.get("end_year") is None or str(item.get("end_year")).upper() == "PRESENT", int(item.get("start_year") or 0))
        for item in content["employment"]
    ]
    gates.append(_gate("CHRONOLOGY", chronology_keys == sorted(chronology_keys, reverse=True), "current roles first, then newest start year"))
    displayed_ids = {item["record_id"] for item in content.get("display_credentials", [])}
    credential_ok = all(
        item["record_id"] not in displayed_ids
        or (item["credential_state"] in content["public_display_policy"]["credential_display"]["allowed_states"] and item["verification_state"] in content["public_display_policy"]["credential_display"]["allowed_verification_states"])
        for item in content["credentials"]
    )
    gates.append(_gate("CREDENTIAL_STATE", credential_ok, "public credential display follows explicit verification policy"))
    unsupported = [token for section in [*content["employment"], *content["projects"]] for bullet in section["bullets"] for token in bullet.get("unsupported_metric_tokens", [])]
    gates.append(_gate("UNSUPPORTED_METRIC", not unsupported, "numeric claims require canonical metric permission"))
    gates.append(_gate("TITLE_NORMALIZATION", all(item["display_title"] == item["actual_title"] for item in content["employment"]), "actual titles remain display authority"))
    required = {item["capability"].casefold() for item in opportunity["requirements"]}
    represented = {item["name"].casefold() for item in content["skills"]}
    gates.append(_gate("ROLE_RELEVANCE", bool(required & represented), "at least one evidenced required capability selected"))
    coverage = len(required & represented) / max(1, len(required))
    gates.append(_gate("JD_COVERAGE", coverage >= 0.5, f"{coverage:.0%} evidenced capability coverage"))
    reader = PdfReader(str(pdf_path))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    gates.append(_gate("ATS_TEXT_EXTRACTION", len(extracted) >= 200, f"{len(extracted)} extracted characters"))
    headings = [APPROVED_SECTION_NAMES["EXPERIENCE"], "EDUCATION"]
    positions = [extracted.find(item) for item in headings]
    gates.append(_gate("ATS_READING_ORDER", all(value >= 0 for value in positions) and positions == sorted(positions), "major sections extract in intended order"))
    candidate = profile["candidate"]
    autofill_values = [candidate["public_name"], candidate["contact"].get("email"), candidate["contact"].get("phone")]
    gates.append(_gate("AUTOFILL", all(not value or value in extracted for value in autofill_values), "name/email/phone recoverable"))
    base_fonts: list[str] = []
    for page in reader.pages:
        resources = page["/Resources"].get_object()
        font_resources = resources.get("/Font", {})
        if hasattr(font_resources, "get_object"):
            font_resources = font_resources.get_object()
        for font_ref in font_resources.values():
            font = font_ref.get_object()
            base_fonts.append(str(font.get("/BaseFont", "")))
    font_ok = bool(base_fonts) and all("Helvetica" in name for name in base_fonts)
    gates.append(_gate("FONT", font_ok, ", ".join(sorted(set(base_fonts)))))
    geometry_ok = all(abs(float(page.mediabox.width) - 612) < 1 and abs(float(page.mediabox.height) - 792) < 1 for page in reader.pages)
    gates.append(_gate("PAGE_GEOMETRY", geometry_ok and len(reader.pages) <= 2, f"letter pages={len(reader.pages)}"))
    gates.append(_gate("PDF_PREFLIGHT", pdf_path.read_bytes().startswith(b"%PDF") and bool(extracted.strip()), "valid PDF with selectable text"))
    visual_ok = True
    visual_detail = "structural PDF bounds pass; raster backend unavailable"
    render_paths: list[str] = []
    poppler = shutil.which("pdftoppm")
    with pdfplumber.open(pdf_path) as document:
        within = all(all(0 <= char["x0"] <= page.width and 0 <= char["x1"] <= page.width and 0 <= char["top"] <= page.height and 0 <= char["bottom"] <= page.height for char in page.chars) and len(page.chars) > 80 for page in document.pages)
        utilizations = [
            (max(char["bottom"] for char in page.chars) - min(char["top"] for char in page.chars)) / max(1.0, page.height - 72)
            for page in document.pages if page.chars
        ]
        actual_utilization = sum(utilizations) / max(1, len(utilizations))
    visual_ok = within
    if poppler:
        render_root = roots.output_root / "qa" / build_id
        render_root.mkdir(parents=True, exist_ok=True)
        prefix = render_root / "page"
        subprocess.run([poppler, "-png", "-r", "144", str(pdf_path), str(prefix)], check=True, capture_output=True)
        images = sorted(render_root.glob("page-*.png"))
        image_checks = []
        for image_path in images:
            with Image.open(image_path) as image:
                bbox = image.convert("L").point(lambda pixel: 0 if pixel > 250 else 255).getbbox()
                image_checks.append(bool(bbox) and bbox[0] > 20 and bbox[1] > 20 and bbox[2] < image.width - 20 and bbox[3] < image.height - 20)
            render_paths.append(str(image_path.relative_to(roots.output_root)))
        visual_ok = visual_ok and bool(images) and all(image_checks)
        visual_detail = f"{len(images)} raster page(s), bounded content, nonblank"
    gates.append(_gate("VISUAL", visual_ok, visual_detail))
    completeness = apply_actual_page_utilization(content.get("resume_completeness", {}), actual_utilization)
    gates.append(_gate(
        "UNDERFILLED_RESUME", not completeness["page_utilization"]["underfilled"],
        f"utilization={actual_utilization:.0%}; unused_relevant={completeness['page_utilization']['unused_relevant_count']}",
    ))
    gates.append(_gate("RESUME_COMPLETENESS", completeness.get("status") == "PASS", f"status={completeness.get('status')}"))
    expected_name = recruiter_safe_filename(candidate["public_name"], content["resume_header"]["positioning_headline"])
    filename_ok = pdf_path.suffix.lower() == ".pdf" and (pdf_path.name == expected_name or pdf_path.name.startswith(Path(expected_name).stem + " - "))
    gates.append(_gate("FILENAME", filename_ok, pdf_path.name))
    metadata = reader.metadata or {}
    metadata_ok = metadata.get("/Author") == candidate["public_name"] and metadata.get("/Title") == f"{candidate['public_name']} - {content['resume_header']['positioning_headline']} Resume" and metadata.get("/Subject") == "Resume"
    gates.append(_gate("PDF_METADATA", metadata_ok, "candidate-driven author and generic title"))
    hash_ok = sha256_file(pdf_path) == artifact["sha256"]
    gates.append(_gate("ARTIFACT_HASH_LINEAGE", hash_ok and artifact["build_id"] == build_id, artifact["sha256"]))
    editorial = content.get("editorial_quality", {})
    gates.append(_gate("EDITORIAL_QUALITY", editorial.get("status") == "PASS", f"score={editorial.get('score')} threshold={editorial.get('threshold')}"))
    gates.append(_gate("SYSTEM_ARTIFACT_LEAKAGE", not editorial.get("system_artifact_leaks"), ", ".join(editorial.get("system_artifact_leaks", [])) or "none"))
    label_leaks = public_label_leaks(extracted)
    gates.append(_gate("PUBLIC_ARTIFACT_NAMING", not label_leaks, ", ".join(label_leaks) or "public labels sanitized"))
    specificity = recruiter_copy_specificity(content, profile)
    gates.append(_gate("RECRUITER_COPY_SPECIFICITY", specificity["status"] == "PASS", ", ".join(specificity["abstract_phrases"]) or "specific copy"))
    boundary = content.get("public_copy_boundary_v1") or public_copy_boundary(content)
    copy_quality = content.get("recruiter_copy_quality_v2") or recruiter_copy_quality_v2(
        content, strategy=content.get("recruiter_conversion_strategy_v2"),
        employer_need_trace=content.get("employer_need_trace"),
    )
    editorial_regression = content.get("targeted_editorial_regression_v1", {})
    gates.append(_gate("PUBLIC_COPY_BOUNDARY", boundary.get("status") == "PASS", f"findings={boundary.get('finding_count', 0)}"))
    gates.append(_gate("RECRUITER_COPY_QUALITY_V2", copy_quality.get("status") == "PASS", f"score={copy_quality.get('score')}"))
    gates.append(_gate("TARGETED_EDITORIAL_REGRESSION", editorial_regression.get("status") == "PASS", str(editorial_regression.get("regressions", []))))
    delta = content.get("targeted_resume_delta", {"status": "NO_MEANINGFUL_DELTA", "acceptance_allowed": False})
    gates.append(_gate("TARGETED_RESUME_DELTA", bool(delta.get("acceptance_allowed")), str(delta.get("status"))))
    gates.append(_gate("SEMANTIC_DUPLICATION", editorial.get("semantic_duplicate_count", 0) == 0, f"count={editorial.get('semantic_duplicate_count', 0)}"))
    conversion = content.get("career_conversion_trace", {})
    for gate_name in (
        "EMPLOYER_NEED_TRACE", "TOP_THIRD_COVERAGE", "STRONGEST_EVIDENCE_OMISSION",
        "ROLE_FACT_PRESERVATION", "MATERIAL_EVIDENCE_LOSS", "CRITICAL_EVIDENCE_LOSS",
    ):
        gates.append(_gate(gate_name, bool(conversion.get("gates", {}).get(gate_name)), f"conversion_status={conversion.get('status', 'MISSING')}"))
    for gate_name, gate in content.get("job_specific_qa", {}).get("checks", {}).items():
        gates.append(_gate(gate_name, bool(gate.get("passed")), str(gate.get("detail", ""))))
    all_pass = all(item["status"] == "PASS" for item in gates)
    accepted_at = utc_now(build_record["created_at"])
    build_record["gate_state"] = "PASSED" if all_pass else "FAILED"
    artifact["status"] = "ACCEPTED" if all_pass else "REJECTED"
    artifact["accepted_at"] = accepted_at if all_pass else None
    manifest = {
        "schema": "careeros.artifact-manifest.v1", "schema_version": "1.0.0",
        "manifest_id": f"manifest:{uuid.uuid5(uuid.NAMESPACE_URL, build_id + ':' + artifact['sha256'])}",
        "build_id": build_id, "artifacts": [artifact], "lineage_hash": sha256_value({"build": build_record, "artifact": artifact}), "created_at": accepted_at,
    }
    registry.validate("urn:careeros:schema:artifact-manifest:v1", manifest)
    result = {"schema": "careeros.resume-validation.v1", "build_id": build_id, "status": "PASS" if all_pass else "FAIL", "gates": gates, "render_paths": render_paths}
    content["resume_completeness"] = completeness
    atomic_write_json(build_dir / "content.json", content)
    atomic_write_json(build_dir / "resume-completeness.json", completeness)
    atomic_write_json(build_dir / "build.json", build_record)
    atomic_write_json(build_dir / "artifact.json", artifact)
    atomic_write_json(build_dir / "artifact-manifest.json", manifest)
    atomic_write_json(build_dir / "validation.json", result)
    atomic_write_json(build_dir / "ats-resume-round-trip.json", round_trip)
    atomic_write_json(build_dir / "resume-visual-density.json", density)
    atomic_write_json(build_dir / "premium-resume-quality.json", premium)
    return result, manifest
