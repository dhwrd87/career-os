"""Fail-closed opportunity freshness and append-only application state.

This module is deliberately local-only.  It models preparation, human approval,
submission evidence, follow-up planning, interview state, and outcomes, but it
contains no network, messaging, calendar, or application-submission adapter.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlsplit, urlunsplit

from careeros.core.io import append_jsonl, atomic_write_json, sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir, utc_now


FRESHNESS_POLICY_VERSION = "opportunity-freshness-v1"
APPLICATION_STATE_POLICY_VERSION = "application-state-v1"
FRESHNESS_STATES = {
    "FRESH", "STALE_REVERIFY", "CLOSED", "EXPIRED", "REPOSTED",
    "SUPERSEDED", "SOURCE_UNAVAILABLE", "UNKNOWN",
}
PACKET_HOLD_STATES = FRESHNESS_STATES - {"FRESH"}
IDENTITY_CLASSES = {"SAME_POSTING", "REPOST", "NEW_ROLE", "AMBIGUOUS"}
OUTCOMES = {
    "UNKNOWN", "ACTIVE", "REJECTED", "WITHDRAWN", "OFFER_RECEIVED",
    "OFFER_ACCEPTED", "OFFER_DECLINED", "HIRED", "ROLE_CLOSED",
    "NO_RESPONSE_CLOSED",
}
EVENT_TYPES = {
    "PACKET_PREPARED", "REVIEW_REQUESTED", "APPROVED", "SUBMISSION_PENDING",
    "SUBMITTED", "FOLLOW_UP_DUE", "FOLLOW_UP_SENT", "EMPLOYER_RESPONSE",
    "INTERVIEW_INVITED", "INTERVIEW_SCHEDULED", "INTERVIEW_COMPLETED",
    "REJECTED", "WITHDRAWN", "OFFER_RECEIVED", "OFFER_ACCEPTED",
    "OFFER_DECLINED", "ROLE_CLOSED", "NO_RESPONSE_CLOSED", "CORRECTION",
    "SUPERSEDED",
}
TERMINAL_OUTCOMES = {
    "REJECTED", "WITHDRAWN", "OFFER_ACCEPTED", "OFFER_DECLINED", "HIRED",
    "ROLE_CLOSED", "NO_RESPONSE_CLOSED",
}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_url(value: Any) -> str | None:
    if not value:
        return None
    parsed = urlsplit(str(value).strip())
    if not parsed.netloc:
        return str(value).strip()
    retained: list[tuple[str, str]] = []
    query = parse_qs(parsed.query)
    for key in ("gh_jid", "job", "jobId", "jk", "pid", "req_id"):
        if query.get(key):
            retained.append((key, query[key][0]))
    rendered_query = "&".join(f"{key}={item}" for key, item in sorted(retained))
    path = re.sub(r"/(apply|application)/?$", "", parsed.path.rstrip("/"), flags=re.I)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, rendered_query, ""))


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")


def _provider_job_id(record: dict[str, Any]) -> str | None:
    for key in ("provider_job_id", "canonical_job_id", "requisition_id", "ATS_ID", "provider_id"):
        if record.get(key):
            return str(record[key]).strip().casefold()
    url = _normalized_url(record.get("canonical_url") or record.get("source_url"))
    if not url:
        return None
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    for key in ("gh_jid", "job", "jobId", "jk", "pid", "req_id"):
        if query.get(key):
            return query[key][0].casefold()
    return None


def _source_kind(record: dict[str, Any]) -> str:
    explicit = str(record.get("source_type") or "").upper()
    if explicit == "SYNTHETIC":
        return "SYNTHETIC"
    host = urlsplit(str(record.get("source_url") or record.get("canonical_url") or "")).netloc.casefold()
    if any(token in host for token in ("greenhouse", "lever.co", "ashbyhq", "workday", "icims", "smartrecruiters")):
        return "OFFICIAL_ATS"
    if host:
        return "EMPLOYER_OR_OTHER"
    return explicit or "UNKNOWN"


def default_freshness_policy() -> dict[str, Any]:
    """Return the portable, versioned freshness policy."""
    return {
        "policy_version": FRESHNESS_POLICY_VERSION,
        "reverify_after_hours": {
            "OFFICIAL_ATS": 72,
            "EMPLOYER_OR_OTHER": 72,
            "USER_SUPPLIED": 168,
            "UNKNOWN": 24,
        },
        "synthetic_fixture_is_fresh": True,
        "age_is_not_closure": True,
        "unknown_fails_closed": True,
        "conflict_fails_closed": True,
    }


def build_opportunity_freshness(
    opportunity: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    verification: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Assess posting freshness without inferring closure from age."""
    verification = verification or {}
    policy = policy or default_freshness_policy()
    now_text = utc_now(timestamp)
    now = _parse_time(now_text) or datetime.now(timezone.utc)
    source_kind = _source_kind({**opportunity, **verification})
    captured_at = snapshot["captured_at"]
    verified_at = verification.get("last_verified_at") or opportunity.get("last_verified_at")
    source_status = str(verification.get("source_status") or opportunity.get("source_status") or "UNKNOWN").upper()
    expiration_signal = verification.get("expiration_signal") or opportunity.get("expiration_signal")
    closure_signal = verification.get("closure_signal") or opportunity.get("closure_signal")
    supersedes = verification.get("supersedes") or opportunity.get("supersedes")
    repost_group_id = verification.get("repost_group_id") or opportunity.get("repost_group_id")
    conflicting = bool(verification.get("conflicting_sources"))

    expiry_time = _parse_time(expiration_signal)
    if source_kind == "SYNTHETIC" and policy.get("synthetic_fixture_is_fresh"):
        state, reason, confidence = "FRESH", "Synthetic fixture is current for deterministic package testing.", "HIGH"
        verified_at = verified_at or captured_at
        source_status = "OPEN"
    elif closure_signal or source_status in {"CLOSED", "FILLED", "REMOVED"}:
        state, reason, confidence = "CLOSED", "Explicit source evidence indicates the posting is closed.", "HIGH"
    elif expiry_time and expiry_time <= now:
        state, reason, confidence = "EXPIRED", "The posting's explicit close/expiration time has passed.", "HIGH"
    elif source_status == "REPOSTED":
        state, reason, confidence = "REPOSTED", "Source evidence identifies this record as a repost.", "HIGH"
    elif source_status == "SUPERSEDED" or supersedes:
        state, reason, confidence = "SUPERSEDED", "A newer posting explicitly supersedes this opportunity.", "HIGH"
    elif source_status in {"UNAVAILABLE", "ERROR", "NOT_FOUND"}:
        state, reason, confidence = "SOURCE_UNAVAILABLE", "The source could not be verified as available.", "MEDIUM"
    elif conflicting:
        state, reason, confidence = "UNKNOWN", "Available sources conflict; human resolution is required.", "LOW"
    elif source_status in {"OPEN", "ACTIVE"} and verified_at:
        verified_time = _parse_time(verified_at)
        maximum = policy["reverify_after_hours"].get(source_kind, policy["reverify_after_hours"]["UNKNOWN"])
        age_hours = (now - verified_time).total_seconds() / 3600 if verified_time else None
        if age_hours is not None and 0 <= age_hours <= maximum:
            state, reason, confidence = "FRESH", "Recent source verification confirms the posting is open.", str(verification.get("verification_confidence") or "HIGH").upper()
        else:
            state, reason, confidence = "STALE_REVERIFY", "Open verification is older than the policy threshold; age does not prove closure.", "MEDIUM"
    elif verified_at:
        state, reason, confidence = "UNKNOWN", "A verification timestamp exists without a resolved source status.", "LOW"
    else:
        state, reason, confidence = "UNKNOWN", "No current source verification establishes that the posting remains open.", "LOW"

    record = {
        "schema": "careeros.opportunity-freshness.v1",
        "schema_version": "1.0.0",
        "opportunity_id": opportunity["opportunity_id"],
        "source_url": opportunity.get("source_url") or opportunity.get("canonical_url"),
        "source_type": source_kind,
        "captured_at": captured_at,
        "last_verified_at": verified_at,
        "source_status": source_status,
        "freshness_state": state,
        "freshness_reason": reason,
        "job_posting_hash": snapshot["content_hash"],
        "jd_snapshot_id": snapshot["snapshot_id"],
        "supersedes": supersedes,
        "repost_group_id": repost_group_id,
        "expiration_signal": expiration_signal,
        "closure_signal": closure_signal,
        "verification_method": str(verification.get("verification_method") or ("FIXTURE" if source_kind == "SYNTHETIC" else "NOT_VERIFIED")),
        "verification_confidence": confidence,
        "policy_version": str(policy["policy_version"]),
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:opportunity-freshness:v1", record)
    return record


def application_prep_decision(freshness: dict[str, Any], *, human_override: dict[str, Any] | None = None) -> dict[str, Any]:
    override_valid = bool(
        human_override
        and human_override.get("human_confirmed") is True
        and str(human_override.get("reason") or "").strip()
        and str(human_override.get("actor") or "").strip()
    )
    allowed = freshness["freshness_state"] == "FRESH" or override_valid
    return {
        "gate": "OPPORTUNITY_FRESHNESS",
        "status": "PASS" if allowed else "FAIL",
        "freshness_state": freshness["freshness_state"],
        "human_override": human_override if override_valid else None,
        "action": "PREPARE_PACKET" if allowed else "HOLD_REVERIFY_RESOLVE",
    }


def classify_opportunity_identity(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Classify posting identity; ambiguous evidence is never auto-merged."""
    previous_provider_id = _provider_job_id(previous)
    current_provider_id = _provider_job_id(current)
    previous_url = _normalized_url(previous.get("canonical_url") or previous.get("source_url"))
    current_url = _normalized_url(current.get("canonical_url") or current.get("source_url"))
    same_employer = _slug(previous.get("employer_name") or previous.get("employer")) == _slug(current.get("employer_name") or current.get("employer"))
    same_title = _slug(previous.get("role_title") or previous.get("title")) == _slug(current.get("role_title") or current.get("title"))
    same_location = _slug(previous.get("location")) == _slug(current.get("location"))
    previous_text = str(previous.get("job_description") or previous.get("text") or "")
    current_text = str(current.get("job_description") or current.get("text") or "")
    similarity = round(SequenceMatcher(None, previous_text.casefold(), current_text.casefold()).ratio(), 3) if previous_text and current_text else None
    explicit_repost = bool(current.get("explicit_repost") or current.get("supersedes"))

    if previous_provider_id and current_provider_id and previous_provider_id == current_provider_id:
        classification, confidence, reason = "SAME_POSTING", "HIGH", "Provider job identifiers match."
    elif previous_url and current_url and previous_url == current_url:
        classification, confidence, reason = "SAME_POSTING", "HIGH", "Normalized canonical URLs match."
    elif not same_employer or not same_title:
        classification, confidence, reason = "NEW_ROLE", "HIGH", "Employer or normalized title differs."
    elif explicit_repost and (similarity is None or similarity >= 0.6):
        classification, confidence, reason = "REPOST", "HIGH", "Explicit repost/supersession evidence exists for a materially similar role."
    elif previous_provider_id and current_provider_id and previous_provider_id != current_provider_id and similarity is not None and similarity >= 0.8:
        classification, confidence, reason = "REPOST", "MEDIUM", "A new provider identifier carries a highly similar JD for the same employer/title."
    elif same_employer and same_title and same_location and similarity is not None and similarity < 0.45:
        classification, confidence, reason = "NEW_ROLE", "MEDIUM", "Same title/location has materially different role content."
    else:
        classification, confidence, reason = "AMBIGUOUS", "LOW", "Available identifiers do not safely prove same-posting, repost, or new-role identity."
    return {
        "classification": classification,
        "confidence": confidence,
        "reason": reason,
        "previous_opportunity_id": previous.get("opportunity_id"),
        "current_opportunity_id": current.get("opportunity_id"),
        "provider_id_match": bool(previous_provider_id and previous_provider_id == current_provider_id),
        "canonical_url_match": bool(previous_url and previous_url == current_url),
        "jd_similarity": similarity,
        "auto_merge_allowed": classification == "SAME_POSTING",
    }


def link_repost(previous: dict[str, Any], current: dict[str, Any], identity: dict[str, Any] | None = None) -> dict[str, Any]:
    identity = identity or classify_opportunity_identity(previous, current)
    if identity["classification"] == "AMBIGUOUS":
        raise PermissionError("ambiguous opportunity identity requires human review")
    if identity["classification"] != "REPOST":
        raise ValueError("opportunities are not classified as a repost")
    linked = dict(current)
    linked["supersedes"] = previous["opportunity_id"]
    linked["repost_group_id"] = previous.get("repost_group_id") or f"repost:{uuid.uuid5(uuid.NAMESPACE_URL, previous['opportunity_id'])}"
    return linked


def _resulting_state(event_type: str, previous_state: str | None, correction_state: str | None = None) -> str:
    if event_type == "CORRECTION":
        if not correction_state:
            raise ValueError("CORRECTION requires correction_state")
        return correction_state
    if event_type in {"FOLLOW_UP_DUE", "FOLLOW_UP_SENT", "EMPLOYER_RESPONSE", "INTERVIEW_INVITED", "INTERVIEW_SCHEDULED", "INTERVIEW_COMPLETED"}:
        return event_type
    return event_type


def make_application_event(
    application_id: str,
    event_type: str,
    *,
    previous_state: str | None,
    actor: str,
    source: str,
    occurred_at: str | None = None,
    recorded_at: str | None = None,
    evidence_refs: Iterable[str] = (),
    artifact_refs: Iterable[dict[str, Any]] = (),
    external_ref: str | None = None,
    notes: str | None = None,
    supersedes_event_id: str | None = None,
    human_confirmed: bool = False,
    correction_state: str | None = None,
    submission_lineage: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported application event: {event_type}")
    recorded = utc_now(recorded_at)
    resulting = _resulting_state(event_type, previous_state, correction_state)
    if event_type == "CORRECTION" and (not supersedes_event_id or not human_confirmed):
        raise PermissionError("corrections require a superseded event and human confirmation")
    material = f"{application_id}:{event_type}:{occurred_at}:{recorded}:{previous_state}:{resulting}:{supersedes_event_id}"
    event = {
        "schema": "careeros.application-event.v1",
        "schema_version": "1.0.0",
        "event_id": event_id or f"application-event:{uuid.uuid5(uuid.NAMESPACE_URL, material)}",
        "application_id": application_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "recorded_at": recorded,
        "actor": actor,
        "source": source,
        "evidence_refs": sorted(set(evidence_refs)),
        "artifact_refs": list(artifact_refs),
        "external_ref": external_ref,
        "previous_state": previous_state,
        "resulting_state": resulting,
        "notes": notes,
        "supersedes_event_id": supersedes_event_id,
        "human_confirmed": human_confirmed,
        "submission_lineage": submission_lineage,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:application-event:v1", event)
    return event


def _outcome_for_event(event_type: str, previous: str) -> str:
    return {
        "SUBMITTED": "ACTIVE",
        "EMPLOYER_RESPONSE": "ACTIVE",
        "INTERVIEW_INVITED": "ACTIVE",
        "INTERVIEW_SCHEDULED": "ACTIVE",
        "INTERVIEW_COMPLETED": "ACTIVE",
        "REJECTED": "REJECTED",
        "WITHDRAWN": "WITHDRAWN",
        "OFFER_RECEIVED": "OFFER_RECEIVED",
        "OFFER_ACCEPTED": "OFFER_ACCEPTED",
        "OFFER_DECLINED": "OFFER_DECLINED",
        "ROLE_CLOSED": "ROLE_CLOSED",
        "NO_RESPONSE_CLOSED": "NO_RESPONSE_CLOSED",
    }.get(event_type, previous)


def validate_event_log(events: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    known: set[str] = set()
    state: str | None = None
    submitted_lineage: dict[str, Any] | None = None
    for index, event in enumerate(events):
        event_id = event.get("event_id")
        if event_id in known:
            findings.append({"gate": "APPLICATION_EVENT_INTEGRITY", "status": "FAIL", "detail": f"duplicate event_id at {index}"})
        if event.get("previous_state") != state:
            findings.append({"gate": "APPLICATION_EVENT_INTEGRITY", "status": "FAIL", "detail": f"previous_state contradiction at {event_id}"})
        if event.get("event_type") == "CORRECTION" and event.get("supersedes_event_id") not in known:
            findings.append({"gate": "APPLICATION_EVENT_INTEGRITY", "status": "FAIL", "detail": f"correction target missing at {event_id}"})
        if event.get("event_type") == "SUBMITTED":
            lineage = event.get("submission_lineage") or {}
            hashes = lineage.get("submitted_artifact_hashes") or []
            required = [lineage.get("resume_artifact_id"), lineage.get("resume_sha256"), lineage.get("job_snapshot_hash"), event.get("occurred_at")]
            if not event.get("human_confirmed") or not hashes or not all(required):
                findings.append({"gate": "SUBMISSION_ARTIFACT_HASH", "status": "FAIL", "detail": "submitted event lacks human confirmation or immutable artifact/JD hashes"})
            elif submitted_lineage is None:
                submitted_lineage = json.loads(json.dumps(lineage))
            elif submitted_lineage != lineage:
                findings.append({"gate": "IMMUTABILITY", "status": "FAIL", "detail": "submitted lineage changed after submission"})
        known.add(str(event_id))
        state = event.get("resulting_state")
    if not any(item["gate"] == "APPLICATION_EVENT_INTEGRITY" for item in findings):
        findings.append({"gate": "APPLICATION_EVENT_INTEGRITY", "status": "PASS", "detail": "append-only sequence is internally consistent"})
    if not any(item["gate"] == "SUBMISSION_ARTIFACT_HASH" for item in findings):
        findings.append({"gate": "SUBMISSION_ARTIFACT_HASH", "status": "PASS", "detail": "submitted lineage is complete or no submission exists"})
    if not any(item["gate"] == "IMMUTABILITY" for item in findings):
        findings.append({"gate": "IMMUTABILITY", "status": "PASS", "detail": "historical submission lineage is unchanged"})
    return {"status": "PASS" if all(item["status"] == "PASS" for item in findings) else "FAIL", "findings": findings}


def derive_application_state(
    *,
    application_id: str,
    opportunity_id: str,
    candidate_profile_id: str,
    qualification_id: str,
    resume_artifact_id: str,
    packet_id: str,
    events: list[dict[str, Any]],
    policy_version: str = APPLICATION_STATE_POLICY_VERSION,
) -> dict[str, Any]:
    if not events:
        raise ValueError("application state requires at least one event")
    integrity = validate_event_log(events)
    outcome = "UNKNOWN"
    submitted_hashes: list[str] = []
    external_reference: str | None = None
    human_confirmed = False
    closure_reason: str | None = None
    for event in events:
        outcome_event = event["resulting_state"] if event["event_type"] == "CORRECTION" else event["event_type"]
        outcome = _outcome_for_event(outcome_event, outcome)
        if event["event_type"] == "SUBMITTED":
            submitted_hashes = list((event.get("submission_lineage") or {}).get("submitted_artifact_hashes") or [])
        if event.get("external_ref"):
            external_reference = event["external_ref"]
        human_confirmed = human_confirmed or bool(event.get("human_confirmed"))
        if outcome_event in TERMINAL_OUTCOMES:
            closure_reason = event.get("notes") or event["event_type"]
    state = {
        "schema": "careeros.application-state.v1",
        "schema_version": "1.0.0",
        "application_id": application_id,
        "opportunity_id": opportunity_id,
        "candidate_profile_id": candidate_profile_id,
        "current_state": events[-1]["resulting_state"],
        "qualification_id": qualification_id,
        "resume_artifact_id": resume_artifact_id,
        "packet_id": packet_id,
        "submitted_artifact_hashes": submitted_hashes,
        "created_at": events[0]["recorded_at"],
        "updated_at": events[-1]["recorded_at"],
        "last_event_id": events[-1]["event_id"],
        "outcome": outcome,
        "closure_reason": closure_reason,
        "external_reference": external_reference,
        "human_confirmed": human_confirmed,
        "policy_version": policy_version,
        "integrity_state": integrity["status"],
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:application-state:v1", state)
    return state


def read_event_log(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_event(path: Path, event: dict[str, Any]) -> list[dict[str, Any]]:
    """Append one event only after validating the resulting immutable sequence."""
    events = read_event_log(path)
    if any(item["event_id"] == event["event_id"] for item in events):
        raise PermissionError("event_id already exists; application events are append-only")
    candidate = [*events, event]
    integrity = validate_event_log(candidate)
    if integrity["status"] != "PASS":
        raise PermissionError(f"application event rejected: {integrity['findings']}")
    append_jsonl(path, event)
    return candidate


def initialize_application(
    *,
    state_root: Path,
    packet: dict[str, Any],
    candidate_profile_id: str,
    timestamp: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    application_id = packet["application_id"]
    log_path = state_root / "application-events" / f"{application_id.split(':', 1)[-1]}.jsonl"
    existing = read_event_log(log_path)
    if existing:
        raise PermissionError("application already initialized; append an event instead")
    event = make_application_event(
        application_id,
        "PACKET_PREPARED",
        previous_state=None,
        actor="CAREER_OS_LOCAL_RUNTIME",
        source="APPLICATION_PACKET",
        occurred_at=timestamp,
        recorded_at=timestamp,
        artifact_refs=[{"artifact_id": packet["resume_artifact_id"], "sha256": packet["resume_sha256"]}],
        notes="Local application packet prepared; no external submission performed.",
    )
    events = append_event(log_path, event)
    state = derive_application_state(
        application_id=application_id,
        opportunity_id=packet["opportunity_id"],
        candidate_profile_id=candidate_profile_id,
        qualification_id=packet["qualification_id"],
        resume_artifact_id=packet["resume_artifact_id"],
        packet_id=packet["packet_id"],
        events=events,
    )
    atomic_write_json(state_root / "applications" / f"{application_id.split(':', 1)[-1]}.json", state)
    return state, event


def record_application_event(state_root: Path, state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Append an event and atomically replace only the derived state projection."""
    if event["application_id"] != state["application_id"]:
        raise ValueError("event application_id does not match state")
    log_path = state_root / "application-events" / f"{state['application_id'].split(':', 1)[-1]}.jsonl"
    events = append_event(log_path, event)
    projected = derive_application_state(
        application_id=state["application_id"], opportunity_id=state["opportunity_id"],
        candidate_profile_id=state["candidate_profile_id"], qualification_id=state["qualification_id"],
        resume_artifact_id=state["resume_artifact_id"], packet_id=state["packet_id"], events=events,
        policy_version=state["policy_version"],
    )
    atomic_write_json(state_root / "applications" / f"{state['application_id'].split(':', 1)[-1]}.json", projected)
    return projected


def build_submission_event(
    state: dict[str, Any],
    *,
    resume_sha256: str,
    job_snapshot_hash: str,
    cover_letter_hash: str | None = None,
    application_answer_hashes: Iterable[str] = (),
    external_ref: str | None = None,
    actor: str,
    occurred_at: str,
) -> dict[str, Any]:
    answer_hashes = list(application_answer_hashes)
    hashes = [resume_sha256, *answer_hashes]
    if cover_letter_hash:
        hashes.append(cover_letter_hash)
    lineage = {
        "resume_artifact_id": state["resume_artifact_id"],
        "resume_sha256": resume_sha256,
        "cover_letter_hash": cover_letter_hash,
        "application_answer_hashes": answer_hashes,
        "job_snapshot_hash": job_snapshot_hash,
        "submitted_artifact_hashes": hashes,
        "submission_timestamp": occurred_at,
        "external_reference": external_ref,
    }
    return make_application_event(
        state["application_id"],
        "SUBMITTED",
        previous_state=state["current_state"],
        actor=actor,
        source="HUMAN_CONFIRMED_EXTERNAL_SUBMISSION",
        occurred_at=occurred_at,
        recorded_at=occurred_at,
        artifact_refs=[{"artifact_id": state["resume_artifact_id"], "sha256": resume_sha256}],
        external_ref=external_ref,
        notes="Human-confirmed external submission recorded locally.",
        human_confirmed=True,
        submission_lineage=lineage,
    )


def build_follow_up(
    application_id: str,
    *,
    due_at: str,
    channel: str,
    draft_artifact: str | None = None,
    approval_state: str = "REVIEW_REQUIRED",
) -> dict[str, Any]:
    record = {
        "schema": "careeros.follow-up.v1", "schema_version": "1.0.0",
        "application_id": application_id, "due_at": due_at, "channel": channel,
        "draft_artifact": draft_artifact, "approval_state": approval_state,
        "sent_at": None, "external_ref": None, "disposition": "PLANNED",
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:follow-up:v1", record)
    return record


def build_interview(
    application_id: str,
    *,
    stage: str,
    scheduled_at: str | None = None,
    format: str | None = None,
    participants: Iterable[str] = (),
    prep_artifact: str | None = None,
) -> dict[str, Any]:
    record = {
        "schema": "careeros.interview.v1", "schema_version": "1.0.0",
        "application_id": application_id, "stage": stage, "scheduled_at": scheduled_at,
        "format": format, "participants": list(participants), "prep_artifact": prep_artifact,
        "result": "PENDING", "next_action": "HUMAN_REVIEW",
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:interview:v1", record)
    return record


def reconcile_application_state(
    state: dict[str, Any] | None,
    events: list[dict[str, Any]],
    *,
    opportunity_index_state: str | None = None,
    legacy_state: str | None = None,
    outcome_registry_state: str | None = None,
    artifact_manifest_hashes: Iterable[str] = (),
) -> dict[str, Any]:
    sources = {
        "event_log": events[-1]["resulting_state"] if events else None,
        "application_state": state.get("current_state") if state else None,
        "opportunity_index": opportunity_index_state,
        "legacy_run_folder": legacy_state,
        "outcome_registry": outcome_registry_state,
    }
    nonempty = {value for value in sources.values() if value}
    event_integrity = validate_event_log(events) if events else {"status": "FAIL", "findings": []}
    submitted_hashes = set(state.get("submitted_artifact_hashes", [])) if state else set()
    manifest_hashes = set(artifact_manifest_hashes)
    missing_hashes = sorted(submitted_hashes - manifest_hashes) if manifest_hashes else []
    if not events and any(value for key, value in sources.items() if key != "event_log"):
        status = "LEGACY_ONLY"
    elif event_integrity["status"] != "PASS" or (len(nonempty) > 1 and state and sources["event_log"] != sources["application_state"]) or missing_hashes:
        status = "RECONCILIATION_REQUIRED"
    elif events and any(value and value != sources["event_log"] for key, value in sources.items() if key not in {"event_log", "application_state"}):
        status = "RECONCILIATION_REQUIRED"
    elif events and any(value for key, value in sources.items() if key not in {"event_log", "application_state"}):
        status = "EVENT_LOG_AUTHORITATIVE"
    else:
        status = "CONSISTENT"
    record = {
        "schema": "careeros.application-state-reconciliation.v1",
        "schema_version": "1.0.0",
        "application_id": (state or {}).get("application_id") or (events[0]["application_id"] if events else "legacy-unresolved"),
        "status": status,
        "sources": sources,
        "conflicts": [] if len(nonempty) <= 1 else sorted(nonempty),
        "missing_artifact_hashes": missing_hashes,
        "event_log_authoritative": bool(events and event_integrity["status"] == "PASS"),
        "human_review_required": status in {"RECONCILIATION_REQUIRED", "LEGACY_ONLY"},
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:application-state-reconciliation:v1", record)
    return record


def evaluate_application_qa(
    freshness: dict[str, Any],
    state: dict[str, Any],
    events: list[dict[str, Any]],
    reconciliation: dict[str, Any],
    *,
    identity: dict[str, Any] | None = None,
    freshness_override: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return the eight composable, fail-closed application gates."""
    integrity = validate_event_log(events)
    integrity_by_gate = {item["gate"]: item for item in integrity["findings"]}
    freshness_decision = application_prep_decision(freshness, human_override=freshness_override)
    freshness_pass = freshness_decision["status"] == "PASS"
    identity_pass = identity is None or identity["classification"] != "AMBIGUOUS"
    repost_pass = identity is None or identity["classification"] != "REPOST" or bool(identity.get("supersedes_resolved"))
    derived = derive_application_state(
        application_id=state["application_id"], opportunity_id=state["opportunity_id"],
        candidate_profile_id=state["candidate_profile_id"], qualification_id=state["qualification_id"],
        resume_artifact_id=state["resume_artifact_id"], packet_id=state["packet_id"], events=events,
        policy_version=state["policy_version"],
    )
    outcome_pass = derived["outcome"] == state["outcome"]
    reconciliation_pass = reconciliation["status"] in {"CONSISTENT", "EVENT_LOG_AUTHORITATIVE"}
    return [
        {"gate": "OPPORTUNITY_FRESHNESS", "status": "PASS" if freshness_pass else "FAIL", "detail": freshness["freshness_state"], "human_override": freshness_decision["human_override"]},
        {"gate": "OPPORTUNITY_IDENTITY", "status": "PASS" if identity_pass else "FAIL", "detail": (identity or {}).get("classification", "SINGLE_RECORD")},
        {"gate": "REPOST_RESOLUTION", "status": "PASS" if repost_pass else "FAIL", "detail": "RESOLVED_OR_NOT_APPLICABLE" if repost_pass else "REPOST_LINK_REQUIRED"},
        integrity_by_gate.get("APPLICATION_EVENT_INTEGRITY", {"gate": "APPLICATION_EVENT_INTEGRITY", "status": "FAIL", "detail": "missing integrity result"}),
        integrity_by_gate.get("SUBMISSION_ARTIFACT_HASH", {"gate": "SUBMISSION_ARTIFACT_HASH", "status": "FAIL", "detail": "missing hash result"}),
        {"gate": "STATE_RECONCILIATION", "status": "PASS" if reconciliation_pass else "FAIL", "detail": reconciliation["status"]},
        {"gate": "OUTCOME_CONSISTENCY", "status": "PASS" if outcome_pass else "FAIL", "detail": state["outcome"]},
        integrity_by_gate.get("IMMUTABILITY", {"gate": "IMMUTABILITY", "status": "FAIL", "detail": "missing immutability result"}),
    ]


def migrate_legacy_state(
    legacy: dict[str, Any],
    *,
    application_id: str,
    recorded_at: str,
) -> dict[str, Any]:
    """Create, but do not persist, provenance-marked seed events."""
    state = str(legacy.get("current_state") or legacy.get("application_state") or legacy.get("status") or "UNKNOWN").upper()
    mapping = {
        "PREPARED": "PACKET_PREPARED", "READY_TO_REVIEW": "REVIEW_REQUESTED",
        "APPROVED": "APPROVED", "SUBMITTED": "SUBMITTED", "REJECTED": "REJECTED",
        "WITHDRAWN": "WITHDRAWN", "OFFER": "OFFER_RECEIVED", "OFFER_RECEIVED": "OFFER_RECEIVED",
        "OFFER_ACCEPTED": "OFFER_ACCEPTED", "OFFER_DECLINED": "OFFER_DECLINED",
        "ROLE_CLOSED": "ROLE_CLOSED", "NO_RESPONSE_CLOSED": "NO_RESPONSE_CLOSED",
    }
    event_type = mapping.get(state)
    if event_type is None:
        return {"status": "RECONCILIATION_REQUIRED", "events": [], "reason": f"unsupported legacy state: {state}"}
    submission_lineage = None
    artifact_refs: list[dict[str, Any]] = []
    complete = True
    if event_type == "SUBMITTED":
        resume_hash = legacy.get("resume_sha256")
        snapshot_hash = legacy.get("job_snapshot_hash") or legacy.get("jd_sha256")
        complete = bool(resume_hash and snapshot_hash and legacy.get("resume_artifact_id"))
        submission_lineage = {
            "resume_artifact_id": legacy.get("resume_artifact_id"),
            "resume_sha256": resume_hash,
            "cover_letter_hash": legacy.get("cover_letter_hash"),
            "application_answer_hashes": legacy.get("application_answer_hashes", []),
            "job_snapshot_hash": snapshot_hash,
            "submitted_artifact_hashes": [item for item in [resume_hash, legacy.get("cover_letter_hash"), *legacy.get("application_answer_hashes", [])] if item],
            "submission_timestamp": legacy.get("submitted_at"),
            "external_reference": legacy.get("external_reference"),
        }
        if resume_hash:
            artifact_refs = [{"artifact_id": legacy.get("resume_artifact_id"), "sha256": resume_hash}]
    event = make_application_event(
        application_id, event_type, previous_state=None, actor="LEGACY_MIGRATION",
        source="MIGRATED_LEGACY_STATE", occurred_at=legacy.get("occurred_at") or legacy.get("submitted_at"),
        recorded_at=recorded_at, evidence_refs=[str(legacy.get("source_ref") or "legacy-state")],
        artifact_refs=artifact_refs, external_ref=legacy.get("external_reference"),
        notes="Seeded from trusted legacy state; source provenance retained.",
        human_confirmed=bool(legacy.get("human_confirmed")), submission_lineage=submission_lineage,
    )
    return {
        "status": "READY" if complete else "RECONCILIATION_REQUIRED",
        "events": [event],
        "reason": None if complete else "legacy submission lacks complete immutable artifact/JD lineage",
        "provenance": "MIGRATED_LEGACY_STATE",
    }
