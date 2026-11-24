"""Adaptive resume completeness and anti-overcompression policy.

Completeness is evaluated independently from job relevance.  The policy never
adds facts; it checks whether enough already-public canonical evidence survived
selection to tell a credible professional-to-technical-to-target story.
"""

from __future__ import annotations

import uuid
from typing import Any

from careeros.core.io import sha256_value


PUBLIC_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}
POSITIVE_TIERS = {"ANCHOR", "SUPPORTING", "TRANSFERABLE_PROFESSIONAL", "FOUNDATIONAL"}
TECHNICAL_EVIDENCE_TYPES = {"PROJECT", "LAB", "COURSEWORK", "TRAINING"}


def _coverage(available: int, included: int, *, required: int = 0) -> dict[str, Any]:
    expected = min(available, required) if required else available
    ratio = 1.0 if expected == 0 else min(1.0, included / expected)
    return {
        "available": available,
        "included": included,
        "expected": expected,
        "ratio": round(ratio, 3),
        "status": "NOT_APPLICABLE" if available == 0 else ("PASS" if included >= expected else "REVIEW"),
    }


def _bullet_evidence(content: dict[str, Any]) -> set[str]:
    return {
        evidence_id
        for section in [*content.get("employment", []), *content.get("projects", [])]
        for bullet in section.get("bullets", [])
        for evidence_id in bullet.get("evidence_ids", [])
    }


def _normalized_reason(reason: str | None, tier: str) -> str:
    value = str(reason or "").upper()
    if "PRIVACY" in value or "RESTRICTED" in value:
        return "PRIVACY"
    if "REDUNDANT" in value:
        return "REDUNDANT"
    if "SPACE" in value or "LIMIT" in value:
        return "SPACE"
    if "QUALIFICATION" in value or "BOUNDARY" in value:
        return "QUALIFICATION_BOUNDARY"
    if "WEAK" in value:
        return "WEAK_EVIDENCE"
    if value in {"LOW_JOB_RELEVANCE", "LOW_ROLE_RELEVANCE", "LOW_PRIORITY"}:
        return "LOW_PRIORITY"
    if tier == "OPTIONAL":
        return "LOW_PRIORITY"
    return "OTHER"


def evaluate_resume_completeness(
    profile: dict[str, Any],
    content: dict[str, Any],
    omitted: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build ResumeCompletenessV1 from canonical availability and selected output."""
    rankings = {
        item["evidence_id"]: item.get("classification", "OPTIONAL")
        for item in content.get("storyline", {}).get("evidence_rankings", [])
    }
    selected_evidence = _bullet_evidence(content)
    selected_employment = {item["record_id"] for item in content.get("employment", [])}
    selected_projects = {item["record_id"] for item in content.get("projects", [])}
    selected_skills = {item["record_id"] for item in content.get("skills", [])}
    omitted_by_evidence: dict[str, str] = {}
    for item in omitted or []:
        for evidence_id in item.get("evidence_ids", []):
            omitted_by_evidence[evidence_id] = str(item.get("reason") or "OTHER")

    visible_evidence = {
        item["record_id"]: item
        for item in profile.get("evidence", [])
        if item.get("visibility") in PUBLIC_VISIBILITY
    }
    visible_employment = [
        item for item in profile.get("employment", [])
        if item.get("visibility") in PUBLIC_VISIBILITY
    ]
    project_candidates = [
        item for item in profile.get("projects", [])
        if item.get("visibility") in PUBLIC_VISIBILITY
        and any(rankings.get(eid) in POSITIVE_TIERS for eid in item.get("evidence_ids", []))
    ]
    technical_evidence = [
        item for item in visible_evidence.values()
        if item.get("project_ids") or str(item.get("evidence_type", "")).upper() in TECHNICAL_EVIDENCE_TYPES
    ]
    transferable_evidence = [item for item in visible_evidence.values() if item.get("employment_ids")]
    visible_education = [item for item in profile.get("education", []) if item.get("visibility") in PUBLIC_VISIBILITY]
    visible_credentials = [item for item in content.get("display_credentials", [])]
    visible_languages = [
        item for item in profile.get("skills", [])
        if item.get("visibility") in PUBLIC_VISIBILITY and str(item.get("category", "")).casefold() == "language"
    ]
    evidenced_skills = [
        item for item in profile.get("skills", [])
        if item.get("visibility") in PUBLIC_VISIBILITY
        and (item.get("evidence_ids") or str(item.get("category", "")).casefold() == "language")
    ]

    omitted_roles = [item["record_id"] for item in visible_employment if item["record_id"] not in selected_employment]
    employment_modes = {
        item["record_id"]: item.get("display_mode", "FULL" if item.get("bullets") else "MINIMAL")
        for item in content.get("employment", [])
    }
    tiers = list(rankings.values())
    anchors_selected = sum(1 for evidence_id in selected_evidence if rankings.get(evidence_id) == "ANCHOR")
    supporting_selected = sum(1 for evidence_id in selected_evidence if rankings.get(evidence_id) == "SUPPORTING")

    unused = []
    for evidence_id, evidence in visible_evidence.items():
        tier = rankings.get(evidence_id, "OPTIONAL")
        if evidence_id in selected_evidence or tier not in POSITIVE_TIERS:
            continue
        unused.append({
            "evidence_id": evidence_id,
            "evidence_tier": tier,
            "exclusion_reason": _normalized_reason(omitted_by_evidence.get(evidence_id), tier),
        })

    professional = _coverage(len(visible_employment), len(selected_employment), required=min(3, len(visible_employment)))
    represented_project_ids = {
        item["record_id"] for item in project_candidates
        if selected_evidence & set(item.get("evidence_ids", []))
    }
    projects = _coverage(
        len(project_candidates),
        len((selected_projects & {item["record_id"] for item in project_candidates}) | represented_project_ids),
        required=min(3, len(project_candidates)),
    )
    technical = _coverage(len(technical_evidence), len(selected_evidence & {item["record_id"] for item in technical_evidence}), required=min(3, len(technical_evidence)))
    transferable = _coverage(
        len(transferable_evidence),
        len(selected_evidence & {item["record_id"] for item in transferable_evidence}),
        required=min(2, len(transferable_evidence)),
    )
    education = _coverage(len(visible_education), len(content.get("display_education", [])), required=len(visible_education))
    credentials = _coverage(len(visible_credentials), len(content.get("display_credentials", [])), required=len(visible_credentials))
    languages = _coverage(len(visible_languages), len(selected_skills & {item["record_id"] for item in visible_languages}), required=len(visible_languages))
    skills = _coverage(len(evidenced_skills), len(selected_skills & {item["record_id"] for item in evidenced_skills}), required=min(6, len(evidenced_skills)))

    professional_foundation = bool(content.get("employment")) or not visible_employment
    technical_preparation = bool(selected_evidence & {item["record_id"] for item in technical_evidence}) or not technical_evidence
    target_direction = bool(content.get("target_role") and content.get("summary"))
    storyline = {
        "professional_foundation": professional_foundation,
        "technical_preparation": technical_preparation,
        "target_role_direction": target_direction,
        "status": "PASS" if professional_foundation and technical_preparation and target_direction else "FAIL",
    }

    content_units = (
        5
        + len(content.get("skill_groups", []))
        + sum(2 + len(item.get("bullets", [])) for item in content.get("employment", []))
        + sum(2 + len(item.get("bullets", [])) for item in content.get("projects", []))
        + len(content.get("display_education", []))
        + len(content.get("display_credentials", []))
    )
    estimated_underfilled = content_units < 18 and bool(unused)
    estimated_overfilled = content_units > 42
    page_utilization = {
        "estimated_content_units": content_units,
        "actual_utilization": None,
        "unused_relevant_count": len(unused),
        "underfilled": estimated_underfilled,
        "overfilled": estimated_overfilled,
        "status": "UNDERFILLED" if estimated_underfilled else ("OVERFILLED" if estimated_overfilled else "PASS"),
    }

    failures = [
        professional["status"] == "REVIEW",
        projects["status"] == "REVIEW",
        technical["status"] == "REVIEW",
        transferable["status"] == "REVIEW" and bool(transferable_evidence),
        languages["status"] == "REVIEW" and bool(visible_languages),
        storyline["status"] == "FAIL",
        estimated_underfilled,
    ]
    reviews = [estimated_overfilled, skills["status"] == "REVIEW", bool(omitted_roles)]
    status = "FAIL" if any(failures) else ("REVIEW" if any(reviews) else "PASS")
    result = {
        "schema": "careeros.resume-completeness.v1",
        "schema_version": "1.0.0",
        "completeness_id": "resume-completeness:" + str(uuid.uuid5(uuid.NAMESPACE_URL, sha256_value({"profile": profile.get("profile_id"), "target": content.get("target_role"), "selected": sorted(selected_evidence)}))),
        "professional_history_coverage": {**professional, "display_modes": employment_modes},
        "career_continuity": {"status": "PASS" if not omitted_roles else "REVIEW", "omitted_material_records": omitted_roles},
        "anchor_evidence_count": {"available": tiers.count("ANCHOR"), "included": anchors_selected},
        "supporting_evidence_count": {"available": tiers.count("SUPPORTING"), "included": supporting_selected},
        "technical_project_coverage": projects,
        "transferable_evidence_coverage": transferable,
        "education_coverage": education,
        "credential_coverage": credentials,
        "language_coverage": languages,
        "skills_coverage": skills,
        "storyline_continuity": storyline,
        "target_role_coverage": {"status": "PASS" if target_direction else "FAIL", "target_role": content.get("target_role")},
        "page_utilization": page_utilization,
        "unused_supported_evidence": unused,
        "status": status,
    }
    return result


def apply_actual_page_utilization(completeness: dict[str, Any], utilization: float) -> dict[str, Any]:
    """Attach renderer evidence without changing the pre-render selection audit."""
    result = dict(completeness)
    page = dict(result["page_utilization"])
    page["actual_utilization"] = round(utilization, 3)
    page["underfilled"] = utilization < 0.62 and page["unused_relevant_count"] > 0
    page["status"] = "UNDERFILLED" if page["underfilled"] else ("OVERFILLED" if page.get("overfilled") else "PASS")
    result["page_utilization"] = page
    if page["underfilled"]:
        result["status"] = "FAIL"
    return result
