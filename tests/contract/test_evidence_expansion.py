from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from careeros import evidence_expansion, onboarding, profile, workspace
from careeros.editorial import build_bullet_candidates, plan_storyline
from careeros.schemas.validation import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures/synthetic"
NOW = "2026-10-03T12:00:00Z"


def provenance(local_id: str) -> list[dict[str, object]]:
    return [{
        "source_id": f"source:{local_id}", "source_type": "DOCUMENT",
        "source_reference": "fixture://old-resume", "source_record_id": local_id,
        "field": "bullet", "source_hash": "a" * 64, "captured_at": NOW,
    }]


def shallow_record(local_id: str = "ev-shallow", *, project: bool = False) -> dict[str, object]:
    return {
        "schema": "careeros.evidence-record.v1", "schema_version": "1.0.0",
        "record_id": f"evidence:{local_id}", "created_at": NOW, "updated_at": NOW,
        "provenance": provenance(local_id), "verification_state": "UNVERIFIED",
        "confidence": "MEDIUM", "visibility": "PUBLIC", "status": "ACTIVE",
        "supersedes_record_id": None, "evidence_type": "PROJECT" if project else "EMPLOYMENT",
        "summary": "Supported service requests.", "context": None, "ownership": None,
        "actions": ["Reviewed requests"], "outcomes": [], "skill_ids": ["skill:service"],
        "employment_ids": [] if project else ["employment:service"],
        "project_ids": ["project:status"] if project else [], "metric_boundaries": [],
        "claim_boundaries": [], "source_original_wording": ["Handled service requests."]
    }


class EvidenceExpansionContractTests(unittest.TestCase):
    def setUp(self):
        self.registry = SchemaRegistry(ROOT / "src/careeros/schemas")

    def test_source_bullet_decomposition_preserves_original_and_atoms(self):
        result = evidence_expansion.decompose_source_bullet(
            "Resolved 30+ service cases daily using a ticketing platform for branch staff.",
            source_ref="fixture://old-resume#bullet-1",
        )
        components = {item["component"] for item in result["atomic_claims"]}
        self.assertTrue({"ACTION", "TOOL", "METRIC", "STAKEHOLDER"} <= components)
        self.assertIn("30+", result["original_text"])
        self.assertTrue(all(item["verification"] != "VERIFIED" for item in result["atomic_claims"]))

    def test_evidence_block_and_depth_contracts_validate(self):
        block = evidence_expansion.evidence_block_from_record(shallow_record(), timestamp=NOW)
        assessment = evidence_expansion.assess_evidence_depth(block, timestamp=NOW)
        self.registry.validate("urn:careeros:schema:evidence-block:v1", block)
        self.registry.validate("urn:careeros:schema:evidence-depth-assessment:v1", assessment)
        self.assertIn(assessment["overall_depth"], {"VERY_THIN", "THIN"})
        self.assertEqual(block["responsibility"]["level"], "UNKNOWN")

    def test_targeted_questions_only_cover_missing_high_value_dimensions(self):
        record = shallow_record()
        record["actions"] = ["Reviewed requests", "Documented findings", "Escalated complex cases"]
        block = evidence_expansion.evidence_block_from_record(record, timestamp=NOW)
        assessment = evidence_expansion.assess_evidence_depth(block, timestamp=NOW)
        questions = evidence_expansion.generate_targeted_questions(
            block, assessment, lane_context=["technical support"], max_questions=4,
        )
        targets = {item["target_field"] for item in questions}
        self.assertNotIn("actions", targets)
        self.assertTrue(all(item["allows_unknown"] for item in questions))
        self.assertLessEqual(len(questions), 4)

    def test_outcome_discovery_strengthens_proposal_without_copy_pollution(self):
        session = evidence_expansion.create_expansion_session([shallow_record()], timestamp=NOW)
        outcome_question = next(
            q for q in session["records"][0]["questions"] if q["target_field"] == "outcomes"
        )
        enriched = evidence_expansion.apply_answers(session, [{
            "question_id": outcome_question["question_id"],
            "value": ["Produced a reviewed escalation handoff."],
        }], timestamp=NOW)
        block = enriched["records"][0]["proposed_block"]
        self.assertIn("Produced a reviewed escalation handoff.", block["outcomes"])
        self.assertNotIn("rockstar", json.dumps(block).casefold())

    def test_metric_reconstruction_retains_formula_and_is_not_public(self):
        metric = evidence_expansion.reconstruct_metric(
            measurement_id="measurement:daily-volume", metric_type="VOLUME", operation="MULTIPLY",
            inputs=[{"name": "calls_per_hour", "value": 6}, {"name": "hours", "value": 8}],
            unit="calls per shift", source_refs=[{"source_reference": "fixture://self-report"}],
        )
        self.assertEqual(metric["value"], 48.0)
        self.assertEqual(metric["state"], "RECONSTRUCTABLE")
        self.assertFalse(metric["public_use_allowed"])
        self.assertEqual(metric["formula"], "6 * 8")

    def test_responsibility_and_skill_linkage_do_not_upgrade_authority(self):
        record = shallow_record()
        record["ownership"] = "Supported a coordinator; approval authority was not held."
        block = evidence_expansion.evidence_block_from_record(record, timestamp=NOW)
        self.assertEqual(block["responsibility"]["level"], "SUPPORTED")
        self.assertEqual(block["skills_demonstrated"][0]["skill_id"], "skill:service")
        self.assertEqual(block["skills_demonstrated"][0]["context"], "PROFESSIONAL")

    def test_lane_and_job_context_prioritize_questions_but_do_not_enter_facts(self):
        session = evidence_expansion.create_expansion_session(
            [shallow_record()], lane_context=["network operations"],
            job_context=["incident ticket escalation"], timestamp=NOW,
        )
        serialized_block = json.dumps(session["records"][0]["proposed_block"]).casefold()
        self.assertNotIn("network operations", serialized_block)
        self.assertNotIn("incident ticket escalation", serialized_block)
        self.assertTrue(any(q["priority"] == "HIGH_VALUE" for q in session["records"][0]["questions"]))

    def test_job_aware_gap_question_preserves_proposed_boundary(self):
        block = evidence_expansion.evidence_block_from_record(shallow_record(), timestamp=NOW)
        questions = evidence_expansion.generate_job_gap_questions([block], [{
            "requirement_id": "requirement:directory", "requirement_class": "REQUIRED",
            "text": "directory account administration",
        }])
        self.assertEqual(len(questions), 1)
        response = evidence_expansion.record_job_gap_response(
            questions[0], "PARTIAL_EVIDENCE", "Used a training directory in a lab.",
        )
        self.assertTrue(response["proposal_only"])
        self.assertFalse(response["canonical_mutation"])
        self.assertNotIn("directory account administration", json.dumps(block).casefold())

    def test_rich_evidence_drives_stronger_editorial_variant(self):
        block = evidence_expansion.evidence_block_from_record(shallow_record(project=True), timestamp=NOW)
        before = evidence_expansion.assess_evidence_depth(block, timestamp=NOW)
        block.update({
            "context": "Fictional service-status lab", "problem_or_need": "Make recurring incidents visible",
            "actions": ["Reviewed event records", "Grouped recurring conditions", "Documented escalation criteria"],
            "tools_methods": ["Log viewer", "Issue tracker"], "stakeholders": ["Lab reviewer"],
            "scope": "One simulated service environment", "frequency": "Three test runs",
            "deliverables": ["Service-status report"], "outcomes": ["Produced a reviewed escalation handoff."],
            "responsibility": {"level": "EXECUTED", "description": "Completed the lab individually"},
            "artifacts": [{"type": "REPORT", "reference": "fixture://status-report"}],
        })
        after = evidence_expansion.assess_evidence_depth(block, timestamp=NOW)
        profile_data = {
            "evidence": [block], "projects": [{"record_id": "project:status"}],
            "skills": [{"record_id": "skill:service", "name": "Event review", "aliases": [], "category": "Operations", "contexts": []}],
        }
        family = {"role_family_id": "role-family:operations", "display_name": "Operations Support", "core_capabilities": ["Event review"]}
        storyline = plan_storyline(profile_data, family)
        bullets = build_bullet_candidates(profile_data, storyline)
        self.assertGreater(("UNKNOWN", "VERY_THIN", "THIN", "USABLE", "RICH").index(after["overall_depth"]), ("UNKNOWN", "VERY_THIN", "THIN", "USABLE", "RICH").index(before["overall_depth"]))
        self.assertEqual(bullets[0]["tool_or_method"], "Log viewer")
        self.assertIn("reviewed escalation handoff", bullets[0]["outcome"].casefold())

    def test_eight_synthetic_case_definitions_are_candidate_neutral(self):
        cases = json.loads((FIXTURE_ROOT / "evidence-expansion/cases.json").read_text())["cases"]
        self.assertEqual(len(cases), 8)
        self.assertTrue(all(case["case_id"] and case["source_bullets"] for case in cases))

    def test_eight_synthetic_cases_expand_without_unsupported_public_claims(self):
        cases = json.loads((FIXTURE_ROOT / "evidence-expansion/cases.json").read_text())["cases"]
        depth_order = {name: index for index, name in enumerate(("UNKNOWN", "VERY_THIN", "THIN", "USABLE", "RICH"))}
        for index, case in enumerate(cases):
            with self.subTest(case=case["case_id"]):
                context = "LAB" if "project" in case["candidate_type"] or "student" in case["candidate_type"] else "PROFESSIONAL_EMPLOYMENT"
                linked = f"project:synthetic-{index}" if context == "LAB" else f"employment:synthetic-{index}"
                block = evidence_expansion.proposed_block_from_source_bullet(
                    case["source_bullets"][0], evidence_id=f"evidence:synthetic-{index}",
                    source_ref=f"fixture://evidence-expansion/{case['case_id']}",
                    evidence_context=context, linked_record_id=linked, timestamp=NOW,
                )
                before = evidence_expansion.assess_evidence_depth(block, timestamp=NOW)
                session = evidence_expansion.create_expansion_session([block], lane_context=["operations support"], timestamp=NOW)
                values = {
                    "actions": ["Reviewed source records", "Documented exceptions", "Escalated unresolved items"],
                    "tools_methods": ["Fictional tracker"],
                    "outcomes": ["Produced a reviewed handoff"],
                    "responsibility": "EXECUTED",
                    "artifacts": [{"type": "REPORT", "reference": f"fixture://artifact/{index}"}],
                }
                answers = [
                    {"question_id": question["question_id"], "value": values[question["target_field"]]}
                    for question in session["records"][0]["questions"]
                    if question["priority"] == "HIGH_VALUE"
                ]
                updated = evidence_expansion.apply_answers(session, answers, timestamp=NOW)
                approved = evidence_expansion.approve_session(updated, actor="fixture-human", timestamp=NOW)
                enriched = approved["records"][0]["proposed_block"]
                after = approved["records"][0]["assessment"]
                self.registry.validate("urn:careeros:schema:evidence-block:v1", enriched)
                self.assertGreaterEqual(depth_order[after["overall_depth"]], depth_order[before["overall_depth"]])
                self.assertTrue(all(not metric["public_use_allowed"] for metric in enriched["metrics"] if metric["state"] == "UNSUPPORTED"))
                profile_data = {
                    "evidence": [enriched],
                    "projects": [{"record_id": linked}] if context == "LAB" else [],
                    "skills": [],
                }
                storyline = plan_storyline(profile_data, {"role_family_id": "role-family:synthetic", "display_name": "Operations Support", "core_capabilities": ["documentation"]})
                self.assertTrue(build_bullet_candidates(profile_data, storyline))

    def test_progressive_workspace_promotion_precedes_canonical_commit(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workspace.init_workspace(target, fixture_mode=True, workspace_id="workspace-evidence-expansion", timestamp=NOW)
            onboarding.start(target, timestamp=NOW)
            result = onboarding.ingest(target, FIXTURE_ROOT / "early-career/onboarding/input.json", timestamp=NOW)
            if result["state"] == "NEEDS_CLARIFICATION":
                onboarding.resolve(target, FIXTURE_ROOT / "early-career/onboarding/resolutions.json", timestamp=NOW)
            session = evidence_expansion.start_workspace_session(target, lane_context=["support operations"], timestamp=NOW)
            answers = []
            for record in session["records"]:
                for question in record["questions"]:
                    if question["priority"] != "HIGH_VALUE":
                        continue
                    values = {
                        "actions": ["Reviewed fictional service records"],
                        "tools_methods": ["Fictional tracker"],
                        "outcomes": ["Produced a reviewed handoff"],
                        "responsibility": "EXECUTED",
                        "artifacts": [{"type": "REPORT", "reference": "fixture://report"}],
                    }
                    answers.append({"question_id": question["question_id"], "value": values[question["target_field"]]})
            updated = evidence_expansion.apply_answers(session, answers, timestamp=NOW)
            self.assertEqual(updated["state"], "REVIEW_READY")
            session_path = target / "state/evidence-expansion/session.json"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(json.dumps(updated), encoding="utf-8")
            evidence_expansion.approve_workspace_session(target, actor="fixture-human", timestamp=NOW)
            promoted = evidence_expansion.promote_workspace_session(target, timestamp=NOW)
            self.assertEqual(promoted["state"], "REVIEW_READY")
            self.assertFalse((target / "data/records/evidence.json").exists())
            onboarding.commit(target, actor="fixture-human", timestamp=NOW)
            built, _ = profile.build_profile(target, timestamp=NOW)
            self.assertTrue(all(item["schema"] == "careeros.evidence-block.v1" for item in built["evidence"]))

    def test_profile_readiness_recommends_expansion_without_blocking_every_thin_record(self):
        profile_data = {
            "employment": [{"record_id": "employment:old"}, {"record_id": "employment:recent"}],
            "evidence": [
                evidence_expansion.evidence_block_from_record(shallow_record("old"), timestamp=NOW),
                evidence_expansion.evidence_block_from_record(shallow_record("recent"), timestamp=NOW),
            ],
            "projects": [],
            "skills": [{"record_id": "skill:linked", "evidence_ids": ["evidence:recent"]}],
        }
        profile_data["evidence"][0]["employment_ids"] = ["employment:old"]
        profile_data["evidence"][1]["employment_ids"] = ["employment:recent"]
        result = evidence_expansion.evaluate_profile_readiness(profile_data, timestamp=NOW)
        self.registry.validate("urn:careeros:schema:profile-evidence-readiness:v1", result)
        self.assertIn(result["status"], {"PROFILE_READY_WITH_GAPS", "EVIDENCE_EXPANSION_RECOMMENDED", "CLARIFICATION_REQUIRED"})


if __name__ == "__main__":
    unittest.main()
