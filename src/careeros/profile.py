"""Compile canonical generic records into CareerProfileV1 and RoleFamilyV1."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config
from careeros.core.io import atomic_write_json, read_json, sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.versions import COMPILER_VERSION, PRIVACY_POLICY_VERSION, QUALIFICATION_POLICY_VERSION, TRUTH_POLICY_VERSION
from careeros.workspace import require_current_workspace, schema_dir, utc_now
from careeros.updates import mark_derivative_current


KINDS = ("employment", "education", "skills", "credentials", "evidence", "projects")


def build_profile(workspace: Path, *, timestamp: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    records = roots.assert_user_data_read_only(roots.user_data_root / "records")
    candidate = read_json(records / "candidate.json")
    preferences = read_json(records / "preferences.json")
    collections = {kind: read_json(records / f"{kind}.json") if (records / f"{kind}.json").exists() else [] for kind in KINDS}
    snapshot = {"candidate": candidate, "preferences": preferences, **collections}
    snapshot_hash = sha256_value(snapshot)
    created_at = utc_now(timestamp)
    profile = {
        "schema": "careeros.career-profile.v1",
        "schema_version": "1.0.0",
        "profile_id": candidate["record_id"].replace("candidate:", "profile:"),
        "generated_at": created_at,
        "source_snapshot_hash": snapshot_hash,
        "candidate": candidate,
        **collections,
        "preferences": preferences,
        "role_families": [],
        "artifacts": [],
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:career-profile:v1", profile)
    profile_hash = sha256_value(profile)
    manifest = {
        "schema": "careeros.profile-build-manifest.v1",
        "input_record_ids": sorted([candidate["record_id"], preferences["record_id"], *[r["record_id"] for kind in KINDS for r in collections[kind]]]),
        "input_hashes": {kind: sha256_value(value) for kind, value in snapshot.items()},
        "profile_schema_version": "1.0.0",
        "compiler_version": COMPILER_VERSION,
        "policy_versions": {"visibility": PRIVACY_POLICY_VERSION, "metrics": TRUTH_POLICY_VERSION},
        "created_at": created_at,
        "profile_hash": profile_hash,
    }
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "profile/career-profile.json", "state"), profile)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "profile/profile-build-manifest.json", "state"), manifest)
    mark_derivative_current(roots, "CAREER_PROFILE", profile["profile_id"], timestamp=created_at, lineage_hash=profile_hash)
    return profile, manifest


def build_role_family(workspace: Path, *, intent_index: int = 0, approve: bool = True, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    profile = read_json(roots.state_root / "profile/career-profile.json")
    intents = profile["preferences"].get("target_role_intents", [])
    if not intents:
        raise ValueError("at least one target role intent is required")
    intent = intents[intent_index]
    created_at = utc_now(timestamp)
    key = f"{profile['profile_id']}:{intent.get('display_name')}:{','.join(intent.get('target_titles', []))}"
    family_id = f"role-family:{uuid.uuid5(uuid.NAMESPACE_URL, key)}"
    evidence_names = {skill["name"].lower() for skill in profile["skills"] if skill["evidence_ids"]}
    core = intent.get("core_capabilities", [])
    gaps = [capability for capability in core if capability.lower() not in evidence_names]
    family = {
        "schema": "careeros.role-family.v1",
        "schema_version": "1.0.0",
        "record_id": family_id,
        "created_at": created_at,
        "updated_at": created_at,
        "provenance": [{
            "source_id": f"source:{family_id}",
            "source_type": "DERIVED",
            "source_reference": "CareerProfileV1.preferences.target_role_intents",
            "source_record_id": profile["preferences"]["record_id"],
            "field": "target_role_intents",
            "source_hash": profile["source_snapshot_hash"],
            "captured_at": created_at,
        }],
        "verification_state": "VERIFIED" if approve else "NEEDS_VERIFICATION",
        "confidence": "HIGH",
        "visibility": "INTERNAL",
        "status": "ACTIVE",
        "family_id": family_id,
        "role_family_id": family_id,
        "label": intent["display_name"],
        "display_name": intent["display_name"],
        "description": intent.get("description", "Candidate-approved target role family."),
        "headline": intent.get("headline"),
        "target_titles": intent["target_titles"],
        "seniority": intent.get("seniority", "ENTRY"),
        "core_capabilities": core,
        "preferred_capabilities": intent.get("preferred_capabilities", []),
        "transferable_capabilities": intent.get("transferable_capabilities", []),
        "hard_requirements": intent.get("hard_requirements", []),
        "common_gaps": gaps,
        "evidence_preferences": intent.get("evidence_preferences", ["VERIFIED", "PUBLIC"]),
        "resume_strategy": intent.get("resume_strategy", "Emphasize directly supported, role-relevant evidence."),
        "qualification_policy_ref": QUALIFICATION_POLICY_VERSION,
        "approval_state": "APPROVED" if approve else "PROPOSED",
        "skill_tags": sorted(set(core + intent.get("preferred_capabilities", []) + intent.get("transferable_capabilities", []))),
        "evidence_requirements": intent.get("evidence_requirements", core),
        "eligibility_rules": intent.get("eligibility_rules", []),
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:role-family:v1", family)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "role-families/active.json", "state"), family)
    profile['role_families']=[v for v in profile.get('role_families',[]) if v['role_family_id']!=family_id]+[family]
    atomic_write_json(roots.assert_write_allowed(roots.state_root/'role-families'/('family-'+family_id.split(':')[-1]+'.json'),'state'),family)
    profile["generated_at"] = created_at
    atomic_write_json(roots.state_root / "profile/career-profile.json", profile)
    manifest_path = roots.state_root / "profile/profile-build-manifest.json"
    manifest = read_json(manifest_path)
    manifest["profile_hash"] = sha256_value(profile)
    manifest["role_family_ids"] = [v["role_family_id"] for v in profile["role_families"]]
    atomic_write_json(manifest_path, manifest)
    mark_derivative_current(roots, "ROLE_FAMILY", family_id, timestamp=created_at, lineage_hash=sha256_value(family))
    return family


def activate_role_family(workspace: Path, role_family_id: str, *, timestamp=None) -> dict[str, Any]:
    """Choose an approved derivative without rewriting the career profile."""
    require_current_workspace(workspace)
    roots=load_config(workspace/'careeros.yaml').roots
    profile=read_json(roots.state_root/'profile/career-profile.json')
    family=next((v for v in profile.get('role_families',[]) if v['role_family_id']==role_family_id),None)
    if not family or family['approval_state']!='APPROVED':raise PermissionError('Choose a career direction that you have approved.')
    atomic_write_json(roots.assert_write_allowed(roots.state_root/'role-families/active.json','state'),family)
    mark_derivative_current(roots,'ROLE_FAMILY',role_family_id,timestamp=utc_now(timestamp),lineage_hash=sha256_value(family))
    return family
