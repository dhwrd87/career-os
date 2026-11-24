"""Candidate-neutral career conversion intelligence.

This module protects the strongest supported employer match and the material
facts that give a role meaning while a resume is prioritized and compressed.
It is a derivative layer only: it neither mutates canonical records nor
creates resume claims.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from typing import Any, Iterable

from careeros.core.io import sha256_value
from careeros.resume_governance import evidence_utility


PUBLIC_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}
SUPPORTED_COVERAGE = {
    "STRONG_SUPPORTED_MATCH", "SUPPORTED_MATCH", "TRANSFERABLE_MATCH", "PARTIALLY_SUPPORTED",
}
OMISSION_REASONS = {
    "SPACE", "REDUNDANCY", "PRIVACY", "PUBLIC_USE_BLOCK", "JOB_MISMATCH",
    "CONTEXT_MISMATCH", "DOCUMENT_BALANCE", "OTHER",
}
NEED_TYPES = {
    "CORE_DELIVERY": ("deliver", "implement", "deploy", "complete", "execute"),
    "TECHNICAL": ("technical", "system", "software", "hardware", "tool"),
    "OPERATIONS": ("operations", "workflow", "shift", "service", "runbook"),
    "CUSTOMER": ("customer", "client", "member", "user support"),
    "SECURITY": ("security", "incident", "threat", "vulnerab", "siem", "ioc"),
    "NETWORKING": ("network", "wireshark", "dns", "dhcp", "vpn", "tcp/ip"),
    "ANALYTICS": ("analytic", "metric", "dashboard", "reporting", "trend"),
    "COMPLIANCE": ("compliance", "audit", "control", "regulatory", "policy"),
    "LEADERSHIP": ("lead", "manage", "supervis", "mentor", "coach"),
    "COMMUNICATION": ("communicat", "present", "document", "stakeholder", "written"),
    "AUTOMATION": ("automat", "script", "python", "orchestrat"),
    "PROCESS": ("process", "procedure", "quality", "improve", "coordinate"),
}
TECHNICAL_TERMS = {
    "api", "automation", "cloud", "code", "database", "dns", "dhcp", "firewall",
    "log", "network", "python", "script", "security", "server", "siem", "sql",
    "system", "tcp", "tool", "vpn", "vulnerability", "wireshark",
}
LEADERSHIP_TERMS = {"lead", "led", "manage", "managed", "mentor", "mentored", "supervis", "coach", "owned"}


def _tokens(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value)
    return {
        token for token in re.findall(r"[a-z0-9+#.]+", str(value or "").casefold())
        if len(token) > 2 and token not in {"and", "for", "the", "with", "from", "into", "your", "you"}
    }


def _plain(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _selected_evidence(content: dict[str, Any]) -> set[str]:
    return {
        evidence_id
        for section in [*content.get("employment", []), *content.get("projects", [])]
        for bullet in section.get("bullets", [])
        for evidence_id in bullet.get("evidence_ids", [])
    }


def _profile_id(profile: dict[str, Any]) -> str:
    return str(profile.get("profile_id") or f"profile:derived-{sha256_value(profile)[:16]}")


def _find_source_position(statement: str, snapshot_text: str) -> tuple[int, str]:
    lowered = snapshot_text.casefold()
    exact = lowered.find(statement.casefold())
    if exact >= 0:
        return exact, f"text.char[{exact}]"
    candidates = sorted(_tokens(statement), key=len, reverse=True)
    positions = [lowered.find(token) for token in candidates if lowered.find(token) >= 0]
    if positions:
        position = min(positions)
        return position, f"text.char[{position}]"
    return -1, "structured.requirement"


def _third(position: int, text_length: int) -> str:
    if position < 0 or text_length <= 0:
        return "UNKNOWN"
    ratio = position / max(1, text_length)
    if ratio <= 1 / 3:
        return "TOP_THIRD"
    if ratio <= 2 / 3:
        return "MIDDLE_THIRD"
    return "BOTTOM_THIRD"


def _need_type(statement: str) -> str:
    lowered = statement.casefold()
    scored = [
        (sum(1 for term in terms if term in lowered), need_type)
        for need_type, terms in NEED_TYPES.items()
    ]
    score, need_type = max(scored, default=(0, "OTHER"))
    return need_type if score else "OTHER"


def _locations_for_evidence(content: dict[str, Any], evidence_ids: set[str], need_tokens: set[str]) -> list[str]:
    locations: list[str] = []
    summary = content.get("recruiter_summary", {})
    if any(evidence_ids & set(clause.get("source_evidence_ids", [])) for clause in summary.get("clauses", [])):
        locations.append("SUMMARY")
    skills = content.get("skills", [])
    for index, skill in enumerate(skills):
        if evidence_ids & set(skill.get("evidence_ids", [])) or need_tokens & _tokens(skill.get("name")):
            locations.append("TOP_SKILLS" if index < 6 else "OTHER_SKILLS")
            break
    employment_bullets = [bullet for section in content.get("employment", []) for bullet in section.get("bullets", [])]
    for index, bullet in enumerate(employment_bullets):
        if evidence_ids & set(bullet.get("evidence_ids", [])):
            locations.append("FIRST_EXPERIENCE_BULLETS" if index < 3 else "EXPERIENCE")
            break
    project_bullets = [bullet for section in content.get("projects", []) for bullet in section.get("bullets", [])]
    for index, bullet in enumerate(project_bullets):
        if evidence_ids & set(bullet.get("evidence_ids", [])):
            locations.append("FIRST_PROJECT_BULLETS" if index < 3 else "PROJECTS")
            break
    return list(dict.fromkeys(locations))


def _normalize_omission_reason(value: str | None) -> str | None:
    text = str(value or "").upper()
    if not text:
        return None
    if "REDUND" in text:
        return "REDUNDANCY"
    if "PRIV" in text or "RESTRICT" in text:
        return "PRIVACY"
    if "PUBLIC" in text and "BLOCK" in text:
        return "PUBLIC_USE_BLOCK"
    if "SPACE" in text or "LIMIT" in text:
        return "SPACE"
    if "BALANCE" in text:
        return "DOCUMENT_BALANCE"
    if "CONTEXT" in text:
        return "CONTEXT_MISMATCH"
    if "JOB" in text or "RELEVANCE" in text or "PRIORITY" in text:
        return "JOB_MISMATCH"
    return "OTHER"


def build_employer_need_trace(
    intelligence: dict[str, Any], matrix: dict[str, Any], snapshot: dict[str, Any],
    content: dict[str, Any] | None = None, omission_reasons: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build EmployerNeedTraceV1 from source-located JD and matrix facts."""
    text = str(snapshot.get("text") or "")
    selected = _selected_evidence(content or {})
    omission_reasons = omission_reasons or {}
    repeated = set(intelligence.get("repeated_emphasized_concepts", []))
    needs: list[dict[str, Any]] = []
    for row in matrix.get("requirements", []):
        statement = _plain(row.get("requirement_text"))
        position, locator = _find_source_position(statement, text)
        placement = _third(position, len(text))
        need_tokens = _tokens(statement)
        frequency = max(1, sum(text.casefold().count(token) for token in need_tokens) // max(1, len(need_tokens)))
        responsibility = row.get("requirement_class") == "RESPONSIBILITY"
        qualification = row.get("requirement_class") in {"REQUIRED", "PREFERRED"}
        mission_tokens = _tokens(intelligence.get("role_mission", {}).get("value"))
        ownership = any(term in statement.casefold() for term in ("own", "accountab", "responsib", "primary", "critical", "core"))
        measurable = any(term in statement.casefold() for term in ("metric", "sla", "target", "uptime", "%", "outcome"))
        score = (
            (4 if row.get("requirement_class") == "REQUIRED" else 2 if row.get("requirement_class") == "PREFERRED" else 1)
            + (2 if placement == "TOP_THIRD" else 0)
            + (2 if responsibility else 0)
            + (2 if need_tokens & mission_tokens else 0)
            + (1 if need_tokens & repeated else 0)
            + (1 if ownership else 0)
            + (1 if measurable else 0)
        )
        importance = "CRITICAL" if score >= 8 else "HIGH" if score >= 5 else "MEDIUM" if score >= 3 else "LOW"
        evidence_ids = set(row.get("candidate_evidence_ids", []))
        locations = _locations_for_evidence(content or {}, evidence_ids, need_tokens)
        used = bool(evidence_ids & selected) or bool(locations)
        prominent = any(location in {"SUMMARY", "TOP_SKILLS", "FIRST_EXPERIENCE_BULLETS", "FIRST_PROJECT_BULLETS"} for location in locations)
        available = bool(evidence_ids) and row.get("coverage_class") in SUPPORTED_COVERAGE
        if row.get("coverage_class") == "STRONG_SUPPORTED_MATCH" and used and prominent:
            treatment = "STRONGLY_COVERED"
        elif row.get("coverage_class") == "TRANSFERABLE_MATCH" and used:
            treatment = "TRANSFERABLE_ONLY"
        elif available and used:
            treatment = "COVERED"
        elif available and not used:
            treatment = "OMITTED"
        elif row.get("coverage_class") == "PARTIALLY_SUPPORTED":
            treatment = "PARTIALLY_COVERED"
        elif row.get("coverage_class") in {"EVIDENCE_MISSING", "BRIDGEABLE_GAP", "HARD_GAP"}:
            treatment = "GAP"
        else:
            treatment = "UNKNOWN"
        omitted_reason = None
        if available and not used:
            reasons = [_normalize_omission_reason(omission_reasons.get(evidence_id)) for evidence_id in evidence_ids]
            omitted_reason = next((reason for reason in reasons if reason), None)
        if available and not used:
            gap_state = "RESUME_OMISSION"
        elif not available and treatment == "GAP":
            gap_state = "NO_CANDIDATE_EVIDENCE"
        elif treatment in {"PARTIALLY_COVERED", "TRANSFERABLE_ONLY"}:
            gap_state = "PARTIAL"
        elif treatment == "UNKNOWN":
            gap_state = "UNKNOWN"
        else:
            gap_state = "NONE"
        needs.append({
            "need_id": row["requirement_id"], "job_id": intelligence["opportunity_id"],
            "source_refs": [{"snapshot_id": snapshot["snapshot_id"], "locator": locator, "quote": statement}],
            "need_statement": statement, "need_type": _need_type(statement), "importance": importance,
            "requirement_class": row["requirement_class"], "frequency": frequency,
            "top_third_signal": placement, "repeated_signal": bool(need_tokens & repeated),
            "responsibility_signal": responsibility, "qualification_signal": qualification,
            "candidate_evidence_ids": sorted(evidence_ids), "coverage_class": treatment,
            "evidence_strength": row.get("evidence_strength", "UNKNOWN"),
            "resume_usage": "USED" if used else "OMITTED", "resume_location": locations,
            "prominence": "HIGH" if prominent else ("STANDARD" if used else "NONE"),
            "omission_reason": omitted_reason, "gap_state": gap_state,
        })
    material = [need for need in needs if need["importance"] in {"CRITICAL", "HIGH"}]
    supported_top = [
        need for need in material
        if need["top_third_signal"] == "TOP_THIRD" and need["candidate_evidence_ids"]
        and need["gap_state"] != "NO_CANDIDATE_EVIDENCE"
    ]
    prominent_top = [need for need in supported_top if need["prominence"] == "HIGH"]
    top_ratio = len(prominent_top) / max(1, len(supported_top))
    trace = {
        "schema": "careeros.employer-need-trace.v1", "schema_version": "1.0.0",
        "trace_id": f"employer-need-trace:{uuid.uuid5(uuid.NAMESPACE_URL, matrix['matrix_id'] + ':' + sha256_value(content or {}))}",
        "job_id": intelligence["opportunity_id"], "snapshot_id": snapshot["snapshot_id"],
        "needs": sorted(needs, key=lambda item: ({"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}[item["importance"]], item["need_id"])),
        "top_third_coverage": {
            "supported_material_needs": len(supported_top), "prominently_represented": len(prominent_top),
            "ratio": round(top_ratio, 3),
            "status": "PASS" if not supported_top or top_ratio >= 0.67 else "FAIL",
        },
        "source_policy": "SOURCE_LOCATED_NO_FREQUENCY_ONLY_IMPORTANCE",
    }
    trace["trace_hash"] = sha256_value(trace)
    return trace


def strongest_evidence_omissions(
    profile: dict[str, Any], employer_need_trace: dict[str, Any], selected_evidence_ids: Iterable[str],
    omission_reasons: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Detect use of weaker evidence while stronger public evidence is available."""
    selected = set(selected_evidence_ids)
    reasons = omission_reasons or {}
    evidence_index = {item["record_id"]: item for item in profile.get("evidence", [])}
    findings: list[dict[str, Any]] = []
    for need in employer_need_trace.get("needs", []):
        if need.get("importance") not in {"CRITICAL", "HIGH"}:
            continue
        candidates = []
        for evidence_id in need.get("candidate_evidence_ids", []):
            evidence = evidence_index.get(evidence_id)
            if not evidence or evidence.get("visibility") not in PUBLIC_VISIBILITY:
                continue
            job_relevance = 1.0 if need.get("evidence_strength") == "HIGH" else 0.8
            utility = evidence_utility(evidence, job_relevance=job_relevance)
            candidates.append((utility["utility"], evidence_id))
        if not candidates:
            continue
        candidates.sort(reverse=True)
        strongest_score, strongest_id = candidates[0]
        selected_candidates = [item for item in candidates if item[1] in selected]
        selected_score = selected_candidates[0][0] if selected_candidates else None
        if strongest_id in selected:
            continue
        materially_weaker = selected_score is None or strongest_score - selected_score >= 0.08
        if not materially_weaker:
            continue
        rationale = _normalize_omission_reason(reasons.get(strongest_id))
        findings.append({
            "need_id": need["need_id"], "strongest_evidence_id": strongest_id,
            "strongest_utility": strongest_score,
            "selected_evidence_ids": [evidence_id for _score, evidence_id in selected_candidates],
            "selected_best_utility": selected_score, "code": "STRONGEST_EVIDENCE_OMITTED",
            "rationale": rationale, "silent": rationale not in OMISSION_REASONS,
        })
    result = {
        "schema": "careeros.strongest-evidence-omission.v1", "schema_version": "1.0.0",
        "assessment_id": f"strongest-evidence:{uuid.uuid5(uuid.NAMESPACE_URL, employer_need_trace['trace_id'] + ':' + sha256_value(sorted(selected)))}",
        "job_id": employer_need_trace["job_id"], "findings": findings,
        "silent_omission_count": sum(bool(item["silent"]) for item in findings),
        "status": "PASS" if not any(item["silent"] for item in findings) else "FAIL",
    }
    result["assessment_hash"] = sha256_value(result)
    return result


def _fact(
    role_id: str, category: str, value: str, importance: str, evidence_ids: Iterable[str],
    verification: str, visibility: str,
) -> dict[str, Any]:
    return {
        "fact_id": f"role-fact:{uuid.uuid5(uuid.NAMESPACE_URL, role_id + ':' + category + ':' + value)}",
        "category": category, "value": _plain(value), "importance": importance,
        "evidence_ids": sorted(set(evidence_ids)), "verification": verification,
        "visibility": visibility, "public_usable": visibility in PUBLIC_VISIBILITY,
    }


def _importance_for_evidence(evidence: dict[str, Any], category: str, category_counts: Counter[str]) -> str:
    # Unique leadership and technical facts are material. They become critical
    # only when they are the sole support for a critical employer need.
    if category in {"LEADERSHIP", "TECHNICAL"} and category_counts[category] == 1:
        return "MATERIAL"
    if category in {"RESPONSIBILITY", "OUTCOME", "TOOL", "SCOPE", "LEADERSHIP", "TECHNICAL"}:
        return "MATERIAL"
    return "SUPPORTING"


def build_role_fact_set(profile: dict[str, Any]) -> dict[str, Any]:
    """Derive RoleFactSetV1 without transforming role facts into resume copy."""
    evidence_index = {item["record_id"]: item for item in profile.get("evidence", [])}
    roles: list[dict[str, Any]] = []
    all_evidence = list(evidence_index.values())
    category_counts: Counter[str] = Counter()
    evidence_categories: dict[str, set[str]] = defaultdict(set)
    for evidence in all_evidence:
        text = " ".join(map(str, [evidence.get("summary"), evidence.get("actions", []), evidence.get("tools_methods", []), evidence.get("leadership_ownership", [])])).casefold()
        if any(term in text for term in LEADERSHIP_TERMS):
            evidence_categories[evidence["record_id"]].add("LEADERSHIP")
            category_counts["LEADERSHIP"] += 1
        if _tokens(text) & TECHNICAL_TERMS:
            evidence_categories[evidence["record_id"]].add("TECHNICAL")
            category_counts["TECHNICAL"] += 1

    def make_role(record: dict[str, Any], context_type: str) -> dict[str, Any]:
        role_id = record["record_id"]
        linked = [evidence_index[evidence_id] for evidence_id in record.get("evidence_ids", []) if evidence_id in evidence_index]
        facts: list[dict[str, Any]] = []
        for evidence in linked:
            evidence_id = evidence["record_id"]
            verification = evidence.get("verification_state", "UNKNOWN")
            visibility = evidence.get("visibility", "INTERNAL")
            for value in evidence.get("actions", []) or ([evidence.get("summary")] if evidence.get("summary") else []):
                facts.append(_fact(role_id, "RESPONSIBILITY", value, "MATERIAL", [evidence_id], verification, visibility))
            for value in evidence.get("outcomes", []):
                facts.append(_fact(role_id, "OUTCOME", value, "MATERIAL", [evidence_id], verification, visibility))
            for value in evidence.get("tools_methods", []):
                facts.append(_fact(role_id, "TOOL", value, "MATERIAL", [evidence_id], verification, visibility))
            for value in [evidence.get("scope"), evidence.get("frequency"), *evidence.get("material_scope", [])]:
                if value:
                    facts.append(_fact(role_id, "SCOPE", str(value), "MATERIAL", [evidence_id], verification, visibility))
            for category in evidence_categories[evidence_id]:
                source = (evidence.get("leadership_ownership") or evidence.get("actions") or evidence.get("tools_methods") or [evidence.get("summary")])[0]
                facts.append(_fact(role_id, category, str(source), _importance_for_evidence(evidence, category, category_counts), [evidence_id], verification, visibility))
        primary = [fact["value"] for fact in facts if fact["category"] == "RESPONSIBILITY"]
        outcomes = [fact["value"] for fact in facts if fact["category"] == "OUTCOME"]
        tools = [fact["value"] for fact in facts if fact["category"] == "TOOL"]
        scope = [fact["value"] for fact in facts if fact["category"] == "SCOPE"]
        leadership = [fact for fact in facts if fact["category"] == "LEADERSHIP"]
        stakeholders = [value for evidence in linked for value in evidence.get("stakeholders", [])]
        dates = record.get("date_range") if context_type == "PROJECT" else {
            "start_month": record.get("start_month"), "start_year": record.get("start_year"),
            "end_month": record.get("end_month"), "end_year": record.get("end_year"),
            "precision": record.get("date_precision"),
        }
        return {
            "role_record_id": role_id,
            "employer_or_context": record.get("employer") or record.get("name") or record.get("role_context") or context_type.title(),
            "actual_title": record.get("actual_title") or record.get("name"),
            "public_title_alias": record.get("public_title"), "dates": dates,
            "location": record.get("location"), "employment_type": record.get("employment_type"),
            "context_type": context_type, "primary_responsibilities": primary,
            "material_outcomes": outcomes, "material_tools": tools, "material_scope": scope,
            "leadership_state": "PRESENT" if leadership else "NOT_EVIDENCED",
            "customer_stakeholder_context": list(dict.fromkeys(map(str, stakeholders))),
            "verification": record.get("verification_state", "UNKNOWN"),
            "visibility": record.get("visibility", "INTERNAL"), "facts": facts,
        }

    roles.extend(make_role(record, "EMPLOYMENT") for record in profile.get("employment", []))
    roles.extend(make_role(record, "PROJECT") for record in profile.get("projects", []))
    profile_id = _profile_id(profile)
    result = {
        "schema": "careeros.role-fact-set.v1", "schema_version": "1.0.0",
        "fact_set_id": f"role-fact-set:{uuid.uuid5(uuid.NAMESPACE_URL, profile_id + ':' + sha256_value(roles))}",
        "profile_id": profile_id, "roles": roles,
        "importance_policy": "IDENTITY_CRITICAL_UNIQUE_LEADERSHIP_OR_TECHNICAL_CRITICAL_MATERIAL_ACTIVITY_PRESERVED",
    }
    result["fact_set_hash"] = sha256_value(result)
    return result


def assess_role_fact_preservation(role_fact_set: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
    selected_sections = {
        section["record_id"]: section
        for section in [*content.get("employment", []), *content.get("projects", [])]
    }
    assessments: list[dict[str, Any]] = []
    for role in role_fact_set.get("roles", []):
        section = selected_sections.get(role["role_record_id"])
        if section is None:
            continue
        selected_ids = {
            evidence_id for bullet in section.get("bullets", []) for evidence_id in bullet.get("evidence_ids", [])
        }
        facts = [fact for fact in role.get("facts", []) if fact.get("public_usable")]
        critical = [fact for fact in facts if fact["importance"] == "CRITICAL"]
        material = [fact for fact in facts if fact["importance"] == "MATERIAL"]
        preserved = [fact for fact in facts if selected_ids & set(fact.get("evidence_ids", []))]
        lost_critical = [fact["fact_id"] for fact in critical if fact not in preserved]
        lost_material = [fact["fact_id"] for fact in material if fact not in preserved]
        identity_ok = bool(section.get("record_id") and (section.get("actual_title") or section.get("name")))
        assessments.append({
            "role_record_id": role["role_record_id"], "included": True,
            "identity_preserved": identity_ok, "preserved_fact_ids": [fact["fact_id"] for fact in preserved],
            "lost_critical_fact_ids": lost_critical, "lost_material_fact_ids": lost_material,
            "status": "FAIL" if not identity_ok or lost_critical else ("REVIEW" if lost_material else "PASS"),
        })
    return {
        "status": "FAIL" if any(item["status"] == "FAIL" for item in assessments) else ("REVIEW" if any(item["status"] == "REVIEW" for item in assessments) else "PASS"),
        "roles": assessments,
    }


def evaluate_material_evidence_loss(
    profile: dict[str, Any], content: dict[str, Any], role_fact_set: dict[str, Any],
    *, employer_need_trace: dict[str, Any] | None = None,
    strongest_omissions: dict[str, Any] | None = None,
    omission_reasons: dict[str, str] | None = None,
    material_loss_threshold: int = 1,
) -> dict[str, Any]:
    """Build MaterialEvidenceLossV1 and its production acceptance decision."""
    selected = _selected_evidence(content)
    reasons = omission_reasons or {}
    preservation = assess_role_fact_preservation(role_fact_set, content)
    included_roles = {item["record_id"] for item in [*content.get("employment", []), *content.get("projects", [])]}
    evidence_index = {item["record_id"]: item for item in profile.get("evidence", [])}
    losses: list[dict[str, Any]] = []
    accounted: set[str] = set()

    for role_assessment in preservation["roles"]:
        role = next(item for item in role_fact_set["roles"] if item["role_record_id"] == role_assessment["role_record_id"])
        for fact_id in [*role_assessment["lost_critical_fact_ids"], *role_assessment["lost_material_fact_ids"]]:
            fact = next(item for item in role["facts"] if item["fact_id"] == fact_id)
            evidence_id = fact["evidence_ids"][0] if fact["evidence_ids"] else fact_id
            classification = "CRITICAL_LOSS" if fact["importance"] == "CRITICAL" else "MATERIAL_LOSS"
            losses.append({
                "evidence_id": evidence_id, "dimension": fact["category"], "classification": classification,
                "reason": _normalize_omission_reason(reasons.get(evidence_id)),
                "detail": f"Included role lost {fact['importance'].lower()} {fact['category'].lower()} fact {fact_id}",
                "role_record_id": role["role_record_id"], "need_id": None,
            })
            accounted.add(evidence_id)

    employment_records = {item["record_id"]: item for item in profile.get("employment", [])}
    visible_employment_roles = [
        role for role in role_fact_set.get("roles", [])
        if role["context_type"] == "EMPLOYMENT" and role.get("visibility") in PUBLIC_VISIBILITY
    ]
    for role in visible_employment_roles:
        if role["role_record_id"] in included_roles:
            continue
        public_facts = [fact for fact in role.get("facts", []) if fact.get("public_usable") and fact["importance"] in {"CRITICAL", "MATERIAL"}]
        if not public_facts:
            continue
        record = employment_records.get(role["role_record_id"], {})
        start = record.get("start_year")
        end = record.get("end_year")
        end_numeric = 9999 if end in {None, "PRESENT", "Present"} else end
        long_running = isinstance(start, int) and isinstance(end_numeric, int) and (end_numeric == 9999 or end_numeric - start >= 3)
        rationale = _normalize_omission_reason(reasons.get(role["role_record_id"]))
        if not long_running and rationale in {"SPACE", "DOCUMENT_BALANCE", "JOB_MISMATCH"}:
            continue
        evidence_id = public_facts[0]["evidence_ids"][0] if public_facts[0]["evidence_ids"] else role["role_record_id"]
        losses.append({
            "evidence_id": evidence_id, "dimension": "PROFESSIONAL_HISTORY",
            "classification": "MATERIAL_LOSS", "reason": rationale,
            "detail": "Omitted professional role contains material public facts needed for continuity or credibility",
            "role_record_id": role["role_record_id"], "need_id": None,
        })
        accounted.add(evidence_id)

    for need in (employer_need_trace or {}).get("needs", []):
        if need.get("importance") not in {"CRITICAL", "HIGH"} or need.get("gap_state") != "RESUME_OMISSION":
            continue
        available = [evidence_id for evidence_id in need.get("candidate_evidence_ids", []) if evidence_id in evidence_index]
        if not available:
            continue
        evidence_id = available[0]
        classification = "CRITICAL_LOSS" if need["importance"] == "CRITICAL" and need["top_third_signal"] == "TOP_THIRD" else "MATERIAL_LOSS"
        losses.append({
            "evidence_id": evidence_id, "dimension": "EMPLOYER_NEED_COVERAGE", "classification": classification,
            "reason": _normalize_omission_reason(reasons.get(evidence_id)),
            "detail": f"Supported {need['importance'].lower()} employer need is not represented",
            "role_record_id": None, "need_id": need["need_id"],
        })
        accounted.add(evidence_id)

    for finding in (strongest_omissions or {}).get("findings", []):
        evidence_id = finding["strongest_evidence_id"]
        if evidence_id in accounted or not finding.get("silent"):
            continue
        losses.append({
            "evidence_id": evidence_id, "dimension": "TARGET_ROLE_CAPABILITY",
            "classification": "MATERIAL_LOSS", "reason": None,
            "detail": "Materially stronger public evidence was silently replaced or omitted",
            "role_record_id": None, "need_id": finding["need_id"],
        })
        accounted.add(evidence_id)

    # Explicitly account for harmless compression; this makes page-budget
    # decisions auditable without treating every omitted fact as a defect.
    for evidence_id, evidence in evidence_index.items():
        if evidence_id in selected or evidence_id in accounted or evidence.get("visibility") not in PUBLIC_VISIBILITY:
            continue
        reason = _normalize_omission_reason(reasons.get(evidence_id))
        linked_included_role = bool(set(evidence.get("employment_ids", []) + evidence.get("project_ids", [])) & included_roles)
        if reason == "REDUNDANCY":
            classification = "NON_MATERIAL"
        elif reason in {"SPACE", "DOCUMENT_BALANCE", "JOB_MISMATCH", "CONTEXT_MISMATCH"} and not linked_included_role:
            classification = "ACCEPTABLE_COMPRESSION"
        else:
            continue
        losses.append({
            "evidence_id": evidence_id, "dimension": "REDUNDANCY" if classification == "NON_MATERIAL" else "DOCUMENT_BALANCE",
            "classification": classification, "reason": reason,
            "detail": "Omission is explicit and does not remove a protected role or employer-need fact",
            "role_record_id": None, "need_id": None,
        })

    # One omitted evidence record may protect several role facts (for example,
    # an action, tool, and outcome). Count the loss incident once per evidence
    # record while retaining fact-level diagnostics in ``losses``.
    counts = {
        classification: len({item["evidence_id"] for item in losses if item["classification"] == classification})
        for classification in ("NON_MATERIAL", "ACCEPTABLE_COMPRESSION", "MATERIAL_LOSS", "CRITICAL_LOSS")
    }
    critical_count = counts["CRITICAL_LOSS"]
    material_count = counts["MATERIAL_LOSS"]
    top_third_ok = (employer_need_trace or {"top_third_coverage": {"status": "PASS"}})["top_third_coverage"]["status"] == "PASS"
    strongest_ok = (strongest_omissions or {"status": "PASS"})["status"] == "PASS"
    if critical_count:
        status = "FAIL"
    elif material_count > material_loss_threshold or not top_third_ok or not strongest_ok or preservation["status"] == "FAIL":
        status = "REVIEW"
    else:
        status = "PASS"
    result = {
        "schema": "careeros.material-evidence-loss.v1", "schema_version": "1.0.0",
        "assessment_id": f"material-loss:{uuid.uuid5(uuid.NAMESPACE_URL, role_fact_set['fact_set_id'] + ':' + sha256_value(content))}",
        "profile_id": _profile_id(profile), "losses": losses,
        "counts": counts,
        "material_loss_threshold": material_loss_threshold, "role_fact_preservation": preservation,
        "document_budget_policy": [
            "REMOVE_REDUNDANCY", "COMPRESS_OPTIONAL_EVIDENCE", "COMPRESS_LOWER_PRIORITY_ROLES_PROJECTS",
            "PRESERVE_CRITICAL_MATERIAL_EVIDENCE", "ALLOW_TWO_PAGES_BEFORE_CRITICAL_LOSS",
        ],
        "top_third_coverage_pass": top_third_ok, "strongest_evidence_omission_pass": strongest_ok,
        "status": status, "acceptance_allowed": status == "PASS",
    }
    result["assessment_hash"] = sha256_value(result)
    return result


def build_career_conversion_trace(
    profile: dict[str, Any], content: dict[str, Any], *, build_scope: str,
    employer_need_trace: dict[str, Any] | None = None,
    omission_reasons: dict[str, str] | None = None,
    material_loss_threshold: int = 1,
) -> dict[str, Any]:
    role_facts = build_role_fact_set(profile)
    strongest = None
    if employer_need_trace is not None:
        strongest = strongest_evidence_omissions(
            profile, employer_need_trace, _selected_evidence(content), omission_reasons,
        )
    material = evaluate_material_evidence_loss(
        profile, content, role_facts, employer_need_trace=employer_need_trace,
        strongest_omissions=strongest, omission_reasons=omission_reasons,
        material_loss_threshold=material_loss_threshold,
    )
    top_needs = [
        {"need_id": item["need_id"], "statement": item["need_statement"], "importance": item["importance"],
         "strongest_matched_evidence_ids": item["candidate_evidence_ids"], "resume_usage": item["resume_usage"],
         "prominence": item["prominence"]}
        for item in (employer_need_trace or {}).get("needs", [])
        if item["importance"] in {"CRITICAL", "HIGH"}
    ]
    preserved = material["role_fact_preservation"]
    result = {
        "schema": "careeros.career-conversion-trace.v1", "schema_version": "1.0.0",
        "trace_id": f"career-conversion:{uuid.uuid5(uuid.NAMESPACE_URL, _profile_id(profile) + ':' + build_scope + ':' + sha256_value(content))}",
        "profile_id": _profile_id(profile), "build_scope": build_scope,
        "employer_need_trace": employer_need_trace,
        "strongest_evidence_omission": strongest,
        "role_fact_set": role_facts, "material_evidence_loss": material,
        "top_employer_needs": top_needs,
        "selected_evidence_ids": sorted(_selected_evidence(content)),
        "omitted_strong_evidence_ids": sorted({item["strongest_evidence_id"] for item in (strongest or {}).get("findings", [])}),
        "role_facts_preserved": sum(len(item["preserved_fact_ids"]) for item in preserved["roles"]),
        "material_losses": material["counts"]["MATERIAL_LOSS"],
        "critical_losses": material["counts"]["CRITICAL_LOSS"],
        "document_budget_decisions": material["document_budget_policy"],
        "gates": {
            "EMPLOYER_NEED_TRACE": employer_need_trace is not None if build_scope == "TARGETED" else True,
            "TOP_THIRD_COVERAGE": material["top_third_coverage_pass"],
            "STRONGEST_EVIDENCE_OMISSION": material["strongest_evidence_omission_pass"],
            "ROLE_FACT_PRESERVATION": preserved["status"] != "FAIL",
            "MATERIAL_EVIDENCE_LOSS": material["counts"]["MATERIAL_LOSS"] <= material["material_loss_threshold"],
            "CRITICAL_EVIDENCE_LOSS": material["counts"]["CRITICAL_LOSS"] == 0,
        },
        "status": "PASS" if material["acceptance_allowed"] else ("FAIL" if material["status"] == "FAIL" else "REVIEW"),
    }
    result["trace_hash"] = sha256_value(result)
    return result
