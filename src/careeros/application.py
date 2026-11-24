"""Prepare a review-only application packet; submission is intentionally absent."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config
from careeros.core.io import atomic_write_json, read_json, sha256_file, sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import require_current_workspace, schema_dir, utc_now
from careeros.updates import mark_derivative_current, require_derivative_current



def prior_application(roots,opportunity_id):
    states=[read_json(p) for p in (roots.state_root/'applications').glob('*.json') if read_json(p)['opportunity_id']==opportunity_id]
    if len(states)>1:raise PermissionError('Several historical application records exist for this posting. Review them before preparing another package.')
    return states[0] if states else None


def history_blocks_preparation(state):
    return bool(state and (state.get('submitted_artifact_hashes') or state.get('current_state') not in {'PACKET_PREPARED','REVIEW_REQUESTED','APPROVED','SUBMISSION_PENDING'}))

def prepare(workspace: Path, opportunity_id: str, build_id: str, *,
            cover_letter_policy: str = "AUTO",
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
    from careeros.application_answers import load_bank, prepare_answers
    from careeros.application_documents import letter_decision, verify_packet
    from careeros.application_state import build_opportunity_freshness
    opportunity = read_json(roots.state_root / 'opportunities' / opportunity_id / 'opportunity.json')
    build=read_json(build_dir/'build.json')
    if build['opportunity_id']!=opportunity_id or build['jd_snapshot_hash']!=snapshot['content_hash']:
        raise PermissionError('The resume must belong to this exact job description. Rebuild it for the selected job.')
    if qualification.get('jd_snapshot_hash')!=snapshot['content_hash']:
        from careeros.opportunity import qualify
        qualification=qualify(workspace,opportunity_id,timestamp=timestamp)
    if build['profile_hash']!=sha256_value(profile) or qualification['profile_hash']!=build['profile_hash']:
        raise PermissionError('Career information has changed. Rebuild and validate this resume before preparing an application.')
    content=read_json(build_dir/'content.json')
    decision=letter_decision(opportunity,snapshot,content,cover_letter_policy)
    freshness=build_opportunity_freshness(opportunity,snapshot,timestamp=timestamp)
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
    signature=sha256_value(['complete-packet-v1',opportunity,snapshot['content_hash'],build_id,decision,load_bank(roots)])
    packet_id = f"packet:{uuid.uuid5(uuid.NAMESPACE_URL, signature)}"
    prior=prior_application(roots,opportunity_id)
    application_id = prior['application_id'] if prior else f"application:{uuid.uuid5(uuid.NAMESPACE_URL, opportunity_id + ':' + profile['profile_id'])}"
    packet_path = roots.state_root / "application-packets" / f"{packet_id.split(':', 1)[1]}.json"
    pdf_path = (roots.output_root / artifact['path']).resolve()
    if not pdf_path.is_relative_to(roots.output_root.resolve()) or not pdf_path.is_file() or sha256_file(pdf_path) != artifact['sha256']:
        raise PermissionError('application packet requires the unchanged validated resume artifact')
    if packet_path.exists():
        existing = read_json(packet_path)
        if existing['resume_sha256'] != artifact['sha256'] or existing['jd_snapshot']['content_hash'] != snapshot['content_hash']:
            raise PermissionError('existing packet lineage differs; prepare a new resume build')
        verify_packet(roots,existing)
        return existing
    if history_blocks_preparation(prior):raise PermissionError('This opportunity already has submitted or closed application history. Its documents are preserved; no duplicate application was prepared.')
    packet = {
        "schema": "careeros.application-packet.v1", "schema_version": "1.0.0",
        "packet_id": packet_id, "application_id": application_id,
        "opportunity_id": opportunity_id, "qualification_id": qualification["qualification_id"],
        "resume_artifact_id": artifact["artifact_id"], "resume_sha256": artifact["sha256"],
        "jd_snapshot": snapshot, "opportunity_freshness": freshness,
        "cover_letter": decision, "application_answers": prepare_answers(roots,opportunity,profile,content,cover_letter_available=decision["generate"],timestamp=timestamp),
        "build_id": build_id,
        "gate_summary": list(validation["gates"]),
        "human_review_state": "REVIEW_REQUIRED", "created_at": created_at,
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:application-packet:v1", packet)
    packet['document_manifest']='packets/'+packet_id.split(':')[-1]+'/manifest.json'
    packet['start_here']='packets/'+packet_id.split(':')[-1]+'/Start Here.html'
    packet['completion_state']='DRAFT_NEEDS_ANSWERS' if packet['application_answers']['material_questions'] or not opportunity.get('application_url') or packet['application_answers']['captured_question_state']!='CAPTURED' else 'DRAFTS_PREPARED'
    from careeros.experience import packet_view
    packet_view(workspace, packet, artifact)
    state_path=roots.state_root/'applications'/f"{application_id.split(':')[-1]}.json"
    if state_path.exists():
        from careeros.application_state import read_event_log
        state=read_json(state_path)
        if state['packet_id']!=packet_id:
            from careeros.application_state import make_application_event,record_application_event
            event=make_application_event(application_id,'PACKET_PREPARED',previous_state=state['current_state'],actor='CAREER_OS_LOCAL_RUNTIME',source='APPLICATION_PACKET',occurred_at=created_at,recorded_at=created_at,artifact_refs=[{'artifact_id':artifact['artifact_id'],'sha256':artifact['sha256']}],notes='Prepared a new local document revision: '+packet_id+'. Earlier documents are retained; review this draft again.',event_id='application-event:'+str(uuid.uuid5(uuid.NAMESPACE_URL,application_id+':revision:'+packet_id)))
            state=record_application_event(roots.state_root,{**state,'packet_id':packet_id,'resume_artifact_id':artifact['artifact_id'],'qualification_id':qualification['qualification_id']},event)
        events=read_event_log(roots.state_root/'application-events'/f"{application_id.split(':')[-1]}.jsonl")
    else:
        state, event = initialize_application(state_root=roots.state_root,packet=packet,candidate_profile_id=profile['profile_id'],timestamp=created_at)
        events=[event]
    reconciliation = reconcile_application_state(state, events)
    packet['gate_summary'].extend(evaluate_application_qa(freshness,state,events,reconciliation,freshness_override=freshness_override))
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:application-packet:v1", packet)
    atomic_write_json(roots.assert_write_allowed(roots.state_root / "application-packets" / f"{packet['packet_id'].split(':', 1)[1]}.json", "state"), packet)
    mark_derivative_current(roots, "APPLICATION_PACKET", packet["packet_id"], timestamp=created_at)
    return packet
