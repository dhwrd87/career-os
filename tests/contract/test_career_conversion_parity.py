from __future__ import annotations

import unittest
from pathlib import Path

from careeros.career_conversion import (
    build_career_conversion_trace,
    build_employer_need_trace,
    build_role_fact_set,
    evaluate_material_evidence_loss,
    strongest_evidence_omissions,
)
from careeros.resume_ats import build_recruiter_summary
from careeros.schemas import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]


def evidence(
    record_id: str, summary: str, *, employment_ids: list[str] | None = None,
    project_ids: list[str] | None = None, actions: list[str] | None = None,
    outcomes: list[str] | None = None, tools: list[str] | None = None,
    leadership: list[str] | None = None,
) -> dict:
    return {
        "record_id": record_id, "summary": summary, "context": "Synthetic conversion regression",
        "actions": actions or [summary], "outcomes": outcomes or [], "tools_methods": tools or [],
        "deliverables": [], "stakeholders": [], "scope": None, "frequency": None,
        "material_scope": [], "leadership_ownership": leadership or [],
        "employment_ids": employment_ids or [], "project_ids": project_ids or [], "skill_ids": [],
        "verification_state": "VERIFIED", "visibility": "PUBLIC", "status": "ACTIVE",
        "metrics": [], "recency_score": 0.8,
    }


def role(record_id: str, evidence_ids: list[str], *, start: int = 2020, end: int | str = 2025) -> dict:
    return {
        "record_id": record_id, "employer": "Fictional Northstar Cooperative",
        "actual_title": "Operations Specialist", "public_title": None,
        "start_month": None, "start_year": start, "end_month": None, "end_year": end,
        "date_precision": "YEAR", "location": "Example City", "employment_type": "FULL_TIME",
        "role_context": "Synthetic operations role", "evidence_ids": evidence_ids,
        "verification_state": "VERIFIED", "visibility": "PUBLIC",
    }


def project(record_id: str, evidence_ids: list[str]) -> dict:
    return {
        "record_id": record_id, "name": "Synthetic Signal Review", "date_range": "2025",
        "contribution": "Reviewed fictional system signals.", "evidence_ids": evidence_ids,
        "verification_state": "VERIFIED", "visibility": "PUBLIC",
    }


def profile(evidence_records: list[dict], *, employment: list[dict] | None = None, projects: list[dict] | None = None) -> dict:
    return {
        "profile_id": "profile:synthetic-conversion", "evidence": evidence_records,
        "employment": employment or [], "projects": projects or [], "skills": [],
        "credentials": [], "education": [], "preferences": {},
    }


def job_contract(candidate_evidence_ids: list[str], *, coverage: str = "STRONG_SUPPORTED_MATCH") -> tuple[dict, dict, dict]:
    snapshot = {
        "snapshot_id": "snapshot:synthetic-monitoring", "content_hash": "a" * 64,
        "text": (
            "Monitor service alerts and document incident handoffs for the operations team. "
            "Work with peers to investigate recurring events and communicate findings. "
            "Preferred qualifications include familiarity with reporting tools."
        ),
    }
    intelligence = {
        "intelligence_id": "jd-intelligence:synthetic", "opportunity_id": "job:synthetic-monitoring",
        "role_mission": {"value": "Monitor service alerts and document incident handoffs"},
        "repeated_emphasized_concepts": ["monitor", "incident"],
    }
    matrix = {
        "matrix_id": "matrix:synthetic-monitoring",
        "requirements": [{
            "requirement_id": "need:monitoring", "requirement_text": "Monitor service alerts and document incident handoffs",
            "requirement_class": "REQUIRED", "requirement_subtype": "SKILL", "importance": "CRITICAL",
            "candidate_evidence_ids": candidate_evidence_ids, "coverage_class": coverage,
            "evidence_strength": "HIGH", "resume_priority": 120,
        }],
    }
    return intelligence, matrix, snapshot


def content_for(
    *, employment_sections: list[dict] | None = None, project_sections: list[dict] | None = None,
    summary_ids: list[str] | None = None,
) -> dict:
    summary_ids = summary_ids or []
    return {
        "target_role": "Monitoring Analyst", "employment": employment_sections or [],
        "projects": project_sections or [], "skills": [], "storyline": {"evidence_rankings": []},
        "recruiter_summary": {
            "clauses": [{"summary_clause": "Supported monitoring work.", "source_evidence_ids": summary_ids}]
            if summary_ids else []
        },
    }


def section(record_id: str, evidence_ids: list[str], *, employment: bool = True) -> dict:
    base = {
        "record_id": record_id,
        "bullets": [{"bullet_id": f"bullet:{evidence_id}", "text": "Synthetic supported fact.", "evidence_ids": [evidence_id]} for evidence_id in evidence_ids],
    }
    if employment:
        base.update({"employer": "Fictional Northstar Cooperative", "actual_title": "Operations Specialist"})
    else:
        base.update({"name": "Synthetic Signal Review"})
    return base


class CareerConversionParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry(ROOT / "src/careeros/schemas")

    def test_01_strongest_evidence_omitted_in_favor_of_weaker_evidence(self) -> None:
        strong = evidence(
            "evidence:strong", "Investigated service alerts and documented incident handoffs",
            employment_ids=["employment:ops"], outcomes=["Produced an incident report"], tools=["Monitoring console"],
        )
        weak = evidence("evidence:weak", "Reviewed an alert example", project_ids=["project:signals"])
        p = profile([strong, weak])
        intelligence, matrix, snapshot = job_contract(["evidence:strong", "evidence:weak"])
        trace = build_employer_need_trace(intelligence, matrix, snapshot, content_for(project_sections=[section("project:signals", ["evidence:weak"], employment=False)]))
        result = strongest_evidence_omissions(p, trace, {"evidence:weak"})
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["findings"][0]["code"], "STRONGEST_EVIDENCE_OMITTED")

    def test_02_top_third_requirement_underrepresented(self) -> None:
        p = profile([evidence("evidence:monitor", "Monitored service alerts", project_ids=["project:signals"])])
        intelligence, matrix, snapshot = job_contract(["evidence:monitor"])
        trace = build_employer_need_trace(intelligence, matrix, snapshot, content_for())
        self.assertEqual(trace["needs"][0]["top_third_signal"], "TOP_THIRD")
        self.assertEqual(trace["top_third_coverage"]["status"], "FAIL")

    def test_03_long_role_compressed_until_material_facts_disappear(self) -> None:
        first = evidence("evidence:service", "Coordinated time-sensitive service requests", employment_ids=["employment:ops"])
        second = evidence("evidence:quality", "Documented quality reviews", employment_ids=["employment:ops"], outcomes=["Produced review records"])
        p = profile([first, second], employment=[role("employment:ops", ["evidence:service", "evidence:quality"], start=2018, end=2025)])
        facts = build_role_fact_set(p)
        loss = evaluate_material_evidence_loss(p, content_for(employment_sections=[section("employment:ops", ["evidence:service"])]), facts)
        self.assertGreaterEqual(loss["counts"]["MATERIAL_LOSS"], 1)

    def test_04_leadership_evidence_dropped(self) -> None:
        base = evidence("evidence:base", "Coordinated daily work", employment_ids=["employment:ops"])
        lead = evidence("evidence:lead", "Led peer handoffs", employment_ids=["employment:ops"], leadership=["Led peer handoffs"])
        p = profile([base, lead], employment=[role("employment:ops", ["evidence:base", "evidence:lead"])])
        loss = evaluate_material_evidence_loss(p, content_for(employment_sections=[section("employment:ops", ["evidence:base"])]), build_role_fact_set(p))
        self.assertTrue(any(item["dimension"] == "LEADERSHIP" and item["classification"] == "MATERIAL_LOSS" for item in loss["losses"]))

    def test_05_only_technical_evidence_dropped(self) -> None:
        base = evidence("evidence:base", "Coordinated daily work", employment_ids=["employment:ops"])
        technical = evidence("evidence:technical", "Automated log review with Python", employment_ids=["employment:ops"], tools=["Python"])
        p = profile([base, technical], employment=[role("employment:ops", ["evidence:base", "evidence:technical"])])
        loss = evaluate_material_evidence_loss(p, content_for(employment_sections=[section("employment:ops", ["evidence:base"])]), build_role_fact_set(p))
        self.assertTrue(any(item["dimension"] == "TECHNICAL" and item["classification"] == "MATERIAL_LOSS" for item in loss["losses"]))

    def test_06_duplicate_evidence_is_correctly_removed(self) -> None:
        duplicate = evidence("evidence:duplicate", "Documented the same synthetic handoff twice")
        p = profile([duplicate])
        loss = evaluate_material_evidence_loss(
            p, content_for(), build_role_fact_set(p), omission_reasons={"evidence:duplicate": "REDUNDANT"},
        )
        self.assertEqual(loss["counts"]["NON_MATERIAL"], 1)
        self.assertEqual(loss["counts"]["CRITICAL_LOSS"], 0)

    def test_07_two_page_budget_allowed_before_critical_loss(self) -> None:
        record = evidence("evidence:full", "Investigated and documented service alerts", employment_ids=["employment:ops"])
        p = profile([record], employment=[role("employment:ops", ["evidence:full"])])
        loss = evaluate_material_evidence_loss(p, content_for(employment_sections=[section("employment:ops", ["evidence:full"])]), build_role_fact_set(p))
        self.assertIn("ALLOW_TWO_PAGES_BEFORE_CRITICAL_LOSS", loss["document_budget_policy"])
        self.assertEqual(loss["status"], "PASS")

    def test_08_career_changer_transferable_evidence_is_explicit(self) -> None:
        record = evidence("evidence:transfer", "Documented real-time service handoffs", employment_ids=["employment:ops"])
        intelligence, matrix, snapshot = job_contract(["evidence:transfer"], coverage="TRANSFERABLE_MATCH")
        trace = build_employer_need_trace(
            intelligence, matrix, snapshot,
            content_for(employment_sections=[section("employment:ops", ["evidence:transfer"])], summary_ids=["evidence:transfer"]),
        )
        self.assertEqual(trace["needs"][0]["coverage_class"], "TRANSFERABLE_ONLY")

    def test_09_project_heavy_entry_candidate_preserves_project_facts(self) -> None:
        record = evidence("evidence:project", "Investigated synthetic service alerts", project_ids=["project:signals"], tools=["Log console"])
        p = profile([record], projects=[project("project:signals", ["evidence:project"])])
        conversion = build_career_conversion_trace(
            p, content_for(project_sections=[section("project:signals", ["evidence:project"], employment=False)]), build_scope="LANE",
        )
        self.assertTrue(conversion["gates"]["ROLE_FACT_PRESERVATION"])
        self.assertEqual(conversion["critical_losses"], 0)

    def test_10_experienced_multi_role_candidate_preserves_each_role(self) -> None:
        one = evidence("evidence:one", "Coordinated service requests", employment_ids=["employment:one"])
        two = evidence("evidence:two", "Documented stakeholder updates", employment_ids=["employment:two"])
        p = profile(
            [one, two], employment=[role("employment:one", ["evidence:one"]), role("employment:two", ["evidence:two"], start=2016, end=2019)],
        )
        conversion = build_career_conversion_trace(
            p, content_for(employment_sections=[section("employment:one", ["evidence:one"]), section("employment:two", ["evidence:two"])]), build_scope="MASTER",
        )
        self.assertEqual(conversion["material_evidence_loss"]["role_fact_preservation"]["status"], "PASS")

    def test_contracts_validate_and_summary_consults_employer_need(self) -> None:
        record = evidence("evidence:monitor", "Investigated service alerts and documented handoffs", project_ids=["project:signals"], tools=["Monitoring console"])
        p = profile([record], projects=[project("project:signals", ["evidence:monitor"])])
        intelligence, matrix, snapshot = job_contract(["evidence:monitor"])
        c = content_for(project_sections=[section("project:signals", ["evidence:monitor"], employment=False)], summary_ids=["evidence:monitor"])
        need_trace = build_employer_need_trace(intelligence, matrix, snapshot, c)
        summary = build_recruiter_summary(
            p, {"evidence_rankings": [{"evidence_id": "evidence:monitor", "classification": "ANCHOR"}]},
            {"role_family_id": "role-family:monitoring", "display_name": "Monitoring Operations", "core_capabilities": []},
            opportunity={"role_title": "Monitoring Analyst"}, selected_evidence_ids={"evidence:monitor"}, employer_need_trace=need_trace,
        )
        self.assertIn("Investigated service alerts", summary["text"])
        self.assertNotIn("directly addressing the need", summary["text"])
        self.assertIn("evidence:monitor", summary["clauses"][1]["source_evidence_ids"])
        conversion = build_career_conversion_trace(
            p, c, build_scope="TARGETED", employer_need_trace=need_trace,
        )
        for urn, contract in (
            ("urn:careeros:schema:employer-need-trace:v1", need_trace),
            ("urn:careeros:schema:strongest-evidence-omission:v1", conversion["strongest_evidence_omission"]),
            ("urn:careeros:schema:role-fact-set:v1", conversion["role_fact_set"]),
            ("urn:careeros:schema:material-evidence-loss:v1", conversion["material_evidence_loss"]),
            ("urn:careeros:schema:career-conversion-trace:v1", conversion),
        ):
            self.registry.validate(urn, contract)


if __name__ == "__main__":
    unittest.main()
