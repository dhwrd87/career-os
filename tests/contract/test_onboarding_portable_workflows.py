from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from docx import Document
from reportlab.pdfgen.canvas import Canvas

from careeros import intake, workflows, workspace
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "synthetic"
SOURCE = FIXTURES / "intake" / "complete-resume.md"
NOW = "2026-10-03T15:00:00Z"


def source_lines() -> list[str]:
    return SOURCE.read_text(encoding="utf-8").splitlines()


class PortableOnboardingTests(unittest.TestCase):
    def test_fast_and_deep_intakes_are_consolidated_and_schema_valid(self):
        for mode, expected in (("FAST", 9), ("DEEP", 11)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                target = Path(root) / "workspace"
                workspace.init_workspace(target, fixture_mode=True, timestamp=NOW)
                result = intake.compile_intake(target, [SOURCE], mode=mode, linked_source_decision=False, timestamp=NOW)
                SchemaRegistry(schema_dir()).validate("urn:careeros:schema:career-intake:v1", result)
                self.assertEqual(result["question_count"], expected)
                self.assertGreaterEqual(result["question_count"], 8)
                self.assertLessEqual(result["question_count"], 15)
                self.assertFalse(result["canonical_mutation"])
                self.assertFalse((target / "data/records/candidate.json").exists())

    def test_prefilled_intake_extracts_identity_history_claims_and_provenance(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workspace.init_workspace(target, fixture_mode=True, timestamp=NOW)
            result = intake.compile_intake(target, [SOURCE], linked_source_decision=False, timestamp=NOW)
            proposed = result["prefilled_onboarding"]
            self.assertEqual(proposed["candidate"]["public_name"], "Jordan Avery")
            self.assertEqual(len(proposed["employment"]), 2)
            self.assertEqual(len(proposed["projects"]), 1)
            self.assertTrue(result["source_claims"])
            self.assertTrue(all(item.get("source_ref") for item in result["source_claims"]))
            self.assertTrue(all(item["verification"] != "VERIFIED" for claim in result["source_claims"] for item in claim["atomic_claims"]))

    def test_pdf_and_docx_source_ingestion_are_self_service(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            pdf = root_path / "resume.pdf"
            canvas = Canvas(str(pdf))
            y = 760
            for line in source_lines():
                canvas.drawString(72, y, line[:100])
                y -= 12
                if y < 60:
                    canvas.showPage()
                    y = 760
            canvas.save()
            docx = root_path / "resume.docx"
            document = Document()
            for line in source_lines():
                document.add_paragraph(line)
            document.save(docx)
            target = root_path / "workspace"
            workspace.init_workspace(target, fixture_mode=True, timestamp=NOW)
            pdf_result = intake.ingest_source(target, pdf, timestamp=NOW)
            docx_result = intake.ingest_source(target, docx, timestamp=NOW)
            self.assertEqual(pdf_result["media_type"], "pdf")
            self.assertEqual(docx_result["media_type"], "docx")
            self.assertTrue(any("Jordan Avery" in item["text"] for item in pdf_result["units"]))
            self.assertTrue(any("Jordan Avery" in item["text"] for item in docx_result["units"]))
            self.assertTrue(all(item["source_hash"] for item in [*pdf_result["units"], *docx_result["units"]]))

    def test_eight_onboarding_profiles_stay_within_friction_budget(self):
        cases = json.loads((FIXTURES / "intake/cases.json").read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 8)
        for case in cases:
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as root:
                target = Path(root) / "workspace"
                workspace.init_workspace(target, fixture_mode=True, timestamp=NOW)
                result = intake.compile_intake(target, [SOURCE], mode="FAST", linked_source_decision=False, timestamp=NOW)
                low, high = case["expected_prompts"]
                self.assertGreaterEqual(result["question_count"], low)
                self.assertLessEqual(result["question_count"], high)

    def test_clean_room_one_shot_requires_approval_and_produces_immediate_outputs(self):
        with tempfile.TemporaryDirectory(prefix="careeros-one-shot-") as root:
            target = Path(root) / "workspace"
            start = workflows.setup_start(target, [SOURCE], mode="FAST", fixture_mode=True, timestamp=NOW)
            self.assertEqual(start["state"], "SOURCE_ENRICHMENT_APPROVAL_REQUIRED")
            start = workflows.setup_enrich(target, approved=False, timestamp=NOW)
            self.assertEqual(start["state"], "AWAITING_COMPLETION")
            raw = json.loads((FIXTURES / "experienced-multi-role/onboarding/input.json").read_text(encoding="utf-8"))
            answers = Path(root) / "answers.json"
            answers.write_text(json.dumps({
                "privacy_consent": True, "review_confirmed": True,
                "confirmed_onboarding": {key: raw[key] for key in (
                    "candidate", "employment", "education", "credentials", "skills",
                    "evidence", "projects", "preferences", "role_intents",
                )},
            }), encoding="utf-8")
            preview = workflows.setup_complete(target, answers, timestamp="2026-10-03T15:01:00Z")
            self.assertEqual(preview["state"], "COMMIT_PREVIEW_READY")
            self.assertTrue(preview["requires_explicit_approval"])
            self.assertFalse((target / "data/records/candidate.json").exists())
            with self.assertRaises(PermissionError):
                workflows.setup_approve(target, actor="fixture-human", approved=False, timestamp=NOW)
            result = workflows.setup_approve(target, actor="fixture-human", approved=True, timestamp="2026-10-03T15:02:00Z")
            self.assertEqual(result["state"], "COMPLETE")
            self.assertTrue((target / result["outputs"]["master_recruiter_resume"]).is_file())
            for key in ("career_profile", "profile_readiness", "career_lane_analysis", "role_title_universe", "career_gap_analysis", "development_priorities"):
                self.assertTrue((target / result["outputs"][key]).exists())
            self.assertEqual(result["external_actions"], 0)

    def test_high_level_workflow_router_hides_internal_command_surface(self):
        for intent in workflows.HIGH_LEVEL_WORKFLOWS:
            routed = workflows.route_high_level(intent)
            self.assertEqual(routed["intent"], intent)
            self.assertEqual(routed["external_actions"], 0)


if __name__ == "__main__":
    unittest.main()
