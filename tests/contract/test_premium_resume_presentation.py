from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from careeros.career_outputs import master_resume_content
from careeros.resume import render_pdf
from careeros.resume_ats import ats_resume_round_trip, build_recruiter_summary, validate_recruiter_summary
from careeros.resume_premium import (
    apply_premium_presentation,
    bullet_rhythm,
    evaluate_premium_quality,
    evaluate_visual_density,
    summary_naturalness,
)
from careeros.schemas import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "fixtures/synthetic/job-tailoring/profile.json"


def profile() -> dict:
    result = json.loads(PROFILE.read_text(encoding="utf-8"))
    result["profile_id"] = "profile:premium-synthetic"
    return result


class PremiumResumePresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry(ROOT / "src/careeros/schemas")

    def test_summary_is_natural_traced_and_not_template_assembled(self) -> None:
        p = profile()
        storyline = {"evidence_rankings": [
            {"evidence_id": item["record_id"], "classification": "ANCHOR"}
            for item in p["evidence"]
        ]}
        role = {
            "role_family_id": "role-family:security-operations",
            "display_name": "Security Operations",
            "core_capabilities": ["SIEM Alert Investigation", "Vulnerability Remediation"],
        }
        summary = build_recruiter_summary(p, storyline, role)
        self.assertEqual(validate_recruiter_summary(summary)["status"], "PASS", summary)
        self.assertEqual(summary_naturalness(summary)["status"], "PASS", summary)
        self.assertNotRegex(summary["text"].casefold(), r"candidate with evidence|supported by professional work|professional work:|technical projects:")
        self.assertTrue(all(item["source_evidence_ids"] or item["approved_config_source"] for item in summary["clauses"]))

    def test_project_skills_and_experience_hierarchy_is_deterministic(self) -> None:
        content = master_resume_content(profile())
        base_project = copy.deepcopy(content["projects"][0])
        while len(content["projects"]) < 6:
            clone = copy.deepcopy(base_project)
            clone["record_id"] = f"project:premium-{len(content['projects'])}"
            clone["name"] = f"Additional Technical Project {len(content['projects'])}"
            content["projects"].append(clone)
        content["skill_groups"] = [
            {"group": "SECURITY & MONITORING", "skills": [{"name": "SIEM"}]},
            {"group": "TOOLS & PLATFORMS", "skills": [{"name": "Scanner"}]},
        ]
        apply_premium_presentation(content)
        self.assertEqual([item["presentation_tier"] for item in content["projects"]], ["FEATURED"] * 4 + ["ADDITIONAL"] * 2)
        self.assertLess(content["section_order"].index("EXPERIENCE"), content["section_order"].index("PROJECTS"))
        self.assertEqual([item["group"] for item in content["skill_groups"]], ["SECURITY", "TOOLS"])

    def test_bullet_rhythm_detects_mechanical_copy(self) -> None:
        result = bullet_rhythm({"employment": [], "projects": [{"bullets": [
            {"text": "Action: reviewed alerts | Context: lab | Outcome: report."},
        ]}]})
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("DATABASE_STYLE_PROSE", {item["code"] for item in result["findings"]})

    def test_premium_render_retains_high_confidence_ats(self) -> None:
        content = master_resume_content(profile())
        # Exercise the premium density gate with a realistically complete
        # one-page career-changer resume rather than a deliberately sparse
        # contract fixture.
        content["employment"][0]["bullets"].extend([
            {"text": "Coordinated time-sensitive updates and recorded clear disposition notes for the next shift.", "evidence_ids": ["evidence:handoff"]},
            {"text": "Maintained concise service records so operators could continue work without recreating prior analysis.", "evidence_ids": ["evidence:handoff"]},
        ])
        additions = [
            ("Incident Documentation Exercise", "Correlated event context and prepared a concise escalation brief for review.", "evidence:siem"),
            ("Endpoint Review Exercise", "Reviewed endpoint indicators and summarized the relevant observations in a structured report.", "evidence:vulnerability"),
            ("Network Handoff Exercise", "Captured packet-analysis observations and organized the results for an operations handoff.", "evidence:network"),
        ]
        for index, (name, bullet, evidence_id) in enumerate(additions, start=1):
            content["projects"].append({
                "name": name,
                "date_range": None,
                "contribution": "Completed a synthetic technical exercise",
                "record_id": f"project:premium-render-{index}",
                "bullets": [{"text": bullet, "evidence_ids": [evidence_id]}],
                "selection_tier": "SUPPORTING",
            })
        content["projects"][0]["bullets"].append({"text": "Documented the alert rationale and the evidence supporting the final disposition.", "evidence_ids": ["evidence:siem"]})
        content["projects"][1]["bullets"].append({"text": "Validated the corrective action and preserved the before-and-after scan context.", "evidence_ids": ["evidence:vulnerability"]})
        content["projects"][2]["bullets"].append({"text": "Prepared a clear escalation note describing the suspected failure domain and next checks.", "evidence_ids": ["evidence:network"]})
        content["projects"][3]["bullets"].append({"text": "Produced a reviewer-ready record of the observed indicators and response sequence.", "evidence_ids": ["evidence:siem"]})
        content["display_education"] = [
            {"institution": "Northbridge College", "program": "A.S. Information Technology", "display_status": "In progress - 2027"},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            pdf = Path(temporary) / "Rowan Vale - Professional Resume.pdf"
            render_pdf(content, pdf)
            round_trip = ats_resume_round_trip(content, pdf)
            density = evaluate_visual_density(content, pdf)
            premium = evaluate_premium_quality(content, density)
            self.registry.validate("urn:careeros:schema:resume-visual-density:v1", density)
            self.registry.validate("urn:careeros:schema:premium-resume-quality:v1", premium)
            extracted = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages)
        self.assertEqual(round_trip["status"], "ATS_SAFE_HIGH_CONFIDENCE", round_trip)
        self.assertLess(extracted.find(content["resume_header"]["positioning_headline"]), extracted.find(content["resume_header"]["email"]))
        self.assertNotIn(" | Bachelor", extracted)
        self.assertEqual(density["status"], "PASS", density)
        self.assertEqual(premium["status"], "PASS", premium)
        self.assertGreaterEqual(premium["score"], 8.8)


if __name__ == "__main__":
    unittest.main()
