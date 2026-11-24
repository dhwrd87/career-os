from __future__ import annotations

import copy
import unittest

from careeros.application_state import (
    application_prep_decision,
    build_follow_up,
    build_interview,
    build_opportunity_freshness,
    build_submission_event,
    classify_opportunity_identity,
    derive_application_state,
    evaluate_application_qa,
    make_application_event,
    migrate_legacy_state,
    reconcile_application_state,
    validate_event_log,
)
from careeros.core.io import sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir


NOW = "2026-10-11T12:00:00Z"
HASH_A = "a" * 64
HASH_B = "b" * 64


def opportunity(**updates):
    record = {
        "opportunity_id": "opp-fictional-1",
        "employer_name": "Example Harbor Cooperative",
        "role_title": "Implementation Coordinator",
        "location": "Remote",
        "source_type": "USER_SUPPLIED",
        "source_url": "https://jobs.example.invalid/roles/101",
        "canonical_url": "https://jobs.example.invalid/roles/101",
        "provider_job_id": "101",
    }
    record.update(updates)
    return record


def snapshot(**updates):
    text = updates.pop("text", "Coordinate implementation intake, documentation, and customer handoffs.")
    record = {
        "snapshot_id": "jd:fictional-1",
        "opportunity_id": "opp-fictional-1",
        "captured_at": "2026-10-11T10:00:00Z",
        "content_hash": sha256_value(text),
        "text": text,
    }
    record.update(updates)
    return record


def initial_event(application_id="application:fictional"):
    return make_application_event(
        application_id,
        "PACKET_PREPARED",
        previous_state=None,
        actor="CAREER_OS_LOCAL_RUNTIME",
        source="SYNTHETIC_TEST",
        occurred_at=NOW,
        recorded_at=NOW,
        artifact_refs=[{"artifact_id": "resume:fictional", "sha256": HASH_A}],
    )


def state_for(events):
    return derive_application_state(
        application_id="application:fictional",
        opportunity_id="opp-fictional-1",
        candidate_profile_id="profile:fictional",
        qualification_id="qualification:fictional",
        resume_artifact_id="resume:fictional",
        packet_id="packet:fictional",
        events=events,
    )


class OpportunityApplicationStateParityTests(unittest.TestCase):
    def test_01_fresh_posting_allows_packet(self):
        freshness = build_opportunity_freshness(
            opportunity(), snapshot(),
            verification={"source_status": "OPEN", "last_verified_at": "2026-10-11T11:00:00Z", "verification_method": "OFFICIAL_ATS"},
            timestamp=NOW,
        )
        self.assertEqual(freshness["freshness_state"], "FRESH")
        self.assertEqual(application_prep_decision(freshness)["status"], "PASS")

    def test_02_stale_posting_requires_reverification(self):
        freshness = build_opportunity_freshness(
            opportunity(), snapshot(),
            verification={"source_status": "OPEN", "last_verified_at": "2026-10-01T00:00:00Z", "verification_method": "OFFICIAL_ATS"},
            timestamp=NOW,
        )
        self.assertEqual(freshness["freshness_state"], "STALE_REVERIFY")
        self.assertEqual(application_prep_decision(freshness)["action"], "HOLD_REVERIFY_RESOLVE")
        override = {"human_confirmed": True, "actor": "fixture-human", "reason": "Current posting reviewed manually."}
        self.assertEqual(application_prep_decision(freshness, human_override=override)["status"], "PASS")

    def test_03_closed_posting_blocks_packet(self):
        freshness = build_opportunity_freshness(
            opportunity(), snapshot(),
            verification={"source_status": "CLOSED", "last_verified_at": NOW, "closure_signal": "ATS says role filled"},
            timestamp=NOW,
        )
        self.assertEqual(freshness["freshness_state"], "CLOSED")
        self.assertEqual(application_prep_decision(freshness)["status"], "FAIL")

    def test_04_repost_detected_and_kept_distinct(self):
        old = opportunity(job_description=snapshot()["text"])
        new = opportunity(
            opportunity_id="opp-fictional-2", provider_job_id="202",
            canonical_url="https://jobs.example.invalid/roles/202",
            source_url="https://jobs.example.invalid/roles/202", explicit_repost=True,
            supersedes="opp-fictional-1", job_description=snapshot()["text"] + " Own weekly status reporting.",
        )
        identity = classify_opportunity_identity(old, new)
        self.assertEqual(identity["classification"], "REPOST")
        self.assertFalse(identity["auto_merge_allowed"])

    def test_05_ambiguous_repost_fails_closed(self):
        old = opportunity(provider_job_id=None, source_url=None, canonical_url=None)
        new = opportunity(opportunity_id="opp-fictional-2", provider_job_id=None, source_url=None, canonical_url=None)
        identity = classify_opportunity_identity(old, new)
        self.assertEqual(identity["classification"], "AMBIGUOUS")
        self.assertFalse(identity["auto_merge_allowed"])

    def test_06_submission_freezes_complete_artifact_lineage(self):
        first = initial_event()
        state = state_for([first])
        submitted = build_submission_event(
            state, resume_sha256=HASH_A, job_snapshot_hash=HASH_B,
            application_answer_hashes=["c" * 64], external_ref="external:fictional",
            actor="fixture-human", occurred_at="2026-10-11T13:00:00Z",
        )
        events = [first, submitted]
        submitted_state = state_for(events)
        self.assertEqual(validate_event_log(events)["status"], "PASS")
        self.assertEqual(submitted_state["outcome"], "ACTIVE")
        self.assertEqual(submitted_state["submitted_artifact_hashes"], [HASH_A, "c" * 64])
        freshness = build_opportunity_freshness(
            opportunity(source_type="SYNTHETIC"), snapshot(), timestamp=NOW,
        )
        reconciliation = reconcile_application_state(
            submitted_state, events, artifact_manifest_hashes=[HASH_A, "c" * 64],
        )
        gates = evaluate_application_qa(freshness, submitted_state, events, reconciliation)
        self.assertEqual(
            {item["gate"] for item in gates},
            {"OPPORTUNITY_FRESHNESS", "OPPORTUNITY_IDENTITY", "REPOST_RESOLUTION",
             "APPLICATION_EVENT_INTEGRITY", "SUBMISSION_ARTIFACT_HASH",
             "STATE_RECONCILIATION", "OUTCOME_CONSISTENCY", "IMMUTABILITY"},
        )
        self.assertTrue(all(item["status"] == "PASS" for item in gates), gates)

    def test_07_post_submit_resume_rebuild_does_not_rewrite_history(self):
        first = initial_event()
        state = state_for([first])
        submitted = build_submission_event(
            state, resume_sha256=HASH_A, job_snapshot_hash=HASH_B,
            actor="fixture-human", occurred_at="2026-10-11T13:00:00Z",
        )
        frozen_events = copy.deepcopy([first, submitted])
        rebuilt_resume = {"artifact_id": "resume:new", "sha256": "d" * 64}
        self.assertNotEqual(rebuilt_resume["sha256"], frozen_events[1]["submission_lineage"]["resume_sha256"])
        self.assertEqual(state_for(frozen_events)["resume_artifact_id"], "resume:fictional")
        self.assertEqual(frozen_events, [first, submitted])

    def test_08_rejection_is_event_derived_terminal_outcome(self):
        first = initial_event()
        rejected = make_application_event(
            "application:fictional", "REJECTED", previous_state="PACKET_PREPARED",
            actor="fixture-human", source="EMPLOYER_NOTICE", occurred_at=NOW,
            recorded_at=NOW, human_confirmed=True, notes="Synthetic rejection notice.",
        )
        state = state_for([first, rejected])
        self.assertEqual(state["outcome"], "REJECTED")
        self.assertEqual(state["closure_reason"], "Synthetic rejection notice.")

    def test_09_offer_event_is_nonfabricating_outcome(self):
        first = initial_event()
        offer = make_application_event(
            "application:fictional", "OFFER_RECEIVED", previous_state="PACKET_PREPARED",
            actor="fixture-human", source="EMPLOYER_NOTICE", occurred_at=NOW,
            recorded_at=NOW, human_confirmed=True, evidence_refs=["fixture://offer-notice"],
        )
        self.assertEqual(state_for([first, offer])["outcome"], "OFFER_RECEIVED")

    def test_10_legacy_state_migration_preserves_provenance(self):
        migrated = migrate_legacy_state(
            {
                "status": "SUBMITTED", "submitted_at": "2026-10-10T12:00:00Z",
                "resume_artifact_id": "resume:fictional", "resume_sha256": HASH_A,
                "job_snapshot_hash": HASH_B, "human_confirmed": True,
                "source_ref": "fixture://legacy/application-1",
            },
            application_id="application:fictional", recorded_at=NOW,
        )
        self.assertEqual(migrated["status"], "READY")
        self.assertEqual(migrated["provenance"], "MIGRATED_LEGACY_STATE")
        self.assertEqual(validate_event_log(migrated["events"])["status"], "PASS")

    def test_11_conflicting_state_requires_reconciliation(self):
        first = initial_event()
        state = state_for([first])
        reconciliation = reconcile_application_state(
            state, [first], opportunity_index_state="SUBMITTED", legacy_state="PACKET_PREPARED",
        )
        self.assertEqual(reconciliation["status"], "RECONCILIATION_REQUIRED")
        self.assertTrue(reconciliation["human_review_required"])

    def test_12_no_response_closure_is_terminal_event(self):
        first = initial_event()
        closed = make_application_event(
            "application:fictional", "NO_RESPONSE_CLOSED", previous_state="PACKET_PREPARED",
            actor="fixture-human", source="HUMAN_REVIEW", occurred_at=NOW,
            recorded_at=NOW, human_confirmed=True, notes="Closed after the configured follow-up window.",
        )
        state = state_for([first, closed])
        self.assertEqual(state["outcome"], "NO_RESPONSE_CLOSED")

    def test_contracts_follow_up_and_interview_are_local_only(self):
        registry = SchemaRegistry(schema_dir())
        for schema_id in (
            "urn:careeros:schema:opportunity-freshness:v1",
            "urn:careeros:schema:application-state:v1",
            "urn:careeros:schema:application-event:v1",
            "urn:careeros:schema:application-state-reconciliation:v1",
            "urn:careeros:schema:follow-up:v1",
            "urn:careeros:schema:interview:v1",
        ):
            self.assertIn(schema_id, registry.by_id)
        follow_up = build_follow_up(
            "application:fictional", due_at="2026-10-20T12:00:00Z", channel="EMAIL",
        )
        interview = build_interview("application:fictional", stage="RECRUITER_SCREEN")
        self.assertEqual(follow_up["approval_state"], "REVIEW_REQUIRED")
        self.assertEqual(interview["next_action"], "HUMAN_REVIEW")


if __name__ == "__main__":
    unittest.main()
