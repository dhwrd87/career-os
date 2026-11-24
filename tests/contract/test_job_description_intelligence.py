from __future__ import annotations

import json
import unittest
from pathlib import Path

from careeros.core.io import sha256_value
from careeros.editorial import lane_differentiation
from careeros.job_intelligence import (
    analyze_job_description,
    build_job_evidence_matrix,
    build_tailoring_trace,
)
from careeros.resume import _content_contract, _select_evidence
from careeros.schemas import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/synthetic/job-tailoring"


def read(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def opportunity_and_snapshot(name: str) -> tuple[dict, dict]:
    raw = read(name)
    opportunity = {
        "opportunity_id": raw["opportunity_id"], "role_title": raw["role_title"],
        "employer_name": raw["employer_name"], "requirements": raw["requirements"],
    }
    snapshot = {
        "snapshot_id": f"snapshot:{raw['opportunity_id']}", "opportunity_id": raw["opportunity_id"],
        "content_hash": sha256_value(raw["job_description"]), "text": raw["job_description"],
    }
    return opportunity, snapshot


def family(name: str, capabilities: list[str]) -> dict:
    return {
        "role_family_id": "role-family:" + name.casefold().replace(" ", "-"), "display_name": name,
        "target_titles": [name], "core_capabilities": capabilities, "preferred_capabilities": [],
        "transferable_capabilities": ["Shift Handoff Documentation"], "skill_tags": capabilities,
    }


class JobDescriptionIntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry(ROOT / "src/careeros/schemas")
        cls.profile = read("profile.json")
        cls.profile_hash = sha256_value(cls.profile)
        cls.soc = family("Security Monitoring Associate", ["SIEM Alert Investigation", "Vulnerability Remediation"])
        cls.noc = family("Network Operations Technician", ["Network Connectivity Analysis", "DNS", "DHCP"])

    def build_case(self, fixture_name: str, role_family: dict) -> dict:
        opportunity, snapshot = opportunity_and_snapshot(fixture_name)
        intelligence = analyze_job_description(opportunity, snapshot)
        self.registry.validate("urn:careeros:schema:job-description-intelligence:v1", intelligence)
        matrix = build_job_evidence_matrix(self.profile, intelligence)
        self.registry.validate("urn:careeros:schema:job-evidence-matrix:v1", matrix)
        qualification = {"qualification_id": "qualification:test", "policy_version": "test", "hard_disqualifiers": []}
        selected, _excluded = _select_evidence(self.profile, opportunity, matrix)
        content, omitted = _content_contract(self.profile, role_family, opportunity, selected, intelligence, matrix, qualification)
        storyline = content["storyline"]
        self.registry.validate("urn:careeros:schema:resume-storyline:v1", storyline)
        self.registry.validate("urn:careeros:schema:resume-completeness:v1", content["resume_completeness"])
        bullets = [bullet for section in [*content["employment"], *content["projects"]] for bullet in section["bullets"]]
        qa = content["job_specific_qa"]
        trace = build_tailoring_trace(intelligence, matrix, content, omitted, qualification)
        self.registry.validate("urn:careeros:schema:job-tailoring-trace:v1", trace)
        return {"opportunity": opportunity, "intelligence": intelligence, "matrix": matrix, "storyline": storyline, "bullets": bullets, "content": content, "qa": qa, "trace": trace}

    def test_requirement_extraction_preserves_source_and_unknown_is_not_hard(self):
        case = self.build_case("overnight-monitoring.json", self.soc)
        self.assertTrue(case["intelligence"]["requirements"])
        self.assertTrue(all(item["source_reference"]["quote"] for item in case["intelligence"]["requirements"]))
        schedule = next(row for row in case["matrix"]["requirements"] if row["requirement_subtype"] == "SCHEDULE")
        self.assertIn(schedule["coverage_class"], {"SUPPORTED_MATCH", "STRONG_SUPPORTED_MATCH", "UNKNOWN"})
        self.assertNotEqual(schedule["coverage_class"], "HARD_GAP")

    def test_same_candidate_three_soc_jobs_are_materially_adaptive(self):
        cases = [self.build_case(name, self.soc) for name in ("siem-heavy.json", "vulnerability-heavy.json", "overnight-monitoring.json")]
        self.assertEqual(sha256_value(self.profile), self.profile_hash)
        summaries = {case["content"]["summary"] for case in cases}
        first_projects = {case["content"]["projects"][0]["record_id"] for case in cases}
        bullet_sets = {tuple(item["bullet_id"] for item in case["bullets"]) for case in cases}
        self.assertEqual(len(summaries), 3)
        self.assertGreaterEqual(len(first_projects), 2)
        self.assertGreaterEqual(len(bullet_sets), 2)
        self.assertTrue(all(case["qa"]["status"] == "PASS" for case in cases), [case["qa"] for case in cases])

    def test_soc_and_noc_routing_change_project_and_bullet_selection(self):
        soc = self.build_case("siem-heavy.json", self.soc)
        noc = self.build_case("noc-heavy.json", self.noc)
        self.assertNotEqual(soc["content"]["projects"][0]["record_id"], noc["content"]["projects"][0]["record_id"])
        self.assertNotEqual([item["bullet_id"] for item in soc["bullets"]], [item["bullet_id"] for item in noc["bullets"]])
        self.assertGreaterEqual(lane_differentiation(soc["storyline"], noc["storyline"]), 0.3)

    def test_adaptive_variants_preserve_truth_boundary(self):
        case = self.build_case("siem-heavy.json", self.soc)
        for bullet in case["bullets"]:
            boundary = bullet["truth_boundary"]
            self.assertEqual(boundary["evidence_ids"], bullet["evidence_ids"])
            self.assertEqual(boundary["action"], bullet["action"])
            self.assertEqual(boundary["outcome"], bullet["outcome"])
            self.assertTrue(bullet["matched_requirement_ids"] or bullet.get("evidence_tier") in {"SUPPORTING", "TRANSFERABLE_PROFESSIONAL", "FOUNDATIONAL"})


if __name__ == "__main__":
    unittest.main()
