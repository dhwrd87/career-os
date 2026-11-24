"""Prepare a review-only application packet; submission is intentionally absent."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config
from careeros.core.io import atomic_write_json, read_json, sha256_file
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import require_current_workspace, schema_dir, utc_now
from careeros.updates import mark_derivative_current, require_derivative_current


def prepare(workspace: Path, opportunity_id: str, build_id: str, *,
            freshness_override: dict[str, Any] | None = None,
            timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    qualification = read_json(roots.state_root / "qualifications" / f"{opportunity_id}.json")
    build_dir = roots.state_root / "resume-builds" / build_id
    artifact = read_json(build_dir / "artifact.json")
    validation = read_json(build_dir / "validation.json")
    snapshot = read_json(roots.state_root / "opportunities" / opportunity_id / "jd-snapshot.json")
    freshness = read_json(roots.state_root / "opportunities" / opportunity_id / "freshness.json")
    profile = read_json(roots.state_root / "profile" / "career-profile.json")
    from careeros.application_state import (
        application_prep_decision,
        evaluate_application_qa,
        initialize_application,
        reconcile_application_state,
    )
    freshness_gate = application_prep_decision(freshness, human_override=freshness_override)
    if freshness_gate["status"] != "PASS":
        raise PermissionError(
            f"application packet held: opportunity freshness is {freshness['freshness_state']}"
        )
    require_derivative_current(roots, "QUALIFICATION", qualification["qualification_id"])
    require_derivative_current(roots, "RESUME_BUILD", build_id)
    if qualification["decision"] != "QUALIFIED" or validation["status"] != "PASS" or artifact["status"] != "ACCEPTED":
        raise PermissionError("application packet requires qualified opportunity and accepted resume")
    created_at = utc_now(timestamp)
    packet_id = f"packet:{uuid.uuid5(uuid.NAMESPACE_URL, opportunity_id + ':' + build_id)}"
    application_id = f"application:{uuid.uuid5(uuid.NAMESPACE_URL, packet_id)}"
    packet_path = roots.state_root / "application-packets" / f"{packet_id.split(':', 1)[1]}.json"
    pdf_path = (roots.output_root / artifact['path']).resolve()
    if not pdf_path.is_relative_to(roots.output_root.resolve()) or not pdf_path.is_file() or sha256_file(pdf_path) != artifact['sha256']:
        raise PermissionError('application packet requires the unchanged validated resume artifact')
    if packet_path.exists():
        existing = read_json(packet_path)
        if existing['resume_sha256'] != artifact['sha256'] or existing['jd_snapshot']['content_hash'] != snapshot['content_hash']:
            raise PermissionError('existing packet lineage differs; prepare a new resume build')
        return existing
    packet = {
        "schema": "careeros.application-packet.v1", "schema_version": "1.0.0",
        "packet_id": packet_id, "application_id": application_id,
        "opportunity_id": opportunity_id, "qualification_id": qualification["qualification_id"],
        "resume_artifact_id": artifact["artifact_id"], "resume_sha256": artifact["sha256"],
        "jd_snapshot": snapshot, "opportunity_freshness": freshness,
        "cover_letter": None, "application_answers": None,
        "gate_summary": list(validation["gates"]),
        "human_review_state": "REVIEW_REQUIRED", "created_at": created_at,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:application-packet:v1", packet)
    state, event = initialize_application(
        state_root=roots.state_root,
        packet=packet,
        candidate_profile_id=profile["profile_id"],
        timestamp=created_at,
    )
    reconciliation = reconcile_application_state(state, [event])
    packet["gate_summary"].extend(evaluate_application_qa(
        freshness, state, [event], reconciliation, freshness_override=freshness_override,
    ))
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:application-packet:v1", packet)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "application-packets" / f"{packet['packet_id'].split(':', 1)[1]}.json", "state"), packet)
    mark_derivative_current(roots, "APPLICATION_PACKET", packet["packet_id"], timestamp=created_at)
    from careeros.experience import packet_view
    packet_view(workspace, packet, artifact)
    return packet
