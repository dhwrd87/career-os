"""Source-grounded job-description intelligence and adaptive tailoring contracts.

The module is deliberately deterministic and offline. Structured opportunity
requirements remain authoritative; prose parsing only identifies text that is
actually present in the retained JD snapshot and always preserves its locator.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from typing import Any, Iterable

from careeros.core.io import sha256_value
from careeros.opportunity import evaluate_requirement


REQUIREMENT_CLASSES = {
    "REQUIRED", "PREFERRED", "OPTIONAL", "RESPONSIBILITY", "OPERATING_CONDITION", "UNKNOWN",
}
COVERAGE_CLASSES = {
    "STRONG_SUPPORTED_MATCH", "SUPPORTED_MATCH", "TRANSFERABLE_MATCH", "PARTIALLY_SUPPORTED",
    "EVIDENCE_MISSING", "BRIDGEABLE_GAP", "HARD_GAP", "UNKNOWN",
}
STORY_SIGNAL_TERMS = {
    "MONITORING": ("monitor", "alert", "observability", "surveillance"),
    "INVESTIGATION": ("investigat", "triage", "analyz", "analyse", "root cause"),
    "TROUBLESHOOTING": ("troubleshoot", "diagnos", "resolve", "connectivity"),
    "CUSTOMER_SUPPORT": ("customer", "client", "member", "end user", "support"),
    "DOCUMENTATION": ("document", "record", "runbook", "ticket", "report"),
    "ESCALATION": ("escalat", "handoff", "hand off"),
    "AUTOMATION": ("automat", "script", "orchestrat"),
    "SECURITY": ("security", "threat", "incident", "vulnerab", "siem", "edr"),
    "NETWORKING": ("network", "tcp/ip", "dns", "dhcp", "routing", "switching", "vpn"),
    "COMPLIANCE": ("compliance", "audit", "control", "policy", "regulatory"),
    "VENDOR_MANAGEMENT": ("vendor", "supplier", "third party", "third-party"),
    "LEADERSHIP": ("lead", "coach", "mentor", "supervis", "manage a team"),
    "DELIVERY": ("deliver", "implement", "launch", "complete", "deploy"),
    "ANALYTICS": ("analytic", "metric", "dashboard", "reporting", "trend"),
    "COMMUNICATION": ("communicat", "present", "stakeholder", "bilingual", "written", "verbal"),
}


def _tokens(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value)
    return {
        token for token in re.findall(r"[a-z0-9+#.]+", str(value or "").casefold())
        if len(token) > 2 and token not in {"and", "the", "with", "for", "from", "into"}
    }


def _source(snapshot: dict[str, Any], locator: str, quote: str) -> dict[str, str]:
    return {"snapshot_id": snapshot["snapshot_id"], "locator": locator, "quote": quote.strip()}


def _sentences(text: str) -> list[tuple[str, int]]:
    output: list[tuple[str, int]] = []
    for match in re.finditer(r"[^\n.!?]+(?:[.!?]|$)", text):
        value = re.sub(r"\s+", " ", match.group(0)).strip()
        if value:
            output.append((value, match.start()))
    return output


def _requirement_item(requirement: dict[str, Any], index: int, snapshot: dict[str, Any]) -> dict[str, Any]:
    text = str(requirement["capability"]).strip()
    requirement_class = str(requirement.get("requirement_class") or "UNKNOWN").upper()
    if requirement_class not in REQUIREMENT_CLASSES:
        requirement_class = "UNKNOWN"
    subtype = str(requirement.get("requirement_subtype") or "SKILL").upper()
    importance = {"REQUIRED": "CRITICAL", "PREFERRED": "HIGH", "OPTIONAL": "MEDIUM"}.get(requirement_class, "MEDIUM")
    requirement_id = f"requirement:{uuid.uuid5(uuid.NAMESPACE_URL, snapshot['snapshot_id'] + ':' + str(index) + ':' + text)}"
    return {
        "requirement_id": requirement_id,
        "text": text,
        "requirement_class": requirement_class,
        "requirement_subtype": subtype,
        "importance": importance,
        "direct_experience": bool(requirement.get("direct_experience", False)),
        "minimum_duration": requirement.get("minimum_duration"),
        "sub_capabilities": list(requirement.get("sub_capabilities") or requirement.get("examples") or []),
        "source_reference": _source(snapshot, f"opportunity.requirements[{index}]", text),
        "ambiguous": requirement_class == "UNKNOWN",
    }


def _matching_sentences(snapshot: dict[str, Any], terms: Iterable[str]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for sentence, offset in _sentences(snapshot["text"]):
        lowered = sentence.casefold()
        if any(term in lowered for term in terms):
            matches.append({"text": sentence, "source_reference": _source(snapshot, f"text.char[{offset}]", sentence)})
    return matches


def analyze_job_description(opportunity: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build JobDescriptionIntelligenceV1 without adding unstated requirements."""
    requirements = [_requirement_item(item, index, snapshot) for index, item in enumerate(opportunity.get("requirements", []))]
    by_subtype: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in requirements:
        by_subtype[item["requirement_subtype"]].append(item)
        by_class[item["requirement_class"]].append(item)
    sentences = _sentences(snapshot["text"])
    mission_text, mission_offset = sentences[0] if sentences else (opportunity["role_title"], 0)
    title = opportunity["role_title"]
    lowered_title = title.casefold()
    if any(term in lowered_title for term in ("senior", "lead", "principal", "manager", "director")):
        seniority = "EXPERIENCED_OR_LEADERSHIP"
    elif any(term in lowered_title for term in ("junior", "entry", "associate", "technician i", "analyst i", "intern", "apprentice")):
        seniority = "ENTRY_OR_ASSOCIATE"
    else:
        seniority = "UNSPECIFIED"
    repeated = Counter(token for token in _tokens(snapshot["text"]) if len(token) >= 5)
    emphasized = [token for token, count in repeated.most_common() if count >= 2][:20]
    ats_terms = sorted(set().union(*(_tokens(item["text"]) for item in requirements)))
    hard = [item for item in requirements if item["requirement_class"] == "REQUIRED" and item["importance"] == "CRITICAL"]
    operating = [item for item in requirements if item["requirement_subtype"] in {"LOGISTICS", "SCHEDULE", "TRAVEL", "LOCATION", "WORK_AUTHORIZATION"}]
    result = {
        "schema": "careeros.job-description-intelligence.v1",
        "schema_version": "1.0.0",
        "intelligence_id": f"jd-intelligence:{uuid.uuid5(uuid.NAMESPACE_URL, snapshot['snapshot_id'] + ':' + snapshot['content_hash'])}",
        "opportunity_id": opportunity["opportunity_id"],
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_hash": snapshot["content_hash"],
        "role_title": {"value": title, "source_reference": _source(snapshot, "opportunity.role_title", title)},
        "role_mission": {"value": mission_text, "source_reference": _source(snapshot, f"text.char[{mission_offset}]", mission_text)},
        "seniority": {"value": seniority, "source_reference": _source(snapshot, "opportunity.role_title", title)},
        "requirements": requirements,
        "responsibilities": by_class["RESPONSIBILITY"] + _matching_sentences(snapshot, ("responsible", "will ", "you will", "duties")),
        "required_qualifications": by_class["REQUIRED"],
        "preferred_qualifications": by_class["PREFERRED"],
        "optional_qualifications": by_class["OPTIONAL"],
        "experience_requirements": by_subtype["EXPERIENCE"],
        "education_requirements": by_subtype["EDUCATION"],
        "credentials": by_subtype["CREDENTIAL"],
        "technical_skills": by_subtype["SKILL"],
        "tools_platforms": by_subtype["TOOL"],
        "domain_knowledge": [item for item in requirements if item["requirement_subtype"] == "SKILL" and any(term in item["text"].casefold() for term in ("domain", "industry", "security", "network"))],
        "operating_environment": operating,
        "shift_schedule": by_subtype["SCHEDULE"],
        "location_work_mode": by_subtype["LOCATION"],
        "travel": by_subtype["TRAVEL"],
        "work_authorization": by_subtype["WORK_AUTHORIZATION"],
        "leadership_expectations": _matching_sentences(snapshot, STORY_SIGNAL_TERMS["LEADERSHIP"]),
        "communication_expectations": _matching_sentences(snapshot, STORY_SIGNAL_TERMS["COMMUNICATION"]),
        "measurable_outcomes": _matching_sentences(snapshot, ("metric", "target", "sla", "uptime", "response time", "%")),
        "repeated_emphasized_concepts": emphasized,
        "ats_relevant_terms": ats_terms,
        "hard_disqualifiers": hard,
        "ambiguous_requirements": [item for item in requirements if item["ambiguous"]],
        "source_policy": "EXTRACT_ONLY_NO_UNSUPPORTED_INFERENCE",
    }
    result["intelligence_hash"] = sha256_value(result)
    return result


def derive_story_signals(intelligence: dict[str, Any]) -> list[dict[str, Any]]:
    text = " ".join(
        [intelligence["role_title"]["value"], intelligence["role_mission"]["value"]]
        + [item["text"] for item in intelligence.get("requirements", [])]
    ).casefold()
    signals: list[dict[str, Any]] = []
    for signal, terms in STORY_SIGNAL_TERMS.items():
        matched = [term for term in terms if term in text]
        if not matched:
            continue
        sources = [
            item["source_reference"] for item in intelligence.get("requirements", [])
            if any(term in item["text"].casefold() for term in matched)
        ]
        if any(term in intelligence["role_mission"]["value"].casefold() for term in matched):
            sources.append(intelligence["role_mission"]["source_reference"])
        signals.append({"signal": signal, "weight": len(matched) + len(sources), "matched_terms": matched, "source_references": sources})
    return sorted(signals, key=lambda item: (-item["weight"], item["signal"]))


def _coverage(profile: dict[str, Any], item: dict[str, Any]) -> tuple[str, list[str], str]:
    requirement = {
        "capability": item["text"], "requirement_class": item["requirement_class"],
        "requirement_subtype": item["requirement_subtype"], "level": "PREFERRED" if item["requirement_class"] == "PREFERRED" else "CORE",
        "direct_experience": item.get("direct_experience", False), "minimum_duration": item.get("minimum_duration"),
        "sub_capabilities": item.get("sub_capabilities", []),
    }
    evidence, gaps, _hard = evaluate_requirement(profile, requirement)
    ids = sorted({record_id for match in evidence for record_id in match.get("record_ids", [])})
    matches = [match["match"] for match in evidence] + [gap["match"] for gap in gaps]
    if "HARD_GAP" in matches:
        coverage = "HARD_GAP"
    elif "PARTIALLY_SUPPORTED" in matches:
        coverage = "PARTIALLY_SUPPORTED"
    elif "SUPPORTED_MATCH" in matches:
        direct = any(
            record_id.startswith("evidence:") and any(
                evidence_record.get("record_id") == record_id and evidence_record.get("employment_ids")
                for evidence_record in profile.get("evidence", [])
            ) for record_id in ids
        )
        coverage = "STRONG_SUPPORTED_MATCH" if direct else "SUPPORTED_MATCH"
    elif "TRANSFERABLE_MATCH" in matches:
        coverage = "TRANSFERABLE_MATCH"
    elif "BRIDGEABLE_GAP" in matches:
        coverage = "BRIDGEABLE_GAP"
    elif "PREFERRED_AND_MISSING" in matches:
        coverage = "EVIDENCE_MISSING"
    else:
        coverage = "UNKNOWN"
    strength = {
        "STRONG_SUPPORTED_MATCH": "HIGH", "SUPPORTED_MATCH": "MEDIUM_HIGH", "TRANSFERABLE_MATCH": "MEDIUM",
        "PARTIALLY_SUPPORTED": "MEDIUM", "BRIDGEABLE_GAP": "LOW", "EVIDENCE_MISSING": "NONE",
        "HARD_GAP": "NONE", "UNKNOWN": "UNKNOWN",
    }[coverage]
    return coverage, ids, strength


def build_job_evidence_matrix(
    profile: dict[str, Any], intelligence: dict[str, Any], qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_by_id = {item["record_id"]: item for item in profile.get("evidence", [])}
    project_ids = {item["record_id"] for item in profile.get("projects", [])}
    skills_by_id = {item["record_id"]: item for item in profile.get("skills", [])}
    skill_ids = set(skills_by_id)
    rows: list[dict[str, Any]] = []
    for item in intelligence.get("requirements", []):
        coverage, ids, strength = _coverage(profile, item)
        ids = sorted(set(ids) | {
            evidence_id for record_id in ids if record_id in skills_by_id
            for evidence_id in skills_by_id[record_id].get("evidence_ids", [])
            if evidence_id in evidence_by_id
        })
        contexts: set[str] = set()
        for record_id in ids:
            if record_id in skill_ids:
                contexts.add("SKILL_RECORD")
            if record_id in project_ids:
                contexts.add("PROJECT")
            evidence = evidence_by_id.get(record_id)
            if evidence:
                if evidence.get("employment_ids"):
                    contexts.add("PROFESSIONAL")
                if evidence.get("project_ids"):
                    contexts.add("PROJECT")
                if "course" in str(evidence.get("context", "")).casefold():
                    contexts.add("COURSEWORK")
        public_claims = [
            evidence_by_id[record_id].get("summary") for record_id in ids
            if record_id in evidence_by_id and evidence_by_id[record_id].get("visibility") in {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}
        ]
        prohibited: list[str] = []
        if item["requirement_subtype"] == "EXPERIENCE" and "PROFESSIONAL" not in contexts:
            prohibited.append("PROJECT_OR_COURSEWORK_IS_NOT_PROFESSIONAL_EXPERIENCE_EQUIVALENCE")
        if coverage == "TRANSFERABLE_MATCH":
            prohibited.append("TRANSFERABLE_EVIDENCE_MUST_NOT_BE_DESCRIBED_AS_DIRECT_DOMAIN_EXPERIENCE")
        gap_action = {
            "HARD_GAP": "QUALIFICATION_POLICY_DECISION",
            "EVIDENCE_MISSING": "CLARIFY_OR_DEVELOP_EVIDENCE",
            "BRIDGEABLE_GAP": "DEVELOP_OR_CLARIFY",
            "PARTIALLY_SUPPORTED": "USE_SUPPORTED_SUBCAPABILITIES_ONLY",
            "UNKNOWN": "CLARIFY_WITH_CANDIDATE",
        }.get(coverage, "NONE")
        priority = {"CRITICAL": 100, "HIGH": 75, "MEDIUM": 50}.get(item["importance"], 25)
        if coverage in {"STRONG_SUPPORTED_MATCH", "SUPPORTED_MATCH"}:
            priority += 15
        headline_terms = _tokens(intelligence["role_title"]["value"]) | _tokens(intelligence["role_mission"]["value"])
        priority += min(20, 10 * len(_tokens(item["text"]) & headline_terms))
        rows.append({
            "requirement_id": item["requirement_id"], "requirement_text": item["text"],
            "requirement_class": item["requirement_class"], "requirement_subtype": item["requirement_subtype"],
            "importance": item["importance"], "source_reference": item["source_reference"],
            "candidate_evidence_ids": ids, "coverage_class": coverage, "evidence_strength": strength,
            "evidence_context": sorted(contexts), "allowed_public_claims": [claim for claim in public_claims if claim],
            "prohibited_equivalence": prohibited, "resume_priority": priority, "gap_action": gap_action,
        })
    result = {
        "schema": "careeros.job-evidence-matrix.v1", "schema_version": "1.0.0",
        "matrix_id": f"job-matrix:{uuid.uuid5(uuid.NAMESPACE_URL, intelligence['intelligence_id'] + ':' + sha256_value(profile))}",
        "opportunity_id": intelligence["opportunity_id"], "job_intelligence_id": intelligence["intelligence_id"],
        "profile_hash": qualification.get("profile_hash") if qualification else sha256_value(profile),
        "qualification_id": qualification.get("qualification_id") if qualification else None,
        "requirements": rows,
    }
    result["matrix_hash"] = sha256_value(result)
    return result


def _evidence_score(row: dict[str, Any]) -> float:
    coverage = {
        "STRONG_SUPPORTED_MATCH": 5.0, "SUPPORTED_MATCH": 4.0, "TRANSFERABLE_MATCH": 2.5,
        "PARTIALLY_SUPPORTED": 2.0, "BRIDGEABLE_GAP": 0.5, "UNKNOWN": 0.0,
        "EVIDENCE_MISSING": -1.0, "HARD_GAP": -4.0,
    }[row["coverage_class"]]
    return coverage + row["resume_priority"] / 25.0


def prioritize_evidence(profile: dict[str, Any], base_storyline: dict[str, Any], matrix: dict[str, Any]) -> list[dict[str, Any]]:
    row_scores: dict[str, float] = defaultdict(float)
    row_ids: dict[str, list[str]] = defaultdict(list)
    for row in matrix.get("requirements", []):
        for record_id in row.get("candidate_evidence_ids", []):
            row_scores[record_id] += _evidence_score(row)
            row_ids[record_id].append(row["requirement_id"])
    lane = {item["evidence_id"]: item for item in base_storyline.get("evidence_rankings", [])}
    ranked: list[dict[str, Any]] = []
    for evidence in profile.get("evidence", []):
        evidence_id = evidence["record_id"]
        lane_score = float(lane.get(evidence_id, {}).get("score", 0.0))
        lane_class = str(lane.get(evidence_id, {}).get("classification", "OPTIONAL"))
        outcome_score = 1.0 if evidence.get("outcomes") else 0.0
        professional_score = 0.75 if evidence.get("employment_ids") else 0.0
        project_score = 0.5 if evidence.get("project_ids") else 0.0
        total = row_scores[evidence_id] * 3.0 + lane_score + outcome_score + professional_score + project_score
        if evidence.get("visibility") not in {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}:
            classification = "IRRELEVANT"
        elif row_scores[evidence_id] >= 8:
            classification = "ANCHOR"
        elif row_scores[evidence_id] > 0:
            classification = "SUPPORTING"
        elif professional_score:
            classification = "TRANSFERABLE_PROFESSIONAL"
        elif project_score and lane_class in {"ANCHOR", "SUPPORTING"}:
            classification = "SUPPORTING"
        elif project_score and (lane_score > 0 or evidence.get("outcomes")):
            classification = "FOUNDATIONAL"
        elif project_score:
            classification = "OPTIONAL"
        else:
            classification = "IRRELEVANT"
        ranked.append({
            "evidence_id": evidence_id, "classification": classification, "score": round(total, 3),
            "matched_requirement_ids": sorted(set(row_ids[evidence_id])),
            "factors": {"requirement_relevance": round(row_scores[evidence_id], 3), "lane_relevance": lane_score,
                        "outcome_strength": outcome_score, "professional_relevance": professional_score,
                        "project_relevance": project_score, "duplication_risk": 0.0, "space_cost": "STANDARD"},
        })
    return sorted(ranked, key=lambda item: (-item["score"], item["evidence_id"]))


def adapt_storyline(
    base_storyline: dict[str, Any], profile: dict[str, Any], family: dict[str, Any], opportunity: dict[str, Any],
    intelligence: dict[str, Any], matrix: dict[str, Any],
) -> dict[str, Any]:
    rankings = prioritize_evidence(profile, base_storyline, matrix)
    by_level: dict[str, list[str]] = defaultdict(list)
    for item in rankings:
        by_level[item["classification"]].append(item["evidence_id"])
    signals = derive_story_signals(intelligence)
    top_signals = [item["signal"].replace("_", " ").title() for item in signals[:3]]
    supported_rows = [row for row in matrix["requirements"] if row["coverage_class"] in {"STRONG_SUPPORTED_MATCH", "SUPPORTED_MATCH", "TRANSFERABLE_MATCH", "PARTIALLY_SUPPORTED"}]
    strongest = [row["requirement_text"] for row in sorted(supported_rows, key=lambda row: -row["resume_priority"])[:3]]
    target = opportunity["role_title"]
    adapted = dict(base_storyline)
    adapted.update({
        "job_id": opportunity["opportunity_id"], "job_story_signals": signals,
        "job_specific_recruiter_takeaway": f"Supported evidence aligns with {', '.join(strongest) or 'selected role requirements'} for the {target} role.",
        "job_anchor_evidence": by_level["ANCHOR"], "job_supporting_evidence": by_level["SUPPORTING"],
        "job_deemphasized_evidence": by_level["OPTIONAL"] + by_level["IRRELEVANT"],
        "job_specific_summary_strategy": f"Lead with the candidate's evidence-backed {family.get('display_name', 'career-lane')} foundation and emphasize {', '.join(top_signals) or 'the stated role mission'}.",
        "section_order_adjustments": ["SUMMARY", "SKILLS", "PROJECTS", "EXPERIENCE", "EDUCATION", "CREDENTIALS"] if len(by_level["ANCHOR"] + by_level["SUPPORTING"]) > 0 else base_storyline["section_priority"],
        "anchor_evidence": by_level["ANCHOR"], "supporting_evidence": by_level["SUPPORTING"],
        "context_evidence": by_level["TRANSFERABLE_PROFESSIONAL"], "evidence_to_minimize": by_level["OPTIONAL"],
        "evidence_to_exclude": by_level["IRRELEVANT"],
        "transferable_professional_evidence": by_level["TRANSFERABLE_PROFESSIONAL"],
        "foundational_evidence": by_level["FOUNDATIONAL"],
        "project_priority": by_level["ANCHOR"] + by_level["SUPPORTING"] + by_level["FOUNDATIONAL"] + by_level["OPTIONAL"],
        "evidence_rankings": rankings,
    })
    return adapted


def _preferred_mode(evidence_id: str, matrix: dict[str, Any], signals: list[dict[str, Any]]) -> str:
    signal_names = [item["signal"] for item in signals]
    requirement_text = " ".join(
        row["requirement_text"] for row in matrix["requirements"] if evidence_id in row["candidate_evidence_ids"]
    ).casefold()
    if "INVESTIGATION" in signal_names and any(term in requirement_text for term in ("investig", "triage", "analy")):
        return "INVESTIGATION"
    if "DOCUMENTATION" in signal_names and any(term in requirement_text for term in ("document", "ticket", "report")):
        return "DOCUMENTATION"
    if "ESCALATION" in signal_names and any(term in requirement_text for term in ("escalat", "handoff")):
        return "ESCALATION"
    if "CUSTOMER_SUPPORT" in signal_names and "customer" in requirement_text:
        return "CUSTOMER"
    if "COMPLIANCE" in signal_names:
        return "COMPLIANCE"
    if "NETWORKING" in signal_names or "SECURITY" in signal_names:
        return "TECHNICAL"
    return "OPERATIONS"


def render_adaptive_bullet(candidate: dict[str, Any], mode: str) -> dict[str, Any]:
    """Recompose supported fields without altering their factual boundary."""
    action = candidate.get("action", "").rstrip(".")
    method = candidate.get("tool_or_method", "").rstrip(".")
    outcome = candidate.get("outcome", "").rstrip(".")
    deliverable = candidate.get("deliverable", "").rstrip(".")
    context = str(candidate.get("role_context") or "").rstrip(".")
    actions = [str(item).rstrip(".") for item in candidate.get("supported_actions", []) if str(item).strip()]
    if not actions and action:
        actions = [action]
        if method:
            actions.append(method)
    actions = actions[:3]
    if len(actions) == 1:
        text = actions[0]
    elif len(actions) == 2:
        text = f"{actions[0]} and {actions[1][0].lower() + actions[1][1:]}"
    elif actions:
        text = f"{actions[0]}, {actions[1][0].lower() + actions[1][1:]}, and {actions[2][0].lower() + actions[2][1:]}"
    else:
        text = deliverable
    if mode == "CUSTOMER" and context and "customer" in context.casefold():
        text += f" in {context[0].lower() + context[1:]}"
    if outcome and outcome.casefold() not in text.casefold():
        text += f"; {outcome[0].lower() + outcome[1:]}"
    adapted = dict(candidate)
    adapted["variant_mode"] = mode
    adapted["base_text"] = candidate.get("text", "")
    adapted["text"] = text.rstrip(".") + "."
    adapted["truth_boundary"] = {
        "evidence_ids": list(candidate.get("evidence_ids", [])), "action": candidate.get("action"),
        "tool_or_method": candidate.get("tool_or_method"), "role_context": candidate.get("role_context"),
        "outcome": candidate.get("outcome"), "supported_actions": candidate.get("supported_actions", []),
    }
    return adapted


def select_adaptive_bullets(
    candidates: list[dict[str, Any]], matrix: dict[str, Any], signals: list[dict[str, Any]], *,
    storyline: dict[str, Any] | None = None, limit: int = 14,
    employer_need_trace: dict[str, Any] | None = None,
    role_fact_set: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requirement_scores: dict[str, float] = defaultdict(float)
    requirement_ids: dict[str, list[str]] = defaultdict(list)
    for row in matrix["requirements"]:
        for evidence_id in row["candidate_evidence_ids"]:
            requirement_scores[evidence_id] += _evidence_score(row)
            requirement_ids[evidence_id].append(row["requirement_id"])
    ranked: list[tuple[float, dict[str, Any]]] = []
    omitted: list[dict[str, Any]] = []
    tiers = {
        item["evidence_id"]: item.get("classification", "OPTIONAL")
        for item in (storyline or {}).get("evidence_rankings", [])
    }
    tier_score = {
        "ANCHOR": 16.0, "SUPPORTING": 10.0, "TRANSFERABLE_PROFESSIONAL": 7.0,
        "FOUNDATIONAL": 6.0, "OPTIONAL": 1.0, "IRRELEVANT": -10.0,
    }
    need_bonus: dict[str, float] = defaultdict(float)
    for need in (employer_need_trace or {}).get("needs", []):
        importance = {"CRITICAL": 8.0, "HIGH": 5.0, "MEDIUM": 2.0, "LOW": 0.0}.get(need.get("importance"), 0.0)
        placement = 4.0 if need.get("top_third_signal") == "TOP_THIRD" else 0.0
        for evidence_id in need.get("candidate_evidence_ids", []):
            need_bonus[evidence_id] += importance + placement
    protected_fact_bonus: dict[str, float] = defaultdict(float)
    for role in (role_fact_set or {}).get("roles", []):
        for fact in role.get("facts", []):
            bonus = {"CRITICAL": 12.0, "MATERIAL": 5.0, "SUPPORTING": 1.0, "OPTIONAL": 0.0}.get(fact.get("importance"), 0.0)
            for evidence_id in fact.get("evidence_ids", []):
                protected_fact_bonus[evidence_id] = max(protected_fact_bonus[evidence_id], bonus)
    for candidate in candidates:
        evidence_id = candidate["evidence_ids"][0]
        matched_ids = sorted(set(requirement_ids[evidence_id]))
        tier = tiers.get(evidence_id, candidate.get("lane_relevance", "OPTIONAL"))
        if not matched_ids and tier in {"OPTIONAL", "IRRELEVANT", "DISTRACTING"}:
            omitted.append({"bullet_id": candidate["bullet_id"], "reason": "LOW_PRIORITY", "evidence_ids": candidate["evidence_ids"]})
            continue
        matched_text = " ".join(row["requirement_text"] for row in matrix["requirements"] if row["requirement_id"] in matched_ids)
        candidate_text = " ".join(str(candidate.get(key) or "") for key in ("action", "tool_or_method", "deliverable", "outcome", "role_context"))
        lexical_overlap = len(_tokens(matched_text) & _tokens(candidate_text))
        score = (
            tier_score.get(tier, 0.0) + requirement_scores[evidence_id] * 3 + lexical_overlap * 3
            + (2 if candidate.get("outcome") else 0) + len(candidate.get("metric_refs", []))
            + need_bonus[evidence_id] + protected_fact_bonus[evidence_id]
        )
        variant = render_adaptive_bullet(candidate, _preferred_mode(evidence_id, matrix, signals))
        variant["matched_requirement_ids"] = matched_ids
        variant["selection_score"] = round(score, 3)
        variant["job_term_overlap"] = lexical_overlap
        variant["evidence_tier"] = tier
        variant["employer_need_priority"] = round(need_bonus[evidence_id], 3)
        variant["role_fact_priority"] = round(protected_fact_bonus[evidence_id], 3)
        ranked.append((score, variant))
    selected: list[dict[str, Any]] = []
    covered: Counter[str] = Counter()
    for _score, candidate in sorted(ranked, key=lambda item: (-item[0], item[1]["bullet_id"])):
        requirements = candidate.get("matched_requirement_ids", [])
        redundant = (
            bool(requirements)
            and all(covered[item] >= 2 for item in requirements)
            and candidate.get("job_term_overlap", 0) == 0
            and candidate.get("evidence_tier") not in {"ANCHOR", "TRANSFERABLE_PROFESSIONAL"}
        )
        if redundant:
            omitted.append({"bullet_id": candidate["bullet_id"], "reason": "REDUNDANT", "evidence_ids": candidate["evidence_ids"]})
            continue
        if len(selected) >= limit:
            omitted.append({"bullet_id": candidate["bullet_id"], "reason": "SPACE", "evidence_ids": candidate["evidence_ids"]})
            continue
        selected.append(candidate)
        covered.update(requirements)
    return selected, omitted


def job_specific_summary(storyline: dict[str, Any], opportunity: dict[str, Any]) -> str:
    signals = [item["signal"].replace("_", " ").lower() for item in storyline.get("job_story_signals", [])[:3]]
    target = opportunity["role_title"]
    focus = ", ".join(signals) if signals else "the role's stated priorities"
    return (
        f"Entry-ready candidate pursuing {target} with completed technical project work aligned to {focus}. "
        "Brings a credible professional foundation in communication, documentation, and disciplined operations while keeping project preparation distinct from professional domain experience."
    )


def evaluate_job_specific_qa(
    content: dict[str, Any], intelligence: dict[str, Any], matrix: dict[str, Any], qualification: dict[str, Any],
) -> dict[str, Any]:
    rows = matrix["requirements"]
    important = [
        row for row in rows if row["importance"] in {"CRITICAL", "HIGH"}
        and row["requirement_subtype"] not in {"LOGISTICS", "WORK_AUTHORIZATION", "SCHEDULE", "TRAVEL", "LOCATION"}
    ]
    covered_ids = {rid for section in [*content.get("employment", []), *content.get("projects", [])] for bullet in section.get("bullets", []) for rid in bullet.get("evidence_ids", [])}
    important_supported = [row for row in important if row["coverage_class"] in {"STRONG_SUPPORTED_MATCH", "SUPPORTED_MATCH", "TRANSFERABLE_MATCH", "PARTIALLY_SUPPORTED"}]
    represented = [row for row in important_supported if covered_ids & set(row["candidate_evidence_ids"])]
    coverage_ratio = len(represented) / max(1, len(important_supported))
    displayed_skills = content.get("skills", [])
    unsupported_skills = [
        item["record_id"] for item in displayed_skills
        if not item.get("evidence_ids") and not item.get("claim_boundary")
    ]
    supported_skill_ids = {record_id for row in rows for record_id in row["candidate_evidence_ids"]}
    hard_gaps = [row for row in rows if row["coverage_class"] == "HARD_GAP"]
    overreach = [row for row in rows if row["coverage_class"] == "TRANSFERABLE_MATCH" and not row["prohibited_equivalence"]]
    evidence_order = {
        item["evidence_id"]: index for index, item in enumerate(content.get("storyline", {}).get("evidence_rankings", []))
    }
    project_order = [
        min([evidence_order.get(record_id, 10_000) for bullet in project.get("bullets", []) for record_id in bullet.get("evidence_ids", [])] or [10_000])
        for project in content.get("projects", [])
    ]
    project_order_ok = project_order == sorted(project_order)
    summary = content.get("summary", "").casefold()
    title_tokens = _tokens(intelligence["role_title"]["value"])
    completeness = content.get("resume_completeness", {})
    checks = {
        "JOB_RELEVANCE": {"passed": coverage_ratio >= 0.5 or not important_supported, "detail": f"{coverage_ratio:.0%} of supported important requirements represented"},
        "RESUME_COMPLETENESS": {"passed": completeness.get("status") == "PASS", "detail": f"completeness={completeness.get('status', 'MISSING')}"},
        "IMPORTANT_REQUIREMENT_COVERAGE": {"passed": coverage_ratio >= 0.5 or not important_supported, "detail": f"{coverage_ratio:.0%} of supported important requirements represented"},
        "UNSUPPORTED_KEYWORD_INSERTION": {"passed": not unsupported_skills, "detail": "displayed skills retain canonical evidence or an explicit self-report boundary"},
        "JOB_STORY_COHERENCE": {"passed": bool(content.get("storyline", {}).get("job_story_signals")), "detail": "summary and selection use source-grounded job signals"},
        "LANE_STORY_COHERENCE": {"passed": bool(content.get("storyline", {}).get("target_role_family")), "detail": "job adaptation retains the approved lane"},
        "PROJECT_ORDER_RELEVANCE": {"passed": project_order_ok, "detail": "project order follows adapted evidence ranking"},
        "BULLET_JOB_RELEVANCE": {"passed": bool(covered_ids & supported_skill_ids), "detail": "selected bullets cover matrix-linked evidence"},
        "SUMMARY_JOB_RELEVANCE": {"passed": bool(title_tokens & _tokens(summary)), "detail": "summary names the exact target role"},
        "HARD_GAP_DISGUISE": {"passed": not hard_gaps and not qualification.get("hard_disqualifiers"), "detail": "resume build remains blocked when hard gaps exist"},
        "TRANSFERABLE_EVIDENCE_OVERREACH": {"passed": not overreach, "detail": "transferable rows carry explicit non-equivalence boundaries"},
    }
    return {"status": "PASS" if all(item["passed"] for item in checks.values()) else "FAIL", "checks": checks}


def build_tailoring_trace(
    intelligence: dict[str, Any], matrix: dict[str, Any], content: dict[str, Any], omitted_bullets: list[dict[str, Any]],
    qualification: dict[str, Any],
) -> dict[str, Any]:
    bullets = [bullet for section in [*content.get("employment", []), *content.get("projects", [])] for bullet in section.get("bullets", [])]
    selected_ids = {record_id for bullet in bullets for record_id in bullet.get("evidence_ids", [])}
    all_ids = {record_id for row in matrix["requirements"] for record_id in row["candidate_evidence_ids"]}
    supported = [row for row in matrix["requirements"] if row["coverage_class"] in {"STRONG_SUPPORTED_MATCH", "SUPPORTED_MATCH", "TRANSFERABLE_MATCH", "PARTIALLY_SUPPORTED"}]
    before = len([row for row in supported if row["candidate_evidence_ids"]])
    after = len([row for row in supported if selected_ids & set(row["candidate_evidence_ids"])])
    return {
        "schema": "careeros.job-tailoring-trace.v1", "schema_version": "1.0.0",
        "trace_id": f"tailoring-trace:{uuid.uuid5(uuid.NAMESPACE_URL, matrix['matrix_id'] + ':' + sha256_value(sorted(selected_ids)))}",
        "opportunity_id": intelligence["opportunity_id"], "job_intelligence_id": intelligence["intelligence_id"],
        "matrix_id": matrix["matrix_id"], "job_story_signals": content["storyline"].get("job_story_signals", []),
        "requirements_selected": [row["requirement_id"] for row in supported],
        "evidence_matched": sorted(selected_ids), "evidence_omitted": sorted(all_ids - selected_ids),
        "bullets_selected": [bullet["bullet_id"] for bullet in bullets],
        "bullet_variants_selected": [{"bullet_id": bullet["bullet_id"], "variant_mode": bullet.get("variant_mode", "BASE"), "evidence_ids": bullet["evidence_ids"]} for bullet in bullets],
        "summary_strategy": content["storyline"].get("job_specific_summary_strategy"),
        "skills_selected": [item["record_id"] for item in content.get("skills", [])],
        "projects_ordered": [item["record_id"] for item in content.get("projects", [])],
        "gaps_not_bridgeable": [row["requirement_id"] for row in matrix["requirements"] if row["coverage_class"] == "HARD_GAP"],
        "coverage_before": before, "coverage_after": after,
        "duplicate_suppression": omitted_bullets,
        "unused_relevant_evidence": content.get("resume_completeness", {}).get("unused_supported_evidence", []),
        "resume_completeness_status": content.get("resume_completeness", {}).get("status"),
        "truth_gate_result": "PASS" if not qualification.get("hard_disqualifiers") else "BLOCKED_HARD_GAP",
    }
