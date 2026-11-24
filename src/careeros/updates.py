"""Governed canonical changes, impact analysis, history, and derivative staleness."""

from __future__ import annotations

import copy
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import fcntl

from careeros.config.loader import load_config
from careeros.core.errors import ChangesetConflictError, ChangesetTransactionFailedError, RecordConflictError
from careeros.core.io import append_jsonl, atomic_write_json, read_json, sha256_file, sha256_value
from careeros.onboarding import TYPE_SPECS
from careeros.schemas.validation import SchemaRegistry
from careeros.versions import SCHEMA_BUNDLE_VERSION
from careeros.workspace import (
    canonical_head,
    canonical_state_hash,
    refresh_manifest_integrity,
    require_current_workspace,
    schema_dir,
    utc_now,
)


CHANGESET_SCHEMA = "urn:careeros:schema:canonical-changeset:v1"
SINGLETON_KINDS = {"candidate", "preferences"}
ADD_OPERATIONS = {"ADD_RECORD", "ADD_EVIDENCE", "ADD_PROJECT"}
VISIBILITY_RANK = {"PUBLIC": 0, "EMPLOYER_SAFE": 1, "INTERNAL": 2, "PRIVATE": 3, "RESTRICTED": 4}
PRECOMMIT_FAILURE_POINTS = {
    "BEFORE_FIRST_WRITE",
    "MID_RECORD_UPDATE",
    "AFTER_RECORD_WRITES_BEFORE_HISTORY",
    "DURING_INDEX_UPDATE",
    "DURING_STALENESS",
}
POSTCOMMIT_FAILURE_POINTS = {"AFTER_CANONICAL_COMMIT", "DURING_DERIVATIVE_REBUILD"}


def _roots(workspace: Path):
    require_current_workspace(workspace)
    return load_config(workspace / "careeros.yaml").roots


def _records_path(roots: Any, kind: str) -> Path:
    if kind not in TYPE_SPECS:
        raise ValueError(f"unsupported record type: {kind}")
    return roots.user_data_root / "records" / f"{kind}.json"


def _load_collection(path: Path, kind: str) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    value = read_json(path)
    return [value] if kind in SINGLETON_KINDS else list(value)


def _write_collection(path: Path, kind: str, records: list[dict[str, Any]]) -> None:
    if kind in SINGLETON_KINDS:
        if len(records) != 1:
            raise ValueError(f"{kind} requires exactly one canonical record")
        atomic_write_json(path, records[0])
    else:
        atomic_write_json(path, records)


def _collection_value(kind: str, records: list[dict[str, Any]]) -> Any:
    return records[0] if kind in SINGLETON_KINDS and records else records


def _changeset_material(changeset: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "changeset_id", "candidate_profile_id", "created_at", "created_by", "source", "reason",
        "proposed_changes", "affected_records", "affected_derivatives", "expected_canonical_revision",
        "expected_canonical_hash",
    )
    return {key: changeset[key] for key in keys}


def _current_head(workspace: Path) -> dict[str, Any]:
    manifest = read_json(workspace / "workspace-manifest.json")
    head = canonical_head(manifest, workspace)
    actual = canonical_state_hash(workspace)
    if head["canonical_sha256"] != actual:
        # Pre-0.3.2 manifests may not carry a head; derived heads are authoritative.
        if "canonical_head" in manifest:
            raise ChangesetConflictError(
                "workspace canonical head does not match current canonical records",
                context={"manifest_hash": head["canonical_sha256"], "actual_hash": actual},
            )
        head["canonical_sha256"] = actual
    return head


def _find(records: list[dict[str, Any]], record_id: str | None) -> tuple[int, dict[str, Any]] | None:
    if record_id is None:
        return None
    for index, record in enumerate(records):
        if record.get("record_id") == record_id:
            return index, record
    return None


def _field_get(record: dict[str, Any], field_path: str | None) -> Any:
    if not field_path:
        return record
    value: Any = record
    for part in field_path.split("."):
        if isinstance(value, list):
            value = value[int(part)]
        else:
            value = value[part]
    return value


def _field_set(record: dict[str, Any], field_path: str | None, value: Any) -> None:
    if not field_path:
        raise ValueError("field_path is required for an in-place record change")
    target: Any = record
    parts = field_path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    last = parts[-1]
    if isinstance(target, list):
        target[int(last)] = value
    else:
        target[last] = value


def _candidate_profile_id(roots: Any) -> str:
    candidate = read_json(roots.user_data_root / "records/candidate.json")
    return candidate["record_id"]


def _impact_classifications(operation: str, record_type: str, field_path: str | None) -> list[str]:
    impacts = ["PROFILE_REBUILD_REQUIRED", "ROLE_FAMILY_REVIEW_REQUIRED"]
    impacts.extend(["QUALIFICATION_STALE", "RESUME_STALE", "APPLICATION_PACKET_STALE"])
    return impacts


def _derivative_inventory(roots: Any, impacts: set[str]) -> list[dict[str, Any]]:
    def display(path: Path) -> str:
        for base, prefix in ((roots.state_root, "state"), (roots.output_root, "outputs"), (roots.user_data_root, "data")):
            try:
                return str(Path(prefix) / path.relative_to(base))
            except ValueError:
                continue
        return path.name

    specs = (
        ("PROFILE_REBUILD_REQUIRED", roots.state_root / "profile/career-profile.json", "CAREER_PROFILE"),
        ("ROLE_FAMILY_REVIEW_REQUIRED", roots.state_root / "role-families/active.json", "ROLE_FAMILY"),
    )
    found: list[dict[str, Any]] = []
    for impact, path, kind in specs:
        if impact in impacts and path.is_file():
            value = read_json(path)
            identity = value.get("profile_id") or value.get("role_family_id") or str(path.name)
            found.append({"derivative_type": kind, "derivative_id": identity, "path": display(path), "impact": impact, "status": "STALE"})
    directory_specs = (
        ("QUALIFICATION_STALE", roots.state_root / "qualifications", "QUALIFICATION", "qualification_id"),
        ("RESUME_STALE", roots.state_root / "resume-builds", "RESUME_BUILD", "build_id"),
        ("RESUME_STALE", roots.state_root / "lane-bases", "LANE_BASE_RESUME", "lane_base_id"),
        ("APPLICATION_PACKET_STALE", roots.state_root / "application-packets", "APPLICATION_PACKET", "packet_id"),
    )
    for impact, directory, kind, id_key in directory_specs:
        if impact not in impacts or not directory.is_dir():
            continue
        pattern = "*/build.json" if kind == "RESUME_BUILD" else "*/lane-base.json" if kind == "LANE_BASE_RESUME" else "*.json"
        for path in sorted(directory.glob(pattern)):
            value = read_json(path)
            found.append({"derivative_type": kind, "derivative_id": value.get(id_key, str(path.name)), "path": display(path), "impact": impact, "status": "STALE"})
    return found


def _conflict(change: dict[str, Any], current: Any, issue: str, change_index: int) -> dict[str, Any]:
    return {
        "change_index": change_index,
        "record_id": change.get("record_id"),
        "field_path": change.get("field_path"),
        "issue_type": issue,
        "canonical_value": current,
        "proposed_before": change.get("before"),
        "proposed_after": change.get("after"),
        "source_refs": change.get("source_refs", []),
        "resolution": None,
    }


def propose(workspace: Path, input_path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    roots = _roots(workspace)
    raw = read_json(input_path)
    changes = copy.deepcopy(raw.get("proposed_changes", []))
    if not changes:
        raise ValueError("at least one proposed change is required")
    created_at = utc_now(timestamp)
    conflicts: list[dict[str, Any]] = []
    affected_records: set[str] = set()
    impact_names: set[str] = set()
    for change_index, change in enumerate(changes):
        kind = change["record_type"]
        records = _load_collection(_records_path(roots, kind), kind)
        change["expected_collection_hash"] = sha256_value(_collection_value(kind, records))
        located = _find(records, change.get("record_id"))
        if change["operation"] in ADD_OPERATIONS:
            change["expected_record_hash"] = None
            after = change.get("after")
            if not isinstance(after, dict):
                conflicts.append(_conflict(change, None, "ADD_REQUIRES_COMPLETE_TYPED_RECORD", change_index))
            elif _find(records, after.get("record_id")):
                conflicts.append(_conflict(change, after.get("record_id"), "RECORD_ALREADY_EXISTS", change_index))
            else:
                affected_records.add(after.get("record_id", "pending-record-id"))
        elif located is None:
            change["expected_record_hash"] = None
            conflicts.append(_conflict(change, None, "CANONICAL_RECORD_NOT_FOUND", change_index))
        else:
            _, record = located
            change["expected_record_hash"] = sha256_value(record)
            try:
                current = _field_get(record, change.get("field_path"))
            except (KeyError, IndexError, ValueError, TypeError):
                conflicts.append(_conflict(change, None, "FIELD_PATH_NOT_FOUND", change_index))
                continue
            if current != change.get("before"):
                conflicts.append(_conflict(change, current, "SOURCE_CONFLICT", change_index))
            if change["operation"] == "CHANGE_VISIBILITY" and current in VISIBILITY_RANK and change.get("after") in VISIBILITY_RANK:
                before_rank = VISIBILITY_RANK[current]
                after_rank = VISIBILITY_RANK[change["after"]]
                expected_impact = "MORE_RESTRICTIVE" if after_rank > before_rank else "LESS_RESTRICTIVE" if after_rank < before_rank else "NONE"
                if change.get("visibility_impact") != expected_impact:
                    conflicts.append(_conflict(change, current, "VISIBILITY_IMPACT_MISMATCH", change_index))
            affected_records.add(record["record_id"])
        impact_names.update(_impact_classifications(change["operation"], kind, change.get("field_path")))
    derivatives = _derivative_inventory(roots, impact_names)
    head = _current_head(workspace)
    key = sha256_value({"workspace": _candidate_profile_id(roots), "created_at": created_at, "changes": changes})
    changeset = {
        "schema": "careeros.canonical-changeset.v1",
        "schema_version": "1.0.0",
        "changeset_id": f"changeset:{uuid.uuid5(uuid.NAMESPACE_URL, key)}",
        "candidate_profile_id": _candidate_profile_id(roots),
        "created_at": created_at,
        "created_by": raw.get("created_by", "user"),
        "source": raw.get("source", {"type": "USER_STATEMENT", "references": []}),
        "reason": raw.get("reason", "User-proposed canonical career update."),
        "proposed_changes": changes,
        "affected_records": sorted(affected_records),
        "affected_derivatives": derivatives,
        "conflicts": conflicts,
        "clarifications": [
            {"clarification_id": f"clarification:{uuid.uuid5(uuid.NAMESPACE_URL, key + ':' + str(index))}", "issue": item, "resolution": None}
            for index, item in enumerate(conflicts)
        ],
        "expected_canonical_revision": head["revision"],
        "expected_canonical_hash": head["canonical_sha256"],
        "changeset_hash": "0" * 64,
        "approval_state": "NEEDS_CLARIFICATION" if conflicts else "REVIEW_READY",
        "approved_at": None,
        "approved_by": None,
        "commit_event_id": None,
        "transaction_id": None,
        "committed_at": None,
    }
    changeset["changeset_hash"] = sha256_value(_changeset_material(changeset))
    SchemaRegistry(schema_dir()).validate(CHANGESET_SCHEMA, changeset)
    target = roots.assert_write_allowed(roots.state_root / "changesets" / f"{changeset['changeset_id'].split(':', 1)[1]}.json", "state")
    atomic_write_json(target, changeset)
    return changeset


def _changeset_path(roots: Any, changeset_id: str) -> Path:
    token = changeset_id.split(":", 1)[-1]
    return roots.state_root / "changesets" / f"{token}.json"


def preview(workspace: Path, changeset_id: str) -> dict[str, Any]:
    roots = _roots(workspace)
    changeset = read_json(_changeset_path(roots, changeset_id))
    return {
        "schema": "careeros.canonical-change-preview.v1",
        "changeset_id": changeset_id,
        "approval_state": changeset["approval_state"],
        "reason": changeset["reason"],
        "proposed_changes": changeset["proposed_changes"],
        "conflicts": changeset["conflicts"],
        "affected_derivatives": changeset["affected_derivatives"],
        "commit_allowed": changeset["approval_state"] == "APPROVED",
    }


def resolve_conflicts(workspace: Path, changeset_id: str, resolutions_path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    roots = _roots(workspace)
    path = _changeset_path(roots, changeset_id)
    changeset = read_json(path)
    resolutions = read_json(resolutions_path).get("resolutions", [])
    by_index = {item["conflict_index"]: item for item in resolutions}
    for index, conflict in enumerate(changeset["conflicts"]):
        if index not in by_index:
            continue
        resolution = by_index[index]
        change_index = conflict["change_index"]
        if resolution.get("decision") == "USE_CANONICAL_BEFORE":
            changeset["proposed_changes"][change_index]["before"] = conflict["canonical_value"]
            conflict["resolution"] = "USE_CANONICAL_BEFORE"
        elif resolution.get("decision") == "REJECT_CHANGE":
            changeset["proposed_changes"][change_index]["operation"] = "CORRECT_FACT"
            changeset["proposed_changes"][change_index]["after"] = conflict["canonical_value"]
            changeset["proposed_changes"][change_index]["before"] = conflict["canonical_value"]
            conflict["resolution"] = "REJECT_CHANGE"
        else:
            raise ValueError("resolution decision must be USE_CANONICAL_BEFORE or REJECT_CHANGE")
        changeset["clarifications"][index]["resolution"] = {"decision": conflict["resolution"], "resolved_at": utc_now(timestamp)}
    unresolved = [item for item in changeset["conflicts"] if item["resolution"] is None]
    changeset["approval_state"] = "NEEDS_CLARIFICATION" if unresolved else "REVIEW_READY"
    changeset["changeset_hash"] = sha256_value(_changeset_material(changeset))
    SchemaRegistry(schema_dir()).validate(CHANGESET_SCHEMA, changeset)
    atomic_write_json(path, changeset)
    return changeset


def approve(workspace: Path, changeset_id: str, *, actor: str, timestamp: str | None = None) -> dict[str, Any]:
    roots = _roots(workspace)
    path = _changeset_path(roots, changeset_id)
    changeset = read_json(path)
    if changeset["approval_state"] != "REVIEW_READY":
        raise RecordConflictError("changeset is not review-ready", context={"approval_state": changeset["approval_state"]})
    changeset["approval_state"] = "APPROVED"
    changeset["approved_at"] = utc_now(timestamp)
    changeset["approved_by"] = actor
    SchemaRegistry(schema_dir()).validate(CHANGESET_SCHEMA, changeset)
    atomic_write_json(path, changeset)
    return changeset


def _validated_result(records: dict[str, list[dict[str, Any]]]) -> None:
    registry = SchemaRegistry(schema_dir())
    ids: list[str] = []
    for kind, values in records.items():
        schema_id = TYPE_SPECS[kind][1]
        for record in values:
            registry.validate(schema_id, record)
            ids.append(record["record_id"])
    if len(ids) != len(set(ids)):
        raise RecordConflictError("committed record IDs must remain unique")


def _write_history_snapshot(roots: Any, record: dict[str, Any], *, changeset_id: str, timestamp: str) -> dict[str, Any]:
    token = record["record_id"].replace(":", "__").replace("/", "_")
    snapshot = {
        "schema": "careeros.canonical-history-snapshot.v1",
        "record_id": record["record_id"],
        "changeset_id": changeset_id,
        "captured_at": timestamp,
        "record_hash": sha256_value(record),
        "record": record,
    }
    name = f"{timestamp.replace(':', '').replace('-', '')}-{snapshot['record_hash'][:12]}.json"
    target = roots.assert_write_allowed(roots.user_data_root / "history" / token / name, "user_data_commit")
    if target.exists():
        raise FileExistsError(f"history snapshot already exists: {target}")
    atomic_write_json(target, snapshot)
    return snapshot


def _write_staleness(roots: Any, changeset: dict[str, Any], timestamp: str) -> dict[str, Any]:
    path = roots.state_root / "derivative-status.json"
    registry = read_json(path) if path.is_file() else {"schema": "careeros.derivative-status-registry.v1", "entries": []}
    by_key = {(item["derivative_type"], item["derivative_id"]): item for item in registry["entries"]}
    for derivative in changeset["affected_derivatives"]:
        key = (derivative["derivative_type"], derivative["derivative_id"])
        by_key[key] = {
            **derivative,
            "status": "STALE",
            "stale_since": timestamp,
            "caused_by_changeset_id": changeset["changeset_id"],
            "historical_artifact_immutable": derivative["derivative_type"] in {"RESUME_BUILD", "APPLICATION_PACKET", "LANE_BASE_RESUME"},
            "reuse_allowed": False,
        }
    registry["entries"] = sorted(by_key.values(), key=lambda item: (item["derivative_type"], item["derivative_id"]))
    atomic_write_json(roots.assert_write_allowed(path, "state"), registry)
    return registry


def _history_snapshot_payload(record: dict[str, Any], *, changeset_id: str, timestamp: str) -> tuple[dict[str, Any], str]:
    snapshot = {
        "schema": "careeros.canonical-history-snapshot.v1",
        "record_id": record["record_id"],
        "changeset_id": changeset_id,
        "captured_at": timestamp,
        "record_hash": sha256_value(record),
        "record": record,
    }
    name = f"{timestamp.replace(':', '').replace('-', '')}-{snapshot['record_hash'][:12]}.json"
    return snapshot, name


@contextmanager
def _transaction_lock(roots: Any):
    lock_path = roots.assert_write_allowed(roots.state_root / "canonical-transaction.lock", "state")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _capture_snapshot(workspace: Path, tx_dir: Path, files: list[Path]) -> list[dict[str, Any]]:
    snapshot_root = tx_dir / "snapshot"
    entries: list[dict[str, Any]] = []
    for path in sorted(set(file.resolve() for file in files), key=str):
        try:
            relative = path.relative_to(workspace.resolve())
        except ValueError as exc:
            raise ValueError(f"transaction participant is outside workspace: {path}") from exc
        entry = {"path": relative.as_posix(), "existed": path.is_file(), "sha256": sha256_file(path) if path.is_file() else None}
        if path.is_file():
            backup = snapshot_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            entry["snapshot_path"] = str(backup.relative_to(tx_dir))
        else:
            entry["snapshot_path"] = None
        entries.append(entry)
    return entries


def _restore_snapshot(workspace: Path, tx_dir: Path, entries: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for entry in reversed(entries):
        target = workspace / entry["path"]
        if entry["existed"]:
            source = tx_dir / entry["snapshot_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if sha256_file(target) != entry["sha256"]:
                failures.append(entry["path"])
        elif target.exists():
            if target.is_file():
                target.unlink()
            else:
                failures.append(entry["path"])
    return failures


def _inject(failure_at: str | None, point: str) -> None:
    if failure_at == point:
        raise RuntimeError(f"injected changeset failure at {point}")


def _events(roots: Any) -> list[dict[str, Any]]:
    path = roots.state_root / "canonical-history/events.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _record_failure(roots: Any, *, changeset_id: str, transaction_id: str, point: str | None,
                    committed: bool, restored: bool, error: Exception, timestamp: str) -> None:
    append_jsonl(roots.assert_write_allowed(roots.state_root / "canonical-transactions/failures.jsonl", "state"), {
        "schema": "careeros.canonical-transaction-failure.v1",
        "transaction_id": transaction_id,
        "changeset_id": changeset_id,
        "occurred_at": timestamp,
        "failure_point": point,
        "canonical_commit_completed": committed,
        "previous_state_restored": restored,
        "error_type": error.__class__.__name__,
    })


def _recover_incomplete_transactions(workspace: Path, roots: Any) -> None:
    directory = roots.state_root / "canonical-transactions"
    if not directory.is_dir():
        return
    for journal_path in sorted(directory.glob("*/transaction.json")):
        journal = read_json(journal_path)
        if journal.get("status") in {"COMMITTED", "ROLLED_BACK"}:
            continue
        changeset_path = _changeset_path(roots, journal["changeset_id"])
        changeset = read_json(changeset_path) if changeset_path.is_file() else {}
        events = _events(roots)
        event_ids = {event.get("event_id") for event in events}
        if changeset.get("approval_state") == "COMMITTED" and changeset.get("commit_event_id") in event_ids:
            journal["status"] = "COMMITTED"
            journal["recovered_at"] = utc_now()
            atomic_write_json(journal_path, journal)
            continue
        failures = _restore_snapshot(workspace, journal_path.parent, journal.get("snapshot", []))
        journal["status"] = "ROLLED_BACK" if not failures else "ROLLBACK_FAILED"
        journal["recovered_at"] = utc_now()
        journal["restore_failures"] = failures
        atomic_write_json(journal_path, journal)
        if failures:
            raise ChangesetTransactionFailedError(
                "incomplete canonical transaction could not be restored",
                context={"transaction_id": journal.get("transaction_id"), "restore_failures": failures},
            )


def _assert_expected_state(workspace: Path, roots: Any, changeset: dict[str, Any]) -> dict[str, Any]:
    if changeset.get("changeset_hash") != sha256_value(_changeset_material(changeset)):
        raise ChangesetConflictError("changeset content changed after proposal")
    head = _current_head(workspace)
    if head["revision"] != changeset["expected_canonical_revision"] or head["canonical_sha256"] != changeset["expected_canonical_hash"]:
        raise ChangesetConflictError(
            "canonical state changed after this changeset was proposed",
            context={
                "expected_revision": changeset["expected_canonical_revision"],
                "current_revision": head["revision"],
                "expected_hash": changeset["expected_canonical_hash"],
                "current_hash": head["canonical_sha256"],
            },
        )
    for change in changeset["proposed_changes"]:
        kind = change["record_type"]
        records = _load_collection(_records_path(roots, kind), kind)
        collection_hash = sha256_value(_collection_value(kind, records))
        if collection_hash != change["expected_collection_hash"]:
            raise ChangesetConflictError("canonical collection changed after proposal", context={"record_type": kind})
        if change["expected_record_hash"] is not None:
            located = _find(records, change.get("record_id"))
            current_hash = sha256_value(located[1]) if located else None
            if current_hash != change["expected_record_hash"]:
                raise ChangesetConflictError("canonical record changed after proposal", context={"record_id": change.get("record_id")})
    return head


def commit(workspace: Path, changeset_id: str, *, actor: str, timestamp: str | None = None,
           failure_at: str | None = None) -> dict[str, Any]:
    if failure_at is not None and failure_at not in PRECOMMIT_FAILURE_POINTS | POSTCOMMIT_FAILURE_POINTS:
        raise ValueError(f"unknown failure injection point: {failure_at}")
    roots = _roots(workspace)
    with _transaction_lock(roots):
        _recover_incomplete_transactions(workspace, roots)
        path = _changeset_path(roots, changeset_id)
        changeset = read_json(path)
        if changeset["approval_state"] == "COMMITTED":
            event = next((item for item in _events(roots) if item.get("event_id") == changeset.get("commit_event_id")), None)
            if event is None:
                raise ChangesetTransactionFailedError("committed changeset has no matching history event")
            return {**event, "idempotency_status": "ALREADY_COMMITTED"}
        if changeset["approval_state"] != "APPROVED":
            raise PermissionError("canonical changes require explicit approval before commit")
        if changeset.get("approved_by") != actor:
            raise PermissionError("commit actor must match the approving actor")
        committed_at = utc_now(timestamp)
        head = _assert_expected_state(workspace, roots, changeset)
        working: dict[str, list[dict[str, Any]]] = {}
        originals: dict[str, dict[str, Any]] = {}
        for change in changeset["proposed_changes"]:
            kind = change["record_type"]
            records = working.setdefault(kind, copy.deepcopy(_load_collection(_records_path(roots, kind), kind)))
            located = _find(records, change.get("record_id"))
            if change["operation"] in ADD_OPERATIONS:
                record = copy.deepcopy(change["after"])
                if _find(records, record.get("record_id")):
                    raise ChangesetConflictError("record already exists", context={"record_id": record.get("record_id")})
                records.append(record)
                continue
            if located is None:
                raise ChangesetConflictError("canonical record disappeared before commit", context={"record_id": change.get("record_id")})
            index, record = located
            current = _field_get(record, change.get("field_path"))
            if current != change.get("before"):
                raise ChangesetConflictError("canonical value changed after proposal", context={"record_id": record["record_id"], "field_path": change.get("field_path"), "current": current})
            originals.setdefault(record["record_id"], copy.deepcopy(record))
            if change["operation"] == "SUPERSEDE_RECORD":
                record["status"] = "SUPERSEDED"
                record["updated_at"] = committed_at
                if isinstance(change.get("after"), dict):
                    records.append(copy.deepcopy(change["after"]))
            else:
                _field_set(record, change.get("field_path"), copy.deepcopy(change.get("after")))
                record["updated_at"] = committed_at
                records[index] = record
        for kind in TYPE_SPECS:
            if kind not in working:
                working[kind] = copy.deepcopy(_load_collection(_records_path(roots, kind), kind))
        _validated_result(working)
        changed_kinds = sorted({change["record_type"] for change in changeset["proposed_changes"]})
        state_payload = {
            f"{kind}.json": _collection_value(kind, working[kind])
            for kind in sorted(TYPE_SPECS)
            if _records_path(roots, kind).is_file() or kind in changed_kinds
        }
        resulting_hash = sha256_value(state_payload)
        before_hashes = {record_id: sha256_value(record) for record_id, record in originals.items()}
        after_records = {record["record_id"]: record for records in working.values() for record in records}
        affected_ids = sorted({rid for rid in changeset["affected_records"] if rid in after_records})
        after_hashes = {record_id: sha256_value(after_records[record_id]) for record_id in affected_ids}
        event_id = f"event:{uuid.uuid5(uuid.NAMESPACE_URL, changeset_id + ':' + committed_at)}"
        transaction_root = roots.state_root / "canonical-transactions"
        attempt_count = len(list(transaction_root.glob("*/transaction.json"))) if transaction_root.exists() else 0
        transaction_key = f"{changeset_id}:{committed_at}:{attempt_count}"
        transaction_id = f"transaction:{uuid.uuid5(uuid.NAMESPACE_URL, transaction_key)}"
        tx_token = transaction_id.split(":", 1)[1]
        tx_dir = roots.assert_write_allowed(roots.state_root / "canonical-transactions" / tx_token, "state")
        tx_dir.mkdir(parents=True, exist_ok=False)
        history_targets: list[tuple[dict[str, Any], Path]] = []
        for record in originals.values():
            snapshot, name = _history_snapshot_payload(record, changeset_id=changeset_id, timestamp=committed_at)
            token = record["record_id"].replace(":", "__").replace("/", "_")
            history_targets.append((snapshot, roots.user_data_root / "history" / token / name))
        participants = [
            *[_records_path(roots, kind) for kind in changed_kinds],
            workspace / "workspace-manifest.json",
            path,
            roots.state_root / "canonical-history/events.jsonl",
            roots.state_root / "derivative-status.json",
            *[target for _, target in history_targets],
        ]
        snapshot_entries = _capture_snapshot(workspace, tx_dir, participants)
        journal_path = tx_dir / "transaction.json"
        journal = {
            "schema": "careeros.canonical-transaction.v1",
            "transaction_id": transaction_id,
            "changeset_id": changeset_id,
            "status": "PREPARED",
            "prepared_at": committed_at,
            "failure_injection": failure_at,
            "source_revision": head["revision"],
            "source_canonical_hash": head["canonical_sha256"],
            "target_revision": head["revision"] + 1,
            "target_canonical_hash": resulting_hash,
            "snapshot": snapshot_entries,
        }
        atomic_write_json(journal_path, journal)
        committed = False
        try:
            journal["status"] = "APPLYING"
            atomic_write_json(journal_path, journal)
            _inject(failure_at, "BEFORE_FIRST_WRITE")
            for index, kind in enumerate(changed_kinds):
                _write_collection(roots.assert_write_allowed(_records_path(roots, kind), "user_data_commit"), kind, working[kind])
                if index == 0:
                    _inject(failure_at, "MID_RECORD_UPDATE")
            _inject(failure_at, "AFTER_RECORD_WRITES_BEFORE_HISTORY")
            for snapshot, target in history_targets:
                atomic_write_json(roots.assert_write_allowed(target, "user_data_commit"), snapshot)
            prior_events = _events(roots)
            previous_event_hash = prior_events[-1].get("event_hash") if prior_events else None
            event = {
                "schema": "careeros.canonical-change-event.v1",
                "event_id": event_id,
                "event": "CANONICAL_CHANGESET_COMMITTED",
                "changeset_id": changeset_id,
                "changeset_hash": changeset["changeset_hash"],
                "actor": actor,
                "occurred_at": committed_at,
                "reason": changeset["reason"],
                "record_ids": affected_ids,
                "before_hashes": before_hashes,
                "after_hashes": after_hashes,
                "approved_at": changeset["approved_at"],
                "approved_by": changeset["approved_by"],
                "previous_canonical_revision": head["revision"],
                "previous_canonical_hash": head["canonical_sha256"],
                "resulting_canonical_revision": head["revision"] + 1,
                "resulting_canonical_hash": resulting_hash,
                "previous_event_hash": previous_event_hash,
                "dependent_state_effects": changeset["affected_derivatives"],
            }
            event["event_hash"] = sha256_value(event)
            append_jsonl(roots.assert_write_allowed(roots.state_root / "canonical-history/events.jsonl", "state"), event)
            manifest_path = workspace / "workspace-manifest.json"
            manifest = read_json(manifest_path)
            manifest["schema_bundle_version"] = SCHEMA_BUNDLE_VERSION
            manifest["canonical_head"] = {
                "revision": head["revision"] + 1,
                "canonical_sha256": resulting_hash,
                "last_event_id": event_id,
                "updated_at": committed_at,
            }
            refresh_manifest_integrity(manifest, workspace / "careeros.yaml", timestamp=committed_at)
            atomic_write_json(manifest_path, manifest)
            _inject(failure_at, "DURING_INDEX_UPDATE")
            _write_staleness(roots, changeset, committed_at)
            _inject(failure_at, "DURING_STALENESS")
            if canonical_state_hash(workspace) != resulting_hash:
                raise RuntimeError("post-apply canonical state hash mismatch")
            changeset["approval_state"] = "COMMITTED"
            changeset["commit_event_id"] = event_id
            changeset["transaction_id"] = transaction_id
            changeset["committed_at"] = committed_at
            SchemaRegistry(schema_dir()).validate(CHANGESET_SCHEMA, changeset)
            atomic_write_json(path, changeset)
            journal["status"] = "COMMITTED"
            journal["committed_at"] = committed_at
            journal["event_id"] = event_id
            atomic_write_json(journal_path, journal)
            committed = True
            _inject(failure_at, "AFTER_CANONICAL_COMMIT")
            _inject(failure_at, "DURING_DERIVATIVE_REBUILD")
            return event
        except Exception as exc:
            if committed:
                _record_failure(roots, changeset_id=changeset_id, transaction_id=transaction_id,
                                point=failure_at, committed=True, restored=False, error=exc, timestamp=committed_at)
                raise ChangesetTransactionFailedError(
                    "canonical commit succeeded but a post-commit operation failed; canonical truth was not rolled back",
                    cause=exc,
                    context={"transaction_id": transaction_id, "canonical_committed": True, "failure_point": failure_at},
                ) from exc
            failures = _restore_snapshot(workspace, tx_dir, snapshot_entries)
            restored = not failures and canonical_state_hash(workspace) == head["canonical_sha256"]
            journal["status"] = "ROLLED_BACK" if restored else "ROLLBACK_FAILED"
            journal["rolled_back_at"] = committed_at
            journal["restore_failures"] = failures
            atomic_write_json(journal_path, journal)
            _record_failure(roots, changeset_id=changeset_id, transaction_id=transaction_id,
                            point=failure_at, committed=False, restored=restored, error=exc, timestamp=committed_at)
            if not restored:
                raise ChangesetTransactionFailedError(
                    "canonical transaction failed and rollback verification failed",
                    cause=exc,
                    context={"transaction_id": transaction_id, "restore_failures": failures},
                ) from exc
            raise ChangesetTransactionFailedError(
                "canonical transaction failed; previous canonical state restored and verified",
                cause=exc,
                context={"transaction_id": transaction_id, "failure_point": failure_at, "rollback_verified": True},
            ) from exc


def verify_history_chain(workspace: Path) -> dict[str, Any]:
    roots = _roots(workspace)
    events = _events(roots)
    failures: list[dict[str, Any]] = []
    previous_hash: str | None = None
    previous_revision: int | None = None
    for index, event in enumerate(events):
        expected_event_hash = sha256_value({key: value for key, value in event.items() if key != "event_hash"})
        if event.get("event_hash") != expected_event_hash:
            failures.append({"index": index, "issue": "EVENT_HASH_MISMATCH"})
        if event.get("previous_event_hash") != previous_hash:
            failures.append({"index": index, "issue": "PREVIOUS_EVENT_HASH_MISMATCH"})
        if previous_revision is not None and event.get("previous_canonical_revision") != previous_revision:
            failures.append({"index": index, "issue": "REVISION_CHAIN_BREAK"})
        if event.get("resulting_canonical_revision") != event.get("previous_canonical_revision", -1) + 1:
            failures.append({"index": index, "issue": "INVALID_REVISION_INCREMENT"})
        previous_hash = event.get("event_hash")
        previous_revision = event.get("resulting_canonical_revision")
    manifest = read_json(workspace / "workspace-manifest.json")
    head = canonical_head(manifest, workspace)
    if events:
        if head.get("last_event_id") != events[-1].get("event_id"):
            failures.append({"index": len(events) - 1, "issue": "MANIFEST_EVENT_HEAD_MISMATCH"})
        if head.get("canonical_sha256") != events[-1].get("resulting_canonical_hash"):
            failures.append({"index": len(events) - 1, "issue": "MANIFEST_CANONICAL_HASH_MISMATCH"})
        if head.get("revision") != events[-1].get("resulting_canonical_revision"):
            failures.append({"index": len(events) - 1, "issue": "MANIFEST_REVISION_MISMATCH"})
    return {
        "schema": "careeros.canonical-history-verification.v1",
        "status": "PASS" if not failures else "FAIL",
        "event_count": len(events),
        "failures": failures,
        "head": head,
    }


def history(workspace: Path, record_id: str | None = None) -> dict[str, Any]:
    roots = _roots(workspace)
    events_path = roots.state_root / "canonical-history/events.jsonl"
    events: list[dict[str, Any]] = []
    if events_path.is_file():
        import json
        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if record_id:
        events = [item for item in events if record_id in item.get("record_ids", [])]
        token = record_id.replace(":", "__").replace("/", "_")
        snapshots = [read_json(path) for path in sorted((roots.user_data_root / "history" / token).glob("*.json"))]
    else:
        snapshots = []
    return {"schema": "careeros.canonical-history.v1", "record_id": record_id, "events": events,
            "snapshots": snapshots, "chain_verification": verify_history_chain(workspace)}


def require_derivative_current(roots: Any, derivative_type: str, derivative_id: str) -> None:
    path = roots.state_root / "derivative-status.json"
    if not path.is_file():
        return
    registry = read_json(path)
    for item in registry.get("entries", []):
        if item.get("derivative_type") == derivative_type and item.get("derivative_id") == derivative_id and item.get("status") == "STALE":
            raise PermissionError(f"{derivative_type} {derivative_id} is stale and must be rebuilt before reuse")


def mark_derivative_current(roots: Any, derivative_type: str, derivative_id: str, *, timestamp: str, lineage_hash: str | None = None) -> None:
    path = roots.state_root / "derivative-status.json"
    registry = read_json(path) if path.is_file() else {"schema": "careeros.derivative-status-registry.v1", "entries": []}
    entries = [item for item in registry.get("entries", []) if not (item.get("derivative_type") == derivative_type and item.get("derivative_id") == derivative_id)]
    entries.append({
        "derivative_type": derivative_type,
        "derivative_id": derivative_id,
        "path": None,
        "impact": "NO_REBUILD_REQUIRED",
        "status": "CURRENT",
        "current_since": timestamp,
        "lineage_hash": lineage_hash,
        "historical_artifact_immutable": derivative_type in {"RESUME_BUILD", "APPLICATION_PACKET", "LANE_BASE_RESUME"},
        "reuse_allowed": True,
    })
    registry["entries"] = sorted(entries, key=lambda item: (item["derivative_type"], item["derivative_id"]))
    atomic_write_json(roots.assert_write_allowed(path, "state"), registry)
