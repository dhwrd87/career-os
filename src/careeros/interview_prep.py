"""Evidence-linked, local-only interview preparation.

The contracts in this module are derivatives of canonical evidence.  They do
not schedule interviews, contact employers, or promote projects and labs into
professional experience.  A story preserves facts; an answer outline only
reorders those facts for an interview format.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Any, Iterable

from careeros.core.io import sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir, utc_now


INTERVIEW_PREP_POLICY_VERSION = "interview-evidence-pack-v1"
PUBLIC_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE"}
PUBLIC_USE = {"ALLOWED", "ALLOWED_WITH_BOUNDARIES"}
SUPPORTED_VERIFICATION = {"VERIFIED", "DOCUMENT_BACKED", "USER_CONFIRMED"}
PROFESSIONAL_CONTEXTS = {"PROFESSIONAL_EMPLOYMENT", "PAID_CONTRACT"}
PROJECT_CONTEXTS = {"PROJECT", "LAB", "SIMULATION", "COURSEWORK", "PERSONAL_PROJECT"}
STAGES = {"RECRUITER_SCREEN", "HIRING_MANAGER", "TECHNICAL", "PANEL", "FINAL"}
THEMES = {
    "CAREER_TRANSITION", "TECHNICAL_DEPTH", "TROUBLESHOOTING", "INCIDENT_RESPONSE",
    "MONITORING", "CUSTOMER_STAKEHOLDER", "DOCUMENTATION", "ESCALATION", "TEAMWORK",
    "LEADERSHIP", "PRIORITIZATION", "QUALITY", "COMPLIANCE", "PROBLEM_SOLVING",
    "LEARNING", "FAILURE_CORRECTION", "MOTIVATION", "ROLE_FIT", "SHIFT_OPERATING_CONDITIONS",
}


def _plain(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tokens(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        value = " ".join(map(str, value))
    return {
        token for token in re.findall(r"[a-z0-9+#.]+", str(value or "").casefold())
        if len(token) > 2 and token not in {"and", "for", "the", "with", "from", "into", "that", "this"}
    }


def _profile_id(profile: dict[str, Any]) -> str:
    return str(profile.get("profile_id") or profile.get("candidate", {}).get("candidate_profile_id") or "profile:unknown")


def _evidence_context(evidence: dict[str, Any]) -> str:
    explicit = str(evidence.get("evidence_context") or "").upper()
    if explicit:
        return explicit
    if evidence.get("employment_ids"):
        return "PROFESSIONAL_EMPLOYMENT"
    if evidence.get("project_ids"):
        return "PROJECT"
    return "OTHER"


def _verification(evidence: dict[str, Any]) -> str:
    return str(evidence.get("verification") or evidence.get("verification_state") or "UNVERIFIED").upper()


def _allowed(evidence: dict[str, Any]) -> bool:
    visibility = str(evidence.get("visibility") or "INTERNAL").upper()
    policy = evidence.get("public_use_policy")
    return (
        evidence.get("status", "ACTIVE") == "ACTIVE"
        and (visibility in PUBLIC_VISIBILITY or (visibility == "INTERNAL" and str(policy).upper() in PUBLIC_USE))
        and (policy is None or str(policy).upper() in PUBLIC_USE)
        and _verification(evidence) != "DISPUTED"
    )


def _metric_text(metric: dict[str, Any]) -> str | None:
    if not metric.get("public_use_allowed"):
        return None
    if str(metric.get("state") or "").upper() not in SUPPORTED_VERIFICATION:
        return None
    value = metric.get("value")
    if value is None:
        return None
    unit = _plain(metric.get("unit"))
    approximate = "approximately " if metric.get("approximate") else ""
    return f"{approximate}{value}{(' ' + unit) if unit else ''}".strip()


def _story_context(evidence: dict[str, Any]) -> str:
    context = _evidence_context(evidence)
    if context in PROFESSIONAL_CONTEXTS:
        return "PROFESSIONAL"
    if context in PROJECT_CONTEXTS:
        return context
    return "OTHER"


def _prohibited_inferences(evidence: dict[str, Any], context: str) -> list[str]:
    boundaries = [
        _plain(item) for item in [
            *evidence.get("claim_boundaries", []), *evidence.get("metric_boundaries", []),
        ] if _plain(item)
    ]
    if context not in {"PROFESSIONAL", "PAID_CONTRACT"}:
        boundaries.extend([
            "Do not describe this project, lab, simulation, or coursework as professional employment.",
            "Do not imply production ownership, enterprise scale, customers, SLAs, or on-call responsibility unless your records show that you had them.",
        ])
    if not evidence.get("leadership_ownership"):
        boundaries.append("Do not imply leadership or team ownership.")
    if not evidence.get("outcomes"):
        boundaries.append("Do not invent a result; state what was completed or learned.")
    return list(dict.fromkeys(boundaries))


def build_story_bank(profile: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
    """Build StoryBankV1 from public-usable canonical evidence facts."""
    stories: list[dict[str, Any]] = []
    for evidence in profile.get("evidence", []):
        if not _allowed(evidence):
            continue
        evidence_id = str(evidence["record_id"])
        context = _story_context(evidence)
        summary = _plain(evidence.get("summary") or evidence.get("context") or evidence_id)
        responsibility = evidence.get("responsibility") or {}
        task = _plain(responsibility.get("description") or evidence.get("problem_or_need") or summary)
        actions = [_plain(item) for item in evidence.get("actions", []) if _plain(item)]
        outcomes = [_plain(item) for item in evidence.get("outcomes", []) if _plain(item)]
        metrics = [text for metric in [*evidence.get("metrics", []), *evidence.get("scale", [])] if (text := _metric_text(metric))]
        story_id = f"story:{uuid.uuid5(uuid.NAMESPACE_URL, _profile_id(profile) + ':' + evidence_id)}"
        stories.append({
            "story_id": story_id,
            "candidate_profile_id": _profile_id(profile),
            "source_evidence_ids": [evidence_id],
            "story_context": context,
            "situation": _plain(evidence.get("context") or summary),
            "task": task,
            "actions": actions,
            "tools_methods": [_plain(item) for item in evidence.get("tools_methods", []) if _plain(item)],
            "stakeholders": [_plain(item) for item in evidence.get("stakeholders", []) if _plain(item)],
            "outcome": outcomes[0] if outcomes else None,
            "metrics": metrics,
            "lessons": [],
            "verification": _verification(evidence),
            "visibility": str(evidence.get("visibility") or "INTERNAL").upper(),
            "professional_context": context in {"PROFESSIONAL", "PAID_CONTRACT"},
            "allowed_use": "INTERVIEW_PREP",
            "prohibited_inferences": _prohibited_inferences(evidence, context),
        })
    record = {
        "schema": "careeros.story-bank.v1", "schema_version": "1.0.0",
        "story_bank_id": f"story-bank:{uuid.uuid5(uuid.NAMESPACE_URL, _profile_id(profile) + ':' + sha256_value(stories))}",
        "candidate_profile_id": _profile_id(profile),
        "candidate_profile_hash": sha256_value(profile),
        "created_at": utc_now(timestamp), "policy_version": INTERVIEW_PREP_POLICY_VERSION,
        "stories": stories,
    }
    record["story_bank_hash"] = sha256_value(record)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:story-bank:v1", record)
    return record


def _theme_for_need(need: dict[str, Any]) -> str:
    kind = str(need.get("need_type") or "OTHER")
    statement = str(need.get("need_statement") or "").casefold()
    if kind == "SECURITY":
        return "INCIDENT_RESPONSE" if "incident" in statement else "MONITORING"
    if kind == "NETWORKING":
        return "TROUBLESHOOTING"
    if kind in {"TECHNICAL", "AUTOMATION", "ANALYTICS"}:
        return "TECHNICAL_DEPTH"
    if kind == "CUSTOMER":
        return "CUSTOMER_STAKEHOLDER"
    if kind == "COMMUNICATION":
        return "DOCUMENTATION"
    if kind == "LEADERSHIP":
        return "LEADERSHIP"
    if kind == "COMPLIANCE":
        return "COMPLIANCE"
    if kind in {"OPERATIONS", "PROCESS", "CORE_DELIVERY"}:
        return "PRIORITIZATION"
    return "ROLE_FIT"


def build_question_themes(
    employer_need_trace: dict[str, Any], *, stage: str,
    role_family: dict[str, Any] | None = None, qualification: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Create traceable themes, never claims that an exact question will be asked."""
    if stage not in STAGES:
        raise ValueError(f"unsupported interview stage: {stage}")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for need in employer_need_trace.get("needs", []):
        if need.get("importance") not in {"CRITICAL", "HIGH", "MEDIUM"}:
            continue
        category = _theme_for_need(need)
        key = f"{category}:{need['need_id']}"
        if key in seen:
            continue
        seen.add(key)
        coverage = need.get("coverage_class", "UNKNOWN")
        rows.append({
            "theme_id": f"theme:{uuid.uuid5(uuid.NAMESPACE_URL, key + ':' + stage)}",
            "category": category, "basis": "JD_SIGNAL", "source_refs": need.get("source_refs", []),
            "need_ids": [need["need_id"]], "candidate_evidence_ids": need.get("candidate_evidence_ids", []),
            "coverage": "GAP" if coverage in {"GAP", "UNKNOWN", "OMITTED"} else ("TRANSFERABLE_ONLY" if coverage == "TRANSFERABLE_ONLY" else "ADEQUATE"),
            "stage": stage,
        })
    stage_categories = {
        "RECRUITER_SCREEN": ["MOTIVATION", "ROLE_FIT", "CAREER_TRANSITION", "SHIFT_OPERATING_CONDITIONS"],
        "HIRING_MANAGER": ["TEAMWORK", "PRIORITIZATION", "DOCUMENTATION", "PROBLEM_SOLVING"],
        "TECHNICAL": ["TECHNICAL_DEPTH", "TROUBLESHOOTING", "FAILURE_CORRECTION"],
        "PANEL": ["TEAMWORK", "CUSTOMER_STAKEHOLDER", "ESCALATION"],
        "FINAL": ["ROLE_FIT", "MOTIVATION", "LEARNING"],
    }[stage]
    role_ref = (role_family or {}).get("role_family_id")
    gap_refs = [str(item.get("requirement_id") or item.get("gap_id")) for item in (qualification or {}).get("gaps", [])]
    for category in stage_categories:
        if any(row["category"] == category for row in rows):
            continue
        rows.append({
            "theme_id": f"theme:{uuid.uuid5(uuid.NAMESPACE_URL, category + ':' + stage + ':' + str(role_ref))}",
            "category": category, "basis": "INTERVIEW_STAGE" if not gap_refs else "CANDIDATE_GAP",
            "source_refs": ([{"role_family_id": role_ref}] if role_ref else []),
            "need_ids": gap_refs if category in {"CAREER_TRANSITION", "TECHNICAL_DEPTH"} else [],
            "candidate_evidence_ids": [], "coverage": "UNKNOWN", "stage": stage,
        })
    return rows


def select_stories(
    story_bank: dict[str, Any], themes: list[dict[str, Any]], employer_need_trace: dict[str, Any],
    *, maximum: int = 6,
) -> dict[str, Any]:
    """Select a diverse story shortlist using need relevance and evidence strength."""
    needs = {need["need_id"]: need for need in employer_need_trace.get("needs", [])}
    evidence_need_weight: Counter[str] = Counter()
    for need in needs.values():
        weight = {"CRITICAL": 5, "HIGH": 3, "MEDIUM": 1, "LOW": 0}[need.get("importance", "LOW")]
        if need.get("top_third_signal") == "TOP_THIRD":
            weight += 2
        for evidence_id in need.get("candidate_evidence_ids", []):
            evidence_need_weight[evidence_id] += weight
    ranked: list[tuple[float, dict[str, Any]]] = []
    for story in story_bank.get("stories", []):
        evidence_score = sum(evidence_need_weight[item] for item in story["source_evidence_ids"])
        text = " ".join([
            story["situation"], story["task"], *story["actions"], *story["tools_methods"], story.get("outcome") or "",
        ])
        theme_matches = sum(bool(_tokens(text) & _tokens(row["category"].replace("_", " "))) for row in themes)
        score = evidence_score + theme_matches + (2 if story["professional_context"] else 0) + (1 if story.get("outcome") else 0) + (1 if story.get("metrics") else 0)
        ranked.append((score, story))
    ranked.sort(key=lambda item: (-item[0], item[1]["story_id"]))
    selected = [story for score, story in ranked if score > 0][:maximum]
    if not selected:
        selected = [story for _score, story in ranked[:maximum]]
    assignments: list[dict[str, Any]] = []
    usage: Counter[str] = Counter()
    for theme in themes:
        candidates = []
        direct = set(theme.get("candidate_evidence_ids", []))
        for story in selected:
            overlap = len(direct & set(story["source_evidence_ids"]))
            text_overlap = len(_tokens(theme["category"].replace("_", " ")) & _tokens(" ".join([story["situation"], story["task"], *story["actions"]])))
            candidates.append((overlap * 10 + text_overlap * 2 + bool(story.get("outcome")) - usage[story["story_id"]] * 2, story))
        candidates.sort(key=lambda item: (-item[0], item[1]["story_id"]))
        chosen = candidates[0][1] if candidates and candidates[0][0] > 0 else None
        if chosen:
            usage[chosen["story_id"]] += 1
        assignments.append({
            "theme_id": theme["theme_id"], "story_id": chosen["story_id"] if chosen else None,
            "source_evidence_ids": chosen["source_evidence_ids"] if chosen else [],
            "coverage": "STRONG_PREP" if chosen and direct & set(chosen["source_evidence_ids"]) else ("ADEQUATE" if chosen else theme["coverage"]),
        })
    return {"selected_story_ids": [item["story_id"] for item in selected], "theme_assignments": assignments}


def build_answer_boundaries(
    themes: list[dict[str, Any]], story_bank: dict[str, Any], qualification: dict[str, Any],
) -> dict[str, Any]:
    evidence_context = {
        evidence_id: story for story in story_bank.get("stories", []) for evidence_id in story["source_evidence_ids"]
    }
    boundaries: list[dict[str, Any]] = []
    for theme in themes:
        supporting = [item for item in theme.get("candidate_evidence_ids", []) if item in evidence_context]
        project_only = bool(supporting) and all(not evidence_context[item]["professional_context"] for item in supporting)
        weak = theme.get("coverage") in {"GAP", "UNKNOWN", "TRANSFERABLE_ONLY"} or project_only
        if not weak:
            continue
        can_say = []
        prohibited = []
        for evidence_id in supporting:
            story = evidence_context[evidence_id]
            can_say.extend(story["actions"] or [story["task"]])
            prohibited.extend(story["prohibited_inferences"])
        if not can_say:
            can_say = ["State that this capability has not yet been demonstrated in the available evidence."]
        if project_only:
            prohibited.append("Do not present project, lab, simulation, or coursework evidence as professional production experience.")
        if not supporting:
            prohibited.append("Do not invent a story, tool, metric, outcome, or responsibility to close this gap.")
        boundaries.append({
            "boundary_id": f"answer-boundary:{uuid.uuid5(uuid.NAMESPACE_URL, theme['theme_id'])}",
            "theme_id": theme["theme_id"], "category": theme["category"],
            "can_say": list(dict.fromkeys(can_say)), "must_not_imply": list(dict.fromkeys(prohibited)),
            "safe_bridge_language": "Be direct about the boundary, describe the closest supported evidence, and explain the next learning step without claiming completed experience.",
            "supporting_evidence_ids": supporting,
            "when_to_answer_unknown": "Answer that this is not yet established when no cited evidence supports the requested detail.",
            "professional_context": "PROJECT_ONLY" if project_only else ("NONE" if not supporting else "MIXED"),
            "verification": "SUPPORTED" if supporting else "UNKNOWN",
            "visibility": "INTERVIEW_INTERNAL",
        })
    record = {
        "schema": "careeros.interview-answer-boundary.v1", "schema_version": "1.0.0",
        "boundary_set_id": f"answer-boundaries:{uuid.uuid5(uuid.NAMESPACE_URL, sha256_value(boundaries) + ':' + str(qualification.get('qualification_id')))}",
        "qualification_id": str(qualification.get("qualification_id") or "qualification:unknown"),
        "boundaries": boundaries,
    }
    record["boundary_set_hash"] = sha256_value(record)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:interview-answer-boundary:v1", record)
    return record


def _answer_outline(story: dict[str, Any], format_name: str) -> dict[str, Any]:
    fields = {
        "situation": story["situation"], "task": story["task"], "actions": story["actions"],
        "result": story.get("outcome"), "metrics": story.get("metrics", []), "lessons": story.get("lessons", []),
    }
    return {
        "outline_id": f"answer-outline:{uuid.uuid5(uuid.NAMESPACE_URL, story['story_id'] + ':' + format_name)}",
        "story_id": story["story_id"], "format": format_name, "source_evidence_ids": story["source_evidence_ids"],
        "fields": fields, "prohibited_inferences": story["prohibited_inferences"],
    }


def _technical_walkthrough(story: dict[str, Any]) -> dict[str, Any]:
    missing = "Your records do not include this detail. Say so if asked."
    return {
        "walkthrough_id": f"technical-walkthrough:{uuid.uuid5(uuid.NAMESPACE_URL, story['story_id'])}",
        "story_id": story["story_id"], "source_evidence_ids": story["source_evidence_ids"],
        "OBJECTIVE": story["task"], "ENVIRONMENT": story["story_context"],
        "TOOLS": story["tools_methods"], "WHAT_I_DID": story["actions"],
        "WHAT_I_OBSERVED": story.get("outcome") or missing,
        "DECISION_ANALYSIS": missing, "RESULT": story.get("outcome") or missing,
        "LIMITATIONS": story["prohibited_inferences"], "WHAT_I_WOULD_DO_NEXT": missing,
    }


def _follow_up_probes(story: dict[str, Any]) -> dict[str, Any]:
    notes = {
        "What exactly did you do?": story["actions"] or [story["task"]],
        "What tool did you use?": story["tools_methods"] or ["Your records do not name a tool for this example."],
        "How did you validate it?": [story.get("outcome") or "Your records do not say how you checked the result."],
        "Was this professional or a lab/project?": [story["story_context"]],
        "What was the scale?": story["metrics"] or ["Your records do not say how large the work was."],
        "What would you do differently?": ["Explain what you would change, and make clear that this is your reflection."],
    }
    return {"story_id": story["story_id"], "source_evidence_ids": story["source_evidence_ids"], "probes": [{"question": key, "safe_notes": value} for key, value in notes.items()]}


def _career_transition_prep(profile: dict[str, Any], selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    professional = [item for item in selected if item["professional_context"]]
    technical = [item for item in selected if item["story_context"] in PROJECT_CONTEXTS]
    evidence_ids = list(dict.fromkeys([item for story in [*professional[:2], *technical[:2]] for item in story["source_evidence_ids"]]))
    target = profile.get("preferences", {}).get("target_role_families") or profile.get("preferences", {}).get("target_roles") or []
    return [{
        "prompt": "Why are you changing careers, why this role, and what have you done to prepare?",
        "response_plan": [
            "Name the target direction without apologizing for the transition.",
            "Connect prior professional work to supported transferable strengths.",
            "Describe technical preparation using its true project, lab, or coursework context.",
            "Close with the role contribution sought now, not a claim that the transition is already complete.",
        ],
        "target_preferences": target, "source_evidence_ids": evidence_ids,
    }]


def _candidate_questions(trace: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    needs = trace.get("needs", [])
    categories = ["SUCCESS_METRICS", "ONBOARDING", "TOOLS", "ESCALATION", "TEAM", "CAREER_DEVELOPMENT"]
    if any(need.get("need_type") in {"OPERATIONS", "NETWORKING", "SECURITY"} for need in needs):
        categories.insert(0, "SHIFT_OPERATIONS")
    templates = {
        "SUCCESS_METRICS": "How will success in this role be evaluated during the first 90 days?",
        "ONBOARDING": "What does the onboarding path look like before someone handles the role's core work independently?",
        "TOOLS": "Which tools are most central to the team's day-to-day workflow, and how are new team members expected to learn them?",
        "ESCALATION": "How does the team decide when and how to escalate an issue?",
        "TEAM": "How does this role collaborate with adjacent teams during routine work and high-priority situations?",
        "CAREER_DEVELOPMENT": "What skills distinguish people who grow successfully from this role?",
        "SHIFT_OPERATIONS": "How are handoffs and priorities managed across shifts or operating windows?",
    }
    jd_text = " ".join(str(ref.get("quote") or "") for need in needs for ref in need.get("source_refs", []))
    result = []
    for category in categories[:5]:
        question = templates[category]
        # Suppress questions only when the source explicitly answers the full
        # concept, not merely because it contains one keyword.
        if category == "SUCCESS_METRICS" and {"first", "days", "success"} <= _tokens(jd_text):
            continue
        result.append({"category": category, "question": question, "derived_from_need_ids": [item["need_id"] for item in needs[:3]], "stage": stage})
    return result


def evaluate_interview_pack_qa(
    pack: dict[str, Any], story_bank: dict[str, Any], *, current_profile_hash: str, current_job_hash: str,
) -> dict[str, Any]:
    stories = {item["story_id"]: item for item in story_bank.get("stories", [])}
    selected = [stories[item] for item in pack.get("selected_story_ids", []) if item in stories]
    trace_ok = all(item.get("source_evidence_ids") for item in selected)
    boundaries_ok = all(item.get("must_not_imply") and item.get("safe_bridge_language") for item in pack.get("gap_boundaries", []))
    equivalence_ok = all(
        story["professional_context"] or any("not describe" in text.casefold() or "not imply production" in text.casefold() for text in story["prohibited_inferences"])
        for story in selected
    )
    metric_ok = all(
        metric in story_bank_metric
        for story in selected
        for metric in story.get("metrics", [])
        for story_bank_metric in [next(item for item in story_bank["stories"] if item["story_id"] == story["story_id"])["metrics"]]
    )
    assignments = pack.get("story_shortlist", {}).get("theme_assignments", [])
    counts = Counter(item.get("story_id") for item in assignments if item.get("story_id"))
    duplication_ok = not counts or max(counts.values()) <= max(2, len(assignments) // 2)
    alignment_ok = all(item.get("basis") in {"JD_SIGNAL", "ROLE_FAMILY", "CANDIDATE_GAP", "INTERVIEW_STAGE"} for item in pack.get("likely_question_themes", []))
    gap_ok = all(item.get("coverage") not in {"GAP", "UNKNOWN", "TRANSFERABLE_ONLY"} or any(boundary["theme_id"] == item["theme_id"] for boundary in pack.get("gap_boundaries", [])) for item in pack.get("likely_question_themes", []))
    lineage = pack.get("lineage", {})
    freshness_ok = lineage.get("candidate_profile_hash") == current_profile_hash and lineage.get("job_snapshot_hash") == current_job_hash
    gates = {
        "STORY_EVIDENCE_TRACE": trace_ok, "ANSWER_BOUNDARY": boundaries_ok,
        "PROFESSIONAL_EQUIVALENCE": equivalence_ok, "METRIC_SUPPORT": metric_ok,
        "STORY_DUPLICATION": duplication_ok, "EMPLOYER_NEED_ALIGNMENT": alignment_ok,
        "GAP_DISCLOSURE": gap_ok, "PACK_FRESHNESS": freshness_ok,
    }
    return {"gates": gates, "status": "PASS" if all(gates.values()) else "FAIL"}


def build_interview_evidence_pack(
    *, profile: dict[str, Any], opportunity: dict[str, Any], snapshot: dict[str, Any],
    qualification: dict[str, Any], employer_need_trace: dict[str, Any], application_id: str,
    interview_id: str, stage: str, role_family: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build and validate InterviewEvidencePackV1 for a qualified opportunity."""
    decision = str(qualification.get("decision") or qualification.get("qualification_state") or "").upper()
    if decision not in {"QUALIFIED", "PASS", "ACCEPTED"}:
        raise ValueError("interview preparation requires a qualified opportunity")
    story_bank = build_story_bank(profile, timestamp=timestamp)
    themes = build_question_themes(employer_need_trace, stage=stage, role_family=role_family, qualification=qualification)
    shortlist = select_stories(story_bank, themes, employer_need_trace)
    story_index = {item["story_id"]: item for item in story_bank["stories"]}
    selected = [story_index[item] for item in shortlist["selected_story_ids"]]
    boundary_set = build_answer_boundaries(themes, story_bank, qualification)
    answer_outlines = [_answer_outline(item, "TECHNICAL_WALKTHROUGH" if item["story_context"] in PROJECT_CONTEXTS else "STAR") for item in selected]
    walkthroughs = [_technical_walkthrough(item) for item in selected if item["story_context"] in PROJECT_CONTEXTS or item["tools_methods"]]
    probes = [_follow_up_probes(item) for item in selected]
    top_needs = [item for item in employer_need_trace.get("needs", []) if item.get("importance") in {"CRITICAL", "HIGH"}][:6]
    created_at = utc_now(timestamp)
    pack = {
        "schema": "careeros.interview-evidence-pack.v1", "schema_version": "1.0.0",
        "pack_id": f"interview-pack:{uuid.uuid5(uuid.NAMESPACE_URL, _profile_id(profile) + ':' + opportunity['opportunity_id'] + ':' + interview_id + ':' + sha256_value([profile, snapshot, employer_need_trace]))}",
        "candidate_profile_id": _profile_id(profile), "opportunity_id": opportunity["opportunity_id"],
        "application_id": application_id, "interview_id": interview_id,
        "job_snapshot_id": snapshot["snapshot_id"], "qualification_id": qualification["qualification_id"],
        "employer_need_trace_id": employer_need_trace["trace_id"], "created_at": created_at,
        "policy_version": INTERVIEW_PREP_POLICY_VERSION, "pack_status": "REVIEW_REQUIRED",
        "role_context": {"role_title": opportunity.get("role_title"), "employer": opportunity.get("employer"), "interview_stage": stage},
        "employer_need_summary": [{"need_id": item["need_id"], "statement": item["need_statement"], "importance": item["importance"], "top_third_signal": item["top_third_signal"], "coverage": item["coverage_class"]} for item in top_needs],
        "likely_question_themes": themes, "selected_story_ids": shortlist["selected_story_ids"],
        "technical_evidence_ids": list(dict.fromkeys([evidence_id for item in selected if item["tools_methods"] or item["story_context"] in PROJECT_CONTEXTS for evidence_id in item["source_evidence_ids"]])),
        "gap_boundaries": boundary_set["boundaries"],
        "prohibited_claims": list(dict.fromkeys([text for item in selected for text in item["prohibited_inferences"]])),
        "candidate_questions": _candidate_questions(employer_need_trace, stage),
        "prep_checklist": [
            "Check each example against your notes and work records.", "Practice concise and detailed versions without memorizing a script.",
            "State project, lab, coursework, and professional context accurately.", "Use only numbers and results you can back up.",
            "Be ready to say when you do not know a detail or have not done something yet.",
        ],
        "artifact_refs": [{"artifact_type": "STORY_SHORTLIST", "artifact_id": story_bank["story_bank_id"]}, {"artifact_type": "ANSWER_BOUNDARIES", "artifact_id": boundary_set["boundary_set_id"]}],
        "lineage": {
            "candidate_profile_hash": sha256_value(profile), "canonical_revision": profile.get("canonical_revision"),
            "opportunity_id": opportunity["opportunity_id"], "job_snapshot_hash": snapshot["content_hash"],
            "qualification_id": qualification["qualification_id"], "employer_need_trace_id": employer_need_trace["trace_id"],
            "story_ids": shortlist["selected_story_ids"], "evidence_ids": list(dict.fromkeys([evidence_id for item in selected for evidence_id in item["source_evidence_ids"]])),
            "pack_version": "1.0.0", "created_at": created_at,
        },
        "story_shortlist": shortlist, "answer_outlines": answer_outlines,
        "technical_walkthroughs": walkthroughs, "follow_up_probes": probes,
        "career_transition_prep": _career_transition_prep(profile, selected),
    }
    qa = evaluate_interview_pack_qa(pack, story_bank, current_profile_hash=sha256_value(profile), current_job_hash=snapshot["content_hash"])
    pack["qa_gates"] = qa["gates"]
    pack["pack_hash"] = sha256_value(pack)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:interview-evidence-pack:v1", pack)
    return pack, story_bank, boundary_set


def accept_interview_evidence_pack(pack: dict[str, Any], *, human_confirmed: bool) -> dict[str, Any]:
    result = dict(pack)
    if not human_confirmed or not all(pack.get("qa_gates", {}).values()):
        raise ValueError("human confirmation and passing interview QA are required")
    result["pack_status"] = "ACCEPTED"
    result.pop("pack_hash", None)
    result["pack_hash"] = sha256_value(result)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:interview-evidence-pack:v1", result)
    return result


def evaluate_pack_freshness(
    pack: dict[str, Any], *, current_profile_hash: str, current_job_hash: str,
    current_employer_need_trace_id: str | None = None,
) -> dict[str, Any]:
    lineage = pack.get("lineage", {})
    reasons = []
    if lineage.get("candidate_profile_hash") != current_profile_hash:
        reasons.append("CANONICAL_EVIDENCE_CHANGED")
    if lineage.get("job_snapshot_hash") != current_job_hash:
        reasons.append("JOB_SNAPSHOT_CHANGED")
    if current_employer_need_trace_id and lineage.get("employer_need_trace_id") != current_employer_need_trace_id:
        reasons.append("EMPLOYER_NEED_TRACE_CHANGED")
    return {"status": "STALE" if reasons else "CURRENT", "reasons": reasons, "pack_status": "STALE" if reasons else pack.get("pack_status")}
