from __future__ import annotations

import unittest

from careeros.core.io import sha256_value
from careeros.interview_prep import (
    accept_interview_evidence_pack,
    build_interview_evidence_pack,
    build_story_bank,
    evaluate_pack_freshness,
)


NOW = "2026-10-11T12:00:00Z"


def evidence(
    evidence_id: str, summary: str, *, context: str = "PROJECT", actions: list[str] | None = None,
    outcomes: list[str] | None = None, tools: list[str] | None = None,
    stakeholders: list[str] | None = None, leadership: list[str] | None = None,
    metrics: list[dict] | None = None,
) -> dict:
    return {
        "record_id": evidence_id, "summary": summary, "context": summary,
        "evidence_context": context, "actions": actions or [summary], "outcomes": outcomes or [],
        "tools_methods": tools or [], "stakeholders": stakeholders or [],
        "leadership_ownership": leadership or [], "metrics": metrics or [], "scale": [],
        "claim_boundaries": [], "metric_boundaries": [], "employment_ids": ["employment:fictional"] if context == "PROFESSIONAL_EMPLOYMENT" else [],
        "project_ids": ["project:fictional"] if context != "PROFESSIONAL_EMPLOYMENT" else [],
        "verification_state": "VERIFIED", "visibility": "PUBLIC", "status": "ACTIVE",
    }


def profile(records: list[dict]) -> dict:
    return {
        "profile_id": "profile:fictional-interview", "canonical_revision": 4,
        "evidence": records, "employment": [], "projects": [], "skills": [], "credentials": [],
        "education": [], "preferences": {"target_roles": ["Fictional Monitoring Analyst"]},
    }


def job(evidence_ids: list[str], *, coverage: str = "STRONGLY_COVERED") -> tuple[dict, dict, dict, dict]:
    opportunity = {"opportunity_id": "opportunity:fictional", "role_title": "Monitoring Analyst", "employer": "Fictional Northstar Cooperative"}
    snapshot = {"snapshot_id": "snapshot:fictional", "content_hash": "a" * 64}
    need = {
        "need_id": "need:monitor", "need_statement": "Monitor alerts, investigate events, and document escalations",
        "need_type": "SECURITY", "importance": "CRITICAL", "top_third_signal": "TOP_THIRD",
        "coverage_class": coverage, "candidate_evidence_ids": evidence_ids,
        "source_refs": [{"snapshot_id": snapshot["snapshot_id"], "locator": "text.char[0]", "quote": "Monitor alerts, investigate events, and document escalations"}],
    }
    trace = {"trace_id": "employer-need-trace:fictional", "needs": [need]}
    qualification = {"qualification_id": "qualification:fictional", "decision": "QUALIFIED", "gaps": []}
    return opportunity, snapshot, trace, qualification


def build(records: list[dict], *, stage: str = "TECHNICAL", coverage: str = "STRONGLY_COVERED"):
    p = profile(records)
    opportunity, snapshot, trace, qualification = job([item["record_id"] for item in records], coverage=coverage)
    return build_interview_evidence_pack(
        profile=p, opportunity=opportunity, snapshot=snapshot, qualification=qualification,
        employer_need_trace=trace, application_id="application:fictional", interview_id="interview:fictional",
        stage=stage, role_family={"role_family_id": "role-family:fictional"}, timestamp=NOW,
    )


class InterviewEvidencePackParityTests(unittest.TestCase):
    def test_01_career_changer_project_evidence_keeps_boundary(self):
        pack, bank, _ = build([evidence("evidence:lab", "Investigated simulated alerts", context="LAB", tools=["Fictional SIEM"])])
        story = bank["stories"][0]
        self.assertFalse(story["professional_context"])
        self.assertTrue(any("professional employment" in item for item in story["prohibited_inferences"]))
        self.assertTrue(pack["qa_gates"]["PROFESSIONAL_EQUIVALENCE"])

    def test_02_experienced_professional_retains_leadership_story(self):
        pack, bank, _ = build([evidence("evidence:lead", "Led a service handoff", context="PROFESSIONAL_EMPLOYMENT", leadership=["Led peer handoff"], outcomes=["Completed the handoff"] )], stage="HIRING_MANAGER")
        self.assertTrue(bank["stories"][0]["professional_context"])
        self.assertIn(bank["stories"][0]["story_id"], pack["selected_story_ids"])

    def test_03_weak_outcome_remains_unknown(self):
        pack, bank, _ = build([evidence("evidence:no-result", "Reviewed fictional alerts", tools=["Log viewer"])])
        self.assertIsNone(bank["stories"][0]["outcome"])
        self.assertIn("Not established in source evidence", pack["technical_walkthroughs"][0]["RESULT"])

    def test_04_project_heavy_candidate_gets_multiple_stories(self):
        records = [
            evidence("evidence:one", "Investigated synthetic alerts", tools=["Log viewer"]),
            evidence("evidence:two", "Documented a synthetic escalation", tools=["Ticket queue"]),
            evidence("evidence:three", "Validated a fictional configuration", tools=["Scanner"]),
        ]
        pack, _, _ = build(records)
        self.assertGreaterEqual(len(pack["selected_story_ids"]), 2)

    def test_05_hard_gap_produces_answer_boundary(self):
        p = profile([])
        opportunity, snapshot, trace, qualification = job([], coverage="GAP")
        qualification["gaps"] = [{"requirement_id": "need:monitor"}]
        pack, _, _ = build_interview_evidence_pack(profile=p, opportunity=opportunity, snapshot=snapshot, qualification=qualification, employer_need_trace=trace, application_id="application:fictional", interview_id="interview:fictional", stage="TECHNICAL", timestamp=NOW)
        self.assertTrue(pack["gap_boundaries"])
        self.assertTrue(any("Do not invent" in text for row in pack["gap_boundaries"] for text in row["must_not_imply"]))

    def test_06_no_supporting_story_is_not_fabricated(self):
        p = profile([])
        opportunity, snapshot, trace, qualification = job([], coverage="UNKNOWN")
        pack, bank, _ = build_interview_evidence_pack(profile=p, opportunity=opportunity, snapshot=snapshot, qualification=qualification, employer_need_trace=trace, application_id="application:fictional", interview_id="interview:fictional", stage="HIRING_MANAGER", timestamp=NOW)
        self.assertEqual(bank["stories"], [])
        self.assertEqual(pack["selected_story_ids"], [])
        self.assertTrue(all(item["story_id"] is None for item in pack["story_shortlist"]["theme_assignments"]))

    def test_07_canonical_update_invalidates_pack(self):
        p = profile([evidence("evidence:one", "Investigated synthetic alerts")])
        pack, _, _ = build([p["evidence"][0]])
        freshness = evaluate_pack_freshness(pack, current_profile_hash="b" * 64, current_job_hash="a" * 64)
        self.assertEqual(freshness["status"], "STALE")
        self.assertIn("CANONICAL_EVIDENCE_CHANGED", freshness["reasons"])

    def test_08_jd_update_invalidates_pack(self):
        pack, _, _ = build([evidence("evidence:one", "Investigated synthetic alerts")])
        freshness = evaluate_pack_freshness(pack, current_profile_hash=pack["lineage"]["candidate_profile_hash"], current_job_hash="c" * 64)
        self.assertEqual(freshness["pack_status"], "STALE")
        self.assertIn("JOB_SNAPSHOT_CHANGED", freshness["reasons"])

    def test_09_technical_interview_has_walkthroughs_and_probes(self):
        pack, _, _ = build([
            evidence("evidence:one", "Investigated synthetic alerts", tools=["Log viewer"], outcomes=["Documented findings"]),
            evidence("evidence:two", "Validated a fictional scan", tools=["Scanner"], outcomes=["Recorded validation"]),
        ])
        self.assertEqual(len(pack["technical_walkthroughs"]), 2)
        self.assertEqual(len(pack["follow_up_probes"]), 2)

    def test_10_recruiter_screen_has_transition_plan_and_human_acceptance(self):
        pack, bank, boundaries = build([evidence("evidence:transfer", "Documented professional handoffs", context="PROFESSIONAL_EMPLOYMENT")], stage="RECRUITER_SCREEN")
        self.assertTrue(pack["career_transition_prep"])
        self.assertTrue(any(item["category"] == "CAREER_TRANSITION" for item in pack["likely_question_themes"]))
        accepted = accept_interview_evidence_pack(pack, human_confirmed=True)
        self.assertEqual(accepted["pack_status"], "ACCEPTED")
        self.assertEqual(bank["candidate_profile_hash"], sha256_value(profile([evidence("evidence:transfer", "Documented professional handoffs", context="PROFESSIONAL_EMPLOYMENT")])))
        self.assertEqual(boundaries["schema"], "careeros.interview-answer-boundary.v1")

    def test_unqualified_opportunity_fails_closed(self):
        p = profile([])
        opportunity, snapshot, trace, qualification = job([])
        qualification["decision"] = "NOT_QUALIFIED"
        with self.assertRaisesRegex(ValueError, "qualified opportunity"):
            build_interview_evidence_pack(profile=p, opportunity=opportunity, snapshot=snapshot, qualification=qualification, employer_need_trace=trace, application_id="application:fictional", interview_id="interview:fictional", stage="TECHNICAL", timestamp=NOW)


if __name__ == "__main__":
    unittest.main()
