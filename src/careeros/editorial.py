"""Evidence-bound resume editorial planning.

This module improves selection, ordering, and recruiter-facing expression.  It
never creates facts: every rendered bullet must retain canonical evidence IDs,
and metrics are usable only when their source record explicitly permits them.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

from careeros.recruiter_conversion import render_recruiter_bullet_v2


PUBLIC_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}
INTERNAL_DISPLAY_TERMS = (
    "claimed complete", "needs verification", "date not supplied", "boundary:",
    "evidence class", "confidence score", "record id", "unspecified",
    "candidate reports", "portfolio reports", "public_use", "canonical",
    "proposed", "review required", "base resume", "lane base", "career os",
    "without overstating", "within established boundaries", "building production depth",
    "under senior review", "prepared to learn", "public-use", "verified evidence",
)
COMPLETED_VERBS = {
    "analyze": "Analyzed", "investigate": "Investigated", "identify": "Identified",
    "document": "Documented", "validate": "Validated", "verify": "Verified",
    "create": "Created", "build": "Built", "develop": "Developed", "complete": "Completed",
    "practice": "Applied", "configure": "Configured", "review": "Reviewed",
    "coordinate": "Coordinated", "support": "Supported", "deliver": "Delivered",
    "map": "Mapped", "draft": "Drafted", "lead": "Led", "facilitate": "Facilitated",
    "log": "Logged", "standardize": "Standardized", "prepare": "Prepared",
}
OUTCOME_KEYWORDS = {
    "TECHNICAL": {"system", "code", "query", "network", "log", "tool", "configured"},
    "OPERATIONAL": {"workflow", "handoff", "process", "operation", "escalat", "triage"},
    "DELIVERY": {"delivered", "completed", "produced", "created", "built"},
    "QUALITY": {"validated", "verified", "accuracy", "reviewed", "quality"},
    "RISK": {"risk", "vulnerab", "threat", "prevent", "remediat", "security"},
    "COMPLIANCE": {"compliance", "policy", "audit", "control"},
    "CUSTOMER": {"customer", "client", "member", "user", "support"},
    "EFFICIENCY": {"time", "faster", "reduced", "efficien", "throughput"},
    "COMMERCIAL": {"revenue", "sales", "savings", "vendor", "procurement"},
    "LEARNING_PROJECT": {"lab", "simulation", "course", "exercise", "project"},
}
SKILL_GROUP_ORDER = (
    "SECURITY & MONITORING", "NETWORKING", "TOOLS & PLATFORMS", "PROGRAMMING",
    "OPERATIONS", "LANGUAGES", "OTHER",
)


def default_public_display_policy() -> dict[str, Any]:
    return {
        "schema": "careeros.public-display-policy.v1",
        "schema_version": "1.0.0",
        "policy_id": "public-display-policy:conservative-v1",
        "credential_display": {
            "allowed_states": ["ACTIVE", "COMPLETED"],
            "allowed_verification_states": ["VERIFIED", "DOCUMENT_BACKED", "USER_CONFIRMED"],
            "show_issuer": True,
            "show_internal_state": False,
        },
        "project_date_display": "OMIT_WHEN_UNKNOWN",
        "skill_display": "EVIDENCE_BACKED_ONLY",
        "verification_sensitive_claims": "OMIT_IF_NOT_PUBLICLY_PERMITTED",
        "allowed_visibility": sorted(PUBLIC_VISIBILITY),
        "private_restricted_evidence": "EXCLUDE",
        "approximate_metrics": "ALLOW_ONLY_WHEN_CANONICAL_POLICY_PERMITS",
    }


def _tokens(value: Any) -> set[str]:
    text = " ".join(str(part) for part in value) if isinstance(value, (list, tuple, set)) else str(value or "")
    return {token for token in re.findall(r"[a-z0-9+#.]+", text.casefold()) if len(token) > 2}


def _family_terms(family: dict[str, Any], opportunity: dict[str, Any] | None) -> set[str]:
    values: list[Any] = [
        family.get("display_name"), family.get("label"), family.get("headline"),
        family.get("description"), family.get("target_titles", []),
        family.get("core_capabilities", []), family.get("preferred_capabilities", []),
        family.get("transferable_capabilities", []), family.get("skill_tags", []),
    ]
    if opportunity:
        values.extend([opportunity.get("role_title"), [item.get("capability") for item in opportunity.get("requirements", [])]])
    return set().union(*(_tokens(value) for value in values))


def _evidence_terms(evidence: dict[str, Any], skill_index: dict[str, dict[str, Any]]) -> set[str]:
    values: list[Any] = [
        evidence.get("summary"), evidence.get("context"), evidence.get("problem_or_need"),
        evidence.get("actions", []), evidence.get("tools_methods", []), evidence.get("stakeholders", []),
        evidence.get("scope"), evidence.get("frequency"), evidence.get("deliverables", []),
        evidence.get("outcomes", []), evidence.get("constraints", []), evidence.get("quality_risk", []),
        evidence.get("leadership_ownership", []), evidence.get("handoffs_escalations", []),
    ]
    for skill_id in evidence.get("skill_ids", []):
        skill = skill_index.get(skill_id, {})
        values.extend([skill.get("name"), skill.get("aliases", []), skill.get("category"), skill.get("contexts", [])])
    return set().union(*(_tokens(value) for value in values))


def _rank_evidence(profile: dict[str, Any], family: dict[str, Any], opportunity: dict[str, Any] | None) -> list[tuple[dict[str, Any], str, float]]:
    lane_terms = _family_terms(family, opportunity)
    skills = {item["record_id"]: item for item in profile.get("skills", [])}
    ranked: list[tuple[dict[str, Any], str, float]] = []
    for evidence in profile.get("evidence", []):
        if evidence.get("visibility") not in PUBLIC_VISIBILITY:
            ranked.append((evidence, "DISTRACTING", -1.0))
            continue
        terms = _evidence_terms(evidence, skills)
        overlap = len(terms & lane_terms)
        professional = bool(evidence.get("employment_ids"))
        project = bool(evidence.get("project_ids"))
        score = overlap * 2.0 + (1.0 if evidence.get("outcomes") else 0.0) + (0.5 if professional else 0.0)
        if overlap >= 3 or (overlap >= 2 and (professional or project)):
            level = "ANCHOR"
        elif overlap >= 1:
            level = "SUPPORTING"
        elif professional:
            level = "CONTEXT"
        elif project:
            level = "OPTIONAL"
        else:
            level = "DISTRACTING"
        ranked.append((evidence, level, score))
    return sorted(ranked, key=lambda item: (item[2], item[0].get("record_id", "")), reverse=True)


def plan_storyline(profile: dict[str, Any], family: dict[str, Any], opportunity: dict[str, Any] | None = None) -> dict[str, Any]:
    ranked = _rank_evidence(profile, family, opportunity)
    by_level: dict[str, list[str]] = defaultdict(list)
    for evidence, level, _score in ranked:
        by_level[level].append(evidence["record_id"])
    target = (opportunity or {}).get("role_title") or family.get("display_name") or family.get("label") or "target role"
    core = family.get("core_capabilities") or family.get("skill_tags") or []
    transferable = family.get("transferable_capabilities") or []
    return {
        "schema": "careeros.resume-storyline.v1",
        "schema_version": "1.0.0",
        "resume_family": family.get("role_family_id") or family.get("family_id") or "role-family",
        "target_role_family": family.get("display_name") or family.get("label") or str(target),
        "candidate_positioning": f"Evidence-backed candidate pursuing {target} with demonstrated {', '.join(core[:3]) or 'transferable capabilities'}.",
        "professional_foundation": "Preserve relevant professional evidence as transferable foundation without implying target-domain equivalence.",
        "transition_narrative": f"Connect supported professional strengths and completed project evidence to {target} while keeping employment, project, and training evidence distinct.",
        "anchor_evidence": by_level["ANCHOR"],
        "supporting_evidence": by_level["SUPPORTING"],
        "context_evidence": by_level["CONTEXT"],
        "evidence_to_minimize": by_level["OPTIONAL"],
        "evidence_to_exclude": by_level["DISTRACTING"],
        "recruiter_takeaway": f"The candidate brings credible entry-ready evidence in {', '.join(core[:3]) or 'the target capabilities'}" + (f" plus {', '.join(transferable[:2])}." if transferable else "."),
        "summary_strategy": "Lead with current supported value, name the target lane, and anchor the transition in evidence rather than aspiration.",
        "section_priority": ["SUMMARY", "SKILLS", "PROJECTS", "EXPERIENCE", "EDUCATION", "CREDENTIALS"],
        "project_priority": [record_id for level in ("ANCHOR", "SUPPORTING", "OPTIONAL") for record_id in by_level[level]],
        "risk_flags": ["NO_DOMAIN_EQUIVALENCE", "NO_UNSUPPORTED_METRICS", "NO_TITLE_INFLATION", "PRESERVE_VISIBILITY"],
        "evidence_rankings": [{"evidence_id": evidence["record_id"], "classification": level, "score": score} for evidence, level, score in ranked],
    }


def _completed_action(text: str, completed: bool) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip()).rstrip(".")
    if not value:
        return ""
    if not completed:
        return value[0].upper() + value[1:]
    first, *rest = value.split(" ", 1)
    replacement = COMPLETED_VERBS.get(first.casefold())
    if replacement:
        return replacement + (" " + rest[0] if rest else "")
    return value[0].upper() + value[1:]


def classify_outcome(text: str, *, project: bool = False) -> str:
    lowered = text.casefold()
    scored = [(sum(1 for token in tokens if token in lowered), category) for category, tokens in OUTCOME_KEYWORDS.items()]
    score, category = max(scored, default=(0, "DELIVERY"))
    if project and score == 0:
        return "LEARNING_PROJECT"
    return category if score else "DELIVERY"


def _metric_refs(evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    structured = []
    structured_unsupported = []
    for metric in evidence.get("metrics", []):
        value = metric.get("value")
        if value is None:
            continue
        item = {
            "value": str(value), "metric_type": metric.get("metric_type", "OTHER"),
            "verification_class": metric.get("state", "UNSUPPORTED"),
            "source_boundary": metric.get("source_refs", []),
            "approximate": bool(metric.get("approximate")),
            "public_use_allowed": bool(metric.get("public_use_allowed")),
        }
        if item["public_use_allowed"] and item["verification_class"] in {"VERIFIED", "DOCUMENT_BACKED", "USER_CONFIRMED"}:
            structured.append(item)
        else:
            structured_unsupported.append(str(value))
    if structured or structured_unsupported:
        return structured, structured_unsupported
    text = " ".join([str(evidence.get("summary", "")), *map(str, evidence.get("outcomes", [])), *map(str, evidence.get("actions", []))])
    numbers = re.findall(r"(?<![A-Za-z])(?:\d[\d,]*(?:\.\d+)?%?|\d+\+)(?![A-Za-z])", text)
    boundaries = [str(item) for item in evidence.get("metric_boundaries", [])]
    allowed = bool(boundaries) and not any("no " in item.casefold() and "metric" in item.casefold() for item in boundaries)
    refs = [{"value": number, "metric_type": "COUNT" if "%" not in number else "IMPROVEMENT", "verification_class": evidence.get("verification_state", "UNSUPPORTED") if allowed else "UNSUPPORTED", "source_boundary": boundaries} for number in numbers]
    unsupported = numbers if numbers and not allowed else []
    return refs, unsupported


def build_bullet_candidates(profile: dict[str, Any], storyline: dict[str, Any]) -> list[dict[str, Any]]:
    rank = {item["evidence_id"]: item["classification"] for item in storyline.get("evidence_rankings", [])}
    project_ids = {item["record_id"] for item in profile.get("projects", [])}
    results: list[dict[str, Any]] = []
    for evidence in profile.get("evidence", []):
        evidence_id = evidence.get("evidence_id") or evidence["record_id"]
        if rank.get(evidence_id) in {"DISTRACTING", "IRRELEVANT"} or evidence.get("visibility") not in PUBLIC_VISIBILITY:
            continue
        completed = evidence.get("status", "ACTIVE") == "ACTIVE" and evidence.get("verification_state") not in {"REJECTED", "CONFLICT"}
        supported_actions = [
            value for value in (_completed_action(item, completed) for item in (evidence.get("actions") or [evidence.get("summary")]))
            if value
        ]
        action = supported_actions[0] if supported_actions else ""
        outcomes = evidence.get("outcomes") or []
        deliverables = evidence.get("deliverables") or []
        deliverable = _completed_action(deliverables[0] if deliverables else evidence.get("summary", ""), completed)
        outcome = _completed_action(outcomes[0], completed) if outcomes else ""
        methods = [str(item) for item in evidence.get("tools_methods", []) if str(item).strip()]
        method = methods[0] if methods else (supported_actions[1] if len(supported_actions) > 1 else "")
        if action and outcome:
            text = f"{action}; {outcome[0].lower() + outcome[1:] if outcome else outcome}."
            pattern = "ACTION + RESULT"
        elif deliverable:
            text = deliverable.rstrip(".") + "."
            pattern = "DELIVERABLE + METHOD + PURPOSE"
        else:
            continue
        metric_refs, source_unsupported = _metric_refs(evidence)
        unsupported = [token for token in source_unsupported if token in text]
        candidate = {
            "schema": "careeros.resume-bullet-candidate.v1", "schema_version": "1.0.0",
            "bullet_id": f"bullet:{evidence_id}", "evidence_ids": [evidence_id],
            "role_context": evidence.get("context"), "action": action,
            "scope": evidence.get("scope") or evidence.get("ownership") or (evidence.get("responsibility") or {}).get("description"),
            "tool_or_method": method, "supported_actions": supported_actions, "deliverable": deliverable, "outcome": outcome,
            "outcome_class": classify_outcome(" ".join([deliverable, outcome]), project=bool(set(evidence.get("project_ids", [])) & project_ids)),
            "metric_refs": metric_refs, "unsupported_metric_tokens": unsupported,
            "source_unsupported_metric_tokens": source_unsupported,
            "verification_state": evidence.get("verification_state", "UNVERIFIED"),
            "visibility": evidence.get("visibility", "INTERNAL"), "lane_relevance": rank.get(evidence_id, "OPTIONAL"),
            "jd_relevance": rank.get(evidence_id, "OPTIONAL"), "confidence": evidence.get("confidence", "UNKNOWN"),
            "source_lineage": evidence.get("provenance", []), "pattern": pattern, "text": text,
        }
        results.append(render_recruiter_bullet_v2(candidate))
    return semantic_dedupe(results)


def _semantic_signature(bullet: dict[str, Any]) -> set[str]:
    return _tokens(" ".join(str(bullet.get(key) or "") for key in ("action", "role_context", "deliverable", "outcome")))


def semantic_dedupe(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    retained: list[dict[str, Any]] = []
    for candidate in candidates:
        signature = _semantic_signature(candidate)
        duplicate_index = None
        for index, existing in enumerate(retained):
            same_source = bool(set(candidate.get("evidence_ids", [])) & set(existing.get("evidence_ids", [])))
            other = _semantic_signature(existing)
            similarity = len(signature & other) / max(1, len(signature | other))
            if same_source or similarity >= 0.78:
                duplicate_index = index
                break
        if duplicate_index is None:
            retained.append(candidate)
            continue
        current = retained[duplicate_index]
        strength = lambda item: (bool(item.get("outcome")), len(item.get("metric_refs", [])), len(item.get("text", "")))
        if strength(candidate) > strength(current):
            retained[duplicate_index] = candidate
    return retained


def public_language_skills(profile: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    """Return candidate-confirmed language records without implying certification."""
    results = []
    for skill in profile.get("skills", []):
        if skill.get("visibility") not in set(policy["allowed_visibility"]):
            continue
        if str(skill.get("category", "")).casefold() != "language":
            continue
        if not skill.get("provenance") or skill.get("confidence") not in {"HIGH", "MEDIUM"}:
            continue
        results.append({
            "name": skill.get("name"), "record_id": skill["record_id"],
            "evidence_ids": skill.get("evidence_ids", []), "proficiency": skill.get("proficiency"),
            "claim_boundary": "SELF_REPORTED_LANGUAGE_PROFICIENCY_NO_CERTIFICATION_CLAIM",
        })
    return results


def group_skills(profile: dict[str, Any], storyline: dict[str, Any], policy: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    selected_evidence = set(
        storyline.get("anchor_evidence", [])
        + storyline.get("supporting_evidence", [])
        + storyline.get("context_evidence", [])
        + storyline.get("transferable_professional_evidence", [])
        + storyline.get("foundational_evidence", [])
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for skill in profile.get("skills", []):
        if skill.get("visibility") not in PUBLIC_VISIBILITY or not set(skill.get("evidence_ids", [])) & selected_evidence:
            continue
        category = str(skill.get("category", "")).casefold()
        name = str(skill.get("name", ""))
        joined = f"{category} {name}".casefold()
        if any(token in joined for token in ("network", "dns", "dhcp", "vpn", "routing", "switch", "tcp")):
            group = "NETWORKING"
        elif any(token in joined for token in ("security", "threat", "incident", "siem", "vulnerab", "monitor")):
            group = "SECURITY & MONITORING"
        elif any(token in joined for token in ("tool", "platform", "splunk", "service")):
            group = "TOOLS & PLATFORMS"
        elif any(token in joined for token in ("program", "python", "code", "sql")):
            group = "PROGRAMMING"
        elif any(token in joined for token in ("language", "english", "spanish", "french")):
            group = "LANGUAGES"
        elif any(token in joined for token in ("operation", "support", "documentation", "process", "communication")):
            group = "OPERATIONS"
        else:
            group = "OTHER"
        grouped[group].append({"name": name, "record_id": skill["record_id"], "evidence_ids": skill.get("evidence_ids", [])})
        if group == "NETWORKING":
            existing = {item["name"].casefold() for item in grouped[group]}
            for alias in skill.get("aliases", []):
                alias_name = str(alias).strip()
                if alias_name and alias_name.casefold() not in existing:
                    grouped[group].append({
                        "name": alias_name, "record_id": skill["record_id"],
                        "evidence_ids": skill.get("evidence_ids", []), "alias_of": name,
                    })
                    existing.add(alias_name.casefold())
    for language in public_language_skills(profile, policy or default_public_display_policy()):
        if not any(item["record_id"] == language["record_id"] for item in grouped["LANGUAGES"]):
            grouped["LANGUAGES"].append(language)
    order = list(SKILL_GROUP_ORDER)
    signals = [item.get("signal") for item in storyline.get("job_story_signals", [])]
    networking_first = "NETWORKING" in signals and (
        "SECURITY" not in signals
        or signals.index("NETWORKING") <= signals.index("SECURITY")
    )
    if networking_first:
        order.remove("NETWORKING")
        order.insert(0, "NETWORKING")
    return [{"group": group, "skills": sorted(grouped[group], key=lambda item: item["name"].casefold())} for group in order if grouped[group]]


def public_education(profile: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for item in profile.get("education", []):
        if item.get("visibility") not in set(policy["allowed_visibility"]):
            continue
        status = item.get("completion_status")
        if status == "IN_PROGRESS":
            display = "In progress" + (f" - expected {item['end_year']}" if item.get("end_year") else "")
        elif status == "COMPLETED":
            display = str(item.get("end_year") or "Completed")
        else:
            display = ""
        output.append({"record_id": item["record_id"], "program": item.get("program"), "field_of_study": item.get("field_of_study"), "institution": item.get("institution"), "display_status": display, "completion_status": status})
    # Current degree programs lead.  A GED remains accurate but may be omitted
    # when current/completed postsecondary education already tells the story.
    has_postsecondary = any(
        item.get("completion_status") in {"IN_PROGRESS", "COMPLETED"}
        and "ged" not in str(item.get("program", "")).casefold()
        for item in output
    )
    if has_postsecondary:
        output = [item for item in output if "ged" not in str(item.get("program", "")).casefold()]
    rank = {"IN_PROGRESS": 0, "COMPLETED": 1}
    return sorted(output, key=lambda item: (rank.get(item.get("completion_status"), 2), str(item.get("institution", "")).casefold()))


def public_credentials(profile: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    rule = policy["credential_display"]
    results = []
    for item in profile.get("credentials", []):
        if item.get("visibility") not in set(policy["allowed_visibility"]):
            continue
        if item.get("credential_state") not in set(rule["allowed_states"]):
            continue
        if item.get("verification_state") not in set(rule["allowed_verification_states"]):
            continue
        results.append({"record_id": item["record_id"], "title": item.get("title"), "issuer": item.get("issuer"), "issued_date": item.get("issued_date"), "expiration_date": item.get("expiration_date")})
    return results


def sanitize_url(url: str) -> str:
    value = re.sub(r"^https?://", "", str(url).strip()).rstrip("/")
    return value.removeprefix("www.")


def system_artifact_leaks(text: str) -> list[str]:
    lowered = text.casefold()
    return [term for term in INTERNAL_DISPLAY_TERMS if term in lowered]


def lane_differentiation(first: dict[str, Any], second: dict[str, Any]) -> float:
    def ranked(storyline: dict[str, Any]) -> list[str]:
        return [item["evidence_id"] for item in storyline.get("evidence_rankings", []) if item["classification"] in {"ANCHOR", "SUPPORTING"}][:8]
    a, b = ranked(first), ranked(second)
    universe = list(dict.fromkeys([*a, *b]))
    if not universe:
        return 0.0
    missing = max(len(universe), 2)
    rank_a = {item: index for index, item in enumerate(a)}
    rank_b = {item: index for index, item in enumerate(b)}
    rank_distance = sum(abs(rank_a.get(item, missing) - rank_b.get(item, missing)) for item in universe) / (len(universe) * max(1, missing - 1))
    label_tokens_a = _tokens(" ".join(str(first.get(key, "")) for key in ("target_role_family", "candidate_positioning", "recruiter_takeaway")))
    label_tokens_b = _tokens(" ".join(str(second.get(key, "")) for key in ("target_role_family", "candidate_positioning", "recruiter_takeaway")))
    narrative_distance = 1.0 - len(label_tokens_a & label_tokens_b) / max(1, len(label_tokens_a | label_tokens_b))
    return round(0.7 * rank_distance + 0.3 * narrative_distance, 3)


def evaluate_editorial_quality(content: dict[str, Any], *, peer_storyline: dict[str, Any] | None = None) -> dict[str, Any]:
    text_parts = [str(content.get("summary", ""))]
    bullets = []
    for section in [*content.get("employment", []), *content.get("projects", [])]:
        for bullet in section.get("bullets", []):
            bullets.append(bullet)
            text_parts.append(str(bullet.get("text", "")))
    text = "\n".join(text_parts)
    leaks = system_artifact_leaks(text)
    unique_sources = [tuple(sorted(item.get("evidence_ids", []))) for item in bullets]
    duplicate_count = len(unique_sources) - len(set(unique_sources))
    unsupported = sum(len(item.get("unsupported_metric_tokens", [])) for item in bullets)
    outcome_density = sum(1 for item in bullets if item.get("outcome")) / max(1, len(bullets))
    components = {
        "ROLE_RELEVANCE": 90 if content.get("skills") else 55,
        "STORY_COHERENCE": 90 if content.get("summary") and content.get("storyline") else 65,
        "EVIDENCE_STRENGTH": 95 if bullets and all(item.get("evidence_ids") for item in bullets) else 50,
        "OUTCOME_DENSITY": round(55 + 45 * outcome_density),
        "METRIC_SCALE_QUALITY": 100 if unsupported == 0 else 40,
        "RECRUITER_CLARITY": 95 if not leaks else 35,
        "CONCISION": 90 if all(len(item.get("text", "")) <= 220 for item in bullets) else 65,
        "HUMAN_VOICE": 92 if not any(item.get("text", "").startswith(("Responsible for", "Worked on", "Familiar with")) for item in bullets) else 65,
        "LANE_DIFFERENTIATION": 100 if peer_storyline is None else round(100 * lane_differentiation(content.get("storyline", {}), peer_storyline)),
        "SYSTEM_ARTIFACT_LEAKAGE": 100 if not leaks else 0,
        "SEMANTIC_DUPLICATION": 100 if duplicate_count == 0 else max(0, 100 - 30 * duplicate_count),
    }
    score = round(sum(components.values()) / len(components), 1)
    human_read = {
        "ten_second_story": bool(content.get("summary") and content.get("target_role")),
        "intentional_human_composition": components["HUMAN_VOICE"] >= 80,
        "each_bullet_earns_space": duplicate_count == 0,
        "transition_without_pretending": "professional" not in content.get("summary", "").casefold() or "project" in content.get("summary", "").casefold(),
        "no_internal_artifact_language": not leaks,
    }
    return {
        "schema": "careeros.resume-editorial-quality.v1", "schema_version": "1.0.0",
        "score": score, "threshold": 80.0, "status": "PASS" if score >= 80 and not leaks and not unsupported and duplicate_count == 0 else "FAIL",
        "components": components, "system_artifact_leaks": leaks, "semantic_duplicate_count": duplicate_count,
        "unsupported_metric_count": unsupported, "human_read_test": human_read,
    }
