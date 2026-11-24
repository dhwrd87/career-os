"""Portable recruiter-facing resume freshness and public-quality governance.

The functions in this module are intentionally candidate-neutral.  They audit
build inputs and rendered content; they never mutate canonical career facts.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from careeros.core.io import sha256_value


FRESHNESS_STATUSES = (
    "STALE_CANONICAL_REVISION",
    "STALE_EVIDENCE",
    "STALE_SKILLS",
    "STALE_CREDENTIALS",
    "STALE_ROLE_FAMILY",
    "STALE_POLICY",
    "STALE_JOB_SNAPSHOT",
)
OMISSION_REASONS = {
    "OMITTED_REDUNDANT",
    "OMITTED_LOW_RELEVANCE",
    "OMITTED_SPACE",
    "OMITTED_PRIVACY",
    "OMITTED_JOB_MISMATCH",
    "OMITTED_WEAK_VERIFICATION",
    "OMITTED_OTHER",
}
PUBLIC_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}
VERIFIED_STATES = {"VERIFIED", "DOCUMENT_BACKED", "USER_CONFIRMED"}
FORBIDDEN_PUBLIC_LABELS = (
    "base resume",
    "master recruiter resume",
    "review required",
    "career os",
    "canonical",
    "evidence class",
    "lane base",
    "internal",
    "generated",
    "draft",
)
ABSTRACT_COPY = (
    "professional foundation",
    "communication and documentation",
    "operational discipline",
    "technical preparation",
    "security exposure",
    "practical experience",
)


def _record_hash(records: Iterable[dict[str, Any]]) -> str:
    return sha256_value(sorted(records, key=lambda item: item.get("record_id", "")))


def build_freshness_contract(
    profile: dict[str, Any],
    profile_manifest: dict[str, Any],
    role_family: dict[str, Any],
    storyline: dict[str, Any],
    *,
    canonical_revision: int,
    compiler_version: str,
    editorial_policy_version: str,
    build_timestamp: str,
    jd_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture every state surface that can make a public resume stale."""
    return {
        "schema": "careeros.canonical-evidence-freshness.v1",
        "schema_version": "1.0.0",
        "candidate_profile_id": profile["profile_id"],
        "canonical_revision": canonical_revision,
        "canonical_profile_hash": profile_manifest["profile_hash"],
        "evidence_bundle_hash": _record_hash(profile.get("evidence", [])),
        "skill_registry_hash": _record_hash(profile.get("skills", [])),
        "credential_registry_hash": _record_hash(profile.get("credentials", [])),
        "role_family_version": sha256_value(role_family),
        "storyline_version": sha256_value(storyline),
        "jd_snapshot_hash": (jd_snapshot or {}).get("content_hash"),
        "compiler_version": compiler_version,
        "editorial_policy_version": editorial_policy_version,
        "build_timestamp": build_timestamp,
    }


def compare_freshness(
    built: dict[str, Any], current: dict[str, Any], *, historical_mode: bool = False,
) -> dict[str, Any]:
    checks = (
        ("canonical_revision", "STALE_CANONICAL_REVISION"),
        ("canonical_profile_hash", "STALE_CANONICAL_REVISION"),
        ("evidence_bundle_hash", "STALE_EVIDENCE"),
        ("skill_registry_hash", "STALE_SKILLS"),
        ("credential_registry_hash", "STALE_CREDENTIALS"),
        ("role_family_version", "STALE_ROLE_FAMILY"),
        ("editorial_policy_version", "STALE_POLICY"),
        ("jd_snapshot_hash", "STALE_JOB_SNAPSHOT"),
    )
    stale = []
    for field, status in checks:
        if built.get(field) != current.get(field) and status not in stale:
            stale.append(status)
    return {
        "status": "CURRENT" if not stale else stale[0],
        "stale_states": stale,
        "acceptance_allowed": not stale or historical_mode,
        "historical_mode": historical_mode,
    }


def evidence_utility(
    evidence: dict[str, Any], *, lane_relevance: float = 0.0, job_relevance: float = 0.0,
    space_cost: float = 0.25, redundancy_risk: float = 0.0,
) -> dict[str, Any]:
    """Route evidence; never score a person or infer qualification."""
    completeness_fields = ("actions", "context", "tools_methods", "deliverables", "outcomes")
    completeness = sum(bool(evidence.get(field)) for field in completeness_fields) / len(completeness_fields)
    verification = 1.0 if evidence.get("verification_state") in VERIFIED_STATES else 0.35
    professional = 1.0 if evidence.get("employment_ids") else 0.55
    outcome = 1.0 if evidence.get("outcomes") else 0.25
    metrics = evidence.get("metrics", [])
    metric_strength = 1.0 if any(item.get("public_use_allowed") for item in metrics) else 0.25
    public = 1.0 if evidence.get("visibility") in PUBLIC_VISIBILITY else 0.0
    distinct = 1.0 if evidence.get("tools_methods") or evidence.get("deliverables") else 0.45
    recency = float(evidence.get("recency_score", 0.5))
    components = {
        "canonical_completeness": completeness,
        "verification_strength": verification,
        "professional_context_strength": professional,
        "lane_relevance": max(0.0, min(1.0, lane_relevance)),
        "job_relevance": max(0.0, min(1.0, job_relevance)),
        "outcome_strength": outcome,
        "metric_scale_strength": metric_strength,
        "recency": max(0.0, min(1.0, recency)),
        "distinctiveness": distinct,
        "public_usability": public,
        "space_cost": max(0.0, min(1.0, space_cost)),
        "redundancy_risk": max(0.0, min(1.0, redundancy_risk)),
    }
    positive = sum(components[key] for key in components if key not in {"space_cost", "redundancy_risk"}) / 10
    utility = max(0.0, positive - 0.12 * components["space_cost"] - 0.18 * components["redundancy_risk"])
    return {
        "schema": "careeros.evidence-utility.v1",
        "evidence_id": evidence["record_id"],
        "components": {key: round(value, 3) for key, value in components.items()},
        "utility": round(utility, 3),
        "routing_tier": "HIGH" if utility >= 0.62 else ("MEDIUM" if utility >= 0.4 else "LOW"),
        "candidate_score": False,
    }


def new_evidence_utilization(
    previous_profile: dict[str, Any] | None,
    current_profile: dict[str, Any],
    used_evidence_ids: Iterable[str],
    omission_dispositions: dict[str, str],
    *,
    relevant_evidence_ids: Iterable[str] = (),
) -> dict[str, Any]:
    previous = {item["record_id"]: item for item in (previous_profile or {}).get("evidence", [])}
    current = {item["record_id"]: item for item in current_profile.get("evidence", [])}
    used = set(used_evidence_ids)
    relevant = set(relevant_evidence_ids)
    items = []
    silent = []
    for record_id, record in current.items():
        prior = previous.get(record_id)
        change = None
        if prior is None:
            change = "NEWLY_ADDED"
        elif sha256_value(prior) != sha256_value(record):
            if prior.get("visibility") != record.get("visibility"):
                change = "CHANGED_VISIBILITY"
            elif prior.get("verification_state") != record.get("verification_state"):
                change = "NEW_ARTIFACT_VERIFICATION"
            elif prior.get("metrics") != record.get("metrics"):
                change = "NEW_PUBLIC_METRIC"
            elif prior.get("outcomes") != record.get("outcomes"):
                change = "STRENGTHENED_OUTCOME"
            else:
                change = "STRENGTHENED_EVIDENCE"
        if not change:
            continue
        utility = evidence_utility(record, lane_relevance=1.0 if record_id in relevant else 0.25)
        disposition = "USED" if record_id in used else omission_dispositions.get(record_id)
        high_value = utility["routing_tier"] == "HIGH" and record_id in relevant and record.get("visibility") in PUBLIC_VISIBILITY
        if disposition is None:
            disposition = "OMITTED_OTHER"
            if high_value:
                silent.append(record_id)
        elif disposition != "USED" and disposition not in OMISSION_REASONS:
            raise ValueError(f"invalid evidence omission disposition: {disposition}")
        items.append({
            "evidence_id": record_id,
            "change_class": change,
            "high_value": high_value,
            "disposition": disposition,
            "utility": utility,
        })
    for collection, change_class in (("skills", "NEW_SKILL_TOOL"), ("employment", "CORRECTED_EMPLOYMENT_FACT")):
        old_records = {item["record_id"]: item for item in (previous_profile or {}).get(collection, [])}
        for record in current_profile.get(collection, []):
            prior = old_records.get(record["record_id"])
            if prior is not None and sha256_value(prior) == sha256_value(record):
                continue
            evidence_ids = set(record.get("evidence_ids", []))
            relevant_change = bool(evidence_ids & relevant)
            disposition = "USED" if evidence_ids & used else omission_dispositions.get(record["record_id"])
            if disposition is None:
                disposition = next((omission_dispositions[item] for item in evidence_ids if item in omission_dispositions), "OMITTED_OTHER")
            high_value = bool(relevant_change and record.get("visibility") in PUBLIC_VISIBILITY)
            if high_value and disposition == "OMITTED_OTHER":
                silent.append(record["record_id"])
            items.append({
                "evidence_id": record["record_id"], "change_class": change_class,
                "high_value": high_value, "disposition": disposition,
                "utility": {"routing_tier": "HIGH" if high_value else "MEDIUM", "candidate_score": False},
            })
    return {
        "schema": "careeros.new-evidence-utilization.v1",
        "items": items,
        "high_value_silent_omissions": silent,
        "status": "FAIL" if silent else "PASS",
    }


def professional_history_sufficiency(
    employment: list[dict[str, Any]], content_employment: list[dict[str, Any]],
    omission_rationales: dict[str, str] | None = None,
) -> dict[str, Any]:
    omission_rationales = omission_rationales or {}
    displayed = {item["record_id"]: item for item in content_employment}
    decisions = []
    failures = []
    for role in employment:
        record_id = role["record_id"]
        rendered = displayed.get(record_id)
        if rendered:
            bullets = [item for item in rendered.get("bullets", []) if str(item.get("text", "")).strip()]
            minimal_fact = str(rendered.get("minimal_fact", "")).strip()
            mode = rendered.get("display_mode") or ("FULL" if len(bullets) >= 2 else "COMPACT")
            if not bullets and not minimal_fact:
                failures.append({"code": "EMPTY_EXPERIENCE_ENTRY", "record_id": record_id})
            decisions.append({"employment_id": record_id, "classification": mode, "rationale": "Rendered with supported content"})
            continue
        rationale = omission_rationales.get(record_id)
        if not rationale:
            failures.append({"code": "MISSING_OMISSION_RATIONALE", "record_id": record_id})
        start = role.get("start_year")
        end = role.get("end_year")
        try:
            duration = (int(end) if end not in {None, "PRESENT"} else int(start) + 3) - int(start)
        except (TypeError, ValueError):
            duration = 0
        if duration >= 3 and role.get("evidence_ids"):
            failures.append({"code": "LONG_RUNNING_ROLE_OMITTED", "record_id": record_id})
        decisions.append({"employment_id": record_id, "classification": "OMITTED", "rationale": rationale})
    return {
        "schema": "careeros.professional-history-sufficiency.v1",
        "decisions": decisions,
        "failures": failures,
        "status": "FAIL" if failures else "PASS",
    }


def public_artifact_title(artifact_kind: str, role_label: str | None = None) -> str:
    role = re.sub(r"\s+", " ", str(role_label or "").strip())
    if role:
        return role
    if artifact_kind == "MASTER_RECRUITER":
        return "Professional Experience | Technical Projects & Operations"
    return "Professional Resume"


def public_label_leaks(text: str) -> list[str]:
    lowered = text.casefold()
    lines = {re.sub(r"\s+", " ", line.strip().casefold()) for line in text.splitlines() if line.strip()}
    leaks = []
    for item in FORBIDDEN_PUBLIC_LABELS:
        if " " in item:
            found = item in lowered
        elif item in {"internal", "generated", "draft"}:
            found = item in lines
        else:
            found = re.search(rf"\b{re.escape(item)}\b", lowered) is not None
        if found:
            leaks.append(item)
    return leaks


def targeted_resume_delta(base: dict[str, Any], targeted: dict[str, Any]) -> dict[str, Any]:
    def bullet_text(content: dict[str, Any]) -> list[str]:
        return [
            item.get("text", "")
            for section in [*content.get("employment", []), *content.get("projects", [])]
            for item in section.get("bullets", [])
        ]

    dimensions = {
        "summary_language": base.get("summary") != targeted.get("summary"),
        "bullet_selection_or_rendering": bullet_text(base) != bullet_text(targeted),
        "skill_ordering": [item.get("record_id") for item in base.get("skills", [])] != [item.get("record_id") for item in targeted.get("skills", [])],
        "project_ordering": [item.get("record_id") for item in base.get("projects", [])] != [item.get("record_id") for item in targeted.get("projects", [])],
        "professional_emphasis": [item.get("record_id") for item in base.get("employment", [])] != [item.get("record_id") for item in targeted.get("employment", [])],
        "section_ordering": base.get("section_order") != targeted.get("section_order"),
    }
    changed = sum(dimensions.values())
    if changed >= 4:
        status = "MATERIAL_DELTA"
    elif changed >= 2:
        status = "SUFFICIENT_DELTA"
    elif changed == 1:
        status = "MINIMAL_DELTA"
    else:
        status = "NO_MEANINGFUL_DELTA"
    return {
        "schema": "careeros.targeted-resume-delta.v1",
        "status": status,
        "acceptance_allowed": status in {"MATERIAL_DELTA", "SUFFICIENT_DELTA"},
        "changed_dimensions": [key for key, value in dimensions.items() if value],
        "dimensions": dimensions,
    }


def recruiter_copy_specificity(content: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    text = "\n".join([
        str(content.get("summary", "")),
        *[
            str(bullet.get("text", ""))
            for section in [*content.get("employment", []), *content.get("projects", [])]
            for bullet in section.get("bullets", [])
        ],
    ])
    lowered = text.casefold()
    abstract_hits = [phrase for phrase in ABSTRACT_COPY if phrase in lowered]
    concrete_available = any(
        record.get("tools_methods") or record.get("deliverables") or record.get("metrics")
        for record in profile.get("evidence", [])
        if record.get("visibility") in PUBLIC_VISIBILITY
    )
    fail = len(abstract_hits) >= 2 and concrete_available
    return {
        "schema": "careeros.recruiter-copy-specificity.v1",
        "status": "FAIL" if fail else "PASS",
        "abstract_phrases": abstract_hits,
        "concrete_evidence_available": concrete_available,
    }


def credential_opportunities(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"credential_id": item["record_id"], "diagnostic": "HIGH_VALUE_CREDENTIAL_VERIFICATION_PENDING"}
        for item in profile.get("credentials", [])
        if item.get("visibility") in PUBLIC_VISIBILITY
        and item.get("credential_state") in {"COMPLETED", "ACTIVE", "CLAIMED_COMPLETE"}
        and item.get("verification_state") not in VERIFIED_STATES
    ]


def career_advancement_signals(evidence: dict[str, Any]) -> list[str]:
    signals = []
    if evidence.get("tools_methods") or evidence.get("deliverables"):
        signals.append("IMMEDIATE_ROLE_READINESS")
    if evidence.get("employment_ids"):
        signals.append("PROFESSIONAL_MATURITY")
    if evidence.get("project_ids"):
        signals.extend(["BRIDGE_ROLE_READINESS", "TECHNICAL_GROWTH_TRAJECTORY"])
    return list(dict.fromkeys(signals)) or ["FUTURE_PROGRESSION_POTENTIAL"]
