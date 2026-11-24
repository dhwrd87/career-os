from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from careeros.opportunity_registry import (
    build_persistent_registry,
    classify_discovered_opportunity,
    normalize_opportunity,
    reconcile_discovery_batch,
)


NOW = "2026-10-12T18:00:00Z"
BASE_TEXT = "Monitor service alerts, document incidents, troubleshoot connectivity, and escalate unresolved events."


def opportunity(**overrides):
    value = {
        "opportunity_id": "opportunity:fictional-100",
        "employer": "Fictional Northstar Cooperative",
        "title": "Operations Monitoring Technician",
        "location": "Example City, Texas",
        "source": "Fictional employer ATS",
        "source_url": "https://jobs.example.invalid/jobs/100",
        "provider_job_id": "REQ-100",
        "job_description": BASE_TEXT,
        "captured_at": NOW,
        "freshness_state": "FRESH",
        "qualification": "QUALIFIED",
        "application_state": "NOT_STARTED",
    }
    value.update(overrides)
    return value


def registry(*records):
    entries = [normalize_opportunity(record, observed_at=NOW) for record in records]
    return {"entries": entries}


class CrossRunOpportunityDeduplicationTests(unittest.TestCase):
    def test_same_job_same_url(self):
        result = classify_discovered_opportunity(opportunity(source_url="https://jobs.example.invalid/jobs/100?utm_source=board"), registry(opportunity()))
        self.assertEqual(result["classification"], "KNOWN_UNCHANGED")
        self.assertFalse(result["count_as_new"])

    def test_same_job_syndicated_url(self):
        previous = opportunity(source="Fictional employer ATS")
        current = opportunity(opportunity_id="discovery:board", source="Fictional job board", source_url="https://board.example.invalid/view/900", provider_job_id="BOARD-900")
        result = classify_discovered_opportunity(current, registry(previous))
        self.assertEqual(result["classification"], "KNOWN_UNCHANGED")
        self.assertIn("same employer, title, and JD", result["identity_reason"])

    def test_same_provider_id_changed_url(self):
        current = opportunity(source_url="https://jobs.example.invalid/careers/monitoring-tech-100")
        result = classify_discovered_opportunity(current, registry(opportunity()))
        self.assertEqual(result["classification"], "KNOWN_UNCHANGED")
        self.assertEqual(result["update_classification"], "NONE")

    def test_changed_url_same_posting_without_provider_id(self):
        previous = opportunity(provider_job_id=None)
        current = opportunity(opportunity_id="discovery:changed-url", provider_job_id=None, source_url="https://careers.example.invalid/operations/monitoring")
        result = classify_discovered_opportunity(current, registry(previous))
        self.assertEqual(result["classification"], "KNOWN_UNCHANGED")
        self.assertFalse(result["count_as_new"])

    def test_same_employer_title_different_requisition_is_new_role(self):
        current = opportunity(
            opportunity_id="opportunity:fictional-200", provider_job_id="REQ-200",
            source_url="https://jobs.example.invalid/jobs/200",
            job_description="Build a new data platform and lead database performance engineering.",
        )
        result = classify_discovered_opportunity(current, registry(opportunity()))
        self.assertEqual(result["classification"], "NEW")

    def test_repost_is_separate_and_linked(self):
        previous = opportunity(freshness_state="CLOSED")
        current = opportunity(opportunity_id="opportunity:fictional-101", provider_job_id="REQ-101", explicit_repost=True)
        result = classify_discovered_opportunity(current, registry(previous))
        self.assertEqual(result["classification"], "REPOST")
        self.assertEqual(result["update_classification"], "REPOST")
        self.assertTrue(result["create_packet_allowed"])

    def test_material_jd_update_requalifies_without_new_label(self):
        current = opportunity(job_description="Administer Windows servers, PowerShell automation, and identity infrastructure across production systems.")
        result = classify_discovered_opportunity(current, registry(opportunity()))
        self.assertEqual(result["classification"], "KNOWN_UPDATED")
        self.assertEqual(result["update_classification"], "MATERIAL_UPDATE")
        self.assertFalse(result["count_as_new"])

    def test_already_applied_suppresses_packet(self):
        result = classify_discovered_opportunity(opportunity(), registry(opportunity(application_state="SUBMITTED")))
        self.assertEqual(result["classification"], "ALREADY_APPLIED")
        self.assertIn("SUBMITTED", result["surface_state"])
        self.assertFalse(result["create_packet_allowed"])

    def test_previously_rejected_suppresses_packet(self):
        result = classify_discovered_opportunity(opportunity(), registry(opportunity(application_state="REJECTED")))
        self.assertEqual(result["classification"], "PREVIOUSLY_REJECTED")
        self.assertFalse(result["create_packet_allowed"])

    def test_previously_skipped_suppresses_packet(self):
        result = classify_discovered_opportunity(opportunity(), registry(opportunity(disposition="DO_NOT_SPEND_TIME")))
        self.assertEqual(result["classification"], "PREVIOUSLY_SKIPPED")
        self.assertFalse(result["create_packet_allowed"])

    def test_ambiguous_identity_fails_closed(self):
        previous = opportunity(provider_job_id=None, job_description="", source_url=None)
        current = opportunity(opportunity_id="discovery:ambiguous", provider_job_id=None, job_description="", source_url=None)
        result = classify_discovered_opportunity(current, registry(previous))
        self.assertEqual(result["classification"], "AMBIGUOUS_IDENTITY")
        self.assertEqual(result["surface_state"], "HOLD_FOR_IDENTITY_REVIEW")

    def test_pending_packet_is_reused_not_rebuilt(self):
        previous = normalize_opportunity(opportunity(), packet_exists=True, observed_at=NOW)
        result = classify_discovered_opportunity(opportunity(), {"entries": [previous]})
        self.assertEqual(result["surface_state"], "KNOWN — APPLICATION PENDING")
        self.assertFalse(result["create_packet_allowed"])

    def test_registry_retains_history_and_new_count_excludes_known(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state"
            old_dir = state / "opportunities" / "run-one" / "fictional-100"
            closed_dir = state / "opportunities" / "run-one" / "fictional-099"
            old_dir.mkdir(parents=True)
            closed_dir.mkdir(parents=True)
            old_dir.joinpath("opportunity.json").write_text(json.dumps(opportunity()), encoding="utf-8")
            closed_dir.joinpath("opportunity.json").write_text(json.dumps(opportunity(
                opportunity_id="opportunity:fictional-099", provider_job_id="REQ-099",
                source_url="https://jobs.example.invalid/jobs/99", freshness_state="CLOSED",
            )), encoding="utf-8")
            built = build_persistent_registry(state, timestamp=NOW)
            self.assertEqual(built["opportunity_count"], 2)
            batch = reconcile_discovery_batch([
                opportunity(),
                opportunity(opportunity_id="opportunity:fictional-200", provider_job_id="REQ-200", source_url="https://jobs.example.invalid/jobs/200", title="Network Support Technician"),
            ], built, observed_at=NOW)
            self.assertEqual(batch["live_opportunities_discovered"], 1)
            self.assertEqual(batch["known_opportunities_reconfirmed"], 1)
            self.assertEqual(batch["duplicate_packets_created"], 0)


if __name__ == "__main__":
    unittest.main()
