"""Provider-neutral, evidence-producing learning-path intelligence.

The module ranks verified learning options from observed career gaps.  It does
not scrape providers, promote course completion into canonical competency, or
allow education to satisfy mandatory professional-experience requirements.
Provider adapters normalize caller-supplied current catalog evidence.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Protocol

from careeros.core.io import sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir, utc_now


LEARNING_PATH_POLICY_VERSION = "learning-path-intelligence-v1"
GAP_TYPES = {
    "KNOWLEDGE", "PRACTICAL_SKILL", "TOOL", "PLATFORM", "PROTOCOL", "DOMAIN",
    "CERTIFICATION", "CREDENTIAL", "EXPERIENCE", "EVIDENCE", "PORTFOLIO",
    "COMMUNICATION", "OPERATIONS", "OTHER",
}
PRIORITY_CLASSES = ("OPTIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL")
COURSE_TYPES = {
    "COURSE", "PROFESSIONAL_CERTIFICATE", "INDUSTRY_CERTIFICATION_PREP",
    "INDUSTRY_CERTIFICATION", "LAB_PLATFORM", "BOOTCAMP", "DEGREE_COURSEWORK", "OTHER",
    "KNOWLEDGE_RESOURCE", "PRACTICAL_PROJECT",
}
FRESHNESS_STATES = {"CURRENT", "REVERIFY", "REMOVED", "REPLACED", "UNKNOWN"}
CREDENTIAL_SIGNALS = {
    "REQUIRED_BY_MARKET", "HIGH_SIGNAL", "MODERATE_SIGNAL", "LOW_SIGNAL",
    "COMPLETION_ONLY", "NO_CREDENTIAL",
}
LEVEL_MATCHES = {"TOO_BASIC", "APPROPRIATE", "STRETCH", "TOO_ADVANCED", "PREREQUISITE_MISSING"}
REDUNDANCY_CLASSES = {"HIGHLY_REDUNDANT", "PARTIALLY_REDUNDANT", "MOSTLY_NEW", "NOVEL_HIGH_VALUE"}
ROI_CLASSES = ("NEGATIVE", "LOW", "MEDIUM", "HIGH", "VERY_HIGH")
PATH_STATUSES = {"PROPOSED", "REVIEWED", "ACTIVE", "PAUSED", "COMPLETE", "STALE", "SUPERSEDED"}
STEP_TYPES = {
    "COURSE", "MODULE", "LAB", "PROJECT", "PORTFOLIO_ARTIFACT",
    "CERTIFICATION_PREP", "CERTIFICATION_ATTEMPT", "PRACTICE", "REVIEW",
}
IMPACT_STATES = {
    "NO_EXPECTED_CHANGE", "EVIDENCE_EXPANSION", "SKILL_STRENGTHENING",
    "QUALIFICATION_IMPROVEMENT", "CREDENTIAL_SIGNAL", "MATERIAL_LANE_IMPROVEMENT",
}
PROVIDER_CAPABILITIES = {"SEARCH", "DETAIL", "CURRICULUM", "CREDENTIAL_TYPE", "DURATION", "COST", "FRESHNESS"}
PUBLIC_PROVIDERS = {"COURSERA", "LINKEDIN_LEARNING", "UDEMY"}


def _tokens(value: Any) -> set[str]:
    if isinstance(value, dict):
        value = " ".join(f"{key} {item}" for key, item in value.items())
    elif isinstance(value, (list, tuple, set)):
        value = " ".join(map(str, value))
    return {
        token for token in re.findall(r"[a-z0-9+#.]+", str(value or "").casefold())
        if len(token) > 2 and token not in {"and", "the", "for", "with", "from", "into", "this", "that", "course"}
    }


def _bounded(value: Any, minimum: float = 0.0, maximum: float = 5.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return round(max(minimum, min(maximum, number)), 3)


def _classify(score: float, labels: tuple[str, ...]) -> str:
    position = min(len(labels) - 1, max(0, int(math.floor(score * len(labels) / 100.0001))))
    return labels[position]


def _stable_id(prefix: str, material: Any) -> str:
    return f"{prefix}:{uuid.uuid5(uuid.NAMESPACE_URL, sha256_value(material))}"


def prioritize_career_gaps(
    *, candidate_profile_id: str, role_family_id: str, gaps: list[dict[str, Any]],
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Build transparent CareerGapPriorityV1 records from observed gap signals."""
    records: list[dict[str, Any]] = []
    for gap in gaps:
        gap_type = str(gap.get("gap_type") or "OTHER").upper()
        if gap_type not in GAP_TYPES:
            gap_type = "OTHER"
        recurrence = max(0, int(gap.get("recurrence_count") or 0))
        job_frequency = _bounded(gap.get("job_frequency"))
        importance = _bounded(gap.get("requirement_importance"))
        hard_frequency = max(0, int(gap.get("hard_gap_frequency") or 0))
        preferred_frequency = max(0, int(gap.get("preferred_gap_frequency") or 0))
        evidence_strength = _bounded(gap.get("current_evidence_strength"))
        proximity = _bounded(gap.get("candidate_proximity"))
        breadth = _bounded(gap.get("career_breadth"))
        market = _bounded(gap.get("market_relevance"))
        urgency = _bounded(gap.get("urgency"))
        effort = _bounded(gap.get("estimated_learning_effort"), 1.0, 5.0)
        evidence_potential = _bounded(gap.get("evidence_creation_potential"))
        # Transparent operating score. Frequency and importance lead; low evidence
        # raises need, while proximity and evidence potential raise actionability.
        components = {
            "recurrence": min(5.0, recurrence / 2.0), "job_frequency": job_frequency,
            "requirement_importance": importance, "hard_gap_frequency": min(5.0, hard_frequency),
            "preferred_gap_frequency": min(5.0, preferred_frequency / 2.0),
            "evidence_need": 5.0 - evidence_strength, "candidate_proximity": proximity,
            "career_breadth": breadth, "market_relevance": market, "urgency": urgency,
            "evidence_creation_potential": evidence_potential, "effort_efficiency": 6.0 - effort,
        }
        weights = {
            "recurrence": 0.11, "job_frequency": 0.10, "requirement_importance": 0.14,
            "hard_gap_frequency": 0.13, "preferred_gap_frequency": 0.04, "evidence_need": 0.09,
            "candidate_proximity": 0.07, "career_breadth": 0.08, "market_relevance": 0.09,
            "urgency": 0.05, "evidence_creation_potential": 0.07, "effort_efficiency": 0.03,
        }
        score = round(sum(components[key] * weights[key] for key in weights) * 20, 2)
        # One-off preferred mentions cannot become HIGH solely through broad fashion signals.
        if recurrence <= 1 and hard_frequency == 0 and importance < 4:
            score = min(score, 59.99)
        record = {
            "schema": "careeros.career-gap-priority.v1", "schema_version": "1.0.0",
            "gap_id": str(gap.get("gap_id") or _stable_id("career-gap", gap)),
            "candidate_profile_id": candidate_profile_id, "role_family_id": role_family_id,
            "source_gap_ids": sorted(set(map(str, gap.get("source_gap_ids") or []))),
            "gap_type": gap_type, "gap_statement": str(gap.get("gap_statement") or "Unspecified observed gap"),
            "recurrence_count": recurrence, "job_frequency": job_frequency,
            "requirement_importance": importance, "hard_gap_frequency": hard_frequency,
            "preferred_gap_frequency": preferred_frequency, "current_evidence_strength": evidence_strength,
            "candidate_proximity": proximity, "career_breadth": breadth, "market_relevance": market,
            "urgency": urgency, "estimated_learning_effort": effort,
            "evidence_creation_potential": evidence_potential, "priority_score": score,
            "priority_class": _classify(score, PRIORITY_CLASSES),
            "score_components": components,
            "provenance": list(gap.get("provenance") or []), "created_at": utc_now(timestamp),
            "policy_version": LEARNING_PATH_POLICY_VERSION,
        }
        SchemaRegistry(schema_dir()).validate("urn:careeros:schema:career-gap-priority:v1", record)
        records.append(record)
    return sorted(records, key=lambda item: (-item["priority_score"], item["gap_id"]))


def build_learning_objective(
    gap: dict[str, Any], *, objective_statement: str, target_competency: str,
    starting_state: str, desired_state: str, completion_evidence: list[str],
    lane_impact: list[str], job_impact: list[str], prerequisites: list[str] | None = None,
    estimated_scope: str = "BOUNDED", timestamp: str | None = None,
) -> dict[str, Any]:
    objective = {
        "schema": "careeros.learning-objective.v1", "schema_version": "1.0.0",
        "objective_id": _stable_id("learning-objective", {"gap": gap["gap_id"], "target": target_competency}),
        "gap_id": gap["gap_id"], "objective_statement": objective_statement,
        "target_competency": target_competency, "starting_state": starting_state,
        "desired_state": desired_state, "completion_evidence": completion_evidence,
        "lane_impact": lane_impact, "job_impact": job_impact,
        "prerequisites": prerequisites or [], "estimated_scope": estimated_scope,
        "created_at": utc_now(timestamp), "policy_version": LEARNING_PATH_POLICY_VERSION,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:learning-objective:v1", objective)
    return objective


def assess_course_freshness(
    *, course_candidate_id: str, last_verified_at: str | None, availability: str,
    as_of: str | None = None, reverify_after_days: int = 30, replacement_id: str | None = None,
) -> dict[str, Any]:
    now = datetime.fromisoformat((as_of or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00"))
    verified = None
    if last_verified_at:
        try:
            verified = datetime.fromisoformat(last_verified_at.replace("Z", "+00:00"))
            if verified.tzinfo is None:verified=None
        except ValueError:
            verified = None
    availability = availability.upper()
    if availability == "REMOVED":
        state, reason = "REMOVED", "Provider reports the course removed."
    elif availability == "REPLACED" or replacement_id:
        state, reason = "REPLACED", "Provider reports a replacement or successor."
    elif not verified or verified > now or availability not in {'AVAILABLE','ACTIVE'}:
        state, reason = "UNKNOWN", "No valid verification timestamp."
    elif (now - verified).days > reverify_after_days:
        state, reason = "REVERIFY", f"Catalog evidence is older than {reverify_after_days} days."
    else:
        state, reason = "CURRENT", "Provider catalog evidence is within the verification window."
    record = {
        "schema": "careeros.course-freshness.v1", "schema_version": "1.0.0",
        "course_candidate_id": course_candidate_id, "freshness_state": state,
        "freshness_reason": reason, "last_verified_at": last_verified_at,
        "reverify_after_days": reverify_after_days, "replacement_course_id": replacement_id,
        "assessed_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "policy_version": LEARNING_PATH_POLICY_VERSION,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:course-freshness:v1", record)
    return record


def build_course_candidate(record: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
    provider = str(record.get("provider") or "UNKNOWN").upper().replace(" ", "_")
    course_id = str(record.get("course_id") or sha256_value({"provider": provider, "url": record.get("url"), "title": record.get("title")})[:16])
    candidate_id = _stable_id("course-candidate", {"provider": provider, "course_id": course_id})
    course_type = str(record.get("course_type") or "COURSE").upper()
    if course_type not in COURSE_TYPES:
        course_type = "OTHER"
    # Import time is not evidence that the provider details were verified.
    # Keep an absent verification unknown while preserving the v1 string field.
    last_verified = record.get("last_verified_at") or ""
    freshness = assess_course_freshness(
        course_candidate_id=candidate_id, last_verified_at=last_verified,
        availability=str(record.get("availability") or "AVAILABLE"), as_of=timestamp,
        reverify_after_days=int(record.get("reverify_after_days") or 30),
        replacement_id=record.get("replacement_course_id"),
    )
    candidate = {
        "schema": "careeros.course-candidate.v1", "schema_version": "1.0.0",
        "course_candidate_id": candidate_id, "provider": provider, "course_id": course_id,
        "title": str(record.get("title") or "Untitled course"), "issuer": record.get("issuer"),
        "instructor": record.get("instructor"), "url": str(record.get("url") or ""),
        "course_type": course_type, "skill_topics": list(record.get("skill_topics") or []),
        "curriculum_topics": list(record.get("curriculum_topics") or []),
        "credential_type": record.get("credential_type") or "NO_CREDENTIAL",
        "certificate_available": bool(record.get("certificate_available")),
        "credential_issuer": record.get("credential_issuer"),
        "estimated_duration": record.get("estimated_duration") or "UNKNOWN",
        "cost_state": str(record.get("cost_state") or "UNKNOWN").upper(),
        "cost_amount": record.get("cost_amount"), "cost_currency": record.get("cost_currency"),
        "price_verified_at": record.get("price_verified_at"), "prerequisites": list(record.get("prerequisites") or []),
        "project_work": list(record.get("project_work") or []), "labs": list(record.get("labs") or []),
        "assessments": list(record.get("assessments") or []), "level": str(record.get("level") or "UNKNOWN").upper(),
        "delivery_modes": list(record.get("delivery_modes") or []),
        "self_paced": record.get("self_paced"),
        "last_verified_at": last_verified, "freshness_state": freshness["freshness_state"],
        "source_refs": list(record.get("source_refs") or []), "affiliate_relationship": bool(record.get("affiliate_relationship", False)),
        "subscription_plans": list(record.get('subscription_plans') or []),
        "duration_hours": record.get('duration_hours'),
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:course-candidate:v1", candidate)
    return candidate


def assess_redundancy(
    course: dict[str, Any], *, canonical_skills: Iterable[str] = (), projects: Iterable[str] = (),
    prior_coursework: Iterable[str] = (), credentials: Iterable[str] = (), evidence: Iterable[str] = (),
) -> dict[str, Any]:
    curriculum = _tokens(course.get("skill_topics", []) + course.get("curriculum_topics", []))
    existing = _tokens(list(canonical_skills) + list(projects) + list(prior_coursework) + list(credentials) + list(evidence))
    overlap = curriculum & existing
    ratio = round(len(overlap) / max(1, len(curriculum)), 3)
    practical = bool(course.get("labs") or course.get("project_work"))
    if ratio >= 0.75:
        classification = "HIGHLY_REDUNDANT"
    elif ratio >= 0.4:
        classification = "PARTIALLY_REDUNDANT"
    elif practical and len(curriculum - existing) >= 3:
        classification = "NOVEL_HIGH_VALUE"
    else:
        classification = "MOSTLY_NEW"
    result = {
        "schema": "careeros.learning-redundancy.v1", "schema_version": "1.0.0",
        "course_candidate_id": course["course_candidate_id"], "classification": classification,
        "overlap_ratio": ratio, "overlapping_topics": sorted(overlap),
        "new_topics": sorted(curriculum - existing), "credential_independent_value": False,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:learning-redundancy:v1", result)
    return result


def classify_credential_signal(course: dict[str, Any], *, market_required: bool = False, issuer_recognition: float = 0.0) -> str:
    course_type = course.get("course_type")
    if market_required and course_type == "INDUSTRY_CERTIFICATION":
        return "REQUIRED_BY_MARKET"
    if course_type == "INDUSTRY_CERTIFICATION" and issuer_recognition >= 4:
        return "HIGH_SIGNAL"
    if course_type == "PROFESSIONAL_CERTIFICATE" and issuer_recognition >= 3:
        return "MODERATE_SIGNAL"
    if course.get("certificate_available"):
        return "COMPLETION_ONLY" if course_type in {"COURSE", "LAB_PLATFORM"} else "LOW_SIGNAL"
    return "NO_CREDENTIAL"


def classify_level_match(
    course: dict[str, Any], *, candidate_level: str, satisfied_prerequisites: Iterable[str] = (),
) -> str:
    prerequisites = _tokens(course.get("prerequisites", []))
    satisfied = _tokens(satisfied_prerequisites)
    if prerequisites - satisfied:
        return "PREREQUISITE_MISSING"
    levels = {"BEGINNER": 1, "FOUNDATIONAL": 1, "INTERMEDIATE": 2, "ADVANCED": 3, "UNKNOWN": 2}
    candidate = levels.get(candidate_level.upper(), 2)
    target = levels.get(str(course.get("level") or "UNKNOWN").upper(), 2)
    if target < candidate:
        return "TOO_BASIC"
    if target == candidate:
        return "APPROPRIATE"
    if target == candidate + 1:
        return "STRETCH"
    return "TOO_ADVANCED"


def evaluate_course(
    course: dict[str, Any], *, objective: dict[str, Any], gap: dict[str, Any],
    existing_evidence: dict[str, Iterable[str]] | None = None, candidate_level: str = "INTERMEDIATE",
    satisfied_prerequisites: Iterable[str] = (), market_required_credential: bool = False,
    issuer_recognition: float = 0.0, employer_terms: Iterable[str] = (), preferences: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    preferences = preferences or {}
    existing = existing_evidence or {}
    redundancy = assess_redundancy(course, **{
        "canonical_skills": existing.get("canonical_skills", ()), "projects": existing.get("projects", ()),
        "prior_coursework": existing.get("prior_coursework", ()), "credentials": existing.get("credentials", ()),
        "evidence": existing.get("evidence", ()),
    })
    objective_tokens = _tokens(objective.get("target_competency")) | _tokens(objective.get("objective_statement"))
    course_tokens = _tokens(course.get("skill_topics", [])) | _tokens(course.get("curriculum_topics", []))
    employer_tokens = _tokens(employer_terms)
    coverage = len(objective_tokens & course_tokens) / max(1, len(objective_tokens))
    employer_coverage = len(employer_tokens & course_tokens) / max(1, len(employer_tokens)) if employer_tokens else 0.5
    practical = min(5.0, 1.0 + len(course.get("labs", [])) * 1.2 + len(course.get("project_work", [])) * 1.2 + len(course.get("assessments", [])) * 0.5)
    evidence_value = min(5.0, practical + (1.0 if course.get("project_work") else 0.0))
    level_match = classify_level_match(course, candidate_level=candidate_level, satisfied_prerequisites=satisfied_prerequisites)
    credential = classify_credential_signal(course, market_required=market_required_credential, issuer_recognition=issuer_recognition)
    credential_score = {"REQUIRED_BY_MARKET": 5, "HIGH_SIGNAL": 4.5, "MODERATE_SIGNAL": 3.5, "LOW_SIGNAL": 2, "COMPLETION_ONLY": 1, "NO_CREDENTIAL": 0}[credential]
    level_score = {"APPROPRIATE": 5, "STRETCH": 4, "TOO_BASIC": 1.5, "TOO_ADVANCED": 1, "PREREQUISITE_MISSING": 0}[level_match]
    redundancy_penalty = {"HIGHLY_REDUNDANT": 5, "PARTIALLY_REDUNDANT": 2.5, "MOSTLY_NEW": 0.5, "NOVEL_HIGH_VALUE": 0}[redundancy["classification"]]
    freshness_score = {"CURRENT": 5, "REVERIFY": 2, "UNKNOWN": 1, "REPLACED": 0, "REMOVED": 0}[course["freshness_state"]]
    duration = str(course.get("estimated_duration") or "").casefold()
    time_efficiency = 4.0 if any(word in duration for word in ("hour", "week")) else 2.5
    cost_efficiency = {"FREE": 5, "SUBSCRIPTION_INCLUDED": 4.5, "FINANCIAL_AID_AVAILABLE": 4, "ONE_TIME": 3, "UNKNOWN": 2}.get(course.get("cost_state"), 2)
    preferred = {str(item).upper().replace(" ", "_") for item in preferences.get("preferred_providers", [])}
    owned = {str(item).upper().replace(" ", "_") for item in preferences.get("subscriptions_owned", [])}
    subscription_covered = bool(owned & {str(v).upper().replace(' ', '_') for v in course.get('subscription_plans', [])}) or (course.get('cost_state') == 'SUBSCRIPTION_INCLUDED' and course['provider'] in owned)
    if subscription_covered:
        cost_efficiency = max(cost_efficiency, 4.5)
    preference_reasons: list[str] = []
    if not coverage:preference_reasons.append('NO_OBSERVED_GAP_COVERAGE')
    preference_adjustment = 0.0
    if course["provider"] in preferred:
        preference_adjustment += 0.25
        preference_reasons.append("PREFERRED_PROVIDER")
    if subscription_covered:
        preference_adjustment += 0.25
        preference_reasons.append("SUBSCRIPTION_OWNED")
    budget = preferences.get("budget")
    budget_exceeded = bool(
        isinstance(budget, (int, float))
        and isinstance(course.get("cost_amount"), (int, float))
        and course["cost_amount"] > budget
        and not subscription_covered
    )
    if budget_exceeded:
        preference_adjustment -= 8.0
        preference_reasons.append("BUDGET_EXCEEDED")
    hours = learning_hours(course)
    max_hours = preferences.get('max_duration_hours')
    if max_hours is None and preferences.get('weekly_hours') and preferences.get('weeks_available'):
        max_hours = preferences['weekly_hours'] * preferences['weeks_available']
    time_blocked = bool(max_hours is not None and (hours is None or hours > max_hours))
    cost = learning_cost(course, preferences)
    unknown_budget_cost = budget is not None and cost is None
    if time_blocked:
        preference_reasons.append('TIME_BUDGET_UNVERIFIED_OR_EXCEEDED')
    if unknown_budget_cost:
        preference_reasons.append('COST_UNVERIFIED_FOR_BUDGET')
    level_unverified=str(course.get('level') or 'UNKNOWN').upper()=='UNKNOWN'
    if level_unverified:preference_reasons.append('LEVEL_UNVERIFIED')
    credential_preference = str(preferences.get("credential_preference") or "NEUTRAL").upper()
    if credential_preference in {"PREFERRED", "HIGH"} and credential_score >= 3:
        preference_adjustment += 0.25
        preference_reasons.append("CREDENTIAL_PREFERENCE_MATCH")
    if preferences.get("self_paced_preference") is True and course.get("self_paced") is True:
        preference_adjustment += 0.15
        preference_reasons.append("SELF_PACED_MATCH")
    learning_styles = {str(item).upper() for item in preferences.get("learning_styles", [])}
    delivery_modes = {str(item).upper() for item in course.get("delivery_modes", [])}
    if learning_styles & delivery_modes:
        preference_adjustment += 0.15
        preference_reasons.append("LEARNING_STYLE_MATCH")
    dimensions = {
        "GAP_COVERAGE": round(coverage * 5, 2), "EMPLOYER_RELEVANCE": round(employer_coverage * 5, 2),
        "LEARNING_DEPTH": min(5.0, 2.5 + len(course.get("curriculum_topics", [])) / 6),
        "PRACTICAL_DEPTH": round(practical, 2), "EVIDENCE_CREATION": round(evidence_value, 2),
        "CREDENTIAL_SIGNAL": credential_score, "PROVIDER_RECOGNITION": _bounded(issuer_recognition),
        "INSTRUCTOR_QUALITY": _bounded(preferences.get("instructor_quality", 3)),
        "CURRICULUM_QUALITY": min(5.0, 2.0 + len(course.get("curriculum_topics", [])) / 5),
        "CANDIDATE_LEVEL_FIT": level_score, "PREREQUISITE_FIT": 5 if level_match != "PREREQUISITE_MISSING" else 0,
        "LANE_BREADTH": _bounded(gap.get("career_breadth")), "JOB_BREADTH": _bounded(gap.get("job_frequency")),
        "TIME_EFFICIENCY": time_efficiency, "COST_EFFICIENCY": cost_efficiency,
        "REDUNDANCY": round(5 - redundancy_penalty, 2), "FRESHNESS": freshness_score,
    }
    four_value = {
        "LearningValue": round((dimensions["GAP_COVERAGE"] + dimensions["LEARNING_DEPTH"] + dimensions["CANDIDATE_LEVEL_FIT"]) / 3, 2),
        "CredentialSignal": credential_score,
        "EmployerRelevance": dimensions["EMPLOYER_RELEVANCE"],
        "EvidenceCreationValue": dimensions["EVIDENCE_CREATION"],
    }
    weighted = round(sum(dimensions.values()) / len(dimensions) * 20 + preference_adjustment - redundancy_penalty * 2, 2)
    if course["freshness_state"] != "CURRENT" or level_match in {"TOO_ADVANCED", "PREREQUISITE_MISSING"}:
        weighted = min(weighted, 49.99)
    evaluation = {
        "schema": "careeros.course-evaluation.v1", "schema_version": "1.0.0",
        "course_evaluation_id": _stable_id("course-evaluation", {"course": course["course_candidate_id"], "objective": objective["objective_id"]}),
        "course_candidate_id": course["course_candidate_id"], "objective_id": objective["objective_id"],
        "gap_id": gap["gap_id"], "dimensions": dimensions, "four_value_model": four_value,
        "credential_signal": credential, "candidate_level_match": level_match,
        "redundancy_class": redundancy["classification"], "overall_routing_score": weighted,
        "ranking_eligible": course["freshness_state"] == "CURRENT" and not level_unverified and level_match not in {"TOO_ADVANCED", "PREREQUISITE_MISSING"} and coverage > 0 and not budget_exceeded and not time_blocked and not unknown_budget_cost and (redundancy['classification'] != 'HIGHLY_REDUNDANT' or gap.get('gap_type') in {'CREDENTIAL', 'CERTIFICATION'}),
        "commercial_adjustment": 0.0, "affiliate_relationship_disregarded": bool(course.get("affiliate_relationship")),
        "preference_alignment": {
            "adjustment": round(preference_adjustment, 2),
            "reasons": preference_reasons,
            "budget_exceeded": budget_exceeded,
            "hard_prerequisites_overridden": False,
        },
        "policy_version": LEARNING_PATH_POLICY_VERSION,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:course-evaluation:v1", evaluation)
    return evaluation, redundancy


def learning_hours(course: dict[str, Any]) -> float | None:
    if isinstance(course.get('duration_hours'), (int, float)):
        return max(0, float(course['duration_hours']))
    text = str(course.get('estimated_duration') or '').casefold()
    iso = re.fullmatch(r'pt(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?',text)
    if iso and any(iso.groups()):return float(iso[1] or 0)+float(iso[2] or 0)/60
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\s*', text)
    return float(match[1]) / (60 if match[2].startswith('min') else 1) if match else None


def learning_cost(course: dict[str, Any], preferences: dict[str, Any]) -> float | None:
    owned = {str(v).upper().replace(' ', '_') for v in preferences.get('subscriptions_owned', [])}
    covered = bool(owned & {str(v).upper().replace(' ', '_') for v in course.get('subscription_plans', [])}) or (course.get('cost_state') == 'SUBSCRIPTION_INCLUDED' and course['provider'] in owned)
    if covered or course.get('cost_state') == 'FREE':
        return 0.0
    amount = course.get('cost_amount')
    if not isinstance(amount, (int, float)) or amount < 0 or not course.get('price_verified_at'):
        return None
    try:
        verified=datetime.fromisoformat(course['price_verified_at'].replace('Z','+00:00'))
        now=datetime.fromisoformat((preferences.get('as_of') or utc_now(None)).replace('Z','+00:00'))
        if verified.tzinfo is None or verified>now or (now-verified).days>30:return None
    except (TypeError,ValueError):return None
    if preferences.get('currency') and course.get('cost_currency') != preferences['currency']:
        return None
    return float(amount)


def build_learning_roi(
    evaluation: dict[str, Any], gap: dict[str, Any], *, jobs_currently_blocked: int = 0,
    jobs_partially_affected: int = 0,
) -> dict[str, Any]:
    values = evaluation["four_value_model"]
    benefit = (
        gap["priority_score"] * 0.35 + values["LearningValue"] * 10 + values["EmployerRelevance"] * 8
        + values["EvidenceCreationValue"] * 8 + values["CredentialSignal"] * 4
        + min(10, jobs_currently_blocked * 2 + jobs_partially_affected)
    )
    costs = (5 - evaluation["dimensions"]["TIME_EFFICIENCY"]) * 5 + (5 - evaluation["dimensions"]["COST_EFFICIENCY"]) * 5
    score = round(max(0, min(100, benefit - costs)), 2)
    roi = {
        "schema": "careeros.learning-roi.v1", "schema_version": "1.0.0",
        "learning_roi_id": _stable_id("learning-roi", evaluation["course_evaluation_id"]),
        "course_evaluation_id": evaluation["course_evaluation_id"], "gap_id": gap["gap_id"],
        "gap_importance": gap["priority_score"], "gap_recurrence": gap["recurrence_count"],
        "jobs_currently_blocked_by_gap": jobs_currently_blocked,
        "jobs_partially_affected": jobs_partially_affected,
        "potential_qualification_impact": "POTENTIAL_QUALIFICATION_IMPACT",
        "benefit_score": round(benefit, 2), "cost_score": round(costs, 2), "roi_score": score,
        "roi_class": _classify(score, ROI_CLASSES), "employment_outcome_promised": False,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:learning-roi:v1", roi)
    return roi


def build_evidence_creation_plan(
    *, learning_step_id: str, target_evidence: str, project_type: str, objective: str,
    required_tools: list[str], expected_actions: list[str], expected_artifacts: list[str],
    verification_method: list[str], public_portfolio_state: str = "REVIEW_REQUIRED",
    resume_impact: list[str] | None = None, interview_impact: list[str] | None = None,
) -> dict[str, Any]:
    plan = {
        "schema": "careeros.evidence-creation-plan.v1", "schema_version": "1.0.0",
        "plan_id": _stable_id("evidence-creation-plan", {"step": learning_step_id, "target": target_evidence}),
        "learning_step_id": learning_step_id, "target_evidence": target_evidence,
        "project_type": project_type, "objective": objective, "required_tools": required_tools,
        "expected_actions": expected_actions, "expected_artifacts": expected_artifacts,
        "verification_method": verification_method, "public_portfolio_state": public_portfolio_state,
        "canonical_promotion_state": "PROPOSED_EVIDENCE_REVIEW_REQUIRED",
        "resume_impact": resume_impact or ["EVIDENCE_EXPANSION"],
        "interview_impact": interview_impact or ["TECHNICAL_WALKTHROUGH_DEPTH"],
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:evidence-creation-plan:v1", plan)
    return plan


def qualification_impact(
    gap: dict[str, Any], *, employer_allows_equivalence: bool = False,
    planned_evidence: bool = True,
) -> dict[str, Any]:
    mandatory_experience = gap.get("gap_type") == "EXPERIENCE" and int(gap.get("hard_gap_frequency") or 0) > 0
    if mandatory_experience and not employer_allows_equivalence:
        return {
            "state": "READINESS_ONLY", "requirement_state_after_learning": "UNSATISFIED",
            "reason": "Learning cannot substitute for mandatory professional experience.",
            "mandatory_professional_experience": True, "employer_allows_equivalence": False,
        }
    return {
        "state": "POTENTIAL_QUALIFICATION_IMPACT" if planned_evidence else "NO_EXPECTED_CHANGE",
        "requirement_state_after_learning": "REQUIRES_REQUALIFICATION",
        "reason": "New reviewed evidence may improve qualification but is not pre-approved competency.",
        "mandatory_professional_experience": mandatory_experience,
        "employer_allows_equivalence": employer_allows_equivalence,
    }


def build_learning_path_impact(
    *, learning_path_id: str, lanes: dict[str, list[str]], qualification_impacts: list[dict[str, Any]],
) -> dict[str, Any]:
    lane_impacts = {}
    for lane, values in lanes.items():
        states = [value for value in values if value in IMPACT_STATES]
        lane_impacts[lane] = states or ["NO_EXPECTED_CHANGE"]
    record = {
        "schema": "careeros.learning-path-impact.v1", "schema_version": "1.0.0",
        "learning_path_id": learning_path_id, "lane_impacts": lane_impacts,
        "qualification_impacts": qualification_impacts,
        "canonical_mutation": False, "requires_evidence_review": True,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:learning-path-impact:v1", record)
    return record


def optimize_minimal_path(
    *, candidate_profile_id: str, role_family_id: str, target_role_ids: list[str],
    objectives: list[dict[str, Any]], candidates: list[dict[str, Any]], evaluations: list[dict[str, Any]],
    evidence_plan_factory: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
    estimated_total_time: str = "UNKNOWN", estimated_total_cost: str = "UNKNOWN",
    timestamp: str | None = None,
    preferences: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    candidate_index = {item["course_candidate_id"]: item for item in candidates}
    objective_index = {item["objective_id"]: item for item in objectives}
    preferences = preferences or {}
    best_by_objective: dict[str, dict[str, Any]] = {}
    reserved: set[str] = set()
    cost_total = hours_total = 0.0
    for objective in objectives:
        options = sorted([e for e in evaluations if e['objective_id'] == objective['objective_id'] and e['ranking_eligible']], key=lambda e: (e['course_candidate_id'] not in reserved, -e['overall_routing_score'], e['course_candidate_id']))
        for evaluation in options:
            candidate = candidate_index[evaluation['course_candidate_id']]
            cost, hours = learning_cost(candidate, preferences), learning_hours(candidate)
            add_cost, add_hours = (0, 0) if candidate['course_candidate_id'] in reserved else (cost, hours)
            max_hours = preferences.get('max_duration_hours')
            if max_hours is None and preferences.get('weekly_hours') and preferences.get('weeks_available'):
                max_hours = preferences['weekly_hours'] * preferences['weeks_available']
            if preferences.get('budget') is not None and (add_cost is None or cost_total + add_cost > preferences['budget']):
                continue
            if max_hours is not None and (add_hours is None or hours_total + add_hours > max_hours):
                continue
            best_by_objective[objective['objective_id']] = evaluation
            reserved.add(candidate['course_candidate_id'])
            cost_total += add_cost or 0
            hours_total += add_hours or 0
            break
    steps: list[dict[str, Any]] = []
    evidence_plans: list[dict[str, Any]] = []
    selected_courses: set[str] = set()
    for index, objective in enumerate(objectives, 1):
        evaluation = best_by_objective.get(objective["objective_id"])
        if not evaluation:
            continue
        course = candidate_index[evaluation["course_candidate_id"]]
        if course["course_candidate_id"] not in selected_courses:
            step_id = _stable_id("learning-step", {"objective": objective["objective_id"], "course": course["course_candidate_id"], "snapshot": sha256_value(course)})
            step = {
                "schema": "careeros.learning-step.v1", "schema_version": "1.0.0",
                "learning_step_id": step_id, "sequence": len(steps) + 1, "step_type": {'KNOWLEDGE_RESOURCE':'REVIEW','PRACTICAL_PROJECT':'PROJECT','LAB_PLATFORM':'LAB','INDUSTRY_CERTIFICATION_PREP':'CERTIFICATION_PREP','INDUSTRY_CERTIFICATION':'CERTIFICATION_ATTEMPT'}.get(course['course_type'], 'COURSE'),
                "objective_ids": [objective["objective_id"]], "course_candidate_id": course["course_candidate_id"],
                "title": course["title"], "completion_condition": "Finish the learning step, then keep a piece of work that shows what you can do. Completing a course alone does not prove the skill.",
                "prerequisites": course["prerequisites"], "estimated_time": course["estimated_duration"],
                "estimated_cost": course["cost_state"], "status": "PROPOSED",
            }
            SchemaRegistry(schema_dir()).validate("urn:careeros:schema:learning-step:v1", step)
            steps.append(step)
            selected_courses.add(course["course_candidate_id"])
            if evidence_plan_factory:
                evidence_plans.append(evidence_plan_factory(step, objective))
        else:
            existing = next(item for item in steps if item.get("course_candidate_id") == course["course_candidate_id"])
            existing["objective_ids"] = sorted(set(existing["objective_ids"] + [objective["objective_id"]]))
            if evidence_plan_factory:evidence_plans.append(evidence_plan_factory(existing,objective))
    for step in steps:
        SchemaRegistry(schema_dir()).validate("urn:careeros:schema:learning-step:v1", step)
    material = {"candidate": candidate_profile_id, "role": role_family_id, "objectives": [item["objective_id"] for item in objectives], "courses": {key:sha256_value(candidate_index[key]) for key in sorted(selected_courses)}}
    path_id = _stable_id("learning-path", material)
    path = {
        "schema": "careeros.learning-path.v1", "schema_version": "1.0.0",
        "learning_path_id": path_id, "candidate_profile_id": candidate_profile_id,
        "role_family_id": role_family_id, "target_role_ids": target_role_ids,
        "objective_ids": [item["objective_id"] for item in objectives],
        "steps": [item["learning_step_id"] for item in steps], "estimated_total_time": estimated_total_time,
        "estimated_total_cost": estimated_total_cost,
        "expected_gap_coverage": sorted({objective["gap_id"] for objective in objectives if objective["objective_id"] in best_by_objective}),
        "expected_lane_impact": ["EVIDENCE_EXPANSION", "SKILL_STRENGTHENING"] if steps else ["NO_EXPECTED_CHANGE"],
        "expected_job_impact": ["POTENTIAL_QUALIFICATION_IMPACT"] if steps else ["NO_EXPECTED_CHANGE"],
        "path_status": "PROPOSED", "created_at": utc_now(timestamp), "last_verified_at": utc_now(timestamp),
        "optimization": {"strategy": "MINIMUM_ONE_ELIGIBLE_COURSE_PER_OBJECTIVE_WITH_COURSE_REUSE", "course_count": len(selected_courses), "course_hoarding": False},
        "policy_version": LEARNING_PATH_POLICY_VERSION,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:learning-path:v1", path)
    return path, steps, evidence_plans


def propose_completion_evidence(
    *, learning_path: dict[str, Any], course: dict[str, Any], completion_artifacts: list[dict[str, Any]],
    candidate_self_report: str | None = None, timestamp: str | None = None,
) -> dict[str, Any]:
    """Return a review packet; never mutate canonical skill or credential records."""
    return {
        "schema": "careeros.learning-completion-evidence-proposal.v1",
        "proposal_id": _stable_id("learning-completion", {"path": learning_path["learning_path_id"], "course": course["course_candidate_id"], "artifacts": completion_artifacts}),
        "learning_path_id": learning_path["learning_path_id"], "course_candidate_id": course["course_candidate_id"],
        "proposed_evidence": completion_artifacts,
        "course_completion_claim": candidate_self_report,
        "competency_claim_state": "NOT_ESTABLISHED_BY_COMPLETION_ALONE",
        "canonical_promotion_state": "REVIEW_REQUIRED", "canonical_mutations": [],
        "created_at": utc_now(timestamp), "policy_version": LEARNING_PATH_POLICY_VERSION,
    }


def compare_provider_options(evaluations: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_index = {item["course_candidate_id"]: item for item in candidates}
    eligible = [item for item in evaluations if item["ranking_eligible"]]
    def best(key: Callable[[dict[str, Any]], float]) -> str | None:
        if not eligible:
            return None
        return max(eligible, key=lambda item: (key(item), item["overall_routing_score"], item["course_candidate_id"]))["course_candidate_id"]
    return {
        "BEST_OVERALL": best(lambda item: item["overall_routing_score"]),
        "BEST_LOW_COST": best(lambda item: item["dimensions"]["COST_EFFICIENCY"]),
        "BEST_CREDENTIAL_SIGNAL": best(lambda item: item["four_value_model"]["CredentialSignal"]),
        "BEST_PRACTICAL_DEPTH": best(lambda item: item["dimensions"]["PRACTICAL_DEPTH"]),
        "BEST_FAST_OPTION": best(lambda item: item["dimensions"]["TIME_EFFICIENCY"]),
        "providers_considered": sorted({candidate_index[item["course_candidate_id"]]["provider"] for item in evaluations}),
        "affiliate_influence": 0,
    }


def learning_path_qa(
    *, gaps: list[dict[str, Any]], objectives: list[dict[str, Any]], candidates: list[dict[str, Any]],
    evaluations: list[dict[str, Any]], path: dict[str, Any], evidence_plans: list[dict[str, Any]],
    qualification_impacts: list[dict[str, Any]] | None = None, privacy_findings: int = 0,
) -> dict[str, Any]:
    gap_ids = {item["gap_id"] for item in gaps}
    objective_ids = {item["objective_id"] for item in objectives}
    candidate_ids = {item["course_candidate_id"] for item in candidates}
    gates = {
        "GAP_TRACE": all(item["gap_id"] in gap_ids for item in objectives),
        "COURSE_FRESHNESS": all(item["freshness_state"] == "CURRENT" for item in candidates if item["course_candidate_id"] in {e["course_candidate_id"] for e in evaluations if e["ranking_eligible"]}),
        "PROVIDER_NEUTRALITY": all(item.get("commercial_adjustment") == 0 for item in evaluations),
        "REDUNDANCY": all(item.get("redundancy_class") in REDUNDANCY_CLASSES for item in evaluations),
        "CREDENTIAL_CLASSIFICATION": all(item.get("credential_signal") in CREDENTIAL_SIGNALS for item in evaluations),
        "CANDIDATE_LEVEL_MATCH": all(item.get("candidate_level_match") in LEVEL_MATCHES for item in evaluations),
        "EVIDENCE_CREATION": bool(evidence_plans) and all(item.get("canonical_promotion_state") == "PROPOSED_EVIDENCE_REVIEW_REQUIRED" for item in evidence_plans),
        "LEARNING_ROI": all(0 <= item.get("overall_routing_score", -1) <= 100 for item in evaluations),
        "QUALIFICATION_BOUNDARY": all(
            not (
                item.get("mandatory_professional_experience") is True
                and item.get("employer_allows_equivalence") is not True
                and item.get("requirement_state_after_learning") == "SATISFIED"
            )
            for item in (qualification_impacts or [])
        ),
        "PRIVACY": privacy_findings == 0,
        "COMMERCIAL_INDEPENDENCE": all(item.get("commercial_adjustment") == 0 for item in evaluations),
        "PATH_REFERENCES": set(path.get("objective_ids", [])) <= objective_ids and all(item in candidate_ids for item in {e["course_candidate_id"] for e in evaluations}),
    }
    return {"schema": "careeros.learning-path-qa.v1", "status": "PASS" if all(gates.values()) else "FAIL", "gates": gates}


class ProviderAdapterV1(Protocol):
    provider: str
    capabilities: frozenset[str]

    def search(self, query: str) -> list[dict[str, Any]]: ...
    def detail(self, course_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class CatalogProviderAdapter:
    """Adapter for current catalog evidence supplied by an external reader.

    The package never sends candidate PII and does not require unsupported
    scraping.  Callers provide provider-specific search/detail functions.
    """

    provider: str
    search_fn: Callable[[str], list[dict[str, Any]]]
    detail_fn: Callable[[str], dict[str, Any] | None]
    capabilities: frozenset[str] = frozenset({"SEARCH", "DETAIL", "FRESHNESS"})

    def __post_init__(self) -> None:
        normalized = self.provider.upper().replace(" ", "_")
        if not normalized or not self.capabilities <= PROVIDER_CAPABILITIES:
            raise ValueError("invalid provider adapter")
        object.__setattr__(self, "provider", normalized)

    def search(self, query: str) -> list[dict[str, Any]]:
        # Generic gap language only; candidate identity is forbidden.
        if re.search(r"@|\b(?:phone|email|candidate_profile_id)\b", query, re.I):
            raise PermissionError("provider search query contains candidate-specific data")
        return [build_course_candidate({**item, "provider": self.provider}) for item in self.search_fn(query)]

    def detail(self, course_id: str) -> dict[str, Any] | None:
        item = self.detail_fn(course_id)
        return build_course_candidate({**item, "provider": self.provider}) if item else None

    def descriptor(self) -> dict[str, Any]:
        record = {
            "schema": "careeros.provider-adapter.v1", "schema_version": "1.0.0",
            "provider": self.provider, "capabilities": sorted(self.capabilities),
            "requires_candidate_pii": False, "core_scraping_required": False,
        }
        SchemaRegistry(schema_dir()).validate("urn:careeros:schema:provider-adapter:v1", record)
        return record


def default_provider_adapters(catalogs: dict[str, list[dict[str, Any]]]) -> dict[str, CatalogProviderAdapter]:
    """Create provider-neutral adapters for caller-supplied current snapshots."""
    adapters = {}
    for provider in ("COURSERA", "LINKEDIN_LEARNING", "UDEMY"):
        records = list(catalogs.get(provider, []))
        index = {str(item.get("course_id")): item for item in records}
        adapters[provider] = CatalogProviderAdapter(
            provider=provider,
            search_fn=lambda query, rows=records: [item for item in rows if _tokens(query) & _tokens([item.get("title"), item.get("skill_topics", []), item.get("curriculum_topics", [])])],
            detail_fn=lambda course_id, rows=index: rows.get(str(course_id)),
            capabilities=frozenset({"SEARCH", "DETAIL", "CURRICULUM", "CREDENTIAL_TYPE", "DURATION", "COST", "FRESHNESS"}),
        )
    return adapters
