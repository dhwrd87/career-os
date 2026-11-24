from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from careeros.career_outputs import master_resume_content
from careeros.editorial import public_education
from careeros.job_intelligence import render_adaptive_bullet
from careeros.resume import render_pdf
from careeros.resume_governance import (
    build_freshness_contract,
    career_advancement_signals,
    compare_freshness,
    credential_opportunities,
    evidence_utility,
    new_evidence_utilization,
    professional_history_sufficiency,
    public_artifact_title,
    public_label_leaks,
    recruiter_copy_specificity,
    targeted_resume_delta,
)
from careeros.schemas import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "fixtures/synthetic/job-tailoring/profile.json"
NOW = "2026-10-10T12:00:00Z"


def profile() -> dict:
    result = json.loads(PROFILE.read_text(encoding="utf-8"))
    result.setdefault("profile_id", "career-profile:synthetic-governance")
    return result


def freshness(p: dict, revision: int = 1, **overrides) -> dict:
    result = build_freshness_contract(
        p, {"profile_hash": "a" * 64}, {"role_family_id": "role-family:generic"},
        {"storyline_id": "storyline:generic"}, canonical_revision=revision,
        compiler_version="test", editorial_policy_version="test", build_timestamp=NOW,
        jd_snapshot={"content_hash": "b" * 64},
    )
    result.update(overrides)
    return result


class ResumeFreshnessPublicQualityTests(unittest.TestCase):
    def test_career_changer_long_non_target_role_is_compressed_not_erased(self):
        employment = [{"record_id": "employment:long", "start_year": 2014, "end_year": 2024, "evidence_ids": ["evidence:transfer"]}]
        compact = [{"record_id": "employment:long", "display_mode": "COMPACT", "bullets": [{"text": "Documented client handoffs.", "evidence_ids": ["evidence:transfer"]}]}]
        self.assertEqual(professional_history_sufficiency(employment, compact)["status"], "PASS")
        omitted = professional_history_sufficiency(employment, [], {"employment:long": "target domain mismatch"})
        self.assertIn("LONG_RUNNING_ROLE_OMITTED", {item["code"] for item in omitted["failures"]})

    def test_enriched_evidence_requires_explicit_propagation(self):
        before = profile()
        after = copy.deepcopy(before)
        item = after["evidence"][0]
        item["metrics"] = [{"value": "25", "public_use_allowed": True, "state": "VERIFIED"}]
        result = new_evidence_utilization(before, after, [item["record_id"]], {}, relevant_evidence_ids=[item["record_id"]])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["items"][0]["change_class"], "NEW_PUBLIC_METRIC")

    def test_six_evidence_propagation_change_classes(self):
        baseline = profile()
        evidence_id = baseline["evidence"][0]["record_id"]
        cases = []

        after = copy.deepcopy(baseline)
        after["evidence"][0]["metrics"] = [{"value": "25", "public_use_allowed": True, "state": "VERIFIED"}]
        cases.append((after, "NEW_PUBLIC_METRIC"))

        before_artifact = copy.deepcopy(baseline)
        before_artifact["evidence"][0]["verification_state"] = "NEEDS_VERIFICATION"
        after_artifact = copy.deepcopy(before_artifact)
        after_artifact["evidence"][0]["verification_state"] = "VERIFIED"
        cases.append((after_artifact, "NEW_ARTIFACT_VERIFICATION", before_artifact))

        after = copy.deepcopy(baseline)
        after["evidence"][0]["outcomes"] = ["Produced a stronger validated deliverable"]
        cases.append((after, "STRENGTHENED_OUTCOME"))

        before_visibility = copy.deepcopy(baseline)
        before_visibility["evidence"][0]["visibility"] = "RESTRICTED"
        after_visibility = copy.deepcopy(before_visibility)
        after_visibility["evidence"][0]["visibility"] = "PUBLIC"
        cases.append((after_visibility, "CHANGED_VISIBILITY", before_visibility))

        after = copy.deepcopy(baseline)
        after["skills"].append({"record_id": "skill:new-tool", "name": "Example Tool", "evidence_ids": [evidence_id], "visibility": "PUBLIC"})
        cases.append((after, "NEW_SKILL_TOOL"))

        after = copy.deepcopy(baseline)
        after["employment"][0]["actual_title"] = "Corrected Client Operations Title"
        cases.append((after, "CORRECTED_EMPLOYMENT_FACT"))

        observed = []
        for case in cases:
            after, expected, *custom_before = case
            result = new_evidence_utilization(custom_before[0] if custom_before else baseline, after, [evidence_id], {}, relevant_evidence_ids=[evidence_id])
            self.assertEqual(result["status"], "PASS")
            observed.extend(item["change_class"] for item in result["items"])
            self.assertIn(expected, observed)
        self.assertEqual(len(cases), 6)

    def test_empty_experience_entry_is_hard_failure(self):
        employment = [{"record_id": "employment:empty", "start_year": 2024, "end_year": 2025, "evidence_ids": []}]
        content = [{"record_id": "employment:empty", "display_mode": "MINIMAL", "bullets": []}]
        result = professional_history_sufficiency(employment, content)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failures"][0]["code"], "EMPTY_EXPERIENCE_ENTRY")

    def test_stale_resume_after_each_governed_input_change(self):
        p = profile()
        built = freshness(p)
        mutations = {
            "canonical_revision": (2, "STALE_CANONICAL_REVISION"),
            "evidence_bundle_hash": ("c" * 64, "STALE_EVIDENCE"),
            "skill_registry_hash": ("d" * 64, "STALE_SKILLS"),
            "credential_registry_hash": ("e" * 64, "STALE_CREDENTIALS"),
            "role_family_version": ("f" * 64, "STALE_ROLE_FAMILY"),
            "editorial_policy_version": ("next", "STALE_POLICY"),
            "jd_snapshot_hash": ("1" * 64, "STALE_JOB_SNAPSHOT"),
        }
        for field, (value, expected) in mutations.items():
            with self.subTest(field=field):
                current = dict(built)
                current[field] = value
                result = compare_freshness(built, current)
                self.assertFalse(result["acceptance_allowed"])
                self.assertIn(expected, result["stale_states"])

    def test_high_value_public_metric_cannot_disappear_silently(self):
        before = profile()
        after = copy.deepcopy(before)
        item = after["evidence"][0]
        item.update({
            "tools_methods": ["Example SIEM"], "deliverables": ["Disposition report"],
            "metrics": [{"value": "25", "public_use_allowed": True, "state": "VERIFIED"}],
            "recency_score": 1.0,
        })
        result = new_evidence_utilization(before, after, [], {}, relevant_evidence_ids=[item["record_id"]])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["high_value_silent_omissions"], [item["record_id"]])

    def test_high_value_private_evidence_is_explicitly_omitted(self):
        before = profile()
        after = copy.deepcopy(before)
        item = after["evidence"][0]
        item["visibility"] = "RESTRICTED"
        result = new_evidence_utilization(
            before, after, [], {item["record_id"]: "OMITTED_PRIVACY"},
            relevant_evidence_ids=[item["record_id"]],
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["items"][0]["disposition"], "OMITTED_PRIVACY")

    def test_targeted_resume_must_differ_and_adaptation_preserves_truth(self):
        base = {"summary": "Network operations.", "skills": [{"record_id": "skill:a"}], "projects": [{"record_id": "project:a", "bullets": []}], "employment": [], "section_order": ["SKILLS", "PROJECTS"]}
        self.assertEqual(targeted_resume_delta(base, copy.deepcopy(base))["status"], "NO_MEANINGFUL_DELTA")
        targeted = copy.deepcopy(base)
        targeted.update({"summary": "Overnight network monitoring and escalation.", "skills": [{"record_id": "skill:b"}, {"record_id": "skill:a"}], "section_order": ["PROJECTS", "SKILLS"]})
        targeted["projects"] = [{"record_id": "project:a", "bullets": [{"text": "Escalated findings.", "evidence_ids": ["evidence:a"]}]}]
        self.assertTrue(targeted_resume_delta(base, targeted)["acceptance_allowed"])
        bullet = {"evidence_ids": ["evidence:a"], "action": "Documented alerts", "tool_or_method": "Example SIEM", "outcome": "Prepared escalation notes", "deliverable": "Notes", "role_context": "Lab", "supported_actions": ["Documented alerts"]}
        adapted = render_adaptive_bullet(bullet, "ESCALATION")
        self.assertEqual(adapted["truth_boundary"]["evidence_ids"], bullet["evidence_ids"])
        self.assertEqual(adapted["truth_boundary"]["outcome"], bullet["outcome"])

    def test_blocked_credential_generates_internal_diagnostic_only(self):
        p = profile()
        p["credentials"] = [{"record_id": "credential:pending", "credential_state": "CLAIMED_COMPLETE", "verification_state": "NEEDS_VERIFICATION", "visibility": "PUBLIC"}]
        self.assertEqual(credential_opportunities(p), [{"credential_id": "credential:pending", "diagnostic": "HIGH_VALUE_CREDENTIAL_VERIFICATION_PENDING"}])

    def test_two_current_degrees_group_before_ged(self):
        p = profile()
        p["education"] = [
            {"record_id": "education:a", "institution": "Example University", "program": "B.S.", "field_of_study": "Cybersecurity", "completion_status": "IN_PROGRESS", "end_year": 2027, "visibility": "PUBLIC"},
            {"record_id": "education:b", "institution": "Example College", "program": "A.A.S.", "field_of_study": "Information Technology", "completion_status": "IN_PROGRESS", "end_year": 2026, "visibility": "PUBLIC"},
            {"record_id": "education:ged", "institution": "Example Board", "program": "GED", "field_of_study": None, "completion_status": "COMPLETED", "end_year": 2012, "visibility": "PUBLIC"},
        ]
        displayed = public_education(p, {"allowed_visibility": ["PUBLIC"]})
        self.assertEqual([item["record_id"] for item in displayed], ["education:b", "education:a"])

    def test_two_page_master_is_permitted_when_evidence_depth_warrants(self):
        p = profile()
        original_role = p["employment"][0]
        original_evidence = next(item for item in p["evidence"] if item["record_id"] in original_role["evidence_ids"])
        p["employment"] = []
        p["evidence"] = [item for item in p["evidence"] if not item.get("employment_ids")]
        for index in range(26):
            role = copy.deepcopy(original_role)
            evidence = copy.deepcopy(original_evidence)
            role["record_id"] = f"employment:history-{index}"
            role["employer"] = f"Example Operations {index}"
            role["start_year"] = 2000 + index
            role["end_year"] = 2001 + index
            evidence["record_id"] = f"evidence:history-{index}"
            evidence["employment_ids"] = [role["record_id"]]
            evidence["summary"] = f"Documented operational handoffs and customer requirements for team {index}"
            role["evidence_ids"] = [evidence["record_id"]]
            p["employment"].append(role)
            p["evidence"].append(evidence)
        content = master_resume_content(p)
        self.assertEqual(len(content["employment"]), 26)
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "master.pdf"
            render_pdf(content, target)
            self.assertEqual(len(PdfReader(str(target)).pages), 2)

    def test_contracts_public_labels_specificity_and_advancement(self):
        p = profile()
        contract = freshness(p)
        SchemaRegistry(ROOT / "src/careeros/schemas").validate("urn:careeros:schema:canonical-evidence-freshness:v1", contract)
        self.assertEqual(public_artifact_title("LANE_BASE", "Network Operations | Monitoring & Escalation"), "Network Operations | Monitoring & Escalation")
        self.assertIn("base resume", public_label_leaks("Base Resume"))
        concrete = {"summary": "Handled client escalations.", "employment": [], "projects": []}
        self.assertEqual(recruiter_copy_specificity(concrete, p)["status"], "PASS")
        self.assertFalse(evidence_utility(p["evidence"][0])["candidate_score"])
        self.assertIn("BRIDGE_ROLE_READINESS", career_advancement_signals(p["evidence"][0]))


if __name__ == "__main__":
    unittest.main()
