"""Canonical evidence expansion before recruiter-facing generation.

The module converts shallow source claims into *proposed* structured evidence,
measures what is still unknown, and asks only high-value follow-up questions.
It never treats source wording or a clarification answer as canonical until the
ordinary onboarding review/approval/commit boundary is crossed.
"""

from __future__ import annotations

import copy
import re
import uuid
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config
from careeros.core.io import atomic_write_json, read_json, sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import require_current_workspace, schema_dir, utc_now


DEPTH_LEVELS = ("UNKNOWN", "VERY_THIN", "THIN", "USABLE", "RICH")
DIMENSIONS = (
    "ACTION_DEPTH", "CONTEXT_DEPTH", "TOOL_DEPTH", "SCOPE_DEPTH", "OUTCOME_DEPTH",
    "METRIC_DEPTH", "OWNERSHIP_DEPTH", "STAKEHOLDER_DEPTH", "ARTIFACT_DEPTH",
    "VERIFICATION_DEPTH",
)
RESPONSIBILITY_LEVELS = ("PARTICIPATED", "SUPPORTED", "EXECUTED", "COORDINATED", "OWNED", "LED", "APPROVED", "UNKNOWN")
METRIC_STATES = ("VERIFIED", "DOCUMENT_BACKED", "USER_CONFIRMED", "USER_APPROXIMATE", "RECONSTRUCTABLE", "UNSUPPORTED")

CONTEXT_BY_TYPE = {
    "EMPLOYMENT": "PROFESSIONAL_EMPLOYMENT",
    "PROFESSIONAL_EMPLOYMENT": "PROFESSIONAL_EMPLOYMENT",
    "PAID_CONTRACT": "PAID_CONTRACT",
    "CONTRACT": "PAID_CONTRACT",
    "VOLUNTEER": "VOLUNTEER",
    "PROJECT": "PROJECT",
    "PUBLIC_PORTFOLIO_PROJECT": "PERSONAL_PROJECT",
    "PORTFOLIO_PROJECT": "PERSONAL_PROJECT",
    "PERSONAL_PROJECT": "PERSONAL_PROJECT",
    "LAB": "LAB",
    "LAB_PROJECT": "LAB",
    "SIMULATION": "SIMULATION",
    "JOB_SIMULATION": "SIMULATION",
    "COURSEWORK": "COURSEWORK",
    "TRAINING": "COURSEWORK",
}

QUESTION_LIBRARY = {
    "ACTION_DEPTH": ("RESPONSIBILITY", "What did you personally do, step by step?", "actions", "HIGH_VALUE"),
    "CONTEXT_DEPTH": ("PROCESS", "Why did this work exist, and what problem or need did it address?", "problem_or_need", "MEDIUM_VALUE"),
    "TOOL_DEPTH": ("TOOLS", "Which tools, systems, methods, or procedures did you actually use?", "tools_methods", "HIGH_VALUE"),
    "SCOPE_DEPTH": ("SCOPE", "What was the recurring scope or scale—such as volume, frequency, systems, locations, or people supported?", "scope", "MEDIUM_VALUE"),
    "OUTCOME_DEPTH": ("OUTCOMES", "What was finished, delivered, validated, improved, resolved, or handed off because of this work?", "outcomes", "HIGH_VALUE"),
    "METRIC_DEPTH": ("METRICS", "Is there a defensible count, volume, duration, frequency, turnaround, accuracy, or other scale measure? Approximate or unknown is acceptable.", "metrics", "MEDIUM_VALUE"),
    "OWNERSHIP_DEPTH": ("LEADERSHIP", "Which responsibility level is accurate: participated, supported, executed, coordinated, owned, led, approved, or unknown?", "responsibility", "HIGH_VALUE"),
    "STAKEHOLDER_DEPTH": ("STAKEHOLDERS", "Who used, received, reviewed, depended on, or was supported by this work?", "stakeholders", "MEDIUM_VALUE"),
    "ARTIFACT_DEPTH": ("ARTIFACT", "What concrete artifact, report, ticket, dataset, dashboard, document, code, or work product exists?", "artifacts", "HIGH_VALUE"),
    "VERIFICATION_DEPTH": ("QUALITY", "What source can verify this claim, if any? Unknown is acceptable.", "source_refs", "MEDIUM_VALUE"),
}


def _identifier(record: dict[str, Any]) -> str:
    return str(record.get("evidence_id") or record.get("record_id") or "")


def decompose_source_bullet(text: str, *, source_ref: str | None = None) -> dict[str, Any]:
    """Conservatively decompose source wording without upgrading its truth state."""
    original = re.sub(r"\s+", " ", str(text or "").strip())
    claims: list[dict[str, Any]] = []
    if not original:
        return {"original_text": original, "source_ref": source_ref, "atomic_claims": claims}

    metric_pattern = re.compile(r"(?<![A-Za-z])(?:~|approximately\s+|about\s+)?\d[\d,]*(?:\.\d+)?%?\+?(?:\s*(?:per|/)?\s*(?:day|week|month|hour|shift|year))?", re.I)
    for match in metric_pattern.finditer(original):
        claims.append({"component": "METRIC", "value": match.group(0).strip(), "source_span": [match.start(), match.end()], "verification": "UNSUPPORTED"})

    result_split = re.split(r"\s+(?:resulting in|which|so that|to enable|leading to|and (?:resolved|reduced|improved|delivered|produced|completed))\s+", original, maxsplit=1, flags=re.I)
    action_clause = result_split[0].strip(" .;")
    if action_clause:
        first = action_clause.split()[0]
        claims.append({"component": "ACTION", "value": first, "source_span": [0, len(first)], "verification": "SOURCE_CLAIM"})
        remainder = action_clause[len(first):].strip(" ,")
        if remainder:
            claims.append({"component": "OBJECT", "value": remainder, "source_span": None, "verification": "SOURCE_CLAIM"})
    if len(result_split) > 1 and result_split[1].strip():
        claims.append({"component": "RESULT", "value": result_split[1].strip(" .;"), "source_span": None, "verification": "SOURCE_CLAIM"})

    tool_match = re.search(r"\b(?:using|via|with|in)\s+([^,.;]+)", original, re.I)
    if tool_match:
        claims.append({"component": "TOOL", "value": tool_match.group(1).strip(), "source_span": [tool_match.start(1), tool_match.end(1)], "verification": "SOURCE_CLAIM"})
    stakeholder_match = re.search(r"\bfor\s+([^,.;]+)", original, re.I)
    if stakeholder_match:
        claims.append({"component": "STAKEHOLDER", "value": stakeholder_match.group(1).strip(), "source_span": [stakeholder_match.start(1), stakeholder_match.end(1)], "verification": "SOURCE_CLAIM"})
    context_match = re.search(r"\b(?:during|within|across|while)\s+([^,.;]+)", original, re.I)
    if context_match:
        claims.append({"component": "CONTEXT", "value": context_match.group(1).strip(), "source_span": [context_match.start(1), context_match.end(1)], "verification": "SOURCE_CLAIM"})
    return {"original_text": original, "source_ref": source_ref, "atomic_claims": claims}


def proposed_block_from_source_bullet(
    text: str, *, evidence_id: str, source_ref: str, evidence_context: str,
    linked_record_id: str | None = None, timestamp: str | None = None,
) -> dict[str, Any]:
    """Create a proposed block from atomic source claims, never polished copy."""
    decomposition = decompose_source_bullet(text, source_ref=source_ref)
    by_component: dict[str, list[str]] = {}
    for claim in decomposition["atomic_claims"]:
        by_component.setdefault(claim["component"], []).append(claim["value"])
    action = " ".join([*(by_component.get("ACTION", [])[:1]), *(by_component.get("OBJECT", [])[:1])]).strip()
    employment = evidence_context in {"PROFESSIONAL_EMPLOYMENT", "PAID_CONTRACT"}
    project = evidence_context in {"PROJECT", "LAB", "SIMULATION", "COURSEWORK", "PERSONAL_PROJECT", "VOLUNTEER"}
    now = utc_now(timestamp)
    source_hash = sha256_value({"text": decomposition["original_text"], "source_ref": source_ref})
    provenance = [{
        "source_id": f"source:{evidence_id}", "source_type": "DOCUMENT",
        "source_reference": source_ref, "source_record_id": evidence_id,
        "field": "source_bullet", "source_hash": source_hash, "captured_at": now,
    }]
    record = {
        "record_id": evidence_id, "evidence_type": evidence_context,
        "summary": decomposition["original_text"], "context": None, "ownership": None,
        "actions": [action] if action else [], "tools_methods": by_component.get("TOOL", []),
        "stakeholders": by_component.get("STAKEHOLDER", []), "outcomes": by_component.get("RESULT", []),
        "metrics": [{
            "measurement_id": f"measurement:{uuid.uuid5(uuid.NAMESPACE_URL, evidence_id + ':' + value)}",
            "metric_type": "OTHER", "value": value, "unit": None, "state": "UNSUPPORTED",
            "approximate": value.casefold().startswith(("~", "about", "approximately")),
            "formula": None, "inputs": [], "source_refs": provenance, "public_use_allowed": False,
        } for value in by_component.get("METRIC", [])],
        "source_original_wording": [decomposition["original_text"]],
        "skill_ids": [], "employment_ids": [linked_record_id] if employment and linked_record_id else [],
        "project_ids": [linked_record_id] if project and linked_record_id else [],
        "provenance": provenance, "verification_state": "UNVERIFIED", "confidence": "LOW",
        "visibility": "INTERNAL", "status": "ACTIVE", "claim_boundaries": [],
        "metric_boundaries": ["Source-document numbers remain unsupported until reviewed."],
        "created_at": now, "updated_at": now,
    }
    block = evidence_block_from_record(record, timestamp=now)
    block["evidence_context"] = evidence_context
    block["record_type"] = "EMPLOYMENT_EVIDENCE" if employment else "PROJECT_EVIDENCE" if project else "OTHER_EVIDENCE"
    block["employment_or_project_id"] = linked_record_id
    return block


def _responsibility(record: dict[str, Any]) -> dict[str, Any]:
    ownership = str(record.get("ownership") or "").strip()
    lowered = ownership.casefold()
    level = "UNKNOWN"
    for candidate in RESPONSIBILITY_LEVELS[:-1]:
        if candidate.casefold() in lowered:
            level = candidate
            break
    if level == "UNKNOWN" and ownership:
        level = "SUPPORTED"
    return {"level": level, "description": ownership or None}


def _public_use_policy(visibility: str, verification: str) -> str:
    if visibility in {"PRIVATE", "RESTRICTED"}:
        return "PROHIBITED"
    if verification in {"DISPUTED"}:
        return "INTERNAL_ONLY"
    if verification in {"UNVERIFIED", "NEEDS_VERIFICATION"}:
        return "REVIEW_REQUIRED"
    return "ALLOWED"


def evidence_block_from_record(record: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
    """Upgrade one shallow evidence record into a fact-preserving proposed block."""
    if record.get("schema") == "careeros.evidence-block.v1":
        block = copy.deepcopy(record)
        block["updated_at"] = utc_now(timestamp or block.get("updated_at") or block.get("created_at"))
        return block
    evidence_id = _identifier(record)
    if not evidence_id:
        raise ValueError("evidence record requires record_id or evidence_id")
    now = utc_now(timestamp or record.get("updated_at") or record.get("created_at"))
    evidence_type = str(record.get("evidence_type") or "OTHER").upper()
    employment_ids = list(record.get("employment_ids", []))
    project_ids = list(record.get("project_ids", []))
    if employment_ids:
        record_type = "EMPLOYMENT_EVIDENCE"
        linked_id = employment_ids[0]
    elif project_ids:
        record_type = "PROJECT_EVIDENCE"
        linked_id = project_ids[0]
    elif evidence_type in {"COURSEWORK", "TRAINING"}:
        record_type = "TRAINING_EVIDENCE"
        linked_id = None
    else:
        record_type = "OTHER_EVIDENCE"
        linked_id = None
    context = CONTEXT_BY_TYPE.get(evidence_type, "PROFESSIONAL_EMPLOYMENT" if employment_ids else "OTHER")
    provenance = copy.deepcopy(record.get("provenance", []))
    source_refs = copy.deepcopy(provenance) or [{"source_reference": "unknown", "source_type": "UNKNOWN"}]
    verification = str(record.get("verification") or record.get("verification_state") or "UNVERIFIED")
    visibility = str(record.get("visibility") or "INTERNAL")
    skills = list(record.get("skill_ids", []))
    skill_context = "PROFESSIONAL" if employment_ids else ("LAB" if context == "LAB" else "PROJECT" if project_ids else "BASIC_FAMILIARITY")
    original = list(record.get("source_original_wording", []))
    if not original and record.get("summary"):
        original = [str(record["summary"])]
    return {
        "schema": "careeros.evidence-block.v1",
        "schema_version": "1.0.0",
        "record_id": evidence_id,
        "evidence_id": evidence_id,
        "record_type": record_type,
        "employment_or_project_id": linked_id,
        "evidence_context": context,
        "source_refs": source_refs,
        "source_original_wording": original,
        "summary": record.get("summary"),
        "context": record.get("context"),
        "problem_or_need": record.get("problem_or_need"),
        "responsibility": copy.deepcopy(record.get("responsibility") or _responsibility(record)),
        "actions": list(record.get("actions", [])),
        "tools_methods": list(record.get("tools_methods", record.get("tools", []))),
        "stakeholders": list(record.get("stakeholders", [])),
        "scope": record.get("scope"),
        "scale": copy.deepcopy(record.get("scale", [])),
        "frequency": record.get("frequency"),
        "deliverables": list(record.get("deliverables", [])),
        "outcomes": list(record.get("outcomes", [])),
        "metrics": copy.deepcopy(record.get("metrics", [])),
        "constraints": list(record.get("constraints", [])),
        "quality_risk": list(record.get("quality_risk", [])),
        "leadership_ownership": list(record.get("leadership_ownership", [])),
        "handoffs_escalations": list(record.get("handoffs_escalations", [])),
        "skills_demonstrated": copy.deepcopy(record.get("skills_demonstrated", [
            {"skill_id": skill_id, "context": skill_context, "level": None, "evidence_basis": record.get("summary")}
            for skill_id in skills
        ])),
        "artifacts": copy.deepcopy(record.get("artifacts", [])),
        "verification": verification,
        "confidence": str(record.get("confidence") or "UNKNOWN"),
        "visibility": visibility,
        "public_use_policy": str(record.get("public_use_policy") or _public_use_policy(visibility, verification)),
        "created_at": str(record.get("created_at") or now),
        "updated_at": now,
        "supersedes": record.get("supersedes") or record.get("supersedes_record_id"),
        "provenance": provenance,
        "status": str(record.get("status") or "ACTIVE"),
        "claim_boundaries": list(record.get("claim_boundaries", [])),
        "metric_boundaries": list(record.get("metric_boundaries", [])),
        "skill_ids": skills,
        "employment_ids": employment_ids,
        "project_ids": project_ids,
    }


def _dimension(count: int, *, rich_at: int = 3, usable_at: int = 1) -> str:
    if count >= rich_at:
        return "RICH"
    if count >= usable_at:
        return "USABLE"
    return "UNKNOWN"


def assess_evidence_depth(block: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
    """Measure evidence completeness, never candidate quality."""
    action_count = len(block.get("actions", []))
    context_count = sum(bool(block.get(field)) for field in ("context", "problem_or_need"))
    scope_count = sum(bool(block.get(field)) for field in ("scope", "frequency")) + len(block.get("scale", []))
    responsibility = block.get("responsibility", {})
    dimensions = {
        "ACTION_DEPTH": _dimension(action_count, rich_at=3),
        "CONTEXT_DEPTH": _dimension(context_count, rich_at=2),
        "TOOL_DEPTH": _dimension(len(block.get("tools_methods", [])), rich_at=3),
        "SCOPE_DEPTH": _dimension(scope_count, rich_at=3),
        "OUTCOME_DEPTH": _dimension(len(block.get("outcomes", [])) + len(block.get("deliverables", [])), rich_at=3),
        "METRIC_DEPTH": _dimension(len(block.get("metrics", [])) + len(block.get("scale", [])), rich_at=2),
        "OWNERSHIP_DEPTH": "USABLE" if responsibility.get("level") not in {None, "UNKNOWN"} else "UNKNOWN",
        "STAKEHOLDER_DEPTH": _dimension(len(block.get("stakeholders", [])), rich_at=2),
        "ARTIFACT_DEPTH": _dimension(len(block.get("artifacts", [])) + len(block.get("deliverables", [])), rich_at=2),
        "VERIFICATION_DEPTH": "RICH" if block.get("verification") in {"VERIFIED", "DOCUMENT_BACKED"} else ("USABLE" if block.get("source_refs") else "UNKNOWN"),
    }
    score = sum(2 if value == "RICH" else 1 if value == "USABLE" else 0 for value in dimensions.values())
    known = sum(value != "UNKNOWN" for value in dimensions.values())
    if score >= 14 and known >= 8:
        overall = "RICH"
    elif score >= 8 and known >= 5:
        overall = "USABLE"
    elif score >= 4:
        overall = "THIN"
    elif score > 0:
        overall = "VERY_THIN"
    else:
        overall = "UNKNOWN"
    evidence_id = _identifier(block)
    return {
        "schema": "careeros.evidence-depth-assessment.v1",
        "schema_version": "1.0.0",
        "assessment_id": f"evidence-depth:{uuid.uuid5(uuid.NAMESPACE_URL, evidence_id + ':' + sha256_value(dimensions))}",
        "evidence_id": evidence_id,
        "dimensions": dimensions,
        "overall_depth": overall,
        "missing_dimensions": [key for key, value in dimensions.items() if value == "UNKNOWN"],
        "assessed_at": utc_now(timestamp),
    }


def generate_targeted_questions(
    block: dict[str, Any], assessment: dict[str, Any], *, lane_context: list[str] | None = None,
    job_context: list[str] | None = None, max_questions: int = 4,
) -> list[dict[str, Any]]:
    """Generate value-ranked questions only for missing evidence dimensions."""
    lane_context = [str(item) for item in (lane_context or [])]
    job_context = [str(item) for item in (job_context or [])]
    signals = " ".join([*lane_context, *job_context]).casefold()
    record_text = " ".join([
        str(block.get("summary") or ""), str(block.get("context") or ""),
        *map(str, block.get("actions", [])), *map(str, block.get("tools_methods", [])),
    ]).casefold()
    questions = []
    for dimension in assessment.get("missing_dimensions", []):
        family, prompt, target, base_priority = QUESTION_LIBRARY[dimension]
        priority = base_priority
        if dimension in {"TOOL_DEPTH", "ACTION_DEPTH", "OUTCOME_DEPTH", "OWNERSHIP_DEPTH"} and signals:
            priority = "HIGH_VALUE"
        if dimension == "METRIC_DEPTH" and assessment.get("overall_depth") in {"UNKNOWN", "VERY_THIN"}:
            priority = "OPTIONAL"
        if dimension == "ARTIFACT_DEPTH" and block.get("evidence_context") in {"PROJECT", "LAB", "SIMULATION", "COURSEWORK", "PERSONAL_PROJECT"}:
            priority = "HIGH_VALUE"
        key = f"{_identifier(block)}:{dimension}:{'|'.join(lane_context)}:{'|'.join(job_context)}"
        questions.append({
            "question_id": f"evidence-question:{uuid.uuid5(uuid.NAMESPACE_URL, key)}",
            "evidence_id": _identifier(block),
            "family": family,
            "question": prompt,
            "target_field": target,
            "priority": priority,
            "rationale": f"{dimension} is missing; filling it may improve qualification, lane analysis, resume quality, interview readiness, or gap analysis.",
            "lane_context": lane_context,
            "job_context": job_context,
            "existing_source_overlap": bool(signals and any(token in record_text for token in re.findall(r"[a-z0-9+#.]+", signals) if len(token) > 3)),
            "answer_type": "structured_or_text",
            "allows_unknown": True,
            "required_for_commit": False,
        })
    priority_order = {"HIGH_VALUE": 0, "MEDIUM_VALUE": 1, "OPTIONAL": 2}
    return sorted(questions, key=lambda item: (priority_order[item["priority"]], item["question_id"]))[:max_questions]


def generate_job_gap_questions(
    evidence: list[dict[str, Any]], requirements: list[dict[str, Any]], *, max_questions: int = 5,
) -> list[dict[str, Any]]:
    """Ask whether an important JD gap reflects missing evidence; never create the evidence."""
    corpus = " ".join(
        " ".join([
            str(item.get("summary") or ""), str(item.get("context") or ""),
            *map(str, item.get("actions", [])), *map(str, item.get("tools_methods", [])),
            *map(str, item.get("outcomes", [])),
        ])
        for item in evidence
    ).casefold()
    questions = []
    for requirement in requirements:
        classification = str(requirement.get("requirement_class") or requirement.get("classification") or "UNKNOWN").upper()
        if classification not in {"REQUIRED", "PREFERRED"}:
            continue
        text = str(requirement.get("text") or requirement.get("capability") or "").strip()
        tokens = {token for token in re.findall(r"[a-z0-9+#.]+", text.casefold()) if len(token) > 3}
        if tokens and sum(token in corpus for token in tokens) >= max(1, len(tokens) // 2):
            continue
        requirement_id = str(requirement.get("requirement_id") or uuid.uuid5(uuid.NAMESPACE_URL, text))
        questions.append({
            "question_id": f"job-evidence-question:{uuid.uuid5(uuid.NAMESPACE_URL, requirement_id + ':' + text)}",
            "requirement_id": requirement_id, "requirement_class": classification,
            "question": f"Do you have any experience with {text} that is not represented in your profile?",
            "response_states": ["SUPPORTED_NEW_EVIDENCE", "PARTIAL_EVIDENCE", "NO_EVIDENCE", "UNKNOWN"],
            "priority": "HIGH_VALUE" if classification == "REQUIRED" else "MEDIUM_VALUE",
            "canonical_mutation": False, "requires_evidence_expansion": True,
        })
    priority_order = {"HIGH_VALUE": 0, "MEDIUM_VALUE": 1}
    return sorted(questions, key=lambda item: (priority_order[item["priority"]], item["requirement_id"]))[:max_questions]


def record_job_gap_response(question: dict[str, Any], response_state: str, details: str | None = None) -> dict[str, Any]:
    allowed = set(question.get("response_states", []))
    if response_state not in allowed:
        raise ValueError("unsupported job-gap response state")
    return {
        "question_id": question["question_id"], "requirement_id": question["requirement_id"],
        "response_state": response_state, "details": details,
        "proposal_only": response_state in {"SUPPORTED_NEW_EVIDENCE", "PARTIAL_EVIDENCE"},
        "canonical_mutation": False,
    }


def create_expansion_session(
    records: list[dict[str, Any]], *, lane_context: list[str] | None = None,
    job_context: list[str] | None = None, timestamp: str | None = None,
) -> dict[str, Any]:
    now = utc_now(timestamp)
    session_records = []
    for source_record in records:
        block = evidence_block_from_record(source_record, timestamp=now)
        assessment = assess_evidence_depth(block, timestamp=now)
        questions = generate_targeted_questions(block, assessment, lane_context=lane_context, job_context=job_context)
        session_records.append({
            "source_record_id": _identifier(source_record),
            "proposal_state": "NEEDS_CLARIFICATION" if questions else "REVIEW_READY",
            "proposed_block": block,
            "assessment": assessment,
            "questions": questions,
            "answers": [],
        })
    source_hash = sha256_value(records)
    return {
        "schema": "careeros.evidence-expansion-session.v1", "schema_version": "1.0.0",
        "session_id": f"evidence-expansion:{uuid.uuid5(uuid.NAMESPACE_URL, source_hash + ':' + '|'.join(lane_context or []) + ':' + '|'.join(job_context or []))}",
        "state": "IN_PROGRESS" if any(item["questions"] for item in session_records) else "REVIEW_READY",
        "source_hash": source_hash, "lane_context": list(lane_context or []), "job_context": list(job_context or []),
        "records": session_records, "created_at": now, "updated_at": now,
        "approved_at": None, "approved_by": None,
    }


def _append_or_set(block: dict[str, Any], field: str, value: Any) -> None:
    if value in (None, "", "UNKNOWN", ["UNKNOWN"]):
        return
    if field == "responsibility":
        if isinstance(value, str):
            value = {"level": value.upper(), "description": None}
        if value.get("level") not in RESPONSIBILITY_LEVELS:
            raise ValueError("invalid responsibility level")
        block[field] = value
        return
    if field in {"actions", "tools_methods", "stakeholders", "outcomes", "artifacts", "source_refs"}:
        values = value if isinstance(value, list) else [value]
        block[field].extend(item for item in values if item not in block[field])
        return
    if field == "metrics":
        values = value if isinstance(value, list) else [value]
        for metric in values:
            if not isinstance(metric, dict) or metric.get("state") not in METRIC_STATES:
                raise ValueError("metric answers require a supported metric state")
            metric = copy.deepcopy(metric)
            metric.setdefault(
                "measurement_id",
                f"measurement:{uuid.uuid5(uuid.NAMESPACE_URL, _identifier(block) + ':' + sha256_value(metric))}",
            )
            metric.setdefault("metric_type", "OTHER")
            metric.setdefault("value", None)
            metric.setdefault("unit", None)
            metric.setdefault("approximate", metric["state"] in {"USER_APPROXIMATE", "RECONSTRUCTABLE"})
            metric.setdefault("formula", None)
            metric.setdefault("inputs", [])
            metric.setdefault("source_refs", [])
            metric.setdefault("public_use_allowed", metric["state"] in {"VERIFIED", "DOCUMENT_BACKED", "USER_CONFIRMED"})
            block[field].append(metric)
        return
    block[field] = value


def apply_answers(session: dict[str, Any], answers: list[dict[str, Any]], *, timestamp: str | None = None) -> dict[str, Any]:
    """Apply human answers to proposals; nothing becomes canonical here."""
    result = copy.deepcopy(session)
    question_index = {
        question["question_id"]: (record, question)
        for record in result["records"] for question in record["questions"]
    }
    for answer in answers:
        question_id = answer["question_id"]
        if question_id not in question_index:
            raise ValueError(f"unknown evidence question: {question_id}")
        record, question = question_index[question_id]
        value = answer.get("value")
        _append_or_set(record["proposed_block"], question["target_field"], value)
        record["answers"].append({"question_id": question_id, "value": value, "answered_at": utc_now(timestamp)})
    for record in result["records"]:
        record["proposed_block"]["updated_at"] = utc_now(timestamp)
        record["assessment"] = assess_evidence_depth(record["proposed_block"], timestamp=timestamp)
        answered = {item["question_id"] for item in record["answers"]}
        unresolved_high = [item for item in record["questions"] if item["priority"] == "HIGH_VALUE" and item["question_id"] not in answered]
        record["proposal_state"] = "REVIEW_READY" if not unresolved_high else "NEEDS_CLARIFICATION"
    result["state"] = "REVIEW_READY" if all(item["proposal_state"] == "REVIEW_READY" for item in result["records"]) else "IN_PROGRESS"
    result["updated_at"] = utc_now(timestamp)
    return result


def approve_session(session: dict[str, Any], *, actor: str, timestamp: str | None = None) -> dict[str, Any]:
    if session.get("state") != "REVIEW_READY":
        raise ValueError("evidence expansion is not review-ready")
    result = copy.deepcopy(session)
    result["state"] = "APPROVED"
    result["approved_at"] = utc_now(timestamp)
    result["approved_by"] = actor
    result["updated_at"] = result["approved_at"]
    return result


def reconstruct_metric(
    *, measurement_id: str, metric_type: str, operation: str, inputs: list[dict[str, Any]],
    unit: str | None = None, source_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    values = [float(item["value"]) for item in inputs]
    if operation == "MULTIPLY":
        value = 1.0
        for item in values:
            value *= item
        formula = " * ".join(str(item["value"]) for item in inputs)
    elif operation == "SUM":
        value = sum(values)
        formula = " + ".join(str(item["value"]) for item in inputs)
    else:
        raise ValueError("only MULTIPLY and SUM reconstruction are supported")
    return {
        "measurement_id": measurement_id, "metric_type": metric_type, "value": value,
        "unit": unit, "state": "RECONSTRUCTABLE", "approximate": True,
        "formula": formula, "inputs": copy.deepcopy(inputs), "source_refs": copy.deepcopy(source_refs or []),
        "public_use_allowed": False,
    }


def evaluate_profile_readiness(profile: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
    evidence = profile.get("evidence", [])
    blocks = [item if item.get("schema") == "careeros.evidence-block.v1" else evidence_block_from_record(item, timestamp=timestamp) for item in evidence]
    assessments = [assess_evidence_depth(item, timestamp=timestamp) for item in blocks]
    recent_employment = profile.get("employment", [])[-2:]
    recent_ids = {item["record_id"] for item in recent_employment}
    recent_assessments = [a for a, block in zip(assessments, blocks) if set(block.get("employment_ids", [])) & recent_ids]
    project_assessments = [a for a, block in zip(assessments, blocks) if block.get("project_ids")]
    thin = [a["evidence_id"] for a in assessments if a["overall_depth"] in {"THIN", "VERY_THIN", "UNKNOWN"}]
    very_thin_recent = [a["evidence_id"] for a in recent_assessments if a["overall_depth"] in {"VERY_THIN", "UNKNOWN"}]
    unlinked_skills = [item["record_id"] for item in profile.get("skills", []) if not item.get("evidence_ids")]
    public_blocks = [item for item in blocks if item.get("public_use_policy") in {"ALLOWED", "ALLOWED_WITH_BOUNDARIES"}]
    outcome_coverage = sum(bool(item.get("outcomes") or item.get("deliverables")) for item in blocks)
    metric_coverage = sum(bool(item.get("metrics") or item.get("scale")) for item in blocks)
    if very_thin_recent or unlinked_skills:
        status = "CLARIFICATION_REQUIRED"
    elif thin and len(thin) >= max(1, len(assessments) // 2):
        status = "EVIDENCE_EXPANSION_RECOMMENDED"
    elif thin:
        status = "PROFILE_READY_WITH_GAPS"
    else:
        status = "PROFILE_READY"
    result = {
        "schema": "careeros.profile-evidence-readiness.v1", "schema_version": "1.0.0", "status": status,
        "dimensions": {
            "career_chronology_completeness": bool(profile.get("employment")),
            "employment_evidence_depth": [a["overall_depth"] for a in assessments if a["evidence_id"] in {b["evidence_id"] for b in blocks if b.get("employment_ids")}],
            "recent_role_evidence_depth": [a["overall_depth"] for a in recent_assessments],
            "target_lane_evidence_depth": [a["overall_depth"] for a in assessments],
            "project_evidence_depth": [a["overall_depth"] for a in project_assessments],
            "skill_to_evidence_linkage": {"unlinked": unlinked_skills},
            "outcome_coverage": outcome_coverage,
            "metric_scale_coverage": metric_coverage,
            "verification_coverage": sum(item.get("verification") in {"VERIFIED", "DOCUMENT_BACKED", "USER_CONFIRMED"} for item in blocks),
            "privacy_eligible_evidence": len(public_blocks),
        },
        "blocking_record_ids": sorted(set(very_thin_recent + unlinked_skills)),
        "recommended_record_ids": sorted(set(thin)),
        "evaluated_at": utc_now(timestamp),
    }
    return result


def start_workspace_session(
    workspace: Path, *, lane_context: list[str] | None = None, job_context: list[str] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    bundle = read_json(roots.state_root / "onboarding/proposed-records.json")
    records = [item["record"] for item in bundle["records"] if item["kind"] == "evidence"]
    session = create_expansion_session(records, lane_context=lane_context, job_context=job_context, timestamp=timestamp)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:evidence-expansion-session:v1", session)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "evidence-expansion/session.json", "state"), session)
    return session


def resolve_workspace_session(workspace: Path, answers_path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    session = read_json(roots.state_root / "evidence-expansion/session.json")
    answers = read_json(answers_path).get("answers", [])
    result = apply_answers(session, answers, timestamp=timestamp)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:evidence-expansion-session:v1", result)
    atomic_write_json(roots.state_root / "evidence-expansion/session.json", result)
    return result


def approve_workspace_session(workspace: Path, *, actor: str, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    result = approve_session(read_json(roots.state_root / "evidence-expansion/session.json"), actor=actor, timestamp=timestamp)
    atomic_write_json(roots.state_root / "evidence-expansion/session.json", result)
    return result


def promote_workspace_session(workspace: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    """Promote approved rich proposals into onboarding review; canonical commit remains separate."""
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    session = read_json(roots.state_root / "evidence-expansion/session.json")
    if session.get("state") != "APPROVED":
        raise ValueError("explicit evidence-expansion approval is required")
    bundle = read_json(roots.state_root / "onboarding/proposed-records.json")
    replacements = {item["source_record_id"]: item["proposed_block"] for item in session["records"]}
    registry = SchemaRegistry(schema_dir())
    for proposal in bundle["records"]:
        record_id = proposal["record"].get("record_id")
        if proposal["kind"] == "evidence" and record_id in replacements:
            registry.validate("urn:careeros:schema:evidence-block:v1", replacements[record_id])
            proposal["record"] = replacements[record_id]
            proposal["proposal_state"] = "REVIEW_READY"
            proposal["validation_errors"] = []
    unresolved_path = roots.state_root / "onboarding/clarifications.json"
    unresolved = []
    if unresolved_path.exists():
        queue = read_json(unresolved_path)
        unresolved = [item for item in queue.get("items", []) if item.get("required_for_commit") and not item.get("resolution")]
    bundle["state"] = "NEEDS_CLARIFICATION" if unresolved else "REVIEW_READY"
    atomic_write_json(roots.state_root / "onboarding/proposed-records.json", bundle)
    session["state"] = "PROMOTED"
    session["updated_at"] = utc_now(timestamp)
    atomic_write_json(roots.state_root / "evidence-expansion/session.json", session)
    return bundle
