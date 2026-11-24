from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from careeros import lane_base, onboarding, profile, updates, workspace
from careeros.core.io import read_json, sha256_file
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/synthetic/early-career"
NOW = "2026-10-03T20:00:00Z"


class LaneBaseResumeTests(unittest.TestCase):
    def _workspace(self, root: str) -> Path:
        target = Path(root) / "workspace"
        workspace.init_workspace(target, fixture_mode=True, timestamp=NOW)
        onboarding.start(target, timestamp=NOW)
        proposed = onboarding.ingest(target, FIXTURE / "onboarding/input.json", timestamp=NOW)
        if proposed["state"] == "NEEDS_CLARIFICATION":
            onboarding.resolve(target, FIXTURE / "onboarding/resolutions.json", timestamp=NOW)
        onboarding.commit(target, actor="synthetic-human", timestamp=NOW)
        profile.build_profile(target, timestamp=NOW)
        profile.build_role_family(target, approve=True, timestamp=NOW)
        return target

    def test_build_accept_and_contract_validation(self):
        with tempfile.TemporaryDirectory() as root:
            target = self._workspace(root)
            result = lane_base.build_lane_base(target, timestamp=NOW)
            self.assertEqual(result["validation"]["status"], "PASS", result["validation"])
            self.assertEqual(result["lane_base"]["status"], "REVIEW_REQUIRED")
            required_gates = {"PDF_OBJECT_PREFLIGHT",
                "SCHEMA", "TRUTH", "PROVENANCE", "CAREER_CONTINUITY", "PROFESSIONAL_CREDIBILITY",
                "STORYLINE_COMPLETENESS", "EVIDENCE_SUFFICIENCY", "EDITORIAL_QUALITY",
                "LANE_DIFFERENTIATION", "UNSUPPORTED_METRIC", "ATS", "AUTOFILL", "PAGE_GEOMETRY",
                "VISUAL_QA", "UNDERFILL_OVERFILL", "METADATA",
                "CANONICAL_EVIDENCE_FRESHNESS", "NEW_EVIDENCE_UTILIZATION",
                "PROFESSIONAL_HISTORY_SUFFICIENCY", "EMPTY_EXPERIENCE_ENTRY",
                "RECRUITER_COPY_SPECIFICITY", "PUBLIC_ARTIFACT_NAMING",
                "PUBLIC_COPY_BOUNDARY", "RECRUITER_COPY_QUALITY_V2",
                "SYSTEM_ARTIFACT_LEAKAGE",
                "NAME_EXTRACTED", "EMAIL_EXTRACTED", "PHONE_EXTRACTED", "LOCATION_EXTRACTED",
                "LINKEDIN_EXTRACTED", "PORTFOLIO_EXTRACTED", "GITHUB_EXTRACTED", "HEADLINE_EXTRACTED",
                "HEADER_READING_ORDER", "LINK_ANNOTATIONS", "MASTHEAD_GEOMETRY", "SUMMARY_EXTRACTED", "SUMMARY_EVIDENCE_TRACE",
                "SECTION_NAMES", "SECTION_READING_ORDER", "PRIMARY_EXTRACTION", "SECONDARY_EXTRACTION",
                "IDENTITY_ROUND_TRIP", "EMPLOYMENT_ROUND_TRIP", "PROJECTS_ROUND_TRIP",
                "EDUCATION_ROUND_TRIP", "CREDENTIALS_ROUND_TRIP", "SKILLS_ROUND_TRIP",
                "TITLE_EMPLOYER_PARSE", "DATE_STANDARD", "PDF_METADATA", "TYPOGRAPHY_GEOMETRY",
                "SINGLE_COLUMN", "NO_GRAPHICAL_DEPENDENCY", "ATS_CONFIDENCE", "SUMMARY_QUALITY",
                "PREMIUM_RESUME_QUALITY", "RESUME_VISUAL_DENSITY",
                "ROLE_FACT_PRESERVATION", "MATERIAL_EVIDENCE_LOSS", "CRITICAL_EVIDENCE_LOSS",
            }
            self.assertEqual({item["gate"] for item in result["validation"]["gates"]}, required_gates)
            SchemaRegistry(schema_dir()).validate("urn:careeros:schema:lane-base-resume:v1", result["lane_base"])
            accepted = lane_base.accept_lane_base(target, result["lane_base"]["lane_base_id"], actor="synthetic-human", timestamp=NOW)
            self.assertEqual(accepted["lane_base"]["status"], "ACCEPTED")
            self.assertTrue(lane_base.effective_status(target, accepted["lane_base"]["lane_base_id"])["reuse_allowed"])

    def test_canonical_change_marks_accepted_base_stale_without_mutating_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            target = self._workspace(root)
            accepted = lane_base.build_lane_base(target, accept=True, actor="synthetic-human", timestamp=NOW)
            base = accepted["lane_base"]
            artifact_path = target / "outputs" / accepted["artifact"]["path"]
            before_hash = sha256_file(artifact_path)
            candidate = read_json(target / "data/records/candidate.json")
            proposal = Path(root) / "change.json"
            proposal.write_text(json.dumps({
                "created_by": "synthetic-human", "reason": "Synthetic location correction",
                "source": {"type": "USER_STATEMENT", "references": []},
                "proposed_changes": [{
                    "operation": "CORRECT_FACT", "record_type": "candidate", "record_id": candidate["record_id"],
                    "field_path": "location", "before": candidate["location"], "after": "Example City Two",
                    "source_refs": [], "confidence": "HIGH", "visibility_impact": "NONE",
                    "verification_impact": "NONE", "reason": "Synthetic correction",
                }],
            }), encoding="utf-8")
            changeset = updates.propose(target, proposal, timestamp="2026-10-03T20:01:00Z")
            updates.approve(target, changeset["changeset_id"], actor="synthetic-human", timestamp="2026-10-03T20:02:00Z")
            updates.commit(target, changeset["changeset_id"], actor="synthetic-human", timestamp="2026-10-03T20:03:00Z")
            status = lane_base.effective_status(target, base["lane_base_id"])
            self.assertEqual(status["effective_status"], "STALE_PROFILE_CHANGE")
            self.assertFalse(status["reuse_allowed"])
            self.assertTrue(status["historical_artifact_immutable"])
            self.assertEqual(sha256_file(artifact_path), before_hash)
            stored = read_json(target / "state/lane-bases" / base["lane_base_id"] / "lane-base.json")
            self.assertEqual(stored["status"], "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
