from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from careeros import onboarding, profile, resume, updates, workspace
from careeros.core.errors import ChangesetConflictError, ChangesetTransactionFailedError
from careeros.core.io import atomic_write_json, read_json, sha256_file


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/synthetic/early-career"
NOW = "2026-10-02T12:00:00Z"
LATER = "2026-10-03T12:00:00Z"


def build_canonical(target: Path) -> None:
    workspace.init_workspace(target, fixture_mode=True, workspace_id="workspace-transaction-test", timestamp=NOW)
    onboarding.start(target, timestamp=NOW)
    result = onboarding.ingest(target, FIXTURE / "onboarding/input.json", timestamp=NOW)
    if result["state"] == "NEEDS_CLARIFICATION":
        onboarding.resolve(target, FIXTURE / "onboarding/resolutions.json", timestamp=NOW)
    onboarding.commit(target, actor="fixture-human", timestamp=NOW)


def change(operation: str, kind: str, record: dict, field: str, after, *, visibility: str = "NONE") -> dict:
    value = record
    for part in field.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return {
        "operation": operation,
        "record_type": kind,
        "record_id": record["record_id"],
        "field_path": field,
        "before": value,
        "after": after,
        "source_refs": ["source:transaction-test"],
        "confidence": "HIGH",
        "visibility_impact": visibility,
        "verification_impact": "NONE",
        "reason": "Transaction regression input.",
    }


def propose_approve(target: Path, changes: list[dict], *, timestamp: str = LATER) -> dict:
    source = target / "sources" / f"update-{len(list((target / 'state/changesets').glob('*.json'))) if (target / 'state/changesets').exists() else 0}.json"
    atomic_write_json(source, {
        "created_by": "fixture-human",
        "source": {"type": "USER_STATEMENT", "references": ["source:transaction-test"]},
        "reason": "Exercise transactional canonical update.",
        "proposed_changes": changes,
    })
    changeset = updates.propose(target, source, timestamp=timestamp)
    if changeset["approval_state"] != "REVIEW_READY":
        raise AssertionError(changeset["conflicts"])
    return updates.approve(target, changeset["changeset_id"], actor="fixture-human", timestamp=timestamp)


class TransactionalChangesetTests(unittest.TestCase):
    def test_single_record_correction(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-tx-single-") as root:
            target = Path(root) / "workspace"
            build_canonical(target)
            record = read_json(target / "data/records/employment.json")[0]
            changeset = propose_approve(target, [change("CORRECT_FACT", "employment", record, "start_year", record["start_year"] - 1)])
            event = updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER)
            self.assertEqual(event["previous_canonical_revision"], 1)
            self.assertEqual(event["resulting_canonical_revision"], 2)

    def test_multi_record_changeset(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-tx-multi-") as root:
            target = Path(root) / "workspace"
            build_canonical(target)
            employment = read_json(target / "data/records/employment.json")[0]
            candidate = read_json(target / "data/records/candidate.json")
            changeset = propose_approve(target, [
                change("CORRECT_FACT", "employment", employment, "start_year", employment["start_year"] - 1),
                change("CORRECT_FACT", "candidate", candidate, "location", "Lakeview, OR"),
            ])
            updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER)
            self.assertEqual(read_json(target / "data/records/candidate.json")["location"], "Lakeview, OR")

    def test_add_record_changeset(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-tx-add-") as root:
            target = Path(root) / "workspace"
            build_canonical(target)
            new_skill = copy.deepcopy(read_json(target / "data/records/skills.json")[0])
            new_skill.update({"record_id": "skill:fictional-new-skill", "name": "Documentation Review", "created_at": LATER, "updated_at": LATER})
            addition = {
                "operation": "ADD_RECORD", "record_type": "skills", "record_id": None, "field_path": None,
                "before": None, "after": new_skill, "source_refs": ["source:transaction-test"], "confidence": "HIGH",
                "visibility_impact": "NONE", "verification_impact": "NONE", "reason": "Add a newly reported skill.",
            }
            changeset = propose_approve(target, [addition])
            updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER)
            self.assertIn("skill:fictional-new-skill", {item["record_id"] for item in read_json(target / "data/records/skills.json")})

    def test_visibility_restriction_commits_before_rebuild_and_preserves_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-tx-privacy-") as root:
            target = Path(root) / "workspace"
            build_canonical(target)
            built_profile, _ = profile.build_profile(target, timestamp=NOW)
            evidence = next(item for item in read_json(target / "data/records/evidence.json") if item["visibility"] == "PUBLIC")
            build_id = "resume-build:historical"
            atomic_write_json(target / "state/resume-builds/historical/build.json", {"build_id": build_id})
            artifact = target / "outputs/resumes/historical.pdf"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"immutable historical artifact")
            before = sha256_file(artifact)
            changeset = propose_approve(target, [change("CHANGE_VISIBILITY", "evidence", evidence, "visibility", "RESTRICTED", visibility="MORE_RESTRICTIVE")])
            updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER)
            self.assertEqual(sha256_file(artifact), before)
            statuses = read_json(target / "state/derivative-status.json")["entries"]
            stale = next(item for item in statuses if item["derivative_id"] == build_id)
            self.assertEqual((stale["status"], stale["reuse_allowed"]), ("STALE", False))
            rebuilt_profile, _ = profile.build_profile(target, timestamp=LATER)
            synthetic_opportunity = {"requirements": [{"capability": skill["name"]} for skill in rebuilt_profile["skills"]]}
            selected, excluded = resume._select_evidence(rebuilt_profile, synthetic_opportunity)
            self.assertNotIn(evidence["record_id"], {item["record_id"] for item in selected})
            self.assertIn(evidence["record_id"], {item["evidence_id"] for item in excluded})
            self.assertEqual(built_profile["profile_id"], rebuilt_profile["profile_id"])

    def test_metric_credential_and_preference_updates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-tx-types-") as root:
            target = Path(root) / "workspace"
            build_canonical(target)
            evidence = read_json(target / "data/records/evidence.json")[0]
            credential = read_json(target / "data/records/credentials.json")[0]
            preferences = read_json(target / "data/records/preferences.json")
            changeset = propose_approve(target, [
                change("CORRECT_METRIC", "evidence", evidence, "outcomes.0", "Completed a documented review without a quantified claim."),
                change("UPDATE_CREDENTIAL_STATE", "credentials", credential, "credential_state", "COMPLETED"),
                change("CHANGE_CAREER_PREFERENCE", "preferences", preferences, "work_modes", ["REMOTE"]),
            ])
            updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER)
            self.assertEqual(read_json(target / "data/records/preferences.json")["work_modes"], ["REMOTE"])

    def test_optimistic_concurrency_rejects_competing_changeset(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-tx-conflict-") as root:
            target = Path(root) / "workspace"
            build_canonical(target)
            employment = read_json(target / "data/records/employment.json")[0]
            first = propose_approve(target, [change("CORRECT_FACT", "employment", employment, "start_year", employment["start_year"] - 1)], timestamp="2026-10-03T12:00:00Z")
            second = propose_approve(target, [change("CORRECT_FACT", "employment", employment, "start_year", employment["start_year"] - 2)], timestamp="2026-10-03T12:00:01Z")
            updates.commit(target, first["changeset_id"], actor="fixture-human", timestamp="2026-10-03T13:00:00Z")
            with self.assertRaises(ChangesetConflictError):
                updates.commit(target, second["changeset_id"], actor="fixture-human", timestamp="2026-10-03T13:00:01Z")

    def test_duplicate_commit_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-tx-idempotent-") as root:
            target = Path(root) / "workspace"
            build_canonical(target)
            candidate = read_json(target / "data/records/candidate.json")
            changeset = propose_approve(target, [change("CORRECT_FACT", "candidate", candidate, "location", "Lakeview, OR")])
            first = updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER)
            second = updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER)
            self.assertEqual(second["idempotency_status"], "ALREADY_COMMITTED")
            self.assertEqual(first["event_id"], second["event_id"])
            self.assertEqual(len(updates.history(target)["events"]), 1)

    def test_precommit_failure_injection_rolls_back(self) -> None:
        for point in sorted(updates.PRECOMMIT_FAILURE_POINTS):
            with self.subTest(point=point), tempfile.TemporaryDirectory(prefix="careeros-tx-rollback-") as root:
                target = Path(root) / "workspace"
                build_canonical(target)
                candidate = read_json(target / "data/records/candidate.json")
                before = sha256_file(target / "data/records/candidate.json")
                changeset = propose_approve(target, [change("CORRECT_FACT", "candidate", candidate, "location", "Lakeview, OR")])
                with self.assertRaises(ChangesetTransactionFailedError):
                    updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER, failure_at=point)
                self.assertEqual(sha256_file(target / "data/records/candidate.json"), before)
                self.assertEqual(read_json(target / "state/changesets" / f"{changeset['changeset_id'].split(':', 1)[1]}.json")["approval_state"], "APPROVED")

    def test_postcommit_failures_preserve_committed_truth(self) -> None:
        for point in sorted(updates.POSTCOMMIT_FAILURE_POINTS):
            with self.subTest(point=point), tempfile.TemporaryDirectory(prefix="careeros-tx-postcommit-") as root:
                target = Path(root) / "workspace"
                build_canonical(target)
                candidate = read_json(target / "data/records/candidate.json")
                changeset = propose_approve(target, [change("CORRECT_FACT", "candidate", candidate, "location", "Lakeview, OR")])
                with self.assertRaises(ChangesetTransactionFailedError) as raised:
                    updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER, failure_at=point)
                self.assertTrue(raised.exception.context["canonical_committed"])
                self.assertEqual(read_json(target / "data/records/candidate.json")["location"], "Lakeview, OR")
                self.assertEqual(updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER)["idempotency_status"], "ALREADY_COMMITTED")

    def test_interrupted_journal_is_recovered_before_retry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-tx-interrupt-") as root:
            target = Path(root) / "workspace"
            build_canonical(target)
            candidate = read_json(target / "data/records/candidate.json")
            changeset = propose_approve(target, [change("CORRECT_FACT", "candidate", candidate, "location", "Lakeview, OR")])
            with self.assertRaises(ChangesetTransactionFailedError):
                updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp=LATER, failure_at="BEFORE_FIRST_WRITE")
            journal_path = next((target / "state/canonical-transactions").glob("*/transaction.json"))
            journal = read_json(journal_path)
            journal["status"] = "APPLYING"
            atomic_write_json(journal_path, journal)
            damaged = read_json(target / "data/records/candidate.json")
            damaged["location"] = "INTERRUPTED-PARTIAL-WRITE"
            atomic_write_json(target / "data/records/candidate.json", damaged)
            with self.assertRaises(ChangesetTransactionFailedError):
                updates.commit(target, changeset["changeset_id"], actor="fixture-human", timestamp="2026-10-03T12:00:01Z", failure_at="BEFORE_FIRST_WRITE")
            self.assertEqual(read_json(target / "data/records/candidate.json")["location"], candidate["location"])

    def test_history_chain_integrity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="careeros-tx-history-") as root:
            target = Path(root) / "workspace"
            build_canonical(target)
            candidate = read_json(target / "data/records/candidate.json")
            first = propose_approve(target, [change("CORRECT_FACT", "candidate", candidate, "location", "Lakeview, OR")], timestamp="2026-10-03T12:00:00Z")
            updates.commit(target, first["changeset_id"], actor="fixture-human", timestamp="2026-10-03T13:00:00Z")
            candidate = read_json(target / "data/records/candidate.json")
            second = propose_approve(target, [change("CORRECT_FACT", "candidate", candidate, "location", "Summit, OR")], timestamp="2026-10-03T14:00:00Z")
            updates.commit(target, second["changeset_id"], actor="fixture-human", timestamp="2026-10-03T15:00:00Z")
            verification = updates.verify_history_chain(target)
            self.assertEqual(verification["status"], "PASS")
            self.assertEqual(verification["event_count"], 2)


if __name__ == "__main__":
    unittest.main()
