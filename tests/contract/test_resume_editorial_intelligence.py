from __future__ import annotations

import unittest
from pathlib import Path

from careeros.editorial import (
    build_bullet_candidates,
    default_public_display_policy,
    evaluate_editorial_quality,
    group_skills,
    lane_differentiation,
    plan_storyline,
    public_credentials,
    public_education,
    semantic_dedupe,
    system_artifact_leaks,
)
from careeros.schemas import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]


def record(record_id: str, **values):
    return {
        "record_id": record_id, "status": "ACTIVE", "verification_state": "VERIFIED",
        "visibility": "PUBLIC", "confidence": "HIGH", "provenance": [{"source_id": f"source:{record_id}"}],
        **values,
    }


def synthetic_profile():
    return {
        "candidate": {"public_name": "Ari Mercer", "location": "Example City", "contact": {"email": "ari.mercer@example.invalid", "phone": None, "urls": ["https://portfolio.example/ari"]}},
        "employment": [record("employment:service", employer="Beacon Community Desk", actual_title="Client Services Coordinator", start_year=2022, end_year="PRESENT", evidence_ids=["evidence:handoff"])],
        "education": [record("education:systems", institution="Example Coast College", program="Associate of Applied Science", field_of_study="Information Systems", completion_status="IN_PROGRESS", end_year=None)],
        "credentials": [
            record("credential:verified", title="Support Operations Certificate", issuer="Example Learning Guild", credential_state="COMPLETED", issued_date="2025-04", expiration_date=None),
            record("credential:unverified", title="Network Foundations Badge", issuer="Example Training Lab", credential_state="CLAIMED_COMPLETE", verification_state="NEEDS_VERIFICATION", issued_date=None, expiration_date=None),
        ],
        "skills": [
            record("skill:alerts", name="Alert Triage", category="Security Monitoring", aliases=[], contexts=["completed lab"], evidence_ids=["evidence:alerts"]),
            record("skill:network", name="Network Connectivity Analysis", category="Networking", aliases=["DNS"], contexts=["completed project"], evidence_ids=["evidence:network"]),
            record("skill:handoff", name="Shift Handoff Documentation", category="Operations", aliases=[], contexts=["client services"], evidence_ids=["evidence:handoff"]),
        ],
        "evidence": [
            record("evidence:alerts", evidence_type="PROJECT", summary="Analyze simulated alerts and document disposition notes", context="Completed monitoring lab", ownership="Individual", actions=["Investigate simulated alerts", "Document findings"], outcomes=["Produced a reviewed alert disposition log"], skill_ids=["skill:alerts"], employment_ids=[], project_ids=["project:alerts"], metric_boundaries=[], claim_boundaries=[]),
            record("evidence:network", evidence_type="PROJECT", summary="Analyze a fictional service interruption across name-resolution and connectivity checks", context="Completed network project", ownership="Individual", actions=["Analyze connectivity evidence"], outcomes=["Validated the likely failure domain and prepared a handoff"], skill_ids=["skill:network"], employment_ids=[], project_ids=["project:network"], metric_boundaries=[], claim_boundaries=[]),
            record("evidence:handoff", evidence_type="EMPLOYMENT", summary="Documented time-sensitive client issues for specialist handoff", context="Client services", ownership="Coordinator", actions=["Document client issues"], outcomes=["Supported consistent specialist handoff"], skill_ids=["skill:handoff"], employment_ids=["employment:service"], project_ids=[], metric_boundaries=[], claim_boundaries=[]),
            record("evidence:metric", evidence_type="PROJECT", summary="Reviewed 18 synthetic requests", context="Completed quality exercise", ownership="Individual", actions=["Review 18 synthetic requests"], outcomes=["Produced a categorized review log"], skill_ids=["skill:alerts"], employment_ids=[], project_ids=["project:alerts"], metric_boundaries=["Count of 18 is documented by the retained synthetic worksheet"], claim_boundaries=[]),
            record("evidence:unsupported", evidence_type="PROJECT", summary="Improved response time by 40%", context="Unmeasured practice exercise", ownership="Individual", actions=["Analyze response steps"], outcomes=["Drafted a process note"], skill_ids=["skill:network"], employment_ids=[], project_ids=["project:network"], metric_boundaries=[], claim_boundaries=["No measurement source exists"]),
        ],
        "projects": [
            record("project:alerts", name="Fictional Alert Review Lab", purpose="Practice evidence review", date_range=None, contribution="Reviewed simulated alerts", technologies=["Example SIEM"], skill_ids=["skill:alerts"], evidence_ids=["evidence:alerts", "evidence:metric"], artifact_references=[], claim_boundaries=[]),
            record("project:network", name="Fictional Connectivity Triage", purpose="Practice structured network triage", date_range="2025", contribution="Analyzed a synthetic outage", technologies=["DNS tools"], skill_ids=["skill:network"], evidence_ids=["evidence:network", "evidence:unsupported"], artifact_references=[], claim_boundaries=[]),
        ],
    }


def family(family_id: str, name: str, capabilities: list[str]):
    return {"role_family_id": family_id, "display_name": name, "label": name, "target_titles": [name], "core_capabilities": capabilities, "preferred_capabilities": [], "transferable_capabilities": ["Shift Handoff Documentation"], "skill_tags": capabilities}


class ResumeEditorialIntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry(ROOT / "src/careeros/schemas")
        cls.profile = synthetic_profile()
        cls.monitoring = family("role-family:monitoring", "Security Monitoring Associate", ["Alert Triage"])
        cls.network = family("role-family:network", "Network Support Technician", ["Network Connectivity Analysis"])

    def test_storyline_contract_and_lane_differentiation(self):
        first = plan_storyline(self.profile, self.monitoring)
        second = plan_storyline(self.profile, self.network)
        self.registry.validate("urn:careeros:schema:resume-storyline:v1", first)
        self.registry.validate("urn:careeros:schema:resume-storyline:v1", second)
        self.assertNotEqual(first["anchor_evidence"], second["anchor_evidence"])
        self.assertGreaterEqual(lane_differentiation(first, second), 0.3)

    def test_completed_voice_metrics_and_lineage(self):
        storyline = plan_storyline(self.profile, self.monitoring)
        bullets = build_bullet_candidates(self.profile, storyline)
        for item in bullets:
            self.registry.validate("urn:careeros:schema:resume-bullet-candidate:v1", item)
            self.assertTrue(item["evidence_ids"])
            self.assertTrue(item["source_lineage"])
        alert = next(item for item in bullets if item["evidence_ids"] == ["evidence:alerts"])
        self.assertTrue(alert["text"].startswith("Investigated"))
        supported = next(item for item in bullets if item["evidence_ids"] == ["evidence:metric"])
        unsupported = next(item for item in bullets if item["evidence_ids"] == ["evidence:unsupported"])
        self.assertTrue(supported["metric_refs"])
        self.assertEqual(supported["unsupported_metric_tokens"], [])
        self.assertEqual(unsupported["unsupported_metric_tokens"], [])
        self.assertEqual(unsupported["source_unsupported_metric_tokens"], ["40%"])

    def test_public_sanitization_credentials_dates_and_skill_groups(self):
        policy = default_public_display_policy()
        self.registry.validate("urn:careeros:schema:public-display-policy:v1", policy)
        displayed = public_credentials(self.profile, policy)
        self.assertEqual([item["record_id"] for item in displayed], ["credential:verified"])
        education = public_education(self.profile, policy)
        self.assertEqual(education[0]["display_status"], "In progress")
        self.assertNotIn("Date not supplied", str(education))
        groups = group_skills(self.profile, plan_storyline(self.profile, self.monitoring))
        self.assertTrue(groups)
        self.assertFalse(any("UNSPECIFIED" in str(item) for item in groups))
        self.assertEqual(system_artifact_leaks("Candidate completed a reviewed project."), [])
        self.assertIn("needs verification", system_artifact_leaks("Needs Verification"))

    def test_semantic_duplicate_keeps_strongest_and_quality_gate(self):
        base = {"evidence_ids": ["evidence:alerts"], "action": "Investigated alerts", "role_context": "lab", "deliverable": "alert notes", "outcome": "", "metric_refs": [], "text": "Investigated alerts."}
        stronger = {**base, "outcome": "Produced reviewed dispositions", "text": "Investigated alerts; produced reviewed dispositions."}
        self.assertEqual(semantic_dedupe([base, stronger]), [stronger])
        content = {"summary": "Career changer pursuing monitoring work through completed project evidence.", "target_role": "Monitoring Associate", "skills": [{"name": "Alert Triage"}], "storyline": plan_storyline(self.profile, self.monitoring), "employment": [], "projects": [{"bullets": [stronger]}]}
        quality = evaluate_editorial_quality(content)
        self.registry.validate("urn:careeros:schema:resume-editorial-quality:v1", quality)
        self.assertEqual(quality["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
