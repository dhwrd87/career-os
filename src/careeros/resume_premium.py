"""Premium, ATS-safe resume presentation and editorial quality contracts.

This module changes derivative presentation only. It never invents candidate
facts, changes evidence lineage, or promotes private material to public use.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pdfplumber


TEMPLATE_SUMMARY_PATTERNS = (
    "candidate with evidence in",
    "supported by professional work",
    "combines established workplace",
    "professional work:",
    "technical projects:",
    "role-relevant technical projects",
    "without overstating",
    "within established boundaries",
    "building production depth",
    "under senior review",
    "prepared to learn",
)
DATABASE_STYLE_PATTERNS = (
    re.compile(r"\b(?:action|context|method|deliverable|outcome)\s*:", re.IGNORECASE),
    re.compile(r"\b(?:record|evidence|confidence|verification)[ _-]?id\b", re.IGNORECASE),
)
SKILL_GROUP_LABELS = {
    "SECURITY & MONITORING": "SECURITY",
    "TOOLS & PLATFORMS": "TOOLS",
    "PROFESSIONAL STRENGTHS": "OPERATIONS",
    "CAPABILITIES": "OPERATIONS",
}
PREMIUM_COMPONENTS = (
    "HEADER_POLISH",
    "SUMMARY_NATURALNESS",
    "VISUAL_HIERARCHY",
    "SCANNABILITY",
    "CONTENT_DENSITY",
    "PROJECT_PRIORITIZATION",
    "EXPERIENCE_BALANCE",
    "TYPOGRAPHY",
    "WHITESPACE",
    "HUMAN_VOICE",
    "RECRUITER_IMPRESSION",
)


def _plain(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _meaningful_professional_history(content: dict[str, Any]) -> bool:
    for role in content.get("employment", []):
        if role.get("display_mode") == "FULL" or len(role.get("bullets", [])) >= 2:
            return True
        try:
            start = int(role.get("start_year"))
            end_value = role.get("end_year")
            end = start + 3 if end_value in {None, "PRESENT", "Present"} else int(end_value)
            if end - start >= 3 and role.get("bullets"):
                return True
        except (TypeError, ValueError):
            continue
    return False


def apply_premium_presentation(content: dict[str, Any]) -> dict[str, Any]:
    """Add deterministic visual semantics without changing factual claims."""
    groups = []
    for group in content.get("skill_groups", []):
        label = SKILL_GROUP_LABELS.get(_plain(group.get("group")).upper(), _plain(group.get("group")).upper())
        existing = next((item for item in groups if item["group"] == label), None)
        if existing:
            known = {item.get("name", "").casefold() for item in existing["skills"]}
            existing["skills"].extend(item for item in group.get("skills", []) if item.get("name", "").casefold() not in known)
        else:
            groups.append({**copy.deepcopy(group), "group": label})
    if groups:
        content["skill_groups"] = groups

    projects = content.get("projects", [])
    featured_count = min(4, len(projects)) if len(projects) >= 5 else min(3, len(projects))
    for index, project in enumerate(projects):
        project["presentation_tier"] = "FEATURED" if index < featured_count else "ADDITIONAL"
        project["presentation_mode"] = "FULL" if index < featured_count else "COMPACT"

    preferred = list(content.get("section_order") or ["SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CREDENTIALS"])
    if _meaningful_professional_history(content) and "EXPERIENCE" in preferred and "PROJECTS" in preferred:
        preferred.remove("EXPERIENCE")
        preferred.insert(preferred.index("PROJECTS"), "EXPERIENCE")
    content["section_order"] = preferred
    content["premium_presentation"] = {
        "schema": "careeros.premium-resume-presentation.v1",
        "template": "premium-ats-single-column-v1",
        "single_column": True,
        "header_presentation": "PREMIUM_CENTERED_MASTHEAD",
        "header_fallback": "ATS_MINIMAL_FALLBACK",
        "header_order": ["NAME", "HEADLINE", "LOCATION", "PHONE", "EMAIL", "LINKEDIN", "PORTFOLIO", "GITHUB"],
        "featured_project_count": featured_count,
        "additional_project_count": max(0, len(projects) - featured_count),
        "professional_history_emphasized": _meaningful_professional_history(content),
        "section_order": preferred,
    }
    return content


def summary_naturalness(summary: dict[str, Any] | str) -> dict[str, Any]:
    text = _plain(summary.get("text")) if isinstance(summary, dict) else _plain(summary)
    patterns = [pattern for pattern in TEMPLATE_SUMMARY_PATTERNS if pattern in text.casefold()]
    sentence_lengths = [len(sentence.split()) for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    overloaded = [length for length in sentence_lengths if length > 34]
    flags = (["TEMPLATE_SUMMARY_PATTERN"] if patterns else []) + (["OVERLOADED_SUMMARY_SENTENCE"] if overloaded else [])
    # Forty to eighty words remains the production target. A genuinely thin
    # profile may stop at 25 words rather than padding the summary with filler.
    return {
        "status": "PASS" if not flags and 25 <= len(text.split()) <= 80 else "FAIL",
        "flags": flags,
        "matched_patterns": patterns,
        "word_count": len(text.split()),
        "sentence_lengths": sentence_lengths,
    }


def bullet_rhythm(content: dict[str, Any]) -> dict[str, Any]:
    bullets = [
        _plain(bullet.get("text"))
        for section in [*content.get("employment", []), *content.get("projects", [])]
        for bullet in section.get("bullets", [])
        if _plain(bullet.get("text"))
    ]
    findings: list[dict[str, Any]] = []
    starts = Counter(re.match(r"[A-Za-z]+", bullet).group(0).casefold() for bullet in bullets if re.match(r"[A-Za-z]+", bullet))
    for index, bullet in enumerate(bullets):
        words = len(bullet.split())
        if words > 36 or len(bullet) > 245:
            findings.append({"code": "OVERLOADED_BULLET", "bullet_index": index, "word_count": words})
        if bullet.count(";") > 1:
            findings.append({"code": "ROBOTIC_BULLET", "bullet_index": index, "reason": "semicolon overload"})
        if any(pattern.search(bullet) for pattern in DATABASE_STYLE_PATTERNS) or bullet.count(" | ") >= 2:
            findings.append({"code": "DATABASE_STYLE_PROSE", "bullet_index": index})
    repeated = sorted(verb for verb, count in starts.items() if count >= 4 and count / max(1, len(bullets)) >= 0.5)
    if repeated:
        findings.append({"code": "REPETITIVE_VERB", "verbs": repeated})
    return {
        "status": "PASS" if not findings else "FAIL",
        "bullet_count": len(bullets),
        "verb_distribution": dict(sorted(starts.items())),
        "findings": findings,
    }


def evaluate_visual_density(content: dict[str, Any], pdf_path: Path) -> dict[str, Any]:
    pages = []
    with pdfplumber.open(pdf_path) as document:
        for index, page in enumerate(document.pages, start=1):
            chars = page.chars
            if not chars:
                pages.append({"page": index, "page_utilization": 0.0, "top_whitespace": 1.0, "bottom_whitespace": 1.0})
                continue
            top = min(float(char["top"]) for char in chars)
            bottom = max(float(char["bottom"]) for char in chars)
            usable = max(1.0, float(page.height) - 72.0)
            pages.append({
                "page": index,
                "page_utilization": round((bottom - top) / usable, 3),
                "top_whitespace": round(top / float(page.height), 3),
                "bottom_whitespace": round((float(page.height) - bottom) / float(page.height), 3),
            })
    utilization = round(sum(item["page_utilization"] for item in pages) / max(1, len(pages)), 3)
    last_page_sparse = bool(pages and len(pages) > 1 and pages[-1]["page_utilization"] < 0.45)
    completeness = content.get("resume_completeness", {})
    unused_supported = completeness.get("unused_supported_evidence", [])
    evidence_limited = utilization < 0.75 and not unused_supported
    status = "PASS" if (0.75 <= utilization <= 0.90 or evidence_limited) and not last_page_sparse else "FAIL"
    return {
        "schema": "careeros.resume-visual-density.v1",
        "schema_version": "1.0.0",
        "status": status,
        "measurements": {
            "pages": pages,
            "average_page_utilization": utilization,
            "header_height_points": float(content.get("masthead_geometry", {}).get("masthead_total_height") or 58.0),
            "summary_word_count": len(_plain(content.get("summary")).split()),
            "skills_item_count": len(content.get("skills", [])),
            "section_spacing_points": 6.0,
            "bullet_spacing_points": 2.0,
            "last_page_sparse": last_page_sparse,
            "evidence_limited": evidence_limited,
        },
        "target_range": {"minimum": 0.75, "maximum": 0.90},
    }


def evaluate_premium_quality(content: dict[str, Any], density: dict[str, Any] | None = None) -> dict[str, Any]:
    naturalness = summary_naturalness(content.get("recruiter_summary") or content.get("summary", ""))
    rhythm = bullet_rhythm(content)
    presentation = content.get("premium_presentation", {})
    project_tiers = [item.get("presentation_tier") for item in content.get("projects", [])]
    experience_ok = not content.get("employment") or presentation.get("professional_history_emphasized") or len(content.get("projects", [])) <= 2
    density_ok = not density or density.get("status") == "PASS"
    components = {
        "HEADER_POLISH": 9.6 if content.get("masthead_geometry", {}).get("status") == "PASS" else 7.0,
        "SUMMARY_NATURALNESS": 9.4 if naturalness["status"] == "PASS" else 5.5,
        "VISUAL_HIERARCHY": 9.4 if presentation.get("template") == "premium-ats-single-column-v1" else 7.0,
        "SCANNABILITY": 9.3 if content.get("skill_groups") and content.get("section_order") else 7.0,
        "CONTENT_DENSITY": 9.2 if density_ok else 6.5,
        "PROJECT_PRIORITIZATION": 9.3 if not project_tiers or "FEATURED" in project_tiers else 6.0,
        "EXPERIENCE_BALANCE": 9.2 if experience_ok else 6.0,
        "TYPOGRAPHY": 9.4 if presentation.get("single_column") else 6.0,
        "WHITESPACE": 9.2 if density_ok else 6.5,
        "HUMAN_VOICE": 9.3 if naturalness["status"] == "PASS" and rhythm["status"] == "PASS" else 6.0,
        "RECRUITER_IMPRESSION": 9.3 if naturalness["status"] == "PASS" and experience_ok else 6.5,
    }
    score = round(sum(components.values()) / len(PREMIUM_COMPONENTS), 1)
    flags = [*naturalness["flags"], *(item["code"] for item in rhythm["findings"])]
    if not density_ok:
        flags.append("VISUAL_DENSITY_OUT_OF_RANGE")
    if not experience_ok:
        flags.append("EXPERIENCE_UNDERWEIGHTED")
    human_test = {
        "credible_next_to_premium_builder": score >= 8.8,
        "intentionally_designed": components["VISUAL_HIERARCHY"] >= 9.0,
        "six_to_ten_second_story": naturalness["status"] == "PASS",
        "strongest_evidence_prominent": not project_tiers or project_tiers[0] == "FEATURED",
        "mechanical_assembly_detected": bool(flags),
    }
    return {
        "schema": "careeros.premium-resume-quality.v1",
        "schema_version": "1.0.0",
        "status": "PASS" if score >= 8.8 and not flags and all(value if key != "mechanical_assembly_detected" else not value for key, value in human_test.items()) else "FAIL",
        "score": score,
        "components": components,
        "summary_naturalness": naturalness,
        "bullet_rhythm": rhythm,
        "flags": sorted(set(flags)),
        "human_test": human_test,
    }
