"""Evidence-bound recruiter conversion copy for public resume artifacts.

This module deliberately separates internal truth/qualification reasoning from
public writing.  It may select, order, and phrase already-supported facts; it
never widens an evidence boundary or promotes a private fact.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable


PUBLIC_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}
SUMMARY_ARCHETYPES = {"EVIDENCE_FIRST", "PROFESSIONAL_TRANSITION", "ROLE_FIRST", "DIFFERENTIATOR_FIRST"}
PUBLIC_SYSTEM_PHRASES = (
    "candidate with evidence in", "supported by professional work", "role-relevant technical projects",
    "combines established workplace", "without overstating", "within established boundaries",
    "building production depth", "under senior review", "prepared to learn", "still developing",
    "does not yet have", "equivalent experience", "project work is not professional experience",
    "qualification", "canonical", "evidence boundary", "public-use", "governance", "verified evidence",
)
INTERNAL_STATE_PHRASES = (
    "hard gap", "unknown state", "unsupported evidence", "professional-equivalence warning",
    "claim boundary", "verification status", "needs verification", "review required",
)
WEAK_FUTURE_PHRASES = (
    "ready to", "prepared to", "hoping to", "seeking to learn", "building toward",
    "developing toward", "will learn", "can learn", "prepared to support",
)
AI_SLOP_PHRASES = (
    "leveraging", "dynamic professional", "results-driven", "passionate", "proven track record",
    "professional foundation", "practical preparation", "disciplined operations",
)
GENERIC_ABSTRACTIONS = (
    "technical preparation", "security exposure", "practical experience",
    "communication and documentation", "operational discipline",
)
CONFIDENT_VERBS = {
    "analyzed", "built", "coordinated", "created", "debugged", "delivered", "documented",
    "implemented", "investigated", "maintained", "performed", "produced", "resolved",
    "reviewed", "supported", "translated", "used", "validated",
}
QUALITY_DIMENSIONS = (
    "POSITIONING", "SPECIFICITY", "PROFESSIONAL_CONFIDENCE", "EMPLOYER_RELEVANCE",
    "CAREER_STORY", "HUMAN_VOICE", "CONCISION", "EVIDENCE_DENSITY", "DIFFERENTIATION",
    "READABILITY", "PERSUASIVENESS", "SYSTEM_LANGUAGE_ABSENCE",
)


def _plain(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("value", "text", "label", "name"):
            if value.get(key) not in {None, ""}:
                return _plain(value[key])
        return ""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _sentence(value: Any) -> str:
    text = _plain(value).strip(" .;:")
    if not text:
        return ""
    return text[0].upper() + text[1:] + "."


def _lower_first(value: Any) -> str:
    text = _plain(value).strip(" .;:")
    return text[:1].lower() + text[1:] if text else ""


def _public_evidence(profile: dict[str, Any], selected_evidence_ids: set[str] | None = None) -> list[dict[str, Any]]:
    selected = selected_evidence_ids or set()
    return [
        item for item in profile.get("evidence", [])
        if item.get("visibility") in PUBLIC_VISIBILITY
        and (not selected or item.get("record_id") in selected)
    ]


def _evidence_phrase(evidence: dict[str, Any]) -> str:
    actions = [_plain(item) for item in evidence.get("actions", []) if _plain(item)]
    methods = [_plain(item) for item in evidence.get("tools_methods", []) if _plain(item)]
    outcomes = [_plain(item) for item in evidence.get("outcomes", []) if _plain(item)]
    deliverables = [_plain(item) for item in evidence.get("deliverables", []) if _plain(item)]
    action = actions[0] if actions else ""
    # Intake can split a verb from its object. Prefer the retained source
    # sentence over emitting an orphan verb such as "Supported".
    source_summary = _plain(evidence.get("summary")).rstrip(".")
    if action and len(action.split()) <= 2 and source_summary.casefold().startswith(action.casefold() + " "):
        action = source_summary
    if action and methods and methods[0].casefold() not in action.casefold():
        action = f"{action} using {methods[0]}"
    if action and outcomes:
        outcome = re.sub(r"^(?:candidate|portfolio) reports?\s+", "", outcomes[0], flags=re.IGNORECASE)
        stop = {'a', 'an', 'the', 'and', 'with'}
        outcome_words = set(re.findall(r'[a-z0-9]+', outcome.casefold())) - stop
        action_words = set(re.findall(r'[a-z0-9]+', action.casefold())) - stop
        if outcome_words and outcome_words <= action_words:
            return action
        return f"{action}; {_lower_first(outcome)}"
    if action and deliverables:
        return f"{action} to produce {_lower_first(deliverables[0])}"
    if action:
        return action
    summary = re.sub(r"^(?:candidate|portfolio) reports?\s+", "", _plain(evidence.get("summary")), flags=re.IGNORECASE)
    return summary


def _top_need_rows(trace: dict[str, Any] | None) -> list[dict[str, Any]]:
    importance = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    rows = list((trace or {}).get("needs", []))
    rows.sort(key=lambda item: (
        0 if item.get("top_third_signal") == "TOP_THIRD" else 1,
        importance.get(item.get("importance"), 4),
        -int(item.get("frequency") or 0),
        item.get("need_id", ""),
    ))
    return rows[:3]


def _supported_skills(profile: dict[str, Any], selected: set[str]) -> list[dict[str, Any]]:
    return [
        item for item in profile.get("skills", [])
        if item.get("visibility") in PUBLIC_VISIBILITY
        and item.get("evidence_ids")
        and (not selected or set(item.get("evidence_ids", [])) & selected)
    ]


def _differentiator(profile: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    languages = [
        _plain(item.get("name")) for item in profile.get("skills", [])
        if item.get("visibility") in PUBLIC_VISIBILITY
        and _plain(item.get("category")).casefold() == "language"
    ]
    if len(languages) >= 2:
        ids = [item.get("record_id") for item in profile.get("skills", []) if _plain(item.get("name")) in languages[:2]]
        return f"bilingual {'/'.join(languages[:2])} communication", [item for item in ids if item]
    professional = [item for item in evidence if item.get("employment_ids")]
    if professional:
        phrase = _evidence_phrase(professional[0])
        return (phrase[:1].lower() + phrase[1:] if phrase else None), [professional[0]["record_id"]]
    return None, []


def build_recruiter_conversion_strategy(
    profile: dict[str, Any], role_family: dict[str, Any], *, opportunity: dict[str, Any] | None = None,
    employer_need_trace: dict[str, Any] | None = None, selected_evidence_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Build internal persuasive strategy without adding public claims."""
    selected = set(selected_evidence_ids)
    evidence = _public_evidence(profile, selected)
    professional = [item for item in evidence if item.get("employment_ids")]
    technical = [item for item in evidence if item.get("project_ids") or item.get("tools_methods")]
    needs = _top_need_rows(employer_need_trace)
    need_ids = {evidence_id for item in needs for evidence_id in item.get("candidate_evidence_ids", [])}
    technical.sort(key=lambda item: (0 if item.get("record_id") in need_ids else 1, item.get("record_id", "")))
    proof = [item for item in technical if _evidence_phrase(item)][:3]
    credibility = [item for item in professional if _evidence_phrase(item)][:3]
    differentiator, differentiator_sources = _differentiator(profile, evidence)
    target = _plain((opportunity or {}).get("role_title") or role_family.get("display_name") or role_family.get("label") or "target role")
    if differentiator and professional and technical:
        archetype = "DIFFERENTIATOR_FIRST"
    elif professional and technical:
        archetype = "PROFESSIONAL_TRANSITION"
    elif len(technical) >= 2:
        archetype = "EVIDENCE_FIRST"
    else:
        archetype = "ROLE_FIRST"
    top_signals = [_evidence_phrase(item) for item in proof]
    professional_signals = [_evidence_phrase(item) for item in credibility]
    positioning = (
        f"Established professional moving into {target} with specific technical proof"
        if professional and technical else f"Evidence-led positioning for {target}"
    )
    takeaway_parts = [positioning.rstrip(".")]
    if top_signals:
        takeaway_parts.append(f"anchored by {top_signals[0]}")
    if differentiator:
        takeaway_parts.append(f"and differentiated by {differentiator}")
    internal_risks = [
        _plain(item) for item in (
            role_family.get("common_gaps", [])
            or (opportunity or {}).get("hard_gaps", [])
            or []
        ) if _plain(item)
    ]
    return {
        "schema": "careeros.recruiter-conversion-strategy.v2", "schema_version": "2.0.0",
        "target_role": target, "candidate_positioning": positioning,
        "career_transition_narrative": "Connect established professional strengths to current technical proof; express limits through claim context, not public disclaimers.",
        "top_employer_needs": [
            {"need_id": item.get("need_id"), "need_statement": _plain(item.get("need_statement")), "importance": item.get("importance", "UNKNOWN")}
            for item in needs
        ],
        "top_candidate_proof_points": [
            {"evidence_id": item["record_id"], "proof": _evidence_phrase(item)} for item in proof
        ],
        "strongest_professional_credibility_signals": professional_signals,
        "strongest_technical_signals": top_signals,
        "key_differentiator": differentiator,
        "key_differentiator_source_ids": differentiator_sources,
        "internal_risks_gaps": internal_risks,
        "desired_recruiter_takeaway": "; ".join(takeaway_parts) + ".",
        "summary_archetype": archetype,
    }


def _summary_clause(text: str, evidence_ids: Iterable[str] = (), *, config_source: str | None = None, job_relevance: str = "LANE") -> dict[str, Any]:
    return {
        "summary_clause": _sentence(text), "source_evidence_ids": sorted(set(evidence_ids)),
        "approved_config_source": config_source, "verification": "SOURCE_BOUND" if list(evidence_ids) else "APPROVED_CONFIG",
        "public_use": True, "job_relevance": job_relevance,
    }


def _skill_phrase(profile: dict[str, Any], selected: set[str], role_family: dict[str, Any]) -> tuple[str, list[str]]:
    skills = _supported_skills(profile, selected)
    core = [_plain(item) for item in role_family.get("core_capabilities", [])]
    names = [_plain(item.get("name")) for item in skills]
    ordered = [item for item in core if item.casefold() in {name.casefold() for name in names}]
    ordered.extend(item for item in names if item.casefold() not in {name.casefold() for name in ordered})
    ordered = list(dict.fromkeys(item for item in ordered if item))[:4]
    source_ids = [evidence_id for skill in skills if _plain(skill.get("name")) in ordered for evidence_id in skill.get("evidence_ids", [])]
    if not ordered:
        return "documented technical projects", source_ids
    if len(ordered) == 1:
        return ordered[0], source_ids
    if len(ordered) == 2:
        return f"{ordered[0]} and {ordered[1]}", source_ids
    return f"{', '.join(ordered[:-1])}, and {ordered[-1]}", source_ids


def build_recruiter_summary_v2(
    profile: dict[str, Any], storyline: dict[str, Any], role_family: dict[str, Any], *,
    opportunity: dict[str, Any] | None = None, selected_evidence_ids: set[str] | None = None,
    employer_need_trace: dict[str, Any] | None = None, strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render natural public prose whose substantive clauses remain traced."""
    selected = selected_evidence_ids or {
        item.get("evidence_id") for item in storyline.get("evidence_rankings", [])
        if item.get("classification") in {"ANCHOR", "SUPPORTING", "CONTEXT", "TRANSFERABLE_PROFESSIONAL", "FOUNDATIONAL"}
    }
    selected.discard(None)
    strategy = strategy or build_recruiter_conversion_strategy(
        profile, role_family, opportunity=opportunity, employer_need_trace=employer_need_trace,
        selected_evidence_ids=selected,
    )
    target = strategy["target_role"]
    evidence = {item["record_id"]: item for item in _public_evidence(profile, selected)}
    professional_ids = [item["record_id"] for item in evidence.values() if item.get("employment_ids") and _evidence_phrase(item)]
    proof_rows = strategy["top_candidate_proof_points"]
    proof_ids = [item["evidence_id"] for item in proof_rows if item["evidence_id"] in evidence]
    proof_phrases = [item["proof"].strip(" .") for item in proof_rows if item.get("proof")]
    skill_phrase, skill_ids = _skill_phrase(profile, selected, role_family)
    differentiator = strategy.get("key_differentiator")
    archetype = strategy["summary_archetype"]
    relevance = "JOB" if opportunity else "LANE"
    clauses: list[dict[str, Any]] = []

    has_projects = any(item.get('project_ids') for item in evidence.values())
    work_context = 'project work' if has_projects else 'work'
    if differentiator and differentiator.casefold().startswith('bilingual '):
        intro = f"Offers {differentiator} and hands-on {skill_phrase} {work_context} for {target} roles"
    elif archetype == 'PROFESSIONAL_TRANSITION':
        intro = f"Moving into {target} roles with hands-on {skill_phrase} {work_context}"
    else:
        intro = f"Brings hands-on {skill_phrase} {work_context} to {target} roles"
    clauses.append(_summary_clause(intro, skill_ids, config_source='RoleFamilyV1', job_relevance=relevance))

    # Keep a concrete professional bridge and a distinct project example.
    # Action predicates are sentences, never noun phrases after "adds" or
    # "strengthens". Each remains bound to its original evidence record.
    if professional_ids:
        item = evidence[professional_ids[0]]
        role = next((r for r in profile.get('employment', []) if r.get('record_id') in item.get('employment_ids', []) and r.get('actual_title') and r.get('employer')), None)
        if role:
            clauses.append(_summary_clause(f"Professional experience includes {role['actual_title']} work at {role['employer']}", [item['record_id']], job_relevance=relevance))
            clauses.append(_summary_clause(_evidence_phrase(item), [item['record_id']], job_relevance=relevance))
        else:
            clauses.append(_summary_clause('Professional experience includes the following: ' + _evidence_phrase(item), [item['record_id']], job_relevance=relevance))
    for row in proof_rows:
        if row['evidence_id'] in professional_ids or not row.get('proof'):
            continue
        clauses.append(_summary_clause(row['proof'], [row['evidence_id']], job_relevance=relevance))
        if len(clauses) >= 5:
            break
    schedules = profile.get('preferences', {}).get('schedule_preferences', [])
    shift = _plain((opportunity or {}).get('shift_schedule'))
    if shift and any(_plain(item).casefold().replace('_', ' ') in shift.casefold().replace('_', ' ') for item in schedules):
        clauses.append(_summary_clause(f"Available for {shift}", config_source='CareerProfileV1.preferences.schedule_preferences', job_relevance='JOB'))
    seen_sentences: set[str] = set()
    for clause in clauses:
        retained = []
        for sentence in re.split(r'(?<=[.!?])\s+', clause['summary_clause']):
            signature = _plain(sentence).casefold()
            if signature and signature not in seen_sentences:
                retained.append(sentence)
                seen_sentences.add(signature)
        clause['summary_clause'] = ' '.join(retained)
    clauses = [c for c in clauses if c['summary_clause']]
    text = ' '.join(item['summary_clause'] for item in clauses)
    while len(text.split()) > 80 and len(clauses) > 2:
        clauses.pop()
        text = ' '.join(item['summary_clause'] for item in clauses)
    return {
        "schema": "careeros.recruiter-summary.v1", "schema_version": "1.0.0",
        "candidate_identity": profile.get("profile_id"),
        "target_role_family": role_family.get("role_family_id") or role_family.get("family_id"),
        "text": text, "word_count": len(text.split()),
        "summary_type": "TARGETED" if opportunity else "LANE", "clauses": clauses,
        "career_transition_boundary": bool(professional_ids and proof_ids),
        "job_specific_emphasis": target if opportunity else None,
    }


def render_recruiter_bullet_v2(candidate: dict[str, Any]) -> dict[str, Any]:
    """Improve rhythm while preserving the candidate's evidence and metrics."""
    output = dict(candidate)
    action = _plain(candidate.get("action")).strip(" .;:")
    method = _plain(candidate.get("tool_or_method")).strip(" .;:")
    outcome = _plain(candidate.get("outcome") or candidate.get("deliverable")).strip(" .;:")
    context = _plain(candidate.get("role_context")).strip(" .;:")
    if not action:
        return output
    text = action
    if method and method.casefold() not in text.casefold():
        text += f" using {method}"
    if context and len(context.split()) <= 8 and context.casefold() not in text.casefold():
        text += f" in {context[0].lower() + context[1:]}"
    if outcome and outcome.casefold() not in text.casefold():
        connector = ", producing " if not re.match(r"^(?:produced|created|delivered|supported|validated|completed)\b", outcome, re.I) else "; "
        text += connector + _lower_first(outcome)
    output["text"] = _sentence(text)
    output["copy_engine"] = "RECRUITER_CONVERSION_V2"
    return output


def public_copy_boundary(content: dict[str, Any]) -> dict[str, Any]:
    surfaces = {"summary": _plain(content.get("summary")), "headline": _plain(content.get("resume_header", {}).get("positioning_headline"))}
    for section_name in ("employment", "projects"):
        for section_index, section in enumerate(content.get(section_name, [])):
            for bullet_index, bullet in enumerate(section.get("bullets", [])):
                surfaces[f"{section_name}[{section_index}].bullets[{bullet_index}]"] = _plain(bullet.get("text"))
    findings = []
    for surface, text in surfaces.items():
        lowered = text.casefold()
        for code, terms in (
            ("SYSTEM_LANGUAGE", PUBLIC_SYSTEM_PHRASES), ("INTERNAL_STATE", INTERNAL_STATE_PHRASES),
            ("WEAK_FUTURE_TENSE", WEAK_FUTURE_PHRASES), ("AI_SLOP", AI_SLOP_PHRASES),
        ):
            for term in terms:
                if term in lowered:
                    findings.append({"code": code, "term": term, "surface": surface})
    return {
        "schema": "careeros.public-copy-boundary.v1", "schema_version": "1.0.0",
        "status": "FAIL" if findings else "PASS", "checked_surfaces": sorted(surfaces),
        "findings": findings, "finding_count": len(findings),
    }


def jd_paraphrase_findings(content: dict[str, Any], employer_need_trace: dict[str, Any] | None = None) -> list[dict[str, str]]:
    public_text = " ".join([
        _plain(content.get("summary")),
        *[_plain(bullet.get("text")) for section in [*content.get("employment", []), *content.get("projects", [])] for bullet in section.get("bullets", [])],
    ]).casefold()
    findings = []
    for need in (employer_need_trace or {}).get("needs", []):
        words = _plain(need.get("need_statement")).casefold().split()
        if len(words) >= 8 and " ".join(words[:8]) in public_text:
            findings.append({"need_id": _plain(need.get("need_id")), "matched_phrase": " ".join(words[:8])})
    return findings


def natural_language_variation(content: dict[str, Any]) -> dict[str, Any]:
    summary = _plain(content.get("summary"))
    sentences = [item for item in re.split(r"(?<=[.!?])\s+", summary) if item]
    starts = [re.match(r"[A-Za-z]+", item).group(0).casefold() for item in sentences if re.match(r"[A-Za-z]+", item)]
    bullet_starts = [
        re.match(r"[A-Za-z]+", _plain(bullet.get("text"))).group(0).casefold()
        for section in [*content.get("employment", []), *content.get("projects", [])]
        for bullet in section.get("bullets", []) if re.match(r"[A-Za-z]+", _plain(bullet.get("text")))
    ]
    repeated_summary = [item for item, count in Counter(starts).items() if count > 1]
    repeated_bullets = [item for item, count in Counter(bullet_starts).items() if count >= 4 and count / max(1, len(bullet_starts)) >= 0.5]
    flags = (["REPEATED_SENTENCE_START"] if repeated_summary else []) + (["TEMPLATE_COPY_PATTERN"] if repeated_bullets else [])
    return {"status": "FAIL" if flags else "PASS", "flags": flags, "summary_starts": starts, "repeated_bullet_verbs": repeated_bullets}


def recruiter_copy_quality_v2(
    content: dict[str, Any], *, strategy: dict[str, Any] | None = None,
    employer_need_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    boundary = public_copy_boundary(content)
    variation = natural_language_variation(content)
    summary = _plain(content.get("summary"))
    words = summary.split()
    sentences = [item for item in re.split(r"(?<=[.!?])\s+", summary) if item]
    bullets = [
        bullet for section in [*content.get("employment", []), *content.get("projects", [])]
        for bullet in section.get("bullets", []) if _plain(bullet.get("text"))
    ]
    public_text = " ".join([summary, *[_plain(item.get("text")) for item in bullets]])
    lowered = public_text.casefold()
    traces_complete = all(item.get("evidence_ids") for item in bullets) and all(
        item.get("source_evidence_ids") or item.get("approved_config_source")
        for item in content.get("recruiter_summary", {}).get("clauses", [])
    )
    concrete = sum(1 for token in re.findall(r"\b[A-Z][A-Za-z0-9+/#.-]*\b|\b\d+[+%]?\b", public_text) if token.casefold() not in {"professional", "summary"})
    confident = sum(1 for verb in CONFIDENT_VERBS if re.search(rf"\b{re.escape(verb)}\b", lowered))
    jd_mimicry = jd_paraphrase_findings(content, employer_need_trace)
    abstract_hits = [item for item in GENERIC_ABSTRACTIONS if item in lowered]
    needs = _top_need_rows(employer_need_trace)
    represented_need = not needs or any(
        set(item.get("candidate_evidence_ids", []))
        & {evidence_id for clause in content.get("recruiter_summary", {}).get("clauses", []) for evidence_id in clause.get("source_evidence_ids", [])}
        for item in needs
    )
    has_professional = bool(content.get("employment"))
    has_technical = bool(content.get("projects"))
    dimensions = {
        "POSITIONING": 9.6 if content.get("target_role") and summary else 6.0,
        "SPECIFICITY": 9.6 if concrete >= 2 and not abstract_hits else (8.8 if concrete else 6.5),
        "PROFESSIONAL_CONFIDENCE": 9.6 if confident >= 1 and not any(item["code"] == "WEAK_FUTURE_TENSE" for item in boundary["findings"]) else 7.0,
        "EMPLOYER_RELEVANCE": 9.6 if represented_need and not jd_mimicry else 7.5,
        "CAREER_STORY": 9.5 if (has_professional and has_technical) or bool(strategy) else 8.8,
        "HUMAN_VOICE": 9.6 if variation["status"] == "PASS" and boundary["status"] == "PASS" else 6.5,
        "CONCISION": 9.5 if 40 <= len(words) <= 80 and all(len(_plain(item.get("text")).split()) <= 36 for item in bullets) else 8.0,
        "EVIDENCE_DENSITY": 9.7 if traces_complete else 5.0,
        "DIFFERENTIATION": 9.4 if strategy and strategy.get("key_differentiator") else 9.0,
        "READABILITY": 9.6 if sentences and all(len(item.split()) <= 34 for item in sentences) else 7.5,
        "PERSUASIVENESS": 9.5 if concrete >= 2 and confident >= 1 else 8.0,
        "SYSTEM_LANGUAGE_ABSENCE": 10.0 if boundary["status"] == "PASS" else 0.0,
    }
    score = round(sum(dimensions.values()) / len(QUALITY_DIMENSIONS), 1)
    takeaway = {
        "who_is_this_person": bool(summary), "target_role_clear": bool(content.get("target_role")),
        "reason_to_keep_reading": concrete >= 2 or bool(strategy and strategy.get("key_differentiator")),
        "evidence_visible": traces_complete and bool(bullets),
        "transition_credibility": not (has_professional and has_technical) or "professional" in summary.casefold(),
    }
    findings = [*boundary["findings"]]
    findings.extend({"code": "JD_LANGUAGE_MIMICRY", **item} for item in jd_mimicry)
    findings.extend({"code": "GENERIC_ABSTRACTION", "term": item, "surface": "resume"} for item in abstract_hits)
    findings.extend({"code": item, "term": "", "surface": "resume"} for item in variation["flags"])
    hard_fail = boundary["status"] == "FAIL" or not traces_complete or bool(jd_mimicry) or not all(takeaway.values())
    return {
        "schema": "careeros.recruiter-copy-quality.v2", "schema_version": "2.0.0",
        "status": "PASS" if score >= 9.3 and not hard_fail else "FAIL", "score": score, "threshold": 9.3,
        "dimensions": dimensions, "findings": findings, "recruiter_takeaway_test": takeaway,
        "public_copy_boundary_status": boundary["status"], "natural_language_variation": variation,
    }


def targeted_editorial_regression(parent: dict[str, Any], targeted: dict[str, Any], *, valid_reasons: Iterable[str] = ()) -> dict[str, Any]:
    parent_quality = parent.get("recruiter_copy_quality_v2") or recruiter_copy_quality_v2(parent, strategy=parent.get("recruiter_conversion_strategy_v2"))
    target_quality = targeted.get("recruiter_copy_quality_v2") or recruiter_copy_quality_v2(
        targeted, strategy=targeted.get("recruiter_conversion_strategy_v2"), employer_need_trace=targeted.get("employer_need_trace"),
    )
    regressions = [
        key for key in QUALITY_DIMENSIONS
        if float(target_quality["dimensions"].get(key, 0)) + 0.5 < float(parent_quality["dimensions"].get(key, 0))
    ]
    delta = round(float(target_quality["score"]) - float(parent_quality["score"]), 1)
    reasons = [item for item in valid_reasons if _plain(item)]
    allowed = bool(reasons) and not any(item in {"HUMAN_VOICE", "SYSTEM_LANGUAGE_ABSENCE", "EVIDENCE_DENSITY"} for item in regressions)
    failed = target_quality["status"] != "PASS" or (delta < -0.2 and not allowed) or (regressions and not allowed)
    return {
        "schema": "careeros.targeted-editorial-regression.v1", "schema_version": "1.0.0",
        "status": "FAIL" if failed else "PASS", "parent_score": parent_quality["score"],
        "targeted_score": target_quality["score"], "score_delta": delta,
        "regressions": regressions, "valid_reasons": reasons,
    }


def cross_summary_templates(contents: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    """Compare carrier language while preserving differences in factual skills.

    Multiple historical builds for the same target are represented by their
    latest supplied content, so normal rebuilds are not called formula reuse.
    """
    latest = {c['target_role']: c for c in contents}
    identities = [r.get('employer', '') for r in profile.get('employment', [])]
    identities += [r.get('title', '') for r in profile.get('credentials', [])]
    frames: dict[str, list[str]] = {}
    for target, content in latest.items():
        sentence = re.split(r'(?<=[.!?])\s+', _plain(content.get('summary')), maxsplit=1)[0].casefold()
        sentence = sentence.replace(target.casefold(), '<target>')
        for identity in sorted(filter(None, identities), key=len, reverse=True):
            sentence = sentence.replace(identity.casefold(), '<source>')
        frame = re.sub(r'[^a-z0-9<>]+', ' ', sentence).strip()
        if frame:
            frames.setdefault(frame, []).append(target)
    repeated = [{'frame': frame, 'targets': targets} for frame, targets in frames.items() if len(targets) > 1]
    return {'status': 'REVIEW' if repeated else 'PASS', 'summaries_compared': len(latest), 'repeated_frames': repeated, 'boundary': 'Review recurring sentence frames; repeated canonical skills and factual terms alone are not penalized. No artifact or source fact is changed.'}
