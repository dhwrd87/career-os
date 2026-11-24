"""Persistent cross-run opportunity identity and discovery reconciliation.

The registry is candidate-workspace state.  Provider adapters and operator-led
discovery must reconcile candidates here before describing any posting as NEW.
The module performs no network access and never submits an application.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from careeros.core.io import atomic_write_json, sha256_value
from careeros.config.loader import load_config
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir, utc_now


OPPORTUNITY_REGISTRY_POLICY_VERSION = "cross-run-opportunity-dedupe-v1"
DISCOVERY_CLASSES = {
    "NEW",
    "KNOWN_UNCHANGED",
    "KNOWN_UPDATED",
    "REPOST",
    "SUPERSEDED",
    "ALREADY_APPLIED",
    "PREVIOUSLY_REJECTED",
    "PREVIOUSLY_SKIPPED",
    "AMBIGUOUS_IDENTITY",
}
UPDATE_CLASSES = {"NONE", "MINOR_UPDATE", "MATERIAL_UPDATE", "REPOST"}
APPLICATION_ACTIVE_STATES = {
    "SUBMITTED", "FOLLOW_UP_DUE", "FOLLOW_UP_SENT", "EMPLOYER_RESPONSE",
    "INTERVIEW_INVITED", "INTERVIEW_SCHEDULED", "INTERVIEW_COMPLETED",
    "OFFER_RECEIVED", "OFFER_ACCEPTED", "HIRED",
}
APPLICATION_REJECTED_STATES = {"REJECTED"}
APPLICATION_SKIPPED_STATES = {"SKIPPED", "DO_NOT_SPEND_TIME", "WITHDRAWN"}
PACKET_PENDING_STATES = {
    "PACKET_PREPARED", "REVIEW_REQUESTED", "APPROVED", "SUBMISSION_PENDING",
}


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", []):
            return value
    return None


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")


def _normalized_url(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    parsed = urlsplit(raw)
    if not parsed.netloc:
        return raw.rstrip("/")
    retained = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=False):
        if key.casefold() in {"gh_jid", "job", "jobid", "jk", "pid", "req_id", "requisitionid"}:
            retained.append((key, item))
    path = re.sub(r"/(apply|application)/?$", "", parsed.path.rstrip("/"), flags=re.I)
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, urlencode(sorted(retained)), ""))


def _source_namespace(record: dict[str, Any]) -> str:
    source = str(_first(record, "source", "source_type", "provider") or "").casefold()
    url = _normalized_url(_first(record, "canonical_url", "source_url"))
    host = urlsplit(url).netloc if url else ""
    for token in ("greenhouse", "lever", "ashby", "workday", "icims", "indeed", "linkedin", "ziprecruiter"):
        if token in host or token in source:
            return token
    return _slug(host or source)


def _jd_text(record: dict[str, Any]) -> str:
    return str(_first(record, "job_description", "text", "jd_text", "description") or "").strip()


def _jd_hash(record: dict[str, Any]) -> str | None:
    explicit = _first(record, "jd_hash", "job_posting_hash", "content_hash", "snapshot_hash")
    if explicit:
        return str(explicit)
    text = _jd_text(record)
    return sha256_value(text) if text else None


def _provider_id(record: dict[str, Any]) -> str | None:
    value = _first(record, "provider_job_id", "provider_id", "requisition_id", "canonical_job_id", "ATS_ID")
    return str(value).strip().casefold() if value else None


def _application_state(record: dict[str, Any]) -> str:
    state = _first(record, "application_state", "current_state", "outcome")
    return str(state or "NOT_STARTED").upper()


def normalize_opportunity(
    record: dict[str, Any],
    *,
    snapshot: dict[str, Any] | None = None,
    freshness: dict[str, Any] | None = None,
    qualification: dict[str, Any] | None = None,
    application: dict[str, Any] | None = None,
    packet_exists: bool = False,
    source_record_path: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Normalize legacy, live-run, and current package opportunity shapes."""
    snapshot = snapshot or {}
    freshness = freshness or {}
    qualification = qualification or {}
    application = application or {}
    observed = observed_at or _first(record, "last_seen_at", "last_verified_at", "captured_at", "created_at")
    first_seen = _first(record, "first_seen_at", "captured_at", "created_at") or observed
    merged_hash_source = {**record, **snapshot, **freshness}
    application_state = _application_state({**record, **application})
    qualification_state = str(_first(record, "qualification_state", "qualification") or qualification.get("decision") or record.get("status") or "UNKNOWN").upper()
    packet_pending = bool(packet_exists or application_state in PACKET_PENDING_STATES)
    identity_seed = "|".join(str(value or "") for value in (
        _first(record, "employer", "employer_name"),
        _first(record, "title", "role_title"),
        _first(record, "provider_job_id", "provider_id", "requisition_id"),
        _first(record, "canonical_url", "source_url"),
    ))
    return {
        "opportunity_id": str(record.get("opportunity_id") or f"opportunity:{uuid.uuid5(uuid.NAMESPACE_URL, identity_seed)}"),
        "employer": str(_first(record, "employer", "employer_name") or ""),
        "title": str(_first(record, "title", "role_title") or ""),
        "location": _first(record, "location"),
        "canonical_url": _normalized_url(_first(record, "canonical_url", "source_url")),
        "provider_job_id": _provider_id(record),
        "source": str(_first(record, "source", "source_type", "provider") or "UNKNOWN"),
        "source_namespace": _source_namespace(record),
        "jd_hash": _jd_hash(merged_hash_source),
        "jd_text": _jd_text({**record, **snapshot}),
        "first_seen_at": first_seen,
        "last_seen_at": observed or first_seen,
        "freshness_state": str(_first(record, "freshness_state") or freshness.get("freshness_state") or "UNKNOWN").upper(),
        "qualification_state": qualification_state,
        "application_state": application_state,
        "packet_state": "APPLICATION_PENDING" if packet_pending and application_state not in APPLICATION_ACTIVE_STATES else "NONE",
        "supersedes": _first(record, "supersedes") or freshness.get("supersedes"),
        "repost_group_id": _first(record, "repost_group_id") or freshness.get("repost_group_id"),
        "explicit_repost": bool(record.get("explicit_repost")),
        "disposition": str(_first(record, "disposition") or "UNKNOWN").upper(),
        "source_record_paths": [source_record_path] if source_record_path else [],
    }


def _merge_entry(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if value not in (None, "", "UNKNOWN", "NOT_STARTED", "NONE", []):
            merged[key] = value
    seen = sorted(set(left.get("source_record_paths", [])) | set(right.get("source_record_paths", [])))
    merged["source_record_paths"] = seen
    candidates = [value for value in (left.get("first_seen_at"), right.get("first_seen_at")) if value]
    merged["first_seen_at"] = min(candidates) if candidates else None
    candidates = [value for value in (left.get("last_seen_at"), right.get("last_seen_at")) if value]
    merged["last_seen_at"] = max(candidates) if candidates else merged.get("first_seen_at")
    return merged


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_persistent_registry(state_root: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    """Build a persistent registry view across every historical search run.

    The recursive scan is intentional: older workspaces stored opportunities under
    run folders while newer workspaces may store them directly by opportunity ID.
    Historical records are retained; no source files are rewritten.
    """
    opportunities_root = state_root / "opportunities"
    applications_root = state_root / "applications"
    applications: dict[str, dict[str, Any]] = {}
    if applications_root.exists():
        for path in applications_root.rglob("*.json"):
            value = _read_json(path)
            if value.get("opportunity_id"):
                applications[str(value["opportunity_id"])] = value
    entries: dict[str, dict[str, Any]] = {}
    if opportunities_root.exists():
        for path in sorted(opportunities_root.rglob("opportunity.json")):
            record = _read_json(path)
            opportunity_id = str(record.get("opportunity_id") or "")
            if not opportunity_id:
                continue
            packet_exists = any((path.parent / name).exists() for name in ("application-packet.json", "tailoring-artifact.json", "packet.json"))
            normalized = normalize_opportunity(
                record,
                snapshot=_read_json(path.with_name("jd-snapshot.json")),
                freshness=_read_json(path.with_name("freshness.json")),
                qualification=_read_json(path.with_name("qualification.json")),
                application=applications.get(opportunity_id),
                packet_exists=packet_exists,
                source_record_path=str(path.relative_to(state_root)),
            )
            entries[opportunity_id] = _merge_entry(entries[opportunity_id], normalized) if opportunity_id in entries else normalized
    built_at = utc_now(timestamp)
    ordered = sorted(entries.values(), key=lambda item: (item.get("first_seen_at") or "", item["opportunity_id"]))
    payload = {
        "schema": "careeros.opportunity-registry.v1",
        "schema_version": "1.0.0",
        "registry_id": "opportunity-registry:persistent",
        "policy_version": OPPORTUNITY_REGISTRY_POLICY_VERSION,
        "built_at": built_at,
        "opportunity_count": len(ordered),
        "entries": ordered,
    }
    payload["registry_hash"] = sha256_value({key: value for key, value in payload.items() if key != "registry_hash"})
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:opportunity-registry:v1", payload)
    return payload


def persist_registry(state_root: Path, registry: dict[str, Any]) -> Path:
    """Persist the derived registry without deleting historical run records."""
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:opportunity-registry:v1", registry)
    target = state_root / "opportunity-registry.json"
    atomic_write_json(target, registry)
    return target


@dataclass(frozen=True)
class _Match:
    entry: dict[str, Any]
    identity_reason: str
    strength: int
    repost: bool = False
    ambiguous: bool = False


def _similarity(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    if left.get("jd_hash") and left.get("jd_hash") == right.get("jd_hash"):
        return 1.0
    if left.get("jd_text") and right.get("jd_text"):
        return round(SequenceMatcher(None, left["jd_text"].casefold(), right["jd_text"].casefold()).ratio(), 3)
    return None


def _identity_match(previous: dict[str, Any], current: dict[str, Any]) -> _Match | None:
    same_employer = bool(_slug(previous.get("employer")) and _slug(previous.get("employer")) == _slug(current.get("employer")))
    same_title = bool(_slug(previous.get("title")) and _slug(previous.get("title")) == _slug(current.get("title")))
    same_location = _slug(previous.get("location")) == _slug(current.get("location"))
    provider_match = bool(previous.get("provider_job_id") and previous.get("provider_job_id") == current.get("provider_job_id"))
    provider_namespace_safe = not previous.get("source_namespace") or not current.get("source_namespace") or previous.get("source_namespace") == current.get("source_namespace") or (same_employer and same_title)
    url_match = bool(previous.get("canonical_url") and previous.get("canonical_url") == current.get("canonical_url"))
    similarity = _similarity(previous, current)
    explicit_supersession = current.get("supersedes") == previous.get("opportunity_id")
    different_requisition = bool(previous.get("provider_job_id") and current.get("provider_job_id") and previous.get("provider_job_id") != current.get("provider_job_id"))

    if explicit_supersession or current.get("explicit_repost"):
        return _Match(previous, "Discovery explicitly supersedes this historical posting.", 100, repost=True)
    if provider_match and provider_namespace_safe:
        return _Match(previous, "Provider/source job identifier matches the persistent registry.", 95)
    if url_match:
        return _Match(previous, "Normalized canonical URL matches the persistent registry.", 90)
    if same_employer and same_title and similarity == 1.0:
        if different_requisition:
            previous_closed = previous.get("freshness_state") in {"CLOSED", "EXPIRED", "SUPERSEDED", "REPOSTED"}
            return _Match(previous, "A new requisition carries the same employer, title, and JD as historical posting.", 82, repost=previous_closed or bool(current.get("explicit_repost")))
        return _Match(previous, "Employer, title, and exact JD match across syndicated or changed URLs.", 85)
    if same_employer and same_title and different_requisition:
        if current.get("explicit_repost") or previous.get("freshness_state") in {"CLOSED", "EXPIRED", "SUPERSEDED", "REPOSTED"}:
            if similarity is None or similarity >= 0.70:
                return _Match(previous, "A new requisition is a materially similar repost of a historical posting.", 78, repost=True)
        if similarity is not None and similarity < 0.65:
            return None
    if same_employer and same_title and same_location:
        if similarity is not None and similarity >= 0.75:
            return _Match(previous, "Employer/title/location and JD similarity identify the same posting.", 70)
        return _Match(previous, "Employer/title/location match but identifiers do not resolve identity safely.", 30, ambiguous=True)
    return None


def _update_class(previous: dict[str, Any], current: dict[str, Any], *, repost: bool) -> str:
    if repost:
        return "REPOST"
    previous_hash, current_hash = previous.get("jd_hash"), current.get("jd_hash")
    if previous_hash and current_hash and previous_hash == current_hash:
        material_fields = ("employer", "title", "location")
        return "MINOR_UPDATE" if any(previous.get(field) != current.get(field) for field in material_fields) else "NONE"
    similarity = _similarity(previous, current)
    if similarity is not None and similarity >= 0.92:
        return "MINOR_UPDATE"
    if previous_hash and current_hash and previous_hash != current_hash:
        return "MATERIAL_UPDATE"
    return "MINOR_UPDATE" if any(previous.get(field) != current.get(field) for field in ("location", "canonical_url", "source")) else "NONE"


def classify_discovered_opportunity(discovered: dict[str, Any], registry: dict[str, Any], *, observed_at: str | None = None) -> dict[str, Any]:
    """Classify one discovery only after checking every persistent registry entry."""
    current = normalize_opportunity(discovered, observed_at=observed_at)
    matches = [match for entry in registry.get("entries", []) if (match := _identity_match(entry, current))]
    if not matches:
        classification = "NEW"
        return {
            "classification": classification, "update_classification": "NONE", "matched_opportunity_id": None,
            "identity_reason": "No persistent registry entry matches available identity evidence.",
            "surface_state": "NEW", "create_packet_allowed": True, "count_as_new": True,
            "registry_checked": True, "requires_freshness_check": True, "requires_requalification": True,
            "current": current,
        }
    strongest = sorted(matches, key=lambda item: item.strength, reverse=True)[0]
    previous = strongest.entry
    if strongest.ambiguous:
        classification, surface, packet_allowed = "AMBIGUOUS_IDENTITY", "HOLD_FOR_IDENTITY_REVIEW", False
        update = "NONE"
    elif strongest.repost:
        classification, surface, packet_allowed = "REPOST", "REPOST_REQUIRES_FRESH_QUALIFICATION", True
        update = "REPOST"
    else:
        update = _update_class(previous, current, repost=False)
        application_state = _application_state(previous)
        if application_state in APPLICATION_ACTIVE_STATES:
            classification, surface, packet_allowed = "ALREADY_APPLIED", f"ALREADY_APPLIED — {application_state}", False
        elif application_state in APPLICATION_REJECTED_STATES:
            classification, surface, packet_allowed = "PREVIOUSLY_REJECTED", "PREVIOUSLY_REJECTED", False
        elif application_state in APPLICATION_SKIPPED_STATES or previous.get("disposition") == "DO_NOT_SPEND_TIME":
            classification, surface, packet_allowed = "PREVIOUSLY_SKIPPED", "PREVIOUSLY_SKIPPED", False
        elif previous.get("packet_state") == "APPLICATION_PENDING":
            classification, surface, packet_allowed = ("KNOWN_UPDATED" if update != "NONE" else "KNOWN_UNCHANGED"), "KNOWN — APPLICATION PENDING", False
        elif previous.get("freshness_state") == "SUPERSEDED":
            classification, surface, packet_allowed = "SUPERSEDED", "SUPERSEDED", False
        else:
            classification = "KNOWN_UPDATED" if update != "NONE" else "KNOWN_UNCHANGED"
            surface, packet_allowed = classification, False
    return {
        "classification": classification,
        "update_classification": update,
        "matched_opportunity_id": previous.get("opportunity_id"),
        "identity_reason": strongest.identity_reason,
        "surface_state": surface,
        "create_packet_allowed": packet_allowed,
        "count_as_new": classification == "NEW",
        "registry_checked": True,
        "requires_freshness_check": update in {"MATERIAL_UPDATE", "REPOST"},
        "requires_requalification": update in {"MATERIAL_UPDATE", "REPOST"},
        "current": current,
        "previous": previous,
    }


def reconcile_discovery_batch(discovered: Iterable[dict[str, Any]], registry: dict[str, Any], *, observed_at: str | None = None) -> dict[str, Any]:
    """Reconcile a run and keep NEW counts free of previously known postings."""
    results: list[dict[str, Any]] = []
    working = {**registry, "entries": [dict(item) for item in registry.get("entries", [])]}
    for candidate in discovered:
        result = classify_discovered_opportunity(candidate, working, observed_at=observed_at)
        results.append(result)
        if result["classification"] == "NEW":
            working["entries"].append(result["current"])
    counts = {classification: sum(result["classification"] == classification for result in results) for classification in sorted(DISCOVERY_CLASSES)}
    return {
        "schema": "careeros.opportunity-discovery-reconciliation.v1",
        "schema_version": "1.0.0",
        "policy_version": OPPORTUNITY_REGISTRY_POLICY_VERSION,
        "registry_checked": True,
        "results": results,
        "counts": counts,
        "live_opportunities_discovered": counts["NEW"],
        "known_opportunities_reconfirmed": sum(counts[name] for name in DISCOVERY_CLASSES if name.startswith("KNOWN_")),
        "duplicate_packets_created": 0,
    }


def reconcile_workspace_discovery(workspace: Path, discovered: Iterable[dict[str, Any]], *, timestamp: str | None = None) -> dict[str, Any]:
    """Read the candidate's persistent state before classifying a discovery run."""
    roots = load_config(workspace / "careeros.yaml").roots
    registry = build_persistent_registry(roots.state_root, timestamp=timestamp)
    result = reconcile_discovery_batch(discovered, registry, observed_at=timestamp)
    result["registry_id"] = registry["registry_id"]
    result["registry_hash"] = registry["registry_hash"]
    result["previously_seen_opportunities"] = registry["opportunity_count"]
    return result
