from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from careeros.completeness import evaluate_resume_completeness
from careeros.core.io import sha256_value
from careeros.editorial import plan_storyline
from careeros.job_intelligence import analyze_job_description, build_job_evidence_matrix
from careeros.resume import _content_contract, _select_evidence
from careeros.schemas import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/synthetic/job-tailoring"


def read(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def family() -> dict:
    return {
        "role_family_id": "role-family:synthetic-monitoring", "display_name": "Security Monitoring Associate",
        "target_titles": ["Security Monitoring Associate"],
        "core_capabilities": ["SIEM Alert Investigation", "Vulnerability Remediation", "Network Connectivity Analysis"],
        "preferred_capabilities": [], "transferable_capabilities": ["Documentation", "Escalation", "Customer Communication"],
        "skill_tags": ["SIEM", "Security Monitoring", "Network Analysis"],
    }


def add_project(profile: dict, number: int, *, anchor: bool = False) -> None:
    evidence_id = f"evidence:depth-{number}"
    project_id = f"project:depth-{number}"
    skill_id = f"skill:depth-{number}"
    supporting_labels = {
        1: "SIEM alert investigation",
        2: "incident response documentation",
        3: "network and DDoS analysis",
        4: "vulnerability remediation validation",
        5: "security automation scripting",
    }
    label = "SIEM alert investigation" if anchor else supporting_labels[number]
    profile["skills"].append({
        "record_id": skill_id, "name": label.title(), "category": "Security Monitoring", "visibility": "PUBLIC",
        "evidence_ids": [evidence_id], "status": "ACTIVE", "verification_state": "VERIFIED", "confidence": "HIGH",
        "provenance": [{"source_id": f"source:{skill_id}"}], "aliases": [], "contexts": ["completed fictional project"],
    })
    profile["evidence"].append({
        "record_id": evidence_id, "evidence_type": "PROJECT", "summary": f"Completed fictional {label}",
        "context": "Completed synthetic portfolio project", "ownership": "Individual",
        "actions": [f"Complete fictional {label}"], "outcomes": [f"Produced a distinct {label} deliverable"],
        "skill_ids": [skill_id], "employment_ids": [], "project_ids": [project_id], "metric_boundaries": [],
        "claim_boundaries": [], "visibility": "PUBLIC", "status": "ACTIVE", "verification_state": "VERIFIED",
        "confidence": "HIGH", "provenance": [{"source_id": f"source:{evidence_id}"}],
    })
    profile["projects"].append({
        "record_id": project_id, "name": f"Fictional Monitoring Project {number}", "purpose": "Synthetic regression",
        "date_range": "2026", "contribution": "Analyzed fictional evidence", "technologies": ["Example Monitor"],
        "skill_ids": [skill_id], "evidence_ids": [evidence_id], "artifact_references": [], "claim_boundaries": [],
        "visibility": "PUBLIC", "status": "ACTIVE", "verification_state": "VERIFIED", "confidence": "HIGH",
        "provenance": [{"source_id": f"source:{project_id}"}],
    })


def add_employment(profile: dict, number: int) -> None:
    employment_id = f"employment:transfer-{number}"
    evidence_id = f"evidence:transfer-{number}"
    profile["employment"].append({
        "record_id": employment_id, "employer": f"Fictional Service Organization {number}",
        "actual_title": "Client Operations Coordinator", "public_title": None,
        "start_year": 2020 + number, "end_year": 2021 + number, "evidence_ids": [evidence_id],
        "visibility": "PUBLIC", "status": "ACTIVE", "verification_state": "VERIFIED", "confidence": "HIGH",
        "provenance": [{"source_id": f"source:{employment_id}"}],
    })
    profile["evidence"].append({
        "record_id": evidence_id, "evidence_type": "EMPLOYMENT", "summary": "Documented time-sensitive customer issues",
        "context": "Fictional client operations", "ownership": "Coordinator", "actions": ["Document customer issues"],
        "outcomes": ["Prepared accurate escalation handoffs"], "skill_ids": [], "employment_ids": [employment_id],
        "project_ids": [], "metric_boundaries": [], "claim_boundaries": [], "visibility": "PUBLIC", "status": "ACTIVE",
        "verification_state": "VERIFIED", "confidence": "HIGH", "provenance": [{"source_id": f"source:{evidence_id}"}],
    })


def compile_profile(profile: dict) -> tuple[dict, list[dict]]:
    raw = read("siem-heavy.json")
    opportunity = {key: raw[key] for key in ("opportunity_id", "role_title", "employer_name", "requirements")}
    snapshot = {
        "snapshot_id": "snapshot:depth", "opportunity_id": opportunity["opportunity_id"],
        "content_hash": sha256_value(raw["job_description"]), "text": raw["job_description"],
    }
    intelligence = analyze_job_description(opportunity, snapshot)
    matrix = build_job_evidence_matrix(profile, intelligence)
    selected, _ = _select_evidence(profile, opportunity, matrix)
    qualification = {"qualification_id": "qualification:depth", "policy_version": "test", "hard_disqualifiers": []}
    return _content_contract(profile, family(), opportunity, selected, intelligence, matrix, qualification)


class ResumeCompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry(ROOT / "src/careeros/schemas")

    def test_career_changer_preserves_rich_transferable_history(self):
        profile = read("profile.json")
        add_employment(profile, 1)
        add_employment(profile, 2)
        content, _ = compile_profile(profile)
        self.assertGreaterEqual(len(content["employment"]), 3)
        self.assertTrue(all(item["display_mode"] in {"FULL", "COMPACT", "MINIMAL"} for item in content["employment"]))
        self.assertEqual(content["resume_completeness"]["professional_history_coverage"]["status"], "PASS")

    def test_five_projects_keep_breadth_without_dumping_every_project(self):
        profile = read("profile.json")
        add_project(profile, 4)
        add_project(profile, 5)
        content, _ = compile_profile(profile)
        self.assertEqual(len(content["projects"]), 4)
        self.assertEqual(content["resume_completeness"]["technical_project_coverage"]["status"], "PASS")

    def test_one_anchor_and_four_supporting_projects_are_not_starved(self):
        profile = read("profile.json")
        profile["projects"] = []
        profile["evidence"] = [item for item in profile["evidence"] if not item.get("project_ids")]
        profile["skills"] = [item for item in profile["skills"] if not item.get("evidence_ids")]
        for number in range(1, 6):
            add_project(profile, number, anchor=number == 1)
        content, _ = compile_profile(profile)
        self.assertEqual(len(content["projects"]), 4)
        self.assertGreaterEqual(content["resume_completeness"]["supporting_evidence_count"]["included"], 2)

    def test_underfilled_page_with_unused_positive_evidence_fails(self):
        profile = read("profile.json")
        storyline = plan_storyline(profile, family())
        storyline["evidence_rankings"] = [{"evidence_id": item["record_id"], "classification": "SUPPORTING", "score": 1} for item in profile["evidence"]]
        content = {"target_role": "Monitoring Associate", "summary": "Synthetic summary.", "storyline": storyline, "skills": [], "skill_groups": [], "employment": [], "projects": [], "display_education": [], "display_credentials": []}
        result = evaluate_resume_completeness(profile, content, [])
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["page_utilization"]["underfilled"])
        self.assertTrue(result["unused_supported_evidence"])

    def test_overfilled_estimate_is_review_not_hidden(self):
        profile = read("profile.json")
        content, _ = compile_profile(profile)
        content["employment"] = content["employment"] * 8
        content["projects"] = content["projects"] * 8
        result = evaluate_resume_completeness(profile, content, [])
        self.assertTrue(result["page_utilization"]["overfilled"])
        self.assertIn(result["status"], {"REVIEW", "FAIL"})

    def test_multiple_concurrent_jobs_remain_visible(self):
        profile = read("profile.json")
        add_employment(profile, 1)
        add_employment(profile, 2)
        profile["employment"][-1]["start_year"] = profile["employment"][-2]["start_year"]
        content, _ = compile_profile(profile)
        selected = {item["record_id"] for item in content["employment"]}
        self.assertIn("employment:transfer-1", selected)
        self.assertIn("employment:transfer-2", selected)

    def test_thin_profile_uses_adaptive_floor(self):
        profile = read("profile.json")
        profile["projects"] = profile["projects"][:1]
        keep = set(profile["projects"][0]["evidence_ids"])
        profile["evidence"] = [item for item in profile["evidence"] if item.get("employment_ids") or item["record_id"] in keep]
        content, _ = compile_profile(profile)
        self.assertEqual(content["resume_completeness"]["technical_project_coverage"]["expected"], 1)
        self.assertEqual(content["resume_completeness"]["technical_project_coverage"]["included"], 1)

    def test_credential_rich_candidate_preserves_publicly_permitted_records(self):
        profile = read("profile.json")
        profile["credentials"] = [
            {"record_id": f"credential:synthetic-{index}", "title": f"Fictional Credential {index}", "issuer": "Example Credential Board", "credential_state": "COMPLETED", "verification_state": "VERIFIED", "visibility": "PUBLIC", "issued_date": "2026-01", "expiration_date": None}
            for index in range(3)
        ]
        content, _ = compile_profile(profile)
        self.assertEqual(len(content["display_credentials"]), 3)
        self.assertEqual(content["resume_completeness"]["credential_coverage"]["status"], "PASS")
        self.registry.validate("urn:careeros:schema:resume-completeness:v1", content["resume_completeness"])


if __name__ == "__main__":
    unittest.main()
