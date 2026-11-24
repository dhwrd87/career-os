from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from careeros import application, onboarding, opportunity, portability, profile, resume, updates, workspace
from careeros.core.errors import RecordConflictError
from careeros.core.io import atomic_write_json, read_json, sha256_file
from careeros.schemas.validation import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/synthetic/early-career"
NOW = "2026-10-02T12:00:00Z"
LATER = "2026-10-03T12:00:00Z"


def build_workspace(target: Path) -> dict[str, str]:
    workspace.init_workspace(target, fixture_mode=True, workspace_id="workspace-update-alpha", timestamp=NOW)
    onboarding.start(target, timestamp=NOW)
    result = onboarding.ingest(target, FIXTURE / "onboarding/input.json", timestamp=NOW)
    if result["state"] == "NEEDS_CLARIFICATION":
        onboarding.resolve(target, FIXTURE / "onboarding/resolutions.json", timestamp=NOW)
    onboarding.commit(target, actor="fixture-human", timestamp=NOW)
    profile.build_profile(target, timestamp=NOW)
    profile.build_role_family(target, approve=True, timestamp=NOW)
    strong, _ = opportunity.ingest(target, FIXTURE / "opportunity/strong.json", timestamp=NOW)
    opportunity.qualify(target, strong["opportunity_id"], timestamp=NOW)
    build, _, artifact = resume.build(target, strong["opportunity_id"], timestamp=NOW)
    resume.validate(target, build["build_id"])
    application.prepare(target, strong["opportunity_id"], build["build_id"], timestamp=NOW)
    return {"opportunity_id": strong["opportunity_id"], "build_id": build["build_id"], "artifact_sha256": artifact["sha256"]}


class CanonicalUpdateWorkflowTests(unittest.TestCase):
    def test_propose_approve_commit_history_staleness_and_immutability(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-update-") as root:
            target = Path(root) / "workspace"
            details = build_workspace(target)
            employment = read_json(target / "data/records/employment.json")[0]
            evidence = read_json(target / "data/records/evidence.json")[0]
            pdf = next((target / "outputs/resumes").glob("*.pdf"))
            before_pdf_hash = sha256_file(pdf)
            proposal_path = target / "sources/update.json"
            atomic_write_json(proposal_path, {
                "created_by": "participant-alpha-a",
                "source": {"type": "USER_STATEMENT", "references": ["session:alpha-a:update-1"]},
                "reason": "Correct employment date and restrict evidence reuse.",
                "proposed_changes": [
                    {"operation": "CORRECT_FACT", "record_type": "employment", "record_id": employment["record_id"], "field_path": "start_year", "before": 2025, "after": 2024, "source_refs": ["session:alpha-a:update-1"], "confidence": "HIGH", "visibility_impact": "NONE", "verification_impact": "NONE", "reason": "Participant corrected the year."},
                    {"operation": "CHANGE_VISIBILITY", "record_type": "evidence", "record_id": evidence["record_id"], "field_path": "visibility", "before": "PUBLIC", "after": "RESTRICTED", "source_refs": ["session:alpha-a:update-1"], "confidence": "HIGH", "visibility_impact": "MORE_RESTRICTIVE", "verification_impact": "NONE", "reason": "Participant withdrew reuse permission."},
                ],
            })
            changeset = updates.propose(target, proposal_path, timestamp=LATER)
            self.assertEqual(changeset["approval_state"], "REVIEW_READY")
            self.assertTrue({"PROFILE_REBUILD_REQUIRED", "QUALIFICATION_STALE", "RESUME_STALE", "APPLICATION_PACKET_STALE"} <= {item["impact"] for item in changeset["affected_derivatives"]})
            preview = updates.preview(target, changeset["changeset_id"])
            self.assertFalse(preview["commit_allowed"])
            with self.assertRaises(PermissionError):
                updates.commit(target, changeset["changeset_id"], actor="participant-alpha-a", timestamp=LATER)
            updates.approve(target, changeset["changeset_id"], actor="participant-alpha-a", timestamp=LATER)
            event = updates.commit(target, changeset["changeset_id"], actor="participant-alpha-a", timestamp=LATER)
            self.assertEqual(event["event"], "CANONICAL_CHANGESET_COMMITTED")
            self.assertEqual(read_json(target / "data/records/employment.json")[0]["start_year"], 2024)
            self.assertEqual(read_json(target / "data/records/evidence.json")[0]["visibility"], "RESTRICTED")
            self.assertEqual(sha256_file(pdf), before_pdf_hash)
            status = read_json(target / "state/derivative-status.json")
            self.assertTrue(status["entries"])
            self.assertTrue(all(item["status"] == "STALE" and item["reuse_allowed"] is False for item in status["entries"]))
            build_status = [item for item in status["entries"] if item["derivative_id"] == details["build_id"]][0]
            self.assertTrue(build_status["historical_artifact_immutable"])
            with self.assertRaises(PermissionError):
                resume.build(target, details["opportunity_id"], timestamp=LATER)
            with self.assertRaises(PermissionError):
                application.prepare(target, details["opportunity_id"], details["build_id"], timestamp=LATER)
            record_history = updates.history(target, employment["record_id"])
            self.assertEqual(len(record_history["events"]), 1)
            self.assertEqual(record_history["snapshots"][0]["record"]["start_year"], 2025)

    def test_conflict_requires_explicit_resolution_and_rechecks_before_commit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-conflict-") as root:
            target = Path(root) / "workspace"
            build_workspace(target)
            employment = read_json(target / "data/records/employment.json")[0]
            proposal_path = target / "sources/conflict.json"
            atomic_write_json(proposal_path, {
                "reason": "Conflicting date correction.",
                "proposed_changes": [{"operation": "CORRECT_FACT", "record_type": "employment", "record_id": employment["record_id"], "field_path": "start_year", "before": 2023, "after": 2024, "source_refs": ["source:verbal"], "confidence": "MEDIUM", "visibility_impact": "NONE", "verification_impact": "DISPUTED", "reason": "New statement differs from canonical value."}],
            })
            changeset = updates.propose(target, proposal_path, timestamp=LATER)
            self.assertEqual(changeset["approval_state"], "NEEDS_CLARIFICATION")
            with self.assertRaises(RecordConflictError):
                updates.approve(target, changeset["changeset_id"], actor="human", timestamp=LATER)
            resolutions = target / "sources/conflict-resolution.json"
            atomic_write_json(resolutions, {"resolutions": [{"conflict_index": 0, "decision": "USE_CANONICAL_BEFORE"}]})
            resolved = updates.resolve_conflicts(target, changeset["changeset_id"], resolutions, timestamp=LATER)
            self.assertEqual(resolved["approval_state"], "REVIEW_READY")

    def test_export_reset_delete_and_cross_workspace_isolation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-portability-") as root:
            base = Path(root)
            first = base / "first"
            second = base / "second"
            build_workspace(first)
            workspace.init_workspace(second, fixture_mode=True, workspace_id="workspace-isolated-b", timestamp=NOW)
            export = base / "participant-export.zip"
            manifest = portability.export_workspace(first, export, timestamp=LATER)
            self.assertTrue(export.is_file())
            self.assertEqual(manifest["categories"]["source_documents"], "EXCLUDED_BY_DEFAULT")
            with zipfile.ZipFile(export) as archive:
                names = set(archive.namelist())
            self.assertIn("data/records/candidate.json", names)
            self.assertFalse(any(name.startswith("sources/") for name in names))
            self.assertFalse((second / "data/records/candidate.json").exists())
            with self.assertRaises(PermissionError):
                portability.reset_generated(first, confirm_workspace_id="wrong")
            reset = portability.reset_generated(first, confirm_workspace_id="workspace-update-alpha", timestamp=LATER)
            self.assertTrue(reset["canonical_data_preserved"])
            self.assertTrue((first / "data/records/candidate.json").is_file())
            self.assertFalse(any((first / "outputs/resumes").glob("*.pdf")))
            with self.assertRaises(PermissionError):
                portability.archive_workspace(second, base / "archived-second", confirm_workspace_id="workspace-isolated-b", confirm_phrase="wrong")
            archived = portability.archive_workspace(second, base / "archived-second", confirm_workspace_id="workspace-isolated-b", confirm_phrase="DELETE WORKSPACE", timestamp=LATER)
            self.assertTrue(archived["recoverable"])
            self.assertFalse(second.exists())
            self.assertTrue((base / "archived-second/workspace-manifest.json").is_file())

    def test_phase5_contracts_validate(self) -> None:
        registry = SchemaRegistry(workspace.schema_dir())
        feedback = {
            "schema": "careeros.alpha-feedback.v1", "schema_version": "1.0.0", "feedback_id": "feedback:example-001",
            "session": "anonymous-session-a", "workflow_reference": "onboarding", "artifact_reference": None,
            "category": "WORKFLOW_FRICTION", "severity": "MEDIUM", "user_comment": None,
            "operator_observation": "Participant requested an explanation.", "requires_product_change": True,
            "requires_data_correction": False, "resolution": None, "status": "OPEN", "created_at": NOW,
        }
        registry.validate("urn:careeros:schema:alpha-feedback:v1", feedback)
        self.assertIn("careeros.canonical-changeset.v1", {item["schema_id"] for item in registry.list_entries()})

    def test_user_supplied_job_is_read_only_workspace_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-user-job-") as root:
            target = Path(root) / "workspace"
            build_workspace(target)
            source = read_json(FIXTURE / "opportunity/strong.json")
            source["source_type"] = "USER_SUPPLIED"
            source["opportunity_id"] = "opportunity:user-supplied-example"
            path = target / "sources/user-job.json"
            atomic_write_json(path, source)
            value, snapshot = opportunity.ingest(target, path, timestamp=LATER)
            self.assertEqual(value["source_type"], "USER_SUPPLIED")
            self.assertEqual(snapshot["rights_class"], "USER_SUPPLIED_READ_ONLY")
            self.assertEqual(snapshot["retention_class"], "USER_WORKSPACE")


if __name__ == "__main__":
    unittest.main()
