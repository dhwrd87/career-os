"""Governed, descriptive career-conversion learning.

Learning is derived only from recorded opportunities, immutable application
events, qualification decisions, and artifact lineage.  The module never
backfills history, turns silence into rejection, or mutates a policy.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from careeros.application_state import validate_event_log
from careeros.core.io import sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir, utc_now


LEARNING_POLICY_VERSION = "career-conversion-learning-v1"
MATURITY_STATES = {"INSUFFICIENT", "EARLY", "DEVELOPING", "MATURE", "STALE"}
PROVENANCE_CLASSES = {"OBSERVED_EVENT", "HUMAN_CONFIRMED", "MIGRATED_LEGACY_EVENT", "UNKNOWN"}
TERMINAL_EVENTS = {"REJECTED", "WITHDRAWN", "OFFER_ACCEPTED", "OFFER_DECLINED", "ROLE_CLOSED", "NO_RESPONSE_CLOSED"}
PROGRESSION_EVENTS = {
    "EMPLOYER_RESPONSE", "INTERVIEW_INVITED", "INTERVIEW_SCHEDULED", "INTERVIEW_COMPLETED",
    "OFFER_RECEIVED", "OFFER_ACCEPTED", "OFFER_DECLINED",
}
RESPONSE_EVENTS = PROGRESSION_EVENTS | {"REJECTED"}
OUTCOME_LABELS = {
    "SUBMITTED": "APPLIED", "EMPLOYER_RESPONSE": "SCREEN", "INTERVIEW_INVITED": "SCREEN",
    "INTERVIEW_SCHEDULED": "INTERVIEW", "INTERVIEW_COMPLETED": "INTERVIEW",
    "REJECTED": "REJECTED", "WITHDRAWN": "WITHDRAWN", "OFFER_RECEIVED": "OFFER",
    "OFFER_ACCEPTED": "OFFER_ACCEPTED", "OFFER_DECLINED": "OFFER_DECLINED",
    "ROLE_CLOSED": "ROLE_CLOSED", "NO_RESPONSE_CLOSED": "NO_RESPONSE",
}
CAPITAL_CATEGORIES = {
    "TECHNICAL", "OPERATIONS", "LEADERSHIP", "CUSTOMER", "DOMAIN", "CREDENTIAL",
    "PORTFOLIO", "TOOL", "PROCESS", "COMMUNICATION",
}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _days_between(first: Any, second: Any) -> float | None:
    left, right = _parse_time(first), _parse_time(second)
    if not left or not right or right < left:
        return None
    return round((right - left).total_seconds() / 86400, 2)


def _tokens(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        value = " ".join(map(str, value))
    return {
        token for token in re.findall(r"[a-z0-9+#.]+", str(value or "").casefold())
        if len(token) > 2 and token not in {"and", "for", "the", "with", "from", "into", "that"}
    }


def default_maturity_policy() -> dict[str, Any]:
    """Return configurable operating thresholds, not statistical claims."""
    return {
        "policy_version": LEARNING_POLICY_VERSION,
        "minimums": {
            "EARLY": {"sample_count": 5, "known_outcomes": 2, "window_days": 7},
            "DEVELOPING": {"sample_count": 15, "known_outcomes": 5, "window_days": 30, "outcome_diversity": 2},
            "MATURE": {"sample_count": 30, "known_outcomes": 12, "window_days": 60, "outcome_diversity": 3, "comparability_ratio": 0.6},
        },
        "stale_after_days": 365,
        "interpretation": "Operational maturity for descriptive review; not statistical significance or causal identification.",
    }


def _event_provenance(event: dict[str, Any]) -> str:
    source = str(event.get("source") or "").upper()
    if source == "MIGRATED_LEGACY_STATE":
        return "MIGRATED_LEGACY_EVENT"
    if event.get("human_confirmed") is True:
        return "HUMAN_CONFIRMED"
    if event.get("event_id") and event.get("recorded_at") and event.get("source"):
        return "OBSERVED_EVENT"
    return "UNKNOWN"


def derive_observed_application(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Project one real submitted application without inferring missing outcomes."""
    if not events or validate_event_log(events)["status"] != "PASS":
        return None
    submitted = next((item for item in events if item.get("event_type") == "SUBMITTED"), None)
    if not submitted:
        return None
    lineage = submitted.get("submission_lineage") or {}
    if not lineage.get("resume_sha256") or not lineage.get("job_snapshot_hash"):
        return None
    observed = []
    provenance = []
    for event in events:
        label = OUTCOME_LABELS.get(event.get("event_type"))
        if label:
            observed.append(label)
            provenance.append({
                "event_id": event["event_id"], "event_type": event["event_type"],
                "outcome": label, "provenance": _event_provenance(event),
                "occurred_at": event.get("occurred_at"),
            })
        if event.get("event_type") == "INTERVIEW_COMPLETED" and any("FINAL" in str(ref).upper() for ref in event.get("evidence_refs", [])):
            observed.append("FINAL")
    terminal = next((item for item in reversed(events) if item.get("event_type") in TERMINAL_EVENTS), None)
    offer = next((item for item in events if item.get("event_type") in {"OFFER_RECEIVED", "OFFER_ACCEPTED", "OFFER_DECLINED"}), None)
    interview = next((item for item in events if item.get("event_type") in {"INTERVIEW_SCHEDULED", "INTERVIEW_COMPLETED"}), None)
    response = next((item for item in events if item.get("event_type") in RESPONSE_EVENTS), None)
    return {
        "application_id": submitted["application_id"],
        "submitted_at": submitted.get("occurred_at"),
        "observed_outcomes": list(dict.fromkeys(observed)),
        "outcome_provenance": provenance,
        "known_outcome": bool(terminal or response),
        "response_observed": bool(response),
        "terminal_outcome": OUTCOME_LABELS.get(terminal.get("event_type")) if terminal else None,
        "time_to_response_days": _days_between(submitted.get("occurred_at"), (response or {}).get("occurred_at")),
        "time_to_interview_days": _days_between(submitted.get("occurred_at"), (interview or {}).get("occurred_at")),
        "time_to_close_days": _days_between(submitted.get("occurred_at"), (terminal or offer or {}).get("occurred_at")),
        "submission_lineage": {
            "resume_artifact_id": lineage.get("resume_artifact_id"),
            "resume_sha256": lineage.get("resume_sha256"),
            "job_snapshot_hash": lineage.get("job_snapshot_hash"),
        },
    }


def assess_comparability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dimensions = ["role_family_id", "seniority", "work_mode", "location", "industry", "qualification_class", "source_provider"]
    distributions = {key: Counter(str(row.get(key) or "UNKNOWN") for row in rows) for key in dimensions}
    if not rows:
        return {"status": "INSUFFICIENT", "dominant_ratio": 0.0, "mixed_dimensions": [], "distributions": {key: {} for key in dimensions}}
    dominant = [max(counter.values()) / len(rows) for counter in distributions.values() if counter]
    ratio = round(sum(dominant) / len(dominant), 3) if dominant else 0.0
    mixed = [key for key, counter in distributions.items() if len([value for value in counter if value != "UNKNOWN"]) > 1]
    requires_stratification = "role_family_id" in mixed or "seniority" in mixed or len(mixed) > 2
    return {
        "status": "COMPARABLE" if ratio >= 0.6 and not requires_stratification else "STRATIFICATION_REQUIRED",
        "dominant_ratio": ratio, "mixed_dimensions": mixed,
        "distributions": {key: dict(counter) for key, counter in distributions.items()},
    }


def assess_maturity(
    *, sample_count: int, known_outcomes: int, outcome_diversity: int,
    window_start: str, window_end: str, comparability_ratio: float,
    policy: dict[str, Any] | None = None, as_of: str | None = None,
) -> str:
    policy = policy or default_maturity_policy()
    start, end = _parse_time(window_start), _parse_time(window_end)
    now = _parse_time(as_of) or datetime.now(timezone.utc)
    if end and (now - end).days > int(policy["stale_after_days"]):
        return "STALE"
    span = (end - start).days if start and end and end >= start else 0
    mature = policy["minimums"]["MATURE"]
    developing = policy["minimums"]["DEVELOPING"]
    early = policy["minimums"]["EARLY"]
    if sample_count >= mature["sample_count"] and known_outcomes >= mature["known_outcomes"] and span >= mature["window_days"] and outcome_diversity >= mature["outcome_diversity"] and comparability_ratio >= mature["comparability_ratio"]:
        return "MATURE"
    if sample_count >= developing["sample_count"] and known_outcomes >= developing["known_outcomes"] and span >= developing["window_days"] and outcome_diversity >= developing["outcome_diversity"]:
        return "DEVELOPING"
    if sample_count >= early["sample_count"] and known_outcomes >= early["known_outcomes"] and span >= early["window_days"]:
        return "EARLY"
    return "INSUFFICIENT"


def build_career_conversion_cohort(
    *, candidate_profile_id: str, opportunities: list[dict[str, Any]],
    applications: list[dict[str, Any]], event_logs: dict[str, list[dict[str, Any]]],
    qualifications: list[dict[str, Any]], resume_variants: list[dict[str, Any]],
    window_start: str, window_end: str, cohort_filters: dict[str, Any] | None = None,
    job_market_context: str = "CANDIDATE_OBSERVED_MARKET", policy: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build CareerConversionCohortV1 from recorded submitted applications only."""
    policy = policy or default_maturity_policy()
    app_index = {item["application_id"]: item for item in applications}
    opp_index = {item["opportunity_id"]: item for item in opportunities}
    qual_index = {item["qualification_id"]: item for item in qualifications}
    resume_index = {item.get("resume_artifact_id"): item for item in resume_variants}
    rows: list[dict[str, Any]] = []
    for application_id, events in event_logs.items():
        observed = derive_observed_application(events)
        application = app_index.get(application_id)
        if not observed or not application:
            continue
        submitted_time = _parse_time(observed["submitted_at"])
        if not submitted_time:
            continue
        if not (_parse_time(window_start) <= submitted_time <= _parse_time(window_end)):
            continue
        opportunity = opp_index.get(application.get("opportunity_id"), {})
        qualification = qual_index.get(application.get("qualification_id"), {})
        resume = resume_index.get(application.get("resume_artifact_id"), {})
        row = {
            **observed, "opportunity_id": application.get("opportunity_id"),
            "role_family_id": qualification.get("role_family_id") or resume.get("role_family_id") or "UNKNOWN",
            "qualification_policy_version": qualification.get("policy_version", "UNKNOWN"),
            "qualification_class": qualification.get("decision", "UNKNOWN"),
            "resume_policy_version": resume.get("policy_version", "UNKNOWN"),
            "resume_family": resume.get("resume_family", "UNKNOWN"),
            "resume_variant": resume.get("resume_variant", "UNKNOWN"),
            "summary_strategy": resume.get("summary_strategy", "UNKNOWN"),
            "evidence_emphasis": resume.get("evidence_emphasis", []),
            "project_ordering": resume.get("project_ordering", []),
            "template_version": resume.get("template_version", "UNKNOWN"),
            "ats_status": resume.get("ats_status", "UNKNOWN"),
            "employer_need_coverage": resume.get("employer_need_coverage"),
            "material_evidence_loss": resume.get("material_evidence_loss"),
            "seniority": opportunity.get("seniority", "UNKNOWN"), "work_mode": opportunity.get("work_mode", "UNKNOWN"),
            "location": opportunity.get("location", "UNKNOWN"), "industry": opportunity.get("industry", "UNKNOWN"),
            "source_provider": opportunity.get("source_type", "UNKNOWN"),
            "freshness_state": opportunity.get("freshness_state", "UNKNOWN"),
        }
        rows.append(row)
    comparability = assess_comparability(rows)
    known = sum(bool(row["known_outcome"]) for row in rows)
    diversity = len({outcome for row in rows for outcome in row["observed_outcomes"] if outcome != "APPLIED"})
    maturity = assess_maturity(
        sample_count=len(rows), known_outcomes=known, outcome_diversity=diversity,
        window_start=window_start, window_end=window_end, comparability_ratio=comparability["dominant_ratio"],
        policy=policy, as_of=timestamp,
    )
    cohort_material = {
        "candidate_profile_id": candidate_profile_id, "window_start": window_start, "window_end": window_end,
        "application_ids": sorted(row["application_id"] for row in rows), "filters": cohort_filters or {},
    }
    cohort = {
        "schema": "careeros.career-conversion-cohort.v1", "schema_version": "1.0.0",
        "cohort_id": f"conversion-cohort:{uuid.uuid5(uuid.NAMESPACE_URL, sha256_value(cohort_material))}",
        "candidate_profile_id": candidate_profile_id, "created_at": utc_now(timestamp),
        "window_start": window_start, "window_end": window_end,
        "opportunity_ids": sorted({row["opportunity_id"] for row in rows if row.get("opportunity_id")}),
        "application_ids": sorted(row["application_id"] for row in rows),
        "role_family_ids": sorted({row["role_family_id"] for row in rows}),
        "qualification_policy_versions": sorted({row["qualification_policy_version"] for row in rows}),
        "resume_policy_versions": sorted({row["resume_policy_version"] for row in rows}),
        "job_market_context": job_market_context, "sample_count": len(rows), "outcome_count": known,
        "unknown_outcome_count": len(rows) - known, "maturity_state": maturity,
        "cohort_filters": {**(cohort_filters or {}), "comparability": comparability, "maturity_policy": policy},
    }
    cohort["cohort_hash"] = sha256_value(cohort)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:career-conversion-cohort:v1", cohort)
    return cohort, rows


def _rate(rows: list[dict[str, Any]], numerator: str, denominator: str = "APPLIED") -> dict[str, Any]:
    eligible = [row for row in rows if denominator in row["observed_outcomes"]]
    count = sum(numerator in row["observed_outcomes"] for row in eligible)
    return {"numerator": count, "denominator": len(eligible), "rate": round(count / len(eligible), 4) if eligible else None}


def build_conversion_metrics(cohort: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    definitions = {
        "APPLICATION_TO_SCREEN": ("SCREEN", "APPLIED"), "APPLICATION_TO_INTERVIEW": ("INTERVIEW", "APPLIED"),
        "INTERVIEW_TO_FINAL": ("FINAL", "INTERVIEW"),
        "FINAL_TO_OFFER": ("OFFER", "FINAL"), "APPLICATION_TO_OFFER": ("OFFER", "APPLIED"),
        "APPLICATION_TO_HIRE": ("OFFER_ACCEPTED", "APPLIED"),
    }
    durations = {}
    for key in ("time_to_response_days", "time_to_interview_days", "time_to_close_days"):
        values = [row[key] for row in rows if row.get(key) is not None]
        durations[key] = {"count": len(values), "median_days": sorted(values)[len(values) // 2] if values else None}
    rates = {name: _rate(rows, numerator, denominator) for name, (numerator, denominator) in definitions.items()}
    rates["APPLICATION_TO_RESPONSE"] = {
        "numerator": sum(bool(row.get("response_observed")) for row in rows),
        "denominator": len(rows),
        "rate": round(sum(bool(row.get("response_observed")) for row in rows) / len(rows), 4) if rows else None,
    }
    return {
        "schema": "careeros.conversion-metrics.v1", "cohort_id": cohort["cohort_id"],
        "maturity_state": cohort["maturity_state"],
        "rates": rates,
        "time_metrics": durations, "descriptive_only": True,
    }


def build_causal_safeguard(
    cohort: dict[str, Any], *, comparison_name: str, observed_association: str,
    confounders: Iterable[str] = (), comparable: bool | None = None,
) -> dict[str, Any]:
    confounders = sorted(set(map(str, confounders)))
    maturity = cohort["maturity_state"]
    comparable = cohort["cohort_filters"]["comparability"]["status"] == "COMPARABLE" if comparable is None else comparable
    if maturity in {"INSUFFICIENT", "EARLY", "STALE"} or not comparable:
        classification = "CAUSAL_CLAIM_NOT_SUPPORTED"
        recommendation_allowed = False
    elif maturity == "DEVELOPING" or confounders:
        classification = "OBSERVED_ASSOCIATION"
        recommendation_allowed = False
    else:
        classification = "PLAUSIBLE_PATTERN"
        recommendation_allowed = True
    record = {
        "schema": "careeros.conversion-causal-safeguard.v1", "schema_version": "1.0.0",
        "safeguard_id": f"causal-safeguard:{uuid.uuid5(uuid.NAMESPACE_URL, cohort['cohort_id'] + ':' + comparison_name)}",
        "cohort_id": cohort["cohort_id"], "comparison_name": comparison_name,
        "classification": classification, "observed_association": observed_association,
        "approved_language": f"{observed_association} in this cohort. This is descriptive and does not establish causation.",
        "prohibited_language": "Do not state that a resume, qualification decision, skill, or policy caused the observed outcome.",
        "confounders": confounders, "sample_maturity": maturity, "comparable": comparable,
        "strong_recommendation_allowed": recommendation_allowed, "policy_mutation_allowed": False,
    }
    record["safeguard_hash"] = sha256_value(record)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:conversion-causal-safeguard:v1", record)
    return record


def analyze_resume_variants(cohort: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[f"{row['role_family_id']}|{row['resume_family']}|{row['resume_variant']}"].append(row)
    variants = []
    for key, group in sorted(groups.items()):
        variants.append({
            "stratum": key, "sample_count": len(group),
            "interview_conversion": _rate(group, "INTERVIEW"), "offer_conversion": _rate(group, "OFFER"),
            "summary_strategies": sorted({row["summary_strategy"] for row in group}),
            "template_versions": sorted({row["template_version"] for row in group}),
            "ats_statuses": sorted({row["ats_status"] for row in group}),
        })
    comparable = cohort["cohort_filters"]["comparability"]["status"] == "COMPARABLE"
    allowed = cohort["maturity_state"] in {"DEVELOPING", "MATURE"} and comparable and len(variants) >= 2
    return {"variants": variants, "comparison_allowed": allowed, "recommendation": None if not allowed else "Review comparable observed differences; retain causal safeguards and require human promotion."}


def calibrate_qualification(cohort: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    progressed = Counter()
    totals = Counter()
    for row in rows:
        qualification = row["qualification_class"]
        totals[qualification] += 1
        if any(item in row["observed_outcomes"] for item in {"SCREEN", "INTERVIEW", "FINAL", "OFFER", "OFFER_ACCEPTED"}):
            progressed[qualification] += 1
    if cohort["maturity_state"] in {"INSUFFICIENT", "EARLY", "STALE"}:
        classification = "INSUFFICIENT_DATA"
    elif progressed["NOT_QUALIFIED"] >= 2:
        classification = "POSSIBLE_OVERSTRICT"
    elif totals["QUALIFIED"] >= 5 and progressed["QUALIFIED"] == 0 and cohort["unknown_outcome_count"] == 0:
        classification = "POSSIBLE_OVERPERMISSIVE"
    else:
        classification = "CALIBRATION_STABLE"
    return {"classification": classification, "totals": dict(totals), "progressed": dict(progressed), "policy_mutation": "PROHIBITED_WITHOUT_APPROVED_PROPOSAL"}


def aggregate_employer_needs(traces: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    supported_source_counts: Counter[str] = Counter()
    types: dict[str, str] = {}
    examples: defaultdict[str, list[str]] = defaultdict(list)
    for trace in traces:
        for need in trace.get("needs", []):
            key = re.sub(r"\s+", " ", str(need.get("need_statement") or "").casefold()).strip()
            if not key:
                continue
            counts[key] += 1
            explicit_confidence = str(need.get("need_confidence") or trace.get("verification_confidence") or "").upper()
            if need.get("source_refs") and explicit_confidence not in {"LOW", "UNKNOWN"}:
                supported_source_counts[key] += 1
            types[key] = need.get("need_type", "OTHER")
            examples[key].append(need.get("need_id"))
    total = max(1, len(traces))
    records = []
    for key, count in counts.most_common():
        ratio = count / total
        classification = "LOW_CONFIDENCE" if supported_source_counts[key] == 0 else "MARKET_FREQUENT" if count >= 3 and ratio >= 0.5 else "ROLE_FAMILY_FREQUENT" if count >= 2 else "ONE_OFF"
        records.append({"need": key, "need_type": types[key], "job_count": count, "frequency": round(ratio, 3), "classification": classification, "need_ids": examples[key]})
    return {"observed_job_count": len(traces), "needs": records, "scope": "CANDIDATE_OBSERVED_MARKET_ONLY"}


def build_career_capital_signals(
    cohort: dict[str, Any], rows: list[dict[str, Any]], traces: list[dict[str, Any]],
) -> dict[str, Any]:
    category_map = {
        "TECHNICAL": "TECHNICAL", "SECURITY": "TECHNICAL", "NETWORKING": "TECHNICAL",
        "OPERATIONS": "OPERATIONS", "LEADERSHIP": "LEADERSHIP", "CUSTOMER": "CUSTOMER",
        "COMPLIANCE": "DOMAIN", "AUTOMATION": "TOOL", "PROCESS": "PROCESS",
        "COMMUNICATION": "COMMUNICATION", "ANALYTICS": "TECHNICAL", "CORE_DELIVERY": "OPERATIONS",
    }
    counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    categories_by_opportunity: defaultdict[str, set[str]] = defaultdict(set)
    for trace in traces:
        trace_categories: set[str] = set()
        for need in trace.get("needs", []):
            category = category_map.get(need.get("need_type"), "DOMAIN")
            trace_categories.add(category)
        for category in trace_categories:
            counts[category]["qualified_jobs"] += 1
        opportunity_id = trace.get("opportunity_id") or trace.get("job_id")
        if opportunity_id:
            categories_by_opportunity[str(opportunity_id)].update(trace_categories)
    for row in rows:
        stages = row["observed_outcomes"]
        # Progression is attributed only to needs from the exact recorded job.
        # A missing trace remains unknown rather than borrowing categories from
        # other opportunities in the cohort.
        for category in categories_by_opportunity.get(str(row.get("opportunity_id")), set()):
            if "INTERVIEW" in stages or "SCREEN" in stages:
                counts[category]["interviews"] += 1
            if "OFFER" in stages or "OFFER_ACCEPTED" in stages:
                counts[category]["offers"] += 1
    signals = []
    for category, values in counts.items():
        signal = {
            "signal_id": f"career-capital:{uuid.uuid5(uuid.NAMESPACE_URL, cohort['cohort_id'] + ':' + category)}",
            "cohort_id": cohort["cohort_id"], "category": category,
            "qualified_job_count": values["qualified_jobs"], "interview_count": values["interviews"],
            "offer_count": values["offers"], "interpretation": "Observed market signal; not evidence that this capability caused progression.",
        }
        signal["signal_hash"] = sha256_value(signal)
        SchemaRegistry(schema_dir()).validate("urn:careeros:schema:career-capital-signal:v1", signal)
        signals.append(signal)
    return {"signals": signals, "causal_boundary": "Counts show co-occurrence only."}


def aggregate_gaps(qualifications: list[dict[str, Any]], resolved_capabilities: Iterable[str] = ()) -> dict[str, Any]:
    resolved = {item.casefold() for item in resolved_capabilities}
    counts: Counter[tuple[str, str]] = Counter()
    refs: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for qualification in qualifications:
        for gap in qualification.get("gaps", []):
            capability = str(gap.get("capability") or "").strip()
            kind = str(gap.get("match") or "UNKNOWN")
            if capability:
                counts[(capability, kind)] += 1
                refs[(capability, kind)].append(qualification["qualification_id"])
    records = []
    for (capability, kind), count in counts.most_common():
        if capability.casefold() in resolved:
            classification = "RESOLVED_GAP"
        elif count == 1:
            classification = "ONE_OFF_GAP"
        elif kind == "HARD_GAP":
            classification = "RECURRING_HARD_GAP"
        elif kind in {"BRIDGEABLE_GAP", "PREFERRED_AND_MISSING", "PARTIALLY_SUPPORTED"}:
            classification = "RECURRING_BRIDGEABLE_GAP"
        else:
            classification = "RECURRING_EVIDENCE_GAP"
        records.append({"capability": capability, "source_gap_class": kind, "job_count": count, "classification": classification, "qualification_ids": refs[(capability, kind)]})
    return {"gaps": records, "source_qualification_count": len(qualifications)}


def build_development_opportunities(
    cohort: dict[str, Any], gaps: dict[str, Any], actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for action in actions:
        matching = [gap for gap in gaps.get("gaps", []) if _tokens(gap["capability"]) & _tokens(action.get("capabilities", []))]
        recurrence = sum(gap["job_count"] for gap in matching)
        breadth = len(set(action.get("role_family_ids", [])))
        proximity = float(action.get("candidate_proximity", 0.5))
        cost = float(action.get("cost_score", 0.5))
        time = float(action.get("time_score", 0.5))
        evidence_value = float(action.get("evidence_generation_value", 0.5))
        utility = recurrence * 2 + breadth + proximity + evidence_value - cost - time
        recommendation_allowed = cohort["maturity_state"] in {"DEVELOPING", "MATURE"}
        priority = "HIGH_PRIORITY" if recurrence >= 3 and utility >= 6 else "MEDIUM_PRIORITY" if recurrence >= 2 or utility >= 3 else "LOW_PRIORITY" if matching else "OPTIONAL"
        if not recommendation_allowed:
            priority = "OPTIONAL"
        record = {
            "schema": "careeros.development-opportunity.v1", "schema_version": "1.0.0",
            "opportunity_id": str(action["opportunity_id"]), "source_cohort_id": cohort["cohort_id"],
            "action_type": action.get("action_type", "PROJECT"), "capabilities": action.get("capabilities", []),
            "gap_recurrence": recurrence, "job_frequency": recurrence, "importance": action.get("importance", "MEDIUM"),
            "candidate_proximity": proximity, "time_cost": time, "financial_cost": cost,
            "evidence_generation_value": evidence_value, "role_family_breadth": breadth,
            "priority": priority, "outcome_boundary": "This prioritizes learning/evidence value and does not promise a job outcome.",
            "sample_maturity": cohort["maturity_state"], "recommendation_allowed": recommendation_allowed,
        }
        record["opportunity_hash"] = sha256_value(record)
        SchemaRegistry(schema_dir()).validate("urn:careeros:schema:development-opportunity:v1", record)
        records.append(record)
    return records


def assess_course_credential_roi(
    gaps: dict[str, Any], options: list[dict[str, Any]], *, sample_maturity: str = "INSUFFICIENT",
) -> list[dict[str, Any]]:
    result = []
    for option in options:
        matched = [gap for gap in gaps.get("gaps", []) if _tokens(gap["capability"]) & _tokens(option.get("capabilities", []))]
        count = sum(item["job_count"] for item in matched)
        required = any(item["source_gap_class"] == "HARD_GAP" for item in matched)
        recognized = bool(option.get("employer_recognized"))
        verifiable = bool(option.get("creates_verifiable_evidence"))
        alternative = bool(option.get("portfolio_alternative_exists"))
        if required and recognized:
            classification = "REQUIRED"
        elif count >= 2 and recognized and verifiable:
            classification = "MARKET_VALUABLE"
        elif alternative:
            classification = "PORTFOLIO_ALTERNATIVE_EXISTS"
        elif count == 0:
            classification = "UNNECESSARY"
        else:
            classification = "LOW_ROI"
        result.append({"option_id": option["option_id"], "classification": classification, "observed_gap_job_count": count, "employer_recognized": recognized, "creates_verifiable_evidence": verifiable, "cost": option.get("cost"), "time": option.get("time"), "sample_maturity": sample_maturity, "recommendation_allowed": sample_maturity in {"DEVELOPING", "MATURE"}, "boundary": "Coursework or a credential may strengthen evidence; it does not create professional employment experience or guarantee outcomes."})
    return result


def build_observed_market_map(
    cohort: dict[str, Any], rows: list[dict[str, Any]], employer_needs: dict[str, Any], career_capital: dict[str, Any],
) -> dict[str, Any]:
    families = Counter(row["role_family_id"] for row in rows)
    fit = Counter(row["qualification_class"] for row in rows)
    return {
        "scope": "CANDIDATE_SPECIFIC_OBSERVED_MARKET", "cohort_id": cohort["cohort_id"],
        "role_availability": dict(families), "qualification_fit": dict(fit),
        "recurring_requirements": employer_needs["needs"], "career_capital_signals": career_capital["signals"],
        "lane_viability": "INSUFFICIENT" if cohort["maturity_state"] in {"INSUFFICIENT", "EARLY", "STALE"} else "DESCRIPTIVE_ONLY",
        "external_market_research_merged": False,
        "boundary": "Personal observed opportunities do not replace broad external market research.",
    }


def build_learning_promotion_proposal(
    *, source_cohorts: list[str], observation: str, recommendation: str,
    sample_maturity: str, confidence: str, affected_policy: str,
    expected_effect: str, risk: str, timestamp: str | None = None,
) -> dict[str, Any]:
    material = sha256_value([source_cohorts, observation, recommendation, affected_policy])
    record = {
        "schema": "careeros.learning-promotion-proposal.v1", "schema_version": "1.0.0",
        "proposal_id": f"learning-proposal:{uuid.uuid5(uuid.NAMESPACE_URL, material)}",
        "source_cohorts": source_cohorts, "observation": observation, "recommendation": recommendation,
        "sample_maturity": sample_maturity, "confidence": confidence, "affected_policy": affected_policy,
        "expected_effect": expected_effect, "risk": risk, "human_review_state": "PENDING",
        "approved_at": None, "created_at": utc_now(timestamp),
    }
    record["proposal_hash"] = sha256_value(record)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:learning-promotion-proposal:v1", record)
    return record


def approve_learning_proposal(proposal: dict[str, Any], *, human_approved: bool, approved_at: str) -> dict[str, Any]:
    if not human_approved:
        raise PermissionError("learning policy promotion requires explicit human approval")
    result = dict(proposal)
    result["human_review_state"] = "APPROVED"
    result["approved_at"] = utc_now(approved_at)
    result.pop("proposal_hash", None)
    result["proposal_hash"] = sha256_value(result)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:learning-promotion-proposal:v1", result)
    return result


def evaluate_learning_qa(
    *, cohort: dict[str, Any], rows: list[dict[str, Any]], event_logs: dict[str, list[dict[str, Any]]],
    causal_safeguards: list[dict[str, Any]], proposals: list[dict[str, Any]], privacy_findings: int = 0,
) -> dict[str, Any]:
    included = set(cohort["application_ids"])
    submitted = {
        app_id for app_id, events in event_logs.items()
        if derive_observed_application(events) is not None
    }
    provenance_ok = all(item["provenance"] in PROVENANCE_CLASSES - {"UNKNOWN"} for row in rows for item in row["outcome_provenance"])
    gates = {
        "COHORT_INTEGRITY": included <= submitted and cohort["sample_count"] == len(rows),
        "OUTCOME_PROVENANCE": provenance_ok,
        "SAMPLE_MATURITY": cohort["maturity_state"] in MATURITY_STATES,
        "CAUSAL_LANGUAGE": all("does not establish causation" in item["approved_language"] for item in causal_safeguards),
        "NO_HISTORICAL_BACKFILL": included == {row["application_id"] for row in rows},
        "POLICY_PROMOTION_APPROVAL": all(item["human_review_state"] in {"PENDING", "REJECTED", "APPROVED"} and not item.get("policy_mutation") for item in proposals),
        "PRIVACY": privacy_findings == 0,
        "MARKET_DRIFT": cohort["maturity_state"] == "STALE" or bool(cohort["cohort_filters"].get("maturity_policy")),
    }
    return {"gates": gates, "status": "PASS" if all(gates.values()) else "FAIL"}


def build_conversion_learning_bundle(
    *, candidate_profile_id: str, opportunities: list[dict[str, Any]], applications: list[dict[str, Any]],
    event_logs: dict[str, list[dict[str, Any]]], qualifications: list[dict[str, Any]],
    resume_variants: list[dict[str, Any]], employer_need_traces: list[dict[str, Any]],
    development_actions: list[dict[str, Any]], course_options: list[dict[str, Any]],
    window_start: str, window_end: str, timestamp: str | None = None,
) -> dict[str, Any]:
    cohort, rows = build_career_conversion_cohort(
        candidate_profile_id=candidate_profile_id, opportunities=opportunities, applications=applications,
        event_logs=event_logs, qualifications=qualifications, resume_variants=resume_variants,
        window_start=window_start, window_end=window_end, timestamp=timestamp,
    )
    metrics = build_conversion_metrics(cohort, rows)
    comparability = cohort["cohort_filters"]["comparability"]
    causal = [build_causal_safeguard(
        cohort, comparison_name="resume_variant_observed_progression",
        observed_association="Applications using the compared resume variants showed different observed progression",
        confounders=comparability["mixed_dimensions"],
    )]
    resume_learning = analyze_resume_variants(cohort, rows)
    calibration = calibrate_qualification(cohort, rows)
    needs = aggregate_employer_needs(employer_need_traces)
    capital = build_career_capital_signals(cohort, rows, employer_need_traces)
    gaps = aggregate_gaps(qualifications)
    development = build_development_opportunities(cohort, gaps, development_actions)
    credential_roi = assess_course_credential_roi(gaps, course_options, sample_maturity=cohort["maturity_state"])
    market = build_observed_market_map(cohort, rows, needs, capital)
    proposals: list[dict[str, Any]] = []
    if cohort["maturity_state"] in {"DEVELOPING", "MATURE"} and calibration["classification"] != "INSUFFICIENT_DATA":
        proposals.append(build_learning_promotion_proposal(
            source_cohorts=[cohort["cohort_id"]], observation=f"Qualification calibration classified {calibration['classification']}",
            recommendation="Review qualification calibration with a human before any policy change.",
            sample_maturity=cohort["maturity_state"], confidence="MEDIUM", affected_policy="qualification",
            expected_effect="Potentially improve future qualification calibration after review.",
            risk="Overfitting a candidate-specific or confounded cohort.", timestamp=timestamp,
        ))
    qa = evaluate_learning_qa(cohort=cohort, rows=rows, event_logs=event_logs, causal_safeguards=causal, proposals=proposals)
    return {
        "schema": "careeros.career-conversion-learning.v1", "policy_version": LEARNING_POLICY_VERSION,
        "learning_scope": "CANDIDATE_SPECIFIC", "cohort": cohort, "observed_applications": rows,
        "conversion_metrics": metrics, "cohort_comparability": comparability,
        "causal_safeguards": causal, "resume_variant_learning": resume_learning,
        "qualification_calibration": calibration, "employer_need_learning": needs,
        "career_capital": capital, "gap_recurrence": gaps, "development_opportunities": development,
        "course_credential_roi": credential_roi, "market_map": market,
        "promotion_proposals": proposals, "qa": qa,
        "policy_mutations": [], "fabricated_historical_events": [],
    }
