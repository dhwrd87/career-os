"""Synthetic opportunity intake and evidence-preserving qualification."""

from __future__ import annotations

import uuid
import re
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config
from careeros.core.io import atomic_write_json, read_json, sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.versions import QUALIFICATION_POLICY_VERSION
from careeros.workspace import require_current_workspace, schema_dir, utc_now
from careeros.updates import mark_derivative_current, require_derivative_current


EMPLOYER_USABLE_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}
REQUIREMENT_SUBTYPES = {
    "EXPERIENCE", "EDUCATION", "CREDENTIAL", "SKILL", "TOOL", "LOGISTICS",
    "WORK_AUTHORIZATION", "SCHEDULE", "TRAVEL", "LOCATION",
}
DECISION_SUBTYPES = {"LOGISTICS", "SCHEDULE", "TRAVEL", "LOCATION"}


def _infer_requirement_subtype(requirement: dict[str, Any]) -> str:
    explicit = requirement.get("requirement_subtype")
    if explicit:
        if explicit not in REQUIREMENT_SUBTYPES:
            raise ValueError(f"unsupported requirement_subtype: {explicit}")
        return explicit
    capability = str(requirement.get("capability", "")).casefold()
    decision_hits = sum(
        bool(re.search(pattern, capability))
        for pattern in (r"\bshift|schedule|24/7", r"\btravel", r"\blocation|office|onsite|on-site|remote|hybrid")
    )
    if decision_hits > 1:
        return "LOGISTICS"
    if re.search(r"\bshift|schedule|24/7", capability):
        return "SCHEDULE"
    if re.search(r"\btravel", capability):
        return "TRAVEL"
    if re.search(r"\blocation|office|onsite|on-site|remote|hybrid", capability):
        return "LOCATION"
    if re.search(r"work authorization|sponsorship|citizen|resident", capability):
        return "WORK_AUTHORIZATION"
    if re.search(r"bachelor|master|doctorate|degree|education", capability):
        return "EDUCATION"
    if re.search(r"credential|certification|certificate|license", capability):
        return "CREDENTIAL"
    if requirement.get("direct_experience") or re.search(r"\bexperience\b|\byears?\b", capability):
        return "EXPERIENCE"
    if requirement.get("tool") is True:
        return "TOOL"
    return "SKILL"


def _normalize_requirement(requirement: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(requirement)
    level = str(normalized.get("level", "CORE")).upper()
    normalized["level"] = level
    normalized["requirement_class"] = str(
        normalized.get("requirement_class") or ("PREFERRED" if level == "PREFERRED" else "REQUIRED")
    ).upper()
    normalized["requirement_subtype"] = _infer_requirement_subtype(normalized)
    if "sub_capabilities" not in normalized and normalized.get("examples"):
        normalized["sub_capabilities"] = list(normalized["examples"])
    return normalized


def _is_mandatory(requirement: dict[str, Any]) -> bool:
    return requirement.get("requirement_class") == "REQUIRED"


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9+#]+", value.casefold())
        if token not in {"a", "an", "and", "or", "of", "the", "with", "based"}
    }


def _token_matches(left: str, right: str) -> bool:
    if left == right:
        return True
    return len(left) >= 4 and len(right) >= 4 and left[:4] == right[:4]


def _text_supports(text: str, capability: str) -> bool:
    text_tokens = _tokens(text)
    wanted = _tokens(capability)
    if not wanted:
        return False
    matched = sum(any(_token_matches(token, candidate) for candidate in text_tokens) for token in wanted)
    if "/" in capability:
        threshold = 1
    elif len(wanted) <= 2:
        threshold = len(wanted)
    else:
        threshold = (len(wanted) + 1) // 2
    return matched >= threshold


def _usable_evidence_ids(skill: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> list[str]:
    return [
        record_id for record_id in skill.get("evidence_ids", [])
        if record_id in evidence_by_id and evidence_by_id[record_id]["visibility"] in EMPLOYER_USABLE_VISIBILITY
    ]


def _skill_aliases(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for skill in profile.get("skills", []):
        for name in [skill.get("name"), *skill.get("aliases", [])]:
            if name:
                result[str(name).casefold()] = skill
    return result


def _search_documents(profile: dict[str, Any]) -> list[tuple[str, str]]:
    documents: list[tuple[str, str]] = []
    evidence_by_id = {record["record_id"]: record for record in profile.get("evidence", [])}
    for skill in profile.get("skills", []):
        if _usable_evidence_ids(skill, evidence_by_id):
            documents.append((" ".join([skill.get("name", ""), *skill.get("aliases", []), *skill.get("contexts", [])]), skill["record_id"]))
    for record in profile.get("evidence", []):
        if record.get("visibility") in EMPLOYER_USABLE_VISIBILITY:
            documents.append((" ".join([record.get("summary", ""), *record.get("actions", []), *record.get("outcomes", [])]), record["record_id"]))
    for record in profile.get("projects", []):
        if record.get("visibility") in EMPLOYER_USABLE_VISIBILITY:
            documents.append((" ".join([
                record.get("name", ""), record.get("purpose", ""), record.get("contribution", ""),
                *record.get("technologies", []),
            ]), record["record_id"]))
    for record in profile.get("credentials", []):
        if record.get("visibility") in EMPLOYER_USABLE_VISIBILITY:
            documents.append((f"{record.get('title', '')} {record.get('issuer', '')}", record["record_id"]))
    return documents


def _aggregate_sub_capabilities(profile: dict[str, Any], requirement: dict[str, Any]) -> dict[str, Any] | None:
    sub_capabilities = [str(item) for item in requirement.get("sub_capabilities", [])]
    if not sub_capabilities:
        return None
    documents = _search_documents(profile)
    supported: list[str] = []
    missing: list[str] = []
    record_ids: set[str] = set()
    for sub_capability in sub_capabilities:
        matches = [record_id for text, record_id in documents if _text_supports(text, sub_capability)]
        if matches:
            supported.append(sub_capability)
            record_ids.update(matches)
        else:
            missing.append(sub_capability)
    return {"supported": supported, "missing": missing, "record_ids": sorted(record_ids)}


def _preferences(profile: dict[str, Any]) -> dict[str, Any]:
    preferences = profile.get("preferences") or {}
    if isinstance(preferences, list):
        return preferences[0] if preferences else {}
    return preferences


def _decision_requirement(profile: dict[str, Any], requirement: dict[str, Any]) -> tuple[str, str, list[str]]:
    subtype = requirement["requirement_subtype"]
    preferences = _preferences(profile)
    capability = requirement["capability"]
    if subtype == "TRAVEL":
        value = preferences.get("travel_preference")
        if not value:
            return "UNKNOWN_DECISION", "Candidate has not made this job-specific travel decision.", []
        required_percent = re.search(r"(\d+)\s*%", capability)
        preferred_percent = re.search(r"(\d+)\s*(?:%|percent)", str(value), re.IGNORECASE)
        if required_percent and preferred_percent:
            satisfied = int(preferred_percent.group(1)) >= int(required_percent.group(1))
            return ("SUPPORTED_MATCH", "Known travel preference satisfies the requirement.", []) if satisfied else ("HARD_GAP", "Known travel preference does not satisfy the mandatory requirement.", [])
        return "UNKNOWN_DECISION", "Travel preference exists, but compatibility cannot be determined safely.", []
    if subtype == "SCHEDULE":
        values = [str(value) for value in preferences.get("schedule_preferences", [])]
        if not values:
            return "UNKNOWN_DECISION", "Candidate has not made this job-specific schedule decision.", []
        joined = " ".join(values).casefold()
        required = capability.casefold()
        if any(term in required for term in ("rotating", "night", "24/7")):
            if any(term in joined for term in ("rotating", "flexible", "night", "24/7", "any shift")):
                return "SUPPORTED_MATCH", "Known schedule preference satisfies the requirement.", []
            if "daytime" in joined or "business hours" in joined:
                return "HARD_GAP", "Known schedule preference does not satisfy the mandatory requirement.", []
        return "UNKNOWN_DECISION", "Schedule preferences exist, but compatibility cannot be determined safely.", []
    if subtype == "LOCATION":
        work_modes = {str(value).upper() for value in preferences.get("work_modes", [])}
        locations = [str(value) for value in preferences.get("location_preferences", [])]
        if not work_modes and not locations:
            return "UNKNOWN_DECISION", "Candidate has not made this job-specific location decision.", []
        required = capability.casefold()
        if any(term in required for term in ("office", "onsite", "on-site", "hybrid")):
            if work_modes & {"ONSITE", "HYBRID"}:
                return "SUPPORTED_MATCH", "Known work-mode preference is compatible with office attendance.", []
            if work_modes == {"REMOTE"}:
                return "HARD_GAP", "Known remote-only preference does not satisfy the mandatory office requirement.", []
        return "UNKNOWN_DECISION", "Location preferences exist, but compatibility cannot be determined safely.", []
    return "UNKNOWN_DECISION", "Combined logistics require a job-specific candidate decision.", []


def _education_requirement(profile: dict[str, Any], requirement: dict[str, Any]) -> tuple[str, str, list[str]]:
    education = profile.get("education", [])
    capability = requirement["capability"].casefold()
    bachelor_required = "bachelor" in capability
    matching = [record for record in education if not bachelor_required or "bachelor" in str(record.get("program", "")).casefold()]
    completed = [record for record in matching if str(record.get("completion_status", "")).upper() == "COMPLETED"]
    if completed:
        return "SUPPORTED_MATCH", "A completed canonical education record satisfies the requirement.", [record["record_id"] for record in completed]
    in_progress = [record for record in matching if str(record.get("completion_status", "")).upper() == "IN_PROGRESS"]
    if in_progress:
        return "HARD_GAP", "Relevant education is in progress; an in-progress degree does not satisfy a completed-degree requirement.", [record["record_id"] for record in in_progress]
    return "HARD_GAP", "The reviewed canonical education inventory does not satisfy the mandatory requirement.", []


def _experience_requirement(profile: dict[str, Any], requirement: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None, bool]:
    capability = requirement["capability"]
    subtype = requirement["requirement_subtype"]
    aliases = _skill_aliases(profile)
    relevant = aliases.get(capability.casefold())
    candidate_skills = [relevant] if relevant else [
        skill for skill in profile.get("skills", [])
        if "security" in str(skill.get("category", "")).casefold()
    ]
    usable: set[str] = set()
    direct: set[str] = set()
    skill_ids: set[str] = set()
    for skill in candidate_skills:
        if not skill:
            continue
        skill_ids.add(skill["record_id"])
        for record_id in _usable_evidence_ids(skill, evidence_by_id):
            usable.add(record_id)
            if evidence_by_id[record_id].get("employment_ids"):
                direct.add(record_id)
    if direct:
        return [{"capability": capability, "requirement_subtype": subtype, "match": "SUPPORTED_MATCH", "record_ids": sorted(skill_ids | direct), "experience_equivalence": True}], None, False
    evidence_items: list[dict[str, Any]] = []
    if usable:
        evidence_items.append({"capability": capability, "requirement_subtype": subtype, "match": "TRANSFERABLE_MATCH", "record_ids": sorted(skill_ids | usable), "experience_equivalence": False})
    mandatory = _is_mandatory(requirement)
    match = "HARD_GAP" if mandatory else "PREFERRED_AND_MISSING"
    reason = "Project, coursework, or adjacent evidence does not establish required professional-experience equivalence."
    return evidence_items, {"capability": capability, "requirement_subtype": subtype, "match": match, "reason": reason}, mandatory


def evaluate_requirement(profile: dict[str, Any], requirement: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Evaluate one normalized requirement without treating unknown as unfavorable."""
    requirement = _normalize_requirement(requirement)
    capability = requirement["capability"]
    subtype = requirement["requirement_subtype"]
    mandatory = _is_mandatory(requirement)
    preferred = requirement["requirement_class"] == "PREFERRED"
    evidence_by_id = {record["record_id"]: record for record in profile.get("evidence", [])}

    if subtype in DECISION_SUBTYPES:
        match, reason, record_ids = _decision_requirement(profile, requirement)
        if preferred and match == "HARD_GAP":
            match = "PREFERRED_AND_MISSING"
        item = {"capability": capability, "requirement_subtype": subtype, "match": match, "reason": reason}
        if record_ids:
            item["record_ids"] = record_ids
        if match == "SUPPORTED_MATCH":
            return [{"capability": capability, "requirement_subtype": subtype, "match": match, "record_ids": record_ids, "experience_equivalence": False}], [], False
        return [], [item], match == "HARD_GAP" and mandatory

    if subtype == "WORK_AUTHORIZATION":
        value = str(profile.get("candidate", {}).get("work_authorization") or "")
        if not value:
            return [], [{"capability": capability, "requirement_subtype": subtype, "match": "UNKNOWN_EVIDENCE", "reason": "Work-authorization evidence is unresolved."}], False
        if "authorized" in value.casefold() and "not authorized" not in value.casefold():
            return [{"capability": capability, "requirement_subtype": subtype, "match": "SUPPORTED_MATCH", "record_ids": [profile["candidate"]["record_id"]], "experience_equivalence": False}], [], False
        match = "HARD_GAP" if mandatory else "PREFERRED_AND_MISSING"
        return [], [{"capability": capability, "requirement_subtype": subtype, "match": match, "reason": "Known work-authorization fact does not satisfy the requirement."}], match == "HARD_GAP"

    if subtype == "EDUCATION":
        match, reason, record_ids = _education_requirement(profile, requirement)
        if preferred and match == "HARD_GAP":
            match = "PREFERRED_AND_MISSING"
        if match == "SUPPORTED_MATCH":
            return [{"capability": capability, "requirement_subtype": subtype, "match": match, "record_ids": record_ids, "experience_equivalence": False}], [], False
        evidence_items = []
        if record_ids:
            evidence_items.append({"capability": capability, "requirement_subtype": subtype, "match": "PARTIALLY_SUPPORTED", "record_ids": record_ids, "experience_equivalence": False})
        return evidence_items, [{"capability": capability, "requirement_subtype": subtype, "match": match, "reason": reason}], match == "HARD_GAP" and mandatory

    if subtype == "EXPERIENCE":
        evidence_items, gap, hard = _experience_requirement(profile, requirement, evidence_by_id)
        return evidence_items, [gap] if gap else [], hard

    aggregate = _aggregate_sub_capabilities(profile, requirement)
    if aggregate and aggregate["supported"]:
        match = "SUPPORTED_MATCH" if not aggregate["missing"] else "PARTIALLY_SUPPORTED"
        evidence_item = {
            "capability": capability, "requirement_subtype": subtype, "match": match,
            "record_ids": aggregate["record_ids"], "experience_equivalence": False,
            "supported_sub_capabilities": aggregate["supported"],
            "missing_sub_capabilities": aggregate["missing"],
        }
        if match == "SUPPORTED_MATCH":
            return [evidence_item], [], False
        gap = {
            "capability": capability, "requirement_subtype": subtype, "match": "PARTIALLY_SUPPORTED",
            "reason": "Some, but not all, requirement sub-capabilities have linked canonical evidence.",
            "supported_sub_capabilities": aggregate["supported"],
            "missing_sub_capabilities": aggregate["missing"],
        }
        return [evidence_item], [gap], False

    aliases = _skill_aliases(profile)
    skill = aliases.get(capability.casefold())
    if skill:
        usable = _usable_evidence_ids(skill, evidence_by_id)
        if usable:
            direct_evidence = [record_id for record_id in usable if evidence_by_id[record_id].get("employment_ids")]
            match = "SUPPORTED_MATCH"
            if requirement.get("direct_experience") and not direct_evidence:
                match = "TRANSFERABLE_MATCH"
            evidence_item = {"capability": capability, "requirement_subtype": subtype, "match": match, "record_ids": [skill["record_id"], *usable], "experience_equivalence": False}
            if requirement.get("direct_experience") and match == "TRANSFERABLE_MATCH":
                gap_match = "HARD_GAP" if mandatory else "BRIDGEABLE_GAP"
                gap = {"capability": capability, "requirement_subtype": subtype, "match": gap_match, "reason": "Adjacent project evidence is not direct employment equivalence."}
                return [evidence_item], [gap], gap_match == "HARD_GAP"
            return [evidence_item], [], False

    if preferred:
        return [], [{"capability": capability, "requirement_subtype": subtype, "match": "PREFERRED_AND_MISSING", "reason": "No linked canonical evidence; preferred requirements are non-disqualifying."}], False
    return [], [{"capability": capability, "requirement_subtype": subtype, "match": "UNKNOWN_EVIDENCE", "reason": "No linked canonical evidence; absence of evidence is not treated as a known unfavorable fact."}], False


def ingest(workspace: Path, input_path: Path, *, timestamp: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    raw = read_json(input_path)
    source_type = raw.get("source_type")
    if source_type not in {"SYNTHETIC", "USER_SUPPLIED"}:
        raise ValueError("opportunity source_type must be SYNTHETIC or USER_SUPPLIED")
    created_at = utc_now(timestamp)
    opportunity_id = raw["opportunity_id"]
    opportunity = {
        "schema": "careeros.opportunity.v1", "schema_version": "1.0.0",
        "opportunity_id": opportunity_id, "employer_name": raw["employer_name"], "role_title": raw["role_title"],
        "location": raw.get("location"), "source_type": source_type, "status": "INTAKE",
        "requirements": [_normalize_requirement(item) for item in raw["requirements"]], "created_at": created_at,
        "source_url": raw.get("source_url") or raw.get("canonical_url"),
        "canonical_url": raw.get("canonical_url") or raw.get("source_url"),
        "provider_job_id": raw.get("provider_job_id"),
        "source_status": raw.get("source_status"),
        "last_verified_at": raw.get("last_verified_at"),
        "expiration_signal": raw.get("expiration_signal"),
        "closure_signal": raw.get("closure_signal"),
        "supersedes": raw.get("supersedes"),
        "repost_group_id": raw.get("repost_group_id"),
    }
    for field in ('application_url','application_url_source','application_questions','application_question_source','cover_letter_requirement'):
        if field in raw:opportunity[field]=raw[field]
    from careeros.application_documents import validate_application_details
    validate_application_details(opportunity)
    snapshot_text = raw["job_description"]
    snapshot = {
        "schema": "careeros.job-description-snapshot.v1", "schema_version": "1.0.0",
        "snapshot_id": f"jd:{uuid.uuid5(uuid.NAMESPACE_URL, opportunity_id + ':' + snapshot_text)}",
        "opportunity_id": opportunity_id, "source_type": source_type, "captured_at": created_at,
        "content_hash": sha256_value(snapshot_text), "text": snapshot_text, "supersedes": None,
        "retention_class": "SYNTHETIC_FIXTURE" if source_type == "SYNTHETIC" else "USER_WORKSPACE",
        "rights_class": "SYNTHETIC_ORIGINAL" if source_type == "SYNTHETIC" else "USER_SUPPLIED_READ_ONLY",
    }
    registry = SchemaRegistry(schema_dir())
    registry.validate("urn:careeros:schema:opportunity:v1", opportunity)
    registry.validate("urn:careeros:schema:job-description-snapshot:v1", snapshot)
    from careeros.job_intelligence import analyze_job_description
    from careeros.application_state import build_opportunity_freshness
    intelligence = analyze_job_description(opportunity, snapshot)
    verification = {
        "source_status": raw.get("source_status"),
        "last_verified_at": raw.get("last_verified_at"),
        "verification_method": raw.get("verification_method"),
        "verification_confidence": raw.get("verification_confidence"),
        "expiration_signal": raw.get("expiration_signal"),
        "closure_signal": raw.get("closure_signal"),
        "conflicting_sources": raw.get("conflicting_sources", False),
        "supersedes": raw.get("supersedes"),
        "repost_group_id": raw.get("repost_group_id"),
    }
    freshness = build_opportunity_freshness(
        opportunity, snapshot, verification=verification, timestamp=created_at,
    )
    registry.validate("urn:careeros:schema:job-description-intelligence:v1", intelligence)
    target = roots.state_root / "opportunities" / opportunity_id
    atomic_write_json(roots.assert_write_allowed(target / "opportunity.json", "state"), opportunity)
    atomic_write_json(roots.assert_write_allowed(target / "jd-snapshot.json", "state"), snapshot)
    atomic_write_json(roots.assert_write_allowed(target / "jd-intelligence.json", "state"), intelligence)
    atomic_write_json(roots.assert_write_allowed(target / "freshness.json", "state"), freshness)
    return opportunity, snapshot


def qualify(workspace: Path, opportunity_id: str, *, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    profile = read_json(roots.state_root / "profile/career-profile.json")
    profile_manifest = read_json(roots.state_root / "profile/profile-build-manifest.json")
    family = read_json(roots.state_root / "role-families/active.json")
    require_derivative_current(roots, "CAREER_PROFILE", profile["profile_id"])
    require_derivative_current(roots, "ROLE_FAMILY", family["role_family_id"])
    opportunity_path = roots.state_root / "opportunities" / opportunity_id / "opportunity.json"
    opportunity = read_json(opportunity_path)
    evidence: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    hard: list[str] = []
    opportunity["requirements"] = [_normalize_requirement(item) for item in opportunity["requirements"]]
    for requirement in opportunity["requirements"]:
        requirement_evidence, requirement_gaps, is_hard = evaluate_requirement(profile, requirement)
        evidence.extend(requirement_evidence)
        gaps.extend(requirement_gaps)
        if is_hard:
            hard.append(requirement["capability"])
    if not opportunity['requirements']:
        gaps.append({'capability': 'Job requirements need review', 'requirement_subtype': 'SKILL', 'match': 'UNKNOWN_DECISION', 'reason': 'An empty requirement list cannot establish qualification.'})
        decision_name = 'BORDERLINE'
    elif hard:
        decision_name = "NOT_QUALIFIED"
    elif any(item["match"] in {"BRIDGEABLE_GAP", "UNKNOWN_DECISION", "UNKNOWN_EVIDENCE", "PARTIALLY_SUPPORTED", "PREFERRED_AND_MISSING"} for item in gaps):
        decision_name = "BORDERLINE"
    else:
        decision_name = "QUALIFIED"
    created_at = utc_now(timestamp)
    qualification_id = f"qualification:{uuid.uuid5(uuid.NAMESPACE_URL, opportunity_id + ':' + profile_manifest['profile_hash'])}"
    decision = {
        "schema": "careeros.qualification-decision.v1", "schema_version": "1.0.0",
        "qualification_id": qualification_id, "opportunity_id": opportunity_id,
        "profile_hash": profile_manifest["profile_hash"], "role_family_id": family["role_family_id"],
        "jd_snapshot_hash": read_json(opportunity_path.parent/"jd-snapshot.json")["content_hash"],
        "policy_version": QUALIFICATION_POLICY_VERSION, "decision": decision_name,
        "evidence": evidence, "gaps": gaps, "hard_disqualifiers": sorted(set(hard)),
        "confidence": "HIGH" if decision_name != "BORDERLINE" else "MEDIUM", "human_override": None, "created_at": created_at,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:qualification-decision:v1", decision)
    from careeros.job_intelligence import build_job_evidence_matrix
    intelligence = read_json(roots.state_root / "opportunities" / opportunity_id / "jd-intelligence.json")
    matrix = build_job_evidence_matrix(profile, intelligence, decision)
    registry = SchemaRegistry(schema_dir())
    registry.validate("urn:careeros:schema:job-evidence-matrix:v1", matrix)
    opportunity["status"] = decision_name
    atomic_write_json(opportunity_path, opportunity)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "qualifications" / f"{opportunity_id}.json", "state"), decision)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "opportunities" / opportunity_id / "job-evidence-matrix.json", "state"), matrix)
    mark_derivative_current(roots, "QUALIFICATION", qualification_id, timestamp=created_at, lineage_hash=sha256_value(decision))
    return decision
