from __future__ import annotations

import json
import unittest
from pathlib import Path

from careeros.recruiter_conversion import (
    build_recruiter_conversion_strategy,
    build_recruiter_summary_v2,
    jd_paraphrase_findings,
    public_copy_boundary,
    recruiter_copy_quality_v2,
    render_recruiter_bullet_v2,
    targeted_editorial_regression,
)
from careeros.schemas import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]


def evidence(record_id: str, *, professional: bool = False, project: bool = True, action: str, outcome: str, tool: str | None = None):
    return {
        "record_id": record_id, "visibility": "PUBLIC", "verification_state": "VERIFIED",
        "employment_ids": ["employment:fictional"] if professional else [],
        "project_ids": ["project:fictional"] if project else [],
        "actions": [action], "outcomes": [outcome], "tools_methods": [tool] if tool else [],
    }


def profile(*, hard_gap: bool = False):
    return {
        "profile_id": "profile:fictional-copy-v2",
        "candidate": {"public_name": "Avery Rowan"},
        "preferences": {"schedule_preferences": ["NIGHT"]},
        "skills": [
            {"record_id": "skill:splunk", "name": "Splunk", "category": "Security", "visibility": "PUBLIC", "evidence_ids": ["evidence:splunk"]},
            {"record_id": "skill:python", "name": "Python", "category": "Programming", "visibility": "PUBLIC", "evidence_ids": ["evidence:python"]},
            {"record_id": "skill:english", "name": "English", "category": "Language", "visibility": "PUBLIC", "evidence_ids": []},
            {"record_id": "skill:spanish", "name": "Spanish", "category": "Language", "visibility": "PUBLIC", "evidence_ids": []},
        ],
        "employment": [{"record_id": "employment:fictional"}],
        "evidence": [
            evidence("evidence:splunk", action="Investigated simulated authentication anomalies", outcome="Produced a documented findings report", tool="Splunk"),
            evidence("evidence:python", action="Processed synthetic machine logs", outcome="Created a categorized review file", tool="Python"),
            evidence("evidence:handoff", professional=True, project=False, action="Documented time-sensitive client issues", outcome="Supported consistent specialist handoffs"),
        ],
        "hard_gaps": ["Professional SOC tenure"] if hard_gap else [],
    }


def family():
    return {
        "role_family_id": "security-operations", "display_name": "Security Monitoring Analyst",
        "core_capabilities": ["Splunk", "Python"], "common_gaps": ["Professional SOC tenure"],
    }


def need_trace():
    return {"needs": [{
        "need_id": "need:monitoring", "need_statement": "Monitor security alerts and document escalation decisions for the operations team",
        "importance": "CRITICAL", "top_third_signal": "TOP_THIRD", "frequency": 3,
        "candidate_evidence_ids": ["evidence:splunk"],
    }]}


def good_content(summary: str, *, target: str = "Security Monitoring Analyst"):
    evidence_ids = ["evidence:splunk", "evidence:python", "evidence:handoff"]
    return {
        "target_role": target, "summary": summary,
        "resume_header": {"positioning_headline": target},
        "recruiter_summary": {"clauses": [{"source_evidence_ids": evidence_ids, "approved_config_source": None}]},
        "employment": [{"bullets": [{"text": "Documented time-sensitive client issues and supported consistent specialist handoffs.", "evidence_ids": ["evidence:handoff"]}]}],
        "projects": [{"bullets": [
            {"text": "Investigated simulated authentication anomalies with Splunk and produced a documented findings report.", "evidence_ids": ["evidence:splunk"]},
            {"text": "Processed synthetic machine logs with Python and created a categorized review file.", "evidence_ids": ["evidence:python"]},
        ]}],
    }


class RecruiterConversionCopyEngineV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry(ROOT / "src/careeros/schemas")
        cls.selected = {"evidence:splunk", "evidence:python", "evidence:handoff"}

    def test_01_career_changer_uses_specific_project_evidence(self):
        strategy = build_recruiter_conversion_strategy(profile(), family(), opportunity={"role_title": "Tier 1 SOC Analyst"}, employer_need_trace=need_trace(), selected_evidence_ids=self.selected)
        summary = build_recruiter_summary_v2(profile(), {}, family(), opportunity={"role_title": "Tier 1 SOC Analyst"}, employer_need_trace=need_trace(), selected_evidence_ids=self.selected, strategy=strategy)
        self.registry.validate("urn:careeros:schema:recruiter-conversion-strategy:v2", strategy)
        self.assertIn("Splunk", summary["text"])
        self.assertNotIn("professional SOC", summary["text"].casefold())

    def test_02_experienced_worker_keeps_professional_bridge(self):
        summary = build_recruiter_summary_v2(profile(), {}, family(), selected_evidence_ids=self.selected)
        self.assertIn("Professional experience", summary["text"])
        self.assertTrue(summary["career_transition_boundary"])

    def test_03_hard_gap_remains_internal(self):
        strategy = build_recruiter_conversion_strategy(profile(hard_gap=True), family(), selected_evidence_ids=self.selected)
        summary = build_recruiter_summary_v2(profile(hard_gap=True), {}, family(), selected_evidence_ids=self.selected, strategy=strategy)
        self.assertIn("Professional SOC tenure", strategy["internal_risks_gaps"])
        self.assertNotIn("tenure", summary["text"].casefold())

    def test_04_technical_support_bridge_keeps_target_specific(self):
        support = {"role_family_id": "technical-support", "display_name": "Technical Support Specialist", "core_capabilities": ["Python"]}
        summary = build_recruiter_summary_v2(profile(), {}, support, opportunity={"role_title": "Technical Support Specialist"}, selected_evidence_ids=self.selected)
        self.assertIn("Technical Support Specialist", summary["text"])

    def test_05_soc_lab_does_not_become_employment(self):
        summary = build_recruiter_summary_v2(profile(), {}, family(), opportunity={"role_title": "SOC Analyst I"}, selected_evidence_ids=self.selected)
        self.assertIn("hands-on", summary["text"].casefold())
        self.assertNotIn("SOC analyst experience", summary["text"].casefold())

    def test_06_jd_language_mimicry_is_detected(self):
        content = good_content("Monitor security alerts and document escalation decisions for the operations team while supporting Splunk investigations and Python log review across structured workflows.")
        self.assertTrue(jd_paraphrase_findings(content, need_trace()))

    def test_07_future_tense_overuse_fails_boundary(self):
        content = good_content("Ready to support security monitoring while prepared to learn Splunk workflows and build toward a future analyst role through project work and careful documentation.")
        self.assertEqual(public_copy_boundary(content)["status"], "FAIL")

    def test_08_governance_disclaimer_leak_fails_boundary(self):
        content = good_content("Security-focused candidate presenting verified evidence without overstating project work as professional experience within established boundaries and qualification policy.")
        result = public_copy_boundary(content)
        self.assertEqual(result["status"], "FAIL")
        self.assertGreaterEqual(result["finding_count"], 2)

    def test_09_generic_ai_summary_fails_quality(self):
        content = good_content("Results-driven dynamic professional leveraging a proven track record and passionate approach to deliver value across changing technology environments and collaborative business priorities.")
        strategy = build_recruiter_conversion_strategy(profile(), family(), selected_evidence_ids=self.selected)
        self.assertEqual(recruiter_copy_quality_v2(content, strategy=strategy)["status"], "FAIL")

    def test_10_strong_targeted_copy_meets_or_beats_base(self):
        base_summary = "Security-focused professional with hands-on Splunk and Python project work. Investigated simulated authentication anomalies, documented findings, and processed synthetic machine logs. Professional client-service experience adds clear communication and dependable handoffs across time-sensitive work."
        target_summary = "Security monitoring professional with hands-on Splunk and Python project work. Investigated simulated authentication anomalies, documented indicators, and produced escalation-ready findings. Professional client-service experience adds confidentiality-sensitive communication, precise documentation, and dependable handoffs for a Tier 1 SOC team."
        base, target = good_content(base_summary), good_content(target_summary, target="Tier 1 SOC Analyst")
        strategy = build_recruiter_conversion_strategy(profile(), family(), selected_evidence_ids=self.selected)
        base["recruiter_conversion_strategy_v2"] = strategy
        target["recruiter_conversion_strategy_v2"] = strategy
        self.assertEqual(targeted_editorial_regression(base, target)["status"], "PASS")

    def test_11_targeted_copy_worse_than_base_fails(self):
        base = good_content("Security-focused professional with hands-on Splunk and Python project work. Investigated simulated authentication anomalies, documented indicators, and produced escalation-ready findings. Professional client-service experience adds confidentiality-sensitive communication, precise documentation, and dependable handoffs for a Tier 1 SOC team.")
        target = good_content("Ready to learn security and prepared to support the team within established boundaries.")
        strategy = build_recruiter_conversion_strategy(profile(), family(), selected_evidence_ids=self.selected)
        base["recruiter_conversion_strategy_v2"] = strategy
        target["recruiter_conversion_strategy_v2"] = strategy
        self.assertEqual(targeted_editorial_regression(base, target)["status"], "FAIL")

    def test_12_supported_metric_survives_bullet_copy(self):
        bullet = render_recruiter_bullet_v2({
            "action": "Reviewed 24 synthetic alerts", "tool_or_method": "Splunk", "outcome": "Produced a categorized disposition log",
            "role_context": "completed monitoring lab", "evidence_ids": ["evidence:metric"],
            "metric_refs": [{"value": "24", "verification_class": "VERIFIED"}], "unsupported_metric_tokens": [],
        })
        self.assertIn("24", bullet["text"])
        self.assertEqual(bullet["metric_refs"][0]["value"], "24")
        self.assertEqual(bullet["evidence_ids"], ["evidence:metric"])

    def test_golden_recruiter_copy_cases(self):
        fixture = json.loads((ROOT / "fixtures/synthetic/recruiter-copy-v2/golden-cases.json").read_text())
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                content = good_content(case["summary"], target=case["target_role"])
                strategy = {"key_differentiator": case["differentiator"]}
                result = recruiter_copy_quality_v2(content, strategy=strategy)
                self.registry.validate("urn:careeros:schema:recruiter-copy-quality:v2", result)
                self.assertEqual(result["status"], "PASS", result)
                self.assertGreaterEqual(result["score"], 9.3)


if __name__ == "__main__":
    unittest.main()

class SummaryBatchTests(unittest.TestCase):
    def test_formula_repetition_ignores_identity_and_preserves_factual_difference(self):
        from careeros.recruiter_conversion import cross_summary_templates
        contents=[{'target_role':'Support Analyst','summary':'Support Analyst-focused professional with hands-on Python project work.'},{'target_role':'Systems Analyst','summary':'Systems Analyst-focused professional with hands-on Python project work.'}]
        self.assertEqual(cross_summary_templates(contents,{})['status'],'REVIEW')
        contents[1]['summary']='Systems Analyst-focused professional with hands-on SQL project work.'
        self.assertEqual(cross_summary_templates(contents,{})['status'],'PASS')
