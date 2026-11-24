"""Governed resume production-family inheritance and routing.

The module resolves candidate-neutral production policy from a global standard
through master, lane/role-family, and targeted families. It never edits
canonical career data and never permits a child to disable global safety.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from careeros.core.io import sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir, utc_now


FAMILY_POLICY_VERSION = "production-family-inheritance-v1"
FAMILY_TYPES = {"MASTER", "LANE", "ROLE_FAMILY", "TARGETED", "SPECIALIZED"}
FAMILY_STATES = {"DRAFT", "SHADOW", "VALIDATED", "PRODUCTION", "RETIRED"}
OVERRIDE_CLASSES = {
    "CONTENT_PRIORITY", "SECTION_ORDER", "SUMMARY", "SKILLS", "PROJECTS",
    "PROFESSIONAL_HISTORY", "DOCUMENT_DENSITY", "TARGET_JOB",
}
PROMOTION_PATH = {
    "DRAFT": "SHADOW", "SHADOW": "VALIDATED", "VALIDATED": "PRODUCTION",
    "PRODUCTION": "RETIRED",
}
STALE_VERSION_KEYS = {
    "global_policy_version", "document_standard_version", "canonical_schema_version",
    "summary_policy_version", "ats_policy_version", "renderer_version", "role_family_version",
}

POLICY_FIELDS = (
    "content_policy", "section_policy", "evidence_policy", "summary_policy",
    "skills_policy", "project_policy", "experience_policy", "document_policy",
    "ats_policy", "public_naming_policy", "fallback_policy",
)

GLOBAL_PRODUCTION_STANDARD: dict[str, dict[str, Any]] = {
    "content_policy": {
        "truth_required": True, "provenance_required": True,
        "public_sanitization_required": True, "career_continuity_required": True,
        "canonical_dump_allowed": False,
    },
    "section_policy": {
        "allowed_sections": ["SUMMARY", "CORE SKILLS", "PROFESSIONAL EXPERIENCE", "PROJECTS", "CERTIFICATIONS", "EDUCATION", "LANGUAGES"],
        "section_order": ["SUMMARY", "CORE SKILLS", "PROFESSIONAL EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS", "LANGUAGES"],
        "normal_document_flow": True,
    },
    "evidence_policy": {
        "material_evidence_loss_gate": True, "role_fact_preservation": True,
        "employer_need_trace_required_for_targeted": True,
        "unsupported_claims_allowed": False,
    },
    "summary_policy": {
        "mode": "BROAD_PROFESSIONAL", "evidence_trace_required": True,
        "job_adaptation_required_for_targeted": True,
    },
    "skills_policy": {
        "mode": "BROAD_VALIDATED", "evidence_supported_only": True,
        "jd_keywords_may_create_skills": False,
    },
    "project_policy": {
        "mode": "GENERAL_STRENGTH", "allowed_dispositions": ["FEATURED", "SUPPORTING", "COMPRESSED", "OMITTED_WITH_REASON"],
        "omission_reason_required": True,
    },
    "experience_policy": {
        "mode": "BROAD_CREDIBILITY", "professional_history_sufficiency": True,
        "career_continuity_required": True, "empty_roles_allowed": False,
    },
    "document_policy": {
        "template": "PREMIUM_ATS_SINGLE_COLUMN", "page_policy": "ONE_OR_TWO_BY_EVIDENCE",
        "minimum_body_size": 9.5, "featured_projects": True,
        "experience_compression": "BOUNDED", "project_compression": "BOUNDED",
        "required_header_fields": ["candidate_name", "public_location", "email", "positioning_headline"],
    },
    "ats_policy": {
        "ats_required": True, "round_trip_required": True, "autofill_required": True,
        "single_column_default": True, "hidden_text_allowed": False,
    },
    "public_naming_policy": {
        "recruiter_safe_required": True, "internal_labels_allowed": False,
    },
    "fallback_policy": {
        "explicit_only": True, "human_review_required": True,
        "safe_terminal": "ATS_STANDARD_SAFE_FALLBACK",
    },
}

PROTECTED_SETTINGS = {
    ("content_policy", "truth_required"),
    ("content_policy", "provenance_required"),
    ("content_policy", "public_sanitization_required"),
    ("evidence_policy", "material_evidence_loss_gate"),
    ("evidence_policy", "role_fact_preservation"),
    ("evidence_policy", "unsupported_claims_allowed"),
    ("experience_policy", "professional_history_sufficiency"),
    ("experience_policy", "career_continuity_required"),
    ("experience_policy", "empty_roles_allowed"),
    ("ats_policy", "ats_required"),
    ("ats_policy", "round_trip_required"),
    ("ats_policy", "autofill_required"),
    ("ats_policy", "hidden_text_allowed"),
    ("public_naming_policy", "recruiter_safe_required"),
    ("public_naming_policy", "internal_labels_allowed"),
}

PROTECTED_VALUES = {
    ("content_policy", "truth_required"): True,
    ("content_policy", "provenance_required"): True,
    ("content_policy", "public_sanitization_required"): True,
    ("evidence_policy", "material_evidence_loss_gate"): True,
    ("evidence_policy", "role_fact_preservation"): True,
    ("evidence_policy", "unsupported_claims_allowed"): False,
    ("experience_policy", "professional_history_sufficiency"): True,
    ("experience_policy", "career_continuity_required"): True,
    ("experience_policy", "empty_roles_allowed"): False,
    ("ats_policy", "ats_required"): True,
    ("ats_policy", "round_trip_required"): True,
    ("ats_policy", "autofill_required"): True,
    ("ats_policy", "hidden_text_allowed"): False,
    ("public_naming_policy", "recruiter_safe_required"): True,
    ("public_naming_policy", "internal_labels_allowed"): False,
}

COMMON_LANE_DEFAULTS = {
    "PROJECT_OPERATIONS": ("Project / Operations", "PROJECT_OPERATIONS"),
    "BUSINESS_ANALYSIS_PROCESS": ("Business Analysis / Process", "BUSINESS_ANALYSIS_PROCESS"),
    "IMPLEMENTATION_BUSINESS_SYSTEMS": ("Implementation / Business Systems", "IMPLEMENTATION_BUSINESS_SYSTEMS"),
    "TECH_SUPPORT_IT_OPERATIONS": ("Tech Support / IT Operations", "TECH_SUPPORT_IT_OPERATIONS"),
    "CRM_REVOPS": ("CRM / RevOps", "CRM_REVOPS"),
    "SECURITY_OPERATIONS": ("Security Operations", "SECURITY_OPERATIONS"),
    "NETWORK_OPERATIONS": ("Network Operations", "NETWORK_OPERATIONS"),
    "VULNERABILITY_OPERATIONS": ("Vulnerability Operations", "VULNERABILITY_OPERATIONS"),
    "CLOUD_INFRASTRUCTURE": ("Cloud / Infrastructure", "CLOUD_INFRASTRUCTURE"),
    "OTHER_GENERIC": ("Other Generic Family", "OTHER_GENERIC"),
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


def _override_index(family: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(item["policy"], item["setting"]): item for item in family.get("override_records", [])}


def _validate_safety(policy: str, setting: str, value: Any) -> None:
    expected = PROTECTED_VALUES.get((policy, setting), object())
    if (policy, setting) in PROTECTED_SETTINGS and value != expected:
        raise PermissionError(f"unsafe family override rejected: {policy}.{setting}")
    if policy == "document_policy" and setting == "required_header_fields":
        required = set(GLOBAL_PRODUCTION_STANDARD[policy][setting])
        if not required <= set(value or []):
            raise PermissionError("unsafe family override removes required public identity fields")


def make_production_family(
    *, family_id: str, family_type: str, display_name: str,
    parent_family_id: str | None, role_family_id: str | None = None,
    candidate_profile_id: str | None = None, status: str = "DRAFT", version: str = "1.0.0",
    policy_overrides: dict[str, dict[str, Any]] | None = None,
    override_records: list[dict[str, Any]] | None = None,
    validation_baseline: dict[str, str] | None = None,
    created_at: str | None = None, updated_at: str | None = None,
) -> dict[str, Any]:
    if family_type not in FAMILY_TYPES or status not in FAMILY_STATES:
        raise ValueError("invalid production family type or status")
    overrides = policy_overrides or {}
    records = override_records or []
    record_index = {(item.get("policy"), item.get("setting")): item for item in records}
    for policy, settings in overrides.items():
        if policy not in POLICY_FIELDS or not isinstance(settings, dict):
            raise ValueError(f"invalid family policy: {policy}")
        for setting, value in settings.items():
            _validate_safety(policy, setting, value)
            record = record_index.get((policy, setting))
            if not record or record.get("classification") not in OVERRIDE_CLASSES or not str(record.get("rationale") or "").strip():
                raise ValueError(f"anonymous family override rejected: {policy}.{setting}")
    now = utc_now(created_at)
    family = {
        "schema": "careeros.production-family.v1", "schema_version": "1.0.0",
        "family_id": family_id, "family_type": family_type, "display_name": display_name,
        "parent_family_id": parent_family_id, "role_family_id": role_family_id,
        "candidate_profile_id": candidate_profile_id, "status": status, "version": version,
        "created_at": now, "updated_at": utc_now(updated_at or created_at),
        "policy_version": FAMILY_POLICY_VERSION,
        **{field: copy.deepcopy(overrides.get(field, {})) for field in POLICY_FIELDS},
        "override_records": copy.deepcopy(records),
        "validation_baseline": copy.deepcopy(validation_baseline or {}),
    }
    family["family_hash"] = sha256_value(family)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:production-family:v1", family)
    return family


def _master_override_records() -> list[dict[str, Any]]:
    values = {
        ("summary_policy", "mode"): ("SUMMARY", "Broad recruiter positioning is owned by the master family."),
        ("skills_policy", "mode"): ("SKILLS", "The master presents the broad validated capability set."),
        ("project_policy", "mode"): ("PROJECTS", "The master selects broadly useful high-value projects."),
        ("experience_policy", "mode"): ("PROFESSIONAL_HISTORY", "The master preserves career continuity and professional credibility."),
    }
    return [{"override_id": f"override:master:{policy}:{setting}", "classification": classification, "policy": policy, "setting": setting, "rationale": rationale} for (policy, setting), (classification, rationale) in values.items()]


def build_default_family_registry(
    *, candidate_profile_id: str | None = None, timestamp: str | None = None,
    version_baseline: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create candidate-neutral master and common lane defaults."""
    baseline = version_baseline or {}
    master = make_production_family(
        family_id="family:master-recruiter", family_type="MASTER", display_name="Professional Resume",
        parent_family_id=None, candidate_profile_id=candidate_profile_id, status="VALIDATED",
        policy_overrides={
            "summary_policy": {"mode": "BROAD_PROFESSIONAL"},
            "skills_policy": {"mode": "BROAD_VALIDATED"},
            "project_policy": {"mode": "GENERAL_STRENGTH"},
            "experience_policy": {"mode": "BROAD_CREDIBILITY"},
        },
        override_records=_master_override_records(), validation_baseline=baseline,
        created_at=timestamp,
    )
    families = [master]
    for key, (label, role_family) in COMMON_LANE_DEFAULTS.items():
        records = [
            {"override_id": f"override:{key}:summary", "classification": "SUMMARY", "policy": "summary_policy", "setting": "mode", "rationale": "Lane positioning specializes the inherited master story."},
            {"override_id": f"override:{key}:skills", "classification": "SKILLS", "policy": "skills_policy", "setting": "mode", "rationale": "Lane evidence determines supported skill priority."},
            {"override_id": f"override:{key}:projects", "classification": "PROJECTS", "policy": "project_policy", "setting": "mode", "rationale": "Lane relevance controls project prominence."},
            {"override_id": f"override:{key}:experience", "classification": "PROFESSIONAL_HISTORY", "policy": "experience_policy", "setting": "mode", "rationale": "Transferable professional evidence is emphasized without erasure."},
        ]
        families.append(make_production_family(
            family_id=f"family:lane:{key.casefold()}", family_type="LANE", display_name=label,
            parent_family_id=master["family_id"], role_family_id=role_family,
            candidate_profile_id=candidate_profile_id, status="VALIDATED",
            policy_overrides={
                "summary_policy": {"mode": "LANE_POSITIONING"},
                "skills_policy": {"mode": "ROLE_FAMILY_PRIORITY"},
                "project_policy": {"mode": "LANE_RELEVANCE"},
                "experience_policy": {"mode": "TRANSFERABLE_CREDIBILITY"},
            }, override_records=records, validation_baseline=baseline, created_at=timestamp,
        ))
    return build_family_registry(families, global_versions=baseline, timestamp=timestamp)


def build_family_registry(
    families: list[dict[str, Any]], *, global_versions: dict[str, str], timestamp: str | None = None,
) -> dict[str, Any]:
    index = {family["family_id"]: family for family in families}
    if len(index) != len(families):
        raise ValueError("duplicate production family ID")
    for family in families:
        parent = family.get("parent_family_id")
        if parent and parent not in index:
            raise ValueError(f"orphan production family: {family['family_id']}")
        if parent and index[parent]["family_type"] == "TARGETED":
            raise ValueError("targeted families cannot be parents")
    entries = []
    for family in families:
        freshness = assess_family_freshness(family, current_versions=global_versions)
        eligible = family["status"] == "PRODUCTION" and freshness["status"] == "CURRENT"
        entries.append({
            "family_id": family["family_id"], "family_type": family["family_type"],
            "parent_family_id": family.get("parent_family_id"), "role_family_id": family.get("role_family_id"),
            "version": family["version"], "status": family["status"],
            "document_standard": family["validation_baseline"].get("document_standard_version"),
            "last_validated": family["updated_at"] if family["status"] in {"VALIDATED", "PRODUCTION"} else None,
            "test_status": "PASS" if family["status"] in {"VALIDATED", "PRODUCTION"} and freshness["status"] == "CURRENT" else "REVALIDATION_REQUIRED",
            "production_eligible": eligible, "family_hash": family["family_hash"],
        })
    registry = {
        "schema": "careeros.production-family-registry.v1", "schema_version": "1.0.0",
        "policy_version": FAMILY_POLICY_VERSION, "updated_at": utc_now(timestamp),
        "global_versions": copy.deepcopy(global_versions), "families": copy.deepcopy(families),
        "entries": entries,
    }
    registry["registry_hash"] = sha256_value(registry)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:production-family-registry:v1", registry)
    return registry


def _family_chain(family_id: str, registry: dict[str, Any]) -> list[dict[str, Any]]:
    index = {item["family_id"]: item for item in registry["families"]}
    if family_id not in index:
        raise KeyError(f"production family not found: {family_id}")
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = index[family_id]
    while current:
        if current["family_id"] in seen:
            raise ValueError("production family inheritance cycle")
        seen.add(current["family_id"])
        chain.append(current)
        parent = current.get("parent_family_id")
        current = index.get(parent) if parent else None
    chain.reverse()
    if chain[0]["family_type"] != "MASTER":
        raise ValueError("production family chain must terminate at MASTER")
    return chain


def resolve_family(
    family_id: str, registry: dict[str, Any], *, job_adaptations: list[dict[str, Any]] | None = None,
    fallbacks_invoked: list[str] | None = None, timestamp: str | None = None,
) -> dict[str, Any]:
    chain = _family_chain(family_id, registry)
    target = chain[-1]
    effective = copy.deepcopy(GLOBAL_PRODUCTION_STANDARD)
    sources = {f"{policy}.{setting}": {"origin": "GLOBAL_DEFAULT", "source": "GLOBAL_PRODUCTION_STANDARD"} for policy, settings in effective.items() for setting in settings}
    inherited: list[dict[str, Any]] = []
    local: list[dict[str, Any]] = []
    for family in chain:
        overrides = _override_index(family)
        for policy in POLICY_FIELDS:
            for setting, value in family.get(policy, {}).items():
                _validate_safety(policy, setting, value)
                record = overrides.get((policy, setting))
                if not record:
                    raise ValueError(f"untraced local override: {family['family_id']}:{policy}.{setting}")
                effective[policy][setting] = copy.deepcopy(value)
                source = {"origin": "LOCAL_OVERRIDE", "source": family["family_id"], "override_id": record["override_id"]}
                sources[f"{policy}.{setting}"] = source
                local.append({**source, "policy": policy, "setting": setting, "rationale": record["rationale"]})
    for key, source in list(sources.items()):
        if source["origin"] == "LOCAL_OVERRIDE" and source["source"] != target["family_id"]:
            sources[key] = {**source, "origin": "PARENT_INHERITED"}
            inherited.append({"setting": key, "source_family_id": source["source"]})
    adaptations = []
    for adaptation in job_adaptations or []:
        if target["family_type"] != "TARGETED":
            raise ValueError("job adaptation requires a TARGETED family")
        policy, setting = adaptation.get("policy"), adaptation.get("setting")
        if policy not in {"content_policy", "section_policy", "summary_policy", "skills_policy", "project_policy", "experience_policy"}:
            raise PermissionError(f"job adaptation cannot alter {policy}")
        if not str(adaptation.get("rationale") or "").strip() or not adaptation.get("source_refs"):
            raise ValueError("job adaptation requires rationale and source_refs")
        _validate_safety(policy, setting, adaptation.get("value"))
        effective[policy][setting] = copy.deepcopy(adaptation.get("value"))
        sources[f"{policy}.{setting}"] = {"origin": "JOB_ADAPTATION", "source": adaptation["source_refs"]}
        adaptations.append(copy.deepcopy(adaptation))
    freshness = assess_family_freshness(target, current_versions=registry["global_versions"], parent_stale=any(assess_family_freshness(item, current_versions=registry["global_versions"])["status"] != "CURRENT" for item in chain[:-1]))
    trace = {
        "schema": "careeros.family-resolution-trace.v1", "schema_version": "1.0.0",
        "trace_id": f"family-resolution:{uuid.uuid5(uuid.NAMESPACE_URL, family_id + ':' + target['version'] + ':' + sha256_value(adaptations))}",
        "family_id": family_id, "family_version": target["version"],
        "parent_family_id": target.get("parent_family_id"),
        "resolution_path": ["GLOBAL_PRODUCTION_STANDARD", *[item["family_id"] for item in chain]],
        "inherited_policies": inherited,
        "local_overrides": [item for item in local if item["source"] == target["family_id"]],
        "job_specific_adaptations": adaptations,
        "fallbacks_invoked": list(fallbacks_invoked or []),
        "setting_sources": sources, "effective_configuration": effective,
        "freshness": freshness, "created_at": utc_now(timestamp),
        "internal_only": True,
    }
    trace["trace_hash"] = sha256_value(trace)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:family-resolution-trace:v1", trace)
    return trace


def assess_family_freshness(
    family: dict[str, Any], *, current_versions: dict[str, str], parent_stale: bool = False,
) -> dict[str, Any]:
    baseline = family.get("validation_baseline", {})
    reasons = [key for key in STALE_VERSION_KEYS if baseline.get(key) != current_versions.get(key)]
    if parent_stale:
        reasons.append("parent_family")
    return {
        "family_id": family["family_id"], "family_version": family["version"],
        "status": "STALE" if reasons else "CURRENT", "stale_reasons": sorted(reasons),
        "production_use_allowed": not reasons and family["status"] == "PRODUCTION",
    }


def build_fallback_route(
    *, source_family_id: str, failure_reason: str, registry: dict[str, Any],
    artifact_impact: str, qa_status: str, timestamp: str | None = None,
) -> dict[str, Any]:
    allowed = {
        "FAMILY_CONFIG_MISSING", "FAMILY_RENDER_FAILURE", "DOCUMENT_STANDARD_INCOMPATIBILITY",
        "ATS_FAILURE", "PAGE_FIT_FAILURE", "UNSUPPORTED_SPECIALIZED_TEMPLATE", "MISSING_JOB_ADAPTATION",
    }
    if failure_reason not in allowed:
        raise ValueError("unsupported fallback reason")
    index = {item["family_id"]: item for item in registry["families"]}
    source = index.get(source_family_id)
    route_path = [source_family_id]
    if failure_reason == "ATS_FAILURE" or source is None:
        fallback_id = "ATS_STANDARD_SAFE_FALLBACK"
    elif source.get("parent_family_id"):
        fallback_id = source["parent_family_id"]
    else:
        fallback_id = "ATS_STANDARD_SAFE_FALLBACK"
    route_path.append(fallback_id)
    fallback_config = copy.deepcopy(GLOBAL_PRODUCTION_STANDARD)
    if fallback_id in index:
        fallback_config = resolve_family(fallback_id, registry)["effective_configuration"]
    for (policy, setting), expected in PROTECTED_VALUES.items():
        if fallback_config[policy][setting] != expected:
            raise PermissionError("fallback would weaken production safety")
    record = {
        "schema": "careeros.fallback-routing.v1", "schema_version": "1.0.0",
        "fallback_id": f"fallback:{uuid.uuid5(uuid.NAMESPACE_URL, source_family_id + ':' + failure_reason + ':' + fallback_id)}",
        "source_family_id": source_family_id, "failure_reason": failure_reason,
        "fallback_family_id": fallback_id, "route_path": route_path,
        "artifact_impact": artifact_impact, "qa_status": qa_status,
        "human_review_required": True, "authorized": False,
        "safety_preserved": True, "created_at": utc_now(timestamp),
    }
    record["fallback_hash"] = sha256_value(record)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:fallback-routing:v1", record)
    return record


def authorize_fallback(record: dict[str, Any], *, human_approved: bool, actor: str, approved_at: str) -> dict[str, Any]:
    if not human_approved or not actor.strip() or record["qa_status"] != "PASS" or not record["safety_preserved"]:
        raise PermissionError("fallback requires human approval, passing QA, and preserved safety")
    result = copy.deepcopy(record)
    result.update({"authorized": True, "approved_by": actor, "approved_at": utc_now(approved_at)})
    result.pop("fallback_hash", None)
    result["fallback_hash"] = sha256_value(result)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:fallback-routing:v1", result)
    return result


def promote_family(
    family: dict[str, Any], *, target_status: str, gate_results: dict[str, bool],
    unresolved_regressions: Iterable[str] = (), actor: str, timestamp: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if PROMOTION_PATH.get(family["status"]) != target_status:
        raise ValueError("invalid production family promotion transition")
    required = {"SYNTHETIC_TESTS", "ATS", "VISUAL_QA", "TRUTH_PROVENANCE", "PRIVATE_ACCEPTANCE"}
    missing = sorted(item for item in required if not gate_results.get(item))
    regressions = sorted(set(unresolved_regressions))
    if target_status in {"VALIDATED", "PRODUCTION"} and (missing or regressions):
        raise PermissionError("family promotion blocked by failed gates or unresolved regression")
    promoted = copy.deepcopy(family)
    promoted["status"] = target_status
    promoted["updated_at"] = utc_now(timestamp)
    promoted.pop("family_hash", None)
    promoted["family_hash"] = sha256_value(promoted)
    promotion = {
        "schema": "careeros.production-family-promotion.v1", "schema_version": "1.0.0",
        "promotion_id": f"family-promotion:{uuid.uuid5(uuid.NAMESPACE_URL, family['family_id'] + ':' + family['version'] + ':' + target_status)}",
        "family_id": family["family_id"], "family_version": family["version"],
        "from_status": family["status"], "to_status": target_status,
        "gate_results": copy.deepcopy(gate_results), "unresolved_regressions": regressions,
        "actor": actor, "promoted_at": utc_now(timestamp), "human_confirmed": True,
    }
    promotion["promotion_hash"] = sha256_value(promotion)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:production-family-promotion:v1", promotion)
    return promoted, promotion


def revise_family(
    family: dict[str, Any], *, new_version: str, policy_overrides: dict[str, dict[str, Any]],
    override_records: list[dict[str, Any]], timestamp: str | None = None,
) -> dict[str, Any]:
    if new_version == family["version"]:
        raise ValueError("a used family version is immutable; revision requires a new version")
    combined = {field: copy.deepcopy(family.get(field, {})) for field in POLICY_FIELDS}
    for policy, settings in policy_overrides.items():
        combined.setdefault(policy, {}).update(copy.deepcopy(settings))
    existing_records = [item for item in family.get("override_records", []) if (item["policy"], item["setting"]) not in {(record["policy"], record["setting"]) for record in override_records}]
    return make_production_family(
        family_id=family["family_id"], family_type=family["family_type"], display_name=family["display_name"],
        parent_family_id=family.get("parent_family_id"), role_family_id=family.get("role_family_id"),
        candidate_profile_id=family.get("candidate_profile_id"), status="DRAFT", version=new_version,
        policy_overrides=combined, override_records=[*existing_records, *override_records],
        validation_baseline=family.get("validation_baseline", {}), created_at=timestamp,
    )


def freeze_family_lineage(trace: dict[str, Any], *, artifact_id: str, artifact_sha256: str) -> dict[str, Any]:
    """Capture immutable family lineage for a resume/submission manifest."""
    return {
        "artifact_id": artifact_id, "artifact_sha256": artifact_sha256,
        "family_id": trace["family_id"], "family_version": trace["family_version"],
        "family_trace_hash": trace["trace_hash"], "resolution_path": copy.deepcopy(trace["resolution_path"]),
    }


def evaluate_family_delta(
    *, parent_trace: dict[str, Any], child_trace: dict[str, Any],
    parent_content: dict[str, Any], child_content: dict[str, Any],
    relation: str, material_loss: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if relation not in {"MASTER_TO_LANE", "LANE_TO_TARGETED"}:
        raise ValueError("invalid family delta relation")
    parent_evidence = set(parent_content.get("evidence_ids", []))
    child_evidence = set(child_content.get("evidence_ids", []))
    policy_diffs = sorted(
        key for key in set(parent_trace["setting_sources"]) | set(child_trace["setting_sources"])
        if parent_trace["effective_configuration"].get(key.split(".", 1)[0], {}).get(key.split(".", 1)[1])
        != child_trace["effective_configuration"].get(key.split(".", 1)[0], {}).get(key.split(".", 1)[1])
    )
    content_diffs = {
        "summary": parent_content.get("summary") != child_content.get("summary"),
        "skills": parent_content.get("skills") != child_content.get("skills"),
        "projects": parent_content.get("projects") != child_content.get("projects"),
        "experience": parent_content.get("experience") != child_content.get("experience"),
        "evidence_added": sorted(child_evidence - parent_evidence),
        "evidence_removed": sorted(parent_evidence - child_evidence),
    }
    findings = []
    # A configured intent is not a rendered delta. Acceptance is based on the
    # actual public content so an unused override cannot satisfy tailoring.
    meaningful = bool(any(value for key, value in content_diffs.items() if key not in {"evidence_added", "evidence_removed"}) or content_diffs["evidence_added"] or content_diffs["evidence_removed"])
    if not meaningful:
        findings.append("NO_MEANINGFUL_DELTA")
    if relation == "LANE_TO_TARGETED" and parent_evidence == child_evidence and content_diffs["summary"] and not (content_diffs["skills"] or content_diffs["projects"] or content_diffs["experience"] or policy_diffs):
        findings.append("COPY_ONLY_VARIATION")
    losses = (material_loss or {}).get("losses", [])
    if any(item.get("classification") in {"MATERIAL_LOSS", "CRITICAL_LOSS"} for item in losses):
        findings.append("MATERIAL_EVIDENCE_LOSS")
    parent_critical = set(parent_content.get("critical_role_fact_ids", []))
    child_facts = set(child_content.get("role_fact_ids", []))
    if parent_critical - child_facts:
        findings.append("ROLE_IDENTITY_DRIFT")
    if child_trace["freshness"]["status"] != "CURRENT":
        findings.append("STALE_INHERITANCE")
    if parent_evidence and len(parent_evidence - child_evidence) / len(parent_evidence) > 0.6:
        findings.append("EXCESSIVE_DELTA")
    record = {
        "schema": "careeros.production-family-delta.v1", "schema_version": "1.0.0",
        "delta_id": f"family-delta:{uuid.uuid5(uuid.NAMESPACE_URL, parent_trace['trace_hash'] + ':' + child_trace['trace_hash'])}",
        "relation": relation, "parent_family_id": parent_trace["family_id"],
        "child_family_id": child_trace["family_id"], "policy_differences": policy_diffs,
        "content_differences": content_diffs, "findings": sorted(set(findings)),
        "status": "PASS" if not findings else "FAIL",
    }
    record["delta_hash"] = sha256_value(record)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:production-family-delta:v1", record)
    return record


def evaluate_family_qa(
    *, trace: dict[str, Any], delta: dict[str, Any] | None = None,
    fallback: dict[str, Any] | None = None, promotion: dict[str, Any] | None = None,
    frozen_lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective = trace["effective_configuration"]
    safe = all(effective[policy][setting] == expected for (policy, setting), expected in PROTECTED_VALUES.items())
    gates = {
        "FAMILY_INHERITANCE": trace["resolution_path"][0] == "GLOBAL_PRODUCTION_STANDARD",
        "FAMILY_RESOLUTION": bool(trace["trace_hash"] and trace["internal_only"]),
        "SAFE_OVERRIDE": safe,
        "FAMILY_DELTA": delta is None or delta["status"] == "PASS",
        "FAMILY_FRESHNESS": trace["freshness"]["status"] == "CURRENT",
        "FALLBACK_ROUTING": fallback is None or (fallback["safety_preserved"] and fallback["qa_status"] == "PASS"),
        "FAMILY_PROMOTION": promotion is None or not promotion["unresolved_regressions"],
        "HISTORICAL_VERSION_INTEGRITY": frozen_lineage is None or (frozen_lineage["family_id"] == trace["family_id"] and frozen_lineage["family_version"] == trace["family_version"]),
        "MATERIAL_EVIDENCE_PRESERVATION": delta is None or "MATERIAL_EVIDENCE_LOSS" not in delta["findings"],
    }
    return {"gates": gates, "status": "PASS" if all(gates.values()) else "FAIL"}
