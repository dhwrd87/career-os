from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from careeros import application, onboarding, opportunity, profile, resume, workspace
from careeros.core.io import read_json


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PACKAGE_ROOT / "fixtures" / "synthetic"
TIMESTAMP = "2026-10-02T12:00:00Z"
FIXTURES = ("early-career", "career-changer", "experienced-multi-role")


class GenericResumeVerticalSliceTests(unittest.TestCase):
    def run_fixture(self, fixture_name: str):
        fixture = FIXTURE_ROOT / fixture_name
        expected = read_json(fixture / "expected/expectations.json")
        with tempfile.TemporaryDirectory(prefix=f"careeros-{fixture_name}-") as root:
            target = Path(root) / "career-workspace"
            manifest = workspace.init_workspace(target, fixture_mode=True, workspace_id=f"workspace-{fixture_name}", timestamp=TIMESTAMP)
            self.assertEqual(manifest["workspace_format_version"], "1.1.0")
            diagnosis = workspace.doctor(target)
            self.assertEqual(diagnosis["outcome"], "READY")
            onboarding.start(target, timestamp=TIMESTAMP)
            proposed = onboarding.ingest(target, fixture / "onboarding/input.json", timestamp=TIMESTAMP)
            clarification_types = sorted(item["issue_type"] for item in onboarding.list_clarifications(target)["items"])
            self.assertEqual(clarification_types, sorted(expected["expected_clarification_types"]))
            if proposed["state"] == "NEEDS_CLARIFICATION":
                queue = onboarding.resolve(target, fixture / "onboarding/resolutions.json", timestamp=TIMESTAMP)
                self.assertEqual(queue["state"], "RESOLVED")
            event = onboarding.commit(target, actor="fixture-human", timestamp=TIMESTAMP)
            self.assertGreater(len(event["record_ids"]), 0)
            compiled, profile_manifest = profile.build_profile(target, timestamp=TIMESTAMP)
            self.assertEqual(compiled["schema"], "careeros.career-profile.v1")
            role = profile.build_role_family(target, approve=True, timestamp=TIMESTAMP)
            self.assertEqual(role["approval_state"], "APPROVED")
            strong, _ = opportunity.ingest(target, fixture / "opportunity/strong.json", timestamp=TIMESTAMP)
            borderline, _ = opportunity.ingest(target, fixture / "opportunity/borderline.json", timestamp=TIMESTAMP)
            strong_decision = opportunity.qualify(target, strong["opportunity_id"], timestamp=TIMESTAMP)
            borderline_decision = opportunity.qualify(target, borderline["opportunity_id"], timestamp=TIMESTAMP)
            self.assertEqual(strong_decision["decision"], expected["strong_decision"])
            self.assertEqual(borderline_decision["decision"], expected["borderline_decision"])
            with self.assertRaises(PermissionError):
                resume.build(target, borderline["opportunity_id"], timestamp=TIMESTAMP)
            build_record, content, artifact = resume.build(target, strong["opportunity_id"], timestamp=TIMESTAMP)
            validation, artifact_manifest = resume.validate(target, build_record["build_id"])
            self.assertEqual(validation["status"], "PASS", validation)
            required_gates = {"PDF_OBJECT_PREFLIGHT","SCHEMA", "CANONICAL_EVIDENCE_FRESHNESS", "NEW_EVIDENCE_UTILIZATION", "PROFESSIONAL_HISTORY_SUFFICIENCY", "EMPTY_EXPERIENCE_ENTRY", "TRUTH", "PROVENANCE", "CHRONOLOGY", "CREDENTIAL_STATE", "UNSUPPORTED_METRIC", "TITLE_NORMALIZATION", "ROLE_RELEVANCE", "JD_COVERAGE", "ATS_TEXT_EXTRACTION", "ATS_READING_ORDER", "AUTOFILL", "FONT", "PAGE_GEOMETRY", "PDF_PREFLIGHT", "VISUAL", "UNDERFILLED_RESUME", "RESUME_COMPLETENESS", "FILENAME", "PDF_METADATA", "ARTIFACT_HASH_LINEAGE", "EDITORIAL_QUALITY", "PUBLIC_ARTIFACT_NAMING", "RECRUITER_COPY_SPECIFICITY", "PUBLIC_COPY_BOUNDARY", "RECRUITER_COPY_QUALITY_V2", "TARGETED_EDITORIAL_REGRESSION", "TARGETED_RESUME_DELTA", "SYSTEM_ARTIFACT_LEAKAGE", "SEMANTIC_DUPLICATION", "JOB_RELEVANCE", "IMPORTANT_REQUIREMENT_COVERAGE", "UNSUPPORTED_KEYWORD_INSERTION", "JOB_STORY_COHERENCE", "LANE_STORY_COHERENCE", "PROJECT_ORDER_RELEVANCE", "BULLET_JOB_RELEVANCE", "SUMMARY_JOB_RELEVANCE", "HARD_GAP_DISGUISE", "TRANSFERABLE_EVIDENCE_OVERREACH", "PREMIUM_RESUME_QUALITY", "RESUME_VISUAL_DENSITY", "EMPLOYER_NEED_TRACE", "TOP_THIRD_COVERAGE", "STRONGEST_EVIDENCE_OMISSION", "ROLE_FACT_PRESERVATION", "MATERIAL_EVIDENCE_LOSS", "CRITICAL_EVIDENCE_LOSS"}
            ats_v1_gates = {
                "NAME_EXTRACTED", "EMAIL_EXTRACTED", "PHONE_EXTRACTED", "LOCATION_EXTRACTED",
                "LINKEDIN_EXTRACTED", "PORTFOLIO_EXTRACTED", "GITHUB_EXTRACTED", "HEADLINE_EXTRACTED",
                "HEADER_READING_ORDER", "LINK_ANNOTATIONS", "MASTHEAD_GEOMETRY", "SUMMARY_EXTRACTED", "SUMMARY_EVIDENCE_TRACE",
                "SECTION_NAMES", "SECTION_READING_ORDER", "PRIMARY_EXTRACTION", "SECONDARY_EXTRACTION",
                "IDENTITY_ROUND_TRIP", "EMPLOYMENT_ROUND_TRIP", "PROJECTS_ROUND_TRIP",
                "EDUCATION_ROUND_TRIP", "CREDENTIALS_ROUND_TRIP", "SKILLS_ROUND_TRIP",
                "TITLE_EMPLOYER_PARSE", "DATE_STANDARD", "TYPOGRAPHY_GEOMETRY", "SINGLE_COLUMN",
                "NO_GRAPHICAL_DEPENDENCY", "ATS_CONFIDENCE", "SUMMARY_QUALITY",
            }
            self.assertEqual({item["gate"] for item in validation["gates"]}, required_gates | ats_v1_gates)
            self.assertLessEqual(artifact["page_count"], expected["expected_page_max"])
            golden = read_json(fixture / "expected/visual-golden.json")
            render_path = target / "outputs" / validation["render_paths"][0]
            with Image.open(render_path) as image:
                self.assertEqual(image.size, (golden["expected_canvas"]["width"], golden["expected_canvas"]["height"]))
                bounds = image.convert("L").point(lambda pixel: 0 if pixel > 250 else 255).getbbox()
            self.assertIsNotNone(bounds)
            self.assertGreaterEqual(bounds[0], golden["content_bounds"]["minimum_left"])
            self.assertGreaterEqual(bounds[1], golden["content_bounds"]["minimum_top"])
            self.assertLessEqual(bounds[2], golden["content_bounds"]["maximum_right"])
            self.assertLessEqual(bounds[3], golden["content_bounds"]["maximum_bottom"])
            packet = application.prepare(target, strong["opportunity_id"], build_record["build_id"], timestamp=TIMESTAMP)
            self.assertEqual(packet["human_review_state"], expected["application_state"])
            final_status = workspace.status(target)
            self.assertTrue(final_status["state"]["application"])
            self.assertFalse(any("submit" in path.name.casefold() for path in target.rglob("*")))
            if fixture_name == "career-changer":
                rendered = str(content).casefold()
                for forbidden in expected["forbid_claims"]:
                    self.assertNotIn(forbidden.casefold(), rendered)
                transfer = [item for item in borderline_decision["evidence"] if item["capability"] == "Implementation Delivery"]
                self.assertTrue(transfer)
                self.assertTrue(all(item["experience_equivalence"] is False for item in transfer))
            if fixture_name == "experienced-multi-role":
                expired = [item for item in content["credentials"] if item["credential_state"] == "EXPIRED"]
                self.assertTrue(expired)
            return {
                "fixture": fixture_name, "workspace_id": manifest["workspace_id"], "profile_hash": profile_manifest["profile_hash"],
                "role_family_id": role["role_family_id"], "strong_decision": strong_decision["decision"],
                "borderline_decision": borderline_decision["decision"], "build_id": build_record["build_id"],
                "pdf_sha256": artifact_manifest["artifacts"][0]["sha256"], "gate_count": len(validation["gates"]),
                "packet_state": packet["human_review_state"],
            }

    def test_early_career(self):
        self.run_fixture("early-career")

    def test_career_changer(self):
        self.run_fixture("career-changer")

    def test_experienced_multi_role(self):
        self.run_fixture("experienced-multi-role")


if __name__ == "__main__":
    unittest.main()
