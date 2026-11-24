"""Propose, clarify, review, and explicitly commit generic career records."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config
from careeros.core.io import append_jsonl, atomic_write_json, read_json, sha256_value
from careeros.evidence_expansion import evidence_block_from_record
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import canonical_state_hash, require_current_workspace, schema_dir, update_canonical_head, utc_now


TYPE_SPECS = {
    "candidate": ("careeros.candidate-profile.v1", "urn:careeros:schema:candidate-profile:v1"),
    "employment": ("careeros.employment-record.v1", "urn:careeros:schema:employment-record:v1"),
    "education": ("careeros.education-record.v1", "urn:careeros:schema:education-record:v1"),
    "skills": ("careeros.skill-record.v1", "urn:careeros:schema:skill-record:v1"),
    "credentials": ("careeros.credential-record.v1", "urn:careeros:schema:credential-record:v1"),
    "evidence": ("careeros.evidence-record.v1", "urn:careeros:schema:evidence-record:v1"),
    "projects": ("careeros.project-evidence-record.v1", "urn:careeros:schema:project-evidence-record:v1"),
    "preferences": ("careeros.career-preference.v1", "urn:careeros:schema:career-preference:v1"),
}


def _workspace(workspace: Path):
    return load_config(workspace / "careeros.yaml")


def _proposal_schema_urn(proposal: dict[str, Any]) -> str:
    record = proposal["record"]
    if proposal["kind"] == "evidence" and record.get("schema") == "careeros.evidence-block.v1":
        return "urn:careeros:schema:evidence-block:v1"
    return TYPE_SPECS[proposal["kind"]][1]


def _record_id(workspace_id: str, kind: str, local_id: str) -> str:
    return f"{kind.rstrip('s')}:{uuid.uuid5(uuid.NAMESPACE_URL, f'careeros:{workspace_id}:{kind}:{local_id}') }"


def start(workspace: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = _workspace(workspace).roots
    target = roots.assert_write_allowed(roots.state_root / "onboarding/session.json", "state")
    session = {
        "schema": "careeros.onboarding-session.v1",
        "state": "STARTED",
        "questionnaire": "generic-onboarding-v1",
        "questionnaire_version": "1.0.0",
        "started_at": utc_now(timestamp),
    }
    atomic_write_json(target, session)
    return session


def _metadata(schema_name: str, record_id: str, source_ref: str, created_at: str, raw: dict[str, Any]) -> dict[str, Any]:
    provenance = raw.get("source_provenance") or [{
        "source_id": f"source:{record_id}",
        "source_type": "SELF_REPORT",
        "source_reference": source_ref,
        "source_record_id": raw.get("local_id"),
        "field": None,
        "source_hash": sha256_value(raw),
        "captured_at": created_at,
    }]
    return {
        "schema": schema_name,
        "schema_version": "1.0.0",
        "record_id": record_id,
        "created_at": created_at,
        "updated_at": created_at,
        "provenance": provenance,
        "verification_state": raw.get("verification_state", "UNVERIFIED"),
        "confidence": raw.get("confidence", "MEDIUM"),
        "visibility": raw.get("visibility", "INTERNAL"),
        "status": "ACTIVE",
    }


def _records(raw: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = [("candidate", raw["candidate"]), ("preferences", raw["preferences"])]
    for kind in ("employment", "education", "skills", "credentials", "evidence", "projects"):
        result.extend((kind, item) for item in raw.get(kind, []))
    return result


def _replace_refs(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_replace_refs(item, ids) for item in value]
    if isinstance(value, dict):
        return {key: _replace_refs(child, ids) for key, child in value.items()}
    if isinstance(value, str) and value.startswith("ref:"):
        return ids[value[4:]]
    return value


def _propose(raw: dict[str, Any], workspace_id: str, source_ref: str, timestamp: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    ids = {item["local_id"]: _record_id(workspace_id, kind, item["local_id"]) for kind, item in _records(raw)}
    proposed: list[dict[str, Any]] = []
    control = {"local_id", "confidence", "visibility", "verification_state", "source_provenance", "source_reference"}
    for kind, item in _records(raw):
        schema_name, _ = TYPE_SPECS[kind]
        body = {key: value for key, value in item.items() if key not in control}
        if kind == "preferences":
            body["target_role_intents"] = raw.get("role_intents", [])
        body = _replace_refs(body, ids)
        record = {**_metadata(schema_name, ids[item["local_id"]], source_ref, timestamp, item), **body}
        if kind == "evidence" and any(key in record for key in ("tools_methods", "stakeholders", "source_original_wording")):
            record = evidence_block_from_record(record, timestamp=timestamp)
        proposed.append({
            "kind": kind,
            "local_id": item["local_id"],
            "proposal_state": "PROPOSED",
            "record": record,
            "validation_errors": [],
        })
    return proposed, ids


def _parse_year(record: dict[str, Any], end: bool = False) -> int | None:
    value = record.get("end_year" if end else "start_year")
    if value in (None, "PRESENT"):
        return 9999 if end and value == "PRESENT" else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clarifications(proposed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    by_id = {item["record"]["record_id"]: item for item in proposed}

    def add(item: dict[str, Any], field: str, issue_type: str, current: Any, severity: str = "ERROR") -> None:
        key = f"{item['record']['record_id']}:{field}:{issue_type}"
        issues.append({
            "clarification_id": f"clarification:{uuid.uuid5(uuid.NAMESPACE_URL, key)}",
            "record_id": item["record"]["record_id"],
            "local_id": item["local_id"],
            "field": field,
            "issue_type": issue_type,
            "current_value": current,
            "candidate_value": None,
            "source_refs": [item["record"]["provenance"][0]["source_reference"]],
            "severity": severity,
            "required_for_commit": True,
            "resolution": None,
            "resolved_at": None,
        })

    employment = [item for item in proposed if item["kind"] == "employment"]
    for item in employment:
        record = item["record"]
        if record.get("start_year") is None or (record.get("end_year") is None and record.get("employment_type") != "CURRENT"):
            add(item, "start_year/end_year", "MISSING_EMPLOYMENT_DATE", {"start_year": record.get("start_year"), "end_year": record.get("end_year")})
        if record.get("public_title") and record.get("public_title") != record.get("actual_title"):
            add(item, "public_title", "ACTUAL_VS_PUBLIC_TITLE", record.get("public_title"), "WARNING")
    ordered = sorted(employment, key=lambda item: _parse_year(item["record"]) or -1)
    for left, right in zip(ordered, ordered[1:]):
        left_end = _parse_year(left["record"], end=True)
        right_start = _parse_year(right["record"])
        if left_end and right_start and right_start < left_end:
            add(right, "start_year/end_year", "OVERLAPPING_EMPLOYMENT", {"overlaps": left["record"]["record_id"]}, "WARNING")
    for item in proposed:
        record = item["record"]
        if item["kind"] == "credentials" and record.get("credential_state") in (None, "UNKNOWN", "INCOMPLETE"):
            add(item, "credential_state", "INCOMPLETE_CREDENTIAL_STATUS", record.get("credential_state"))
        if item["kind"] == "evidence":
            text = " ".join([record.get("summary", ""), *record.get("outcomes", [])])
            has_metric = any(char.isdigit() for char in text)
            if has_metric and not record.get("metric_boundaries"):
                add(item, "summary/outcomes", "UNSUPPORTED_METRIC", text)
        if item["kind"] == "projects" and record.get("contribution") in (None, "", "AMBIGUOUS"):
            add(item, "contribution", "AMBIGUOUS_PROJECT_CONTRIBUTION", record.get("contribution"))
        if item["kind"] == "skills" and not record.get("evidence_ids"):
            add(item, "evidence_ids", "MISSING_SKILL_EVIDENCE", [])
        if item["kind"] == "skills" and record.get("visibility") == "PUBLIC":
            private_links = [rid for rid in record.get("evidence_ids", []) if by_id.get(rid, {}).get("record", {}).get("visibility") == "PRIVATE"]
            if private_links:
                add(item, "visibility", "CONFLICTING_VISIBILITY", {"skill": "PUBLIC", "private_evidence": private_links})
        if item["kind"] == "education" and record.get("completion_status") in (None, "UNKNOWN", "INCOMPLETE_UNSPECIFIED"):
            add(item, "completion_status", "INCOMPLETE_EDUCATION_STATE", record.get("completion_status"))
        if item["kind"] == "preferences":
            for gap in record.get("career_gaps", []):
                if gap.get("display") is None:
                    add(item, "career_gaps", "CAREER_GAP_DISPLAY_CHOICE", gap, "WARNING")
    return issues


def ingest(workspace: Path, input_path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    validated = _workspace(workspace)
    roots = validated.roots
    raw = read_json(input_path)
    if raw.get("schema") != "careeros.onboarding-input.v1" or raw.get("privacy_consent") is not True or raw.get("review_confirmed") is not True:
        raise ValueError("onboarding input, privacy consent, and review confirmation are required")
    manifest = read_json(workspace / "workspace-manifest.json")
    created_at = utc_now(timestamp)
    source_target = roots.assert_write_allowed(workspace / "sources/onboarding-input.json", "state") if False else workspace / "sources/onboarding-input.json"
    # Sources are immutable workspace intake, not package source or canonical user data.
    if source_target.exists():
        raise FileExistsError("onboarding source already exists")
    atomic_write_json(source_target, raw)
    proposed, ids = _propose(raw, manifest["workspace_id"], "sources/onboarding-input.json", created_at)
    registry = SchemaRegistry(schema_dir())
    for item in proposed:
        try:
            registry.validate(_proposal_schema_urn(item), item["record"])
        except Exception as exc:
            item["validation_errors"] = [str(exc)]
    clarifications = _clarifications(proposed)
    blocked = {item["record_id"] for item in clarifications if item["required_for_commit"]}
    for item in proposed:
        item["proposal_state"] = "NEEDS_CLARIFICATION" if item["record"]["record_id"] in blocked or item["validation_errors"] else "REVIEW_READY"
    bundle = {
        "schema": "careeros.proposed-record-bundle.v1",
        "state": "NEEDS_CLARIFICATION" if clarifications else "REVIEW_READY",
        "created_at": created_at,
        "source_hash": sha256_value(raw),
        "local_id_map": ids,
        "records": proposed,
    }
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "onboarding/proposed-records.json", "state"), bundle)
    queue = {"schema": "careeros.clarification-queue.v1", "state": "OPEN" if clarifications else "RESOLVED", "items": clarifications}
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "onboarding/clarifications.json", "state"), queue)
    session = read_json(roots.state_root / "onboarding/session.json")
    session.update({"state": bundle["state"], "input_hash": bundle["source_hash"], "proposed_count": len(proposed), "clarification_count": len(clarifications)})
    atomic_write_json(roots.state_root / "onboarding/session.json", session)
    return bundle


def list_clarifications(workspace: Path) -> dict[str, Any]:
    require_current_workspace(workspace)
    return read_json(_workspace(workspace).roots.state_root / "onboarding/clarifications.json")


def resolve(workspace: Path, resolutions_path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = _workspace(workspace).roots
    queue = read_json(roots.state_root / "onboarding/clarifications.json")
    bundle = read_json(roots.state_root / "onboarding/proposed-records.json")
    resolutions = read_json(resolutions_path)["resolutions"]
    by_key = {(item["local_id"], item["issue_type"]): item for item in resolutions}
    proposed_by_id = {item["record"]["record_id"]: item for item in bundle["records"]}
    local_map = bundle["local_id_map"]
    resolved_at = utc_now(timestamp)
    for clarification in queue["items"]:
        key = (clarification["local_id"], clarification["issue_type"])
        if key not in by_key:
            continue
        resolution = by_key[key]
        proposal = proposed_by_id[clarification["record_id"]]
        record = proposal["record"]
        for field, value in resolution.get("set_fields", {}).items():
            if isinstance(value, list):
                value = [local_map.get(child.replace("ref:", ""), child) if isinstance(child, str) and child.startswith("ref:") else child for child in value]
            record[field] = value
        clarification["candidate_value"] = resolution.get("set_fields")
        clarification["resolution"] = resolution["decision"]
        clarification["resolved_at"] = resolved_at
    unresolved = [item for item in queue["items"] if item["required_for_commit"] and not item["resolution"]]
    registry = SchemaRegistry(schema_dir())
    for proposal in bundle["records"]:
        proposal["validation_errors"] = []
        try:
            registry.validate(_proposal_schema_urn(proposal), proposal["record"])
        except Exception as exc:
            proposal["validation_errors"] = [str(exc)]
        has_unresolved = any(item["record_id"] == proposal["record"]["record_id"] for item in unresolved)
        proposal["proposal_state"] = "NEEDS_CLARIFICATION" if has_unresolved or proposal["validation_errors"] else "REVIEW_READY"
    queue["state"] = "OPEN" if unresolved else "RESOLVED"
    bundle["state"] = "NEEDS_CLARIFICATION" if unresolved or any(item["validation_errors"] for item in bundle["records"]) else "REVIEW_READY"
    atomic_write_json(roots.state_root / "onboarding/clarifications.json", queue)
    atomic_write_json(roots.state_root / "onboarding/proposed-records.json", bundle)
    session = read_json(roots.state_root / "onboarding/session.json")
    session.update({"state": bundle["state"], "resolved_at": resolved_at, "unresolved_count": len(unresolved)})
    atomic_write_json(roots.state_root / "onboarding/session.json", session)
    return queue


def commit(workspace: Path, *, actor: str, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = _workspace(workspace).roots
    bundle = read_json(roots.state_root / "onboarding/proposed-records.json")
    if bundle["state"] != "REVIEW_READY":
        raise ValueError("records are not review-ready")
    created_at = utc_now(timestamp)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for proposal in bundle["records"]:
        if proposal["proposal_state"] != "REVIEW_READY" or proposal["validation_errors"]:
            raise ValueError("all records must be schema-valid and review-ready")
        SchemaRegistry(schema_dir()).validate(_proposal_schema_urn(proposal), proposal["record"])
        grouped[proposal["kind"]].append(proposal["record"])
    committed: list[str] = []
    for kind, records in grouped.items():
        target = roots.assert_write_allowed(roots.user_data_root / "records" / f"{kind}.json", "user_data_commit")
        if target.exists():
            raise FileExistsError(f"canonical record file already exists: {target.name}")
        payload: Any = records[0] if kind in {"candidate", "preferences"} else records
        atomic_write_json(target, payload)
        committed.extend(record["record_id"] for record in records)
    event = {
        "schema": "careeros.audit-event.v1",
        "event": "CANONICAL_RECORDS_COMMITTED",
        "actor": actor,
        "occurred_at": created_at,
        "source_hash": bundle["source_hash"],
        "record_ids": sorted(committed),
    }
    append_jsonl(roots.assert_write_allowed(roots.state_root / "audit-events.jsonl", "state"), event)
    update_canonical_head(workspace, revision=1, canonical_sha256=canonical_state_hash(workspace),
                          last_event_id=None, timestamp=created_at)
    session = read_json(roots.state_root / "onboarding/session.json")
    session.update({"state": "APPROVED", "committed_at": created_at, "committed_record_count": len(committed), "actor": actor})
    atomic_write_json(roots.state_root / "onboarding/session.json", session)
    return event
