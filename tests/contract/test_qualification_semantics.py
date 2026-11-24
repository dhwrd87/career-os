from __future__ import annotations

import unittest

from careeros.opportunity import REQUIREMENT_SUBTYPES, _normalize_requirement, evaluate_requirement


def profile_fixture() -> dict:
    return {
        "candidate": {"record_id": "candidate:test", "work_authorization": None},
        "employment": [],
        "education": [
            {
                "record_id": "education:in-progress",
                "program": "Bachelor of Science",
                "field_of_study": "Information Technology",
                "completion_status": "IN_PROGRESS",
            }
        ],
        "credentials": [],
        "skills": [
            {
                "record_id": "skill:network-security",
                "name": "Network Security",
                "aliases": ["IDS", "Firewall"],
                "category": "Security Technology",
                "contexts": ["portfolio lab"],
                "evidence_ids": ["evidence:network-lab"],
            }
        ],
        "evidence": [
            {
                "record_id": "evidence:network-lab",
                "visibility": "EMPLOYER_SAFE",
                "summary": "Analyzed a DDoS exercise using IDS and firewall concepts.",
                "actions": ["Reviewed simulated traffic"],
                "outcomes": ["Documented findings"],
                "employment_ids": [],
            }
        ],
        "projects": [],
        "preferences": {
            "schedule_preferences": [],
            "travel_preference": None,
            "location_preferences": [],
            "work_modes": [],
        },
    }


class QualificationSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.profile = profile_fixture()

    def classify(self, requirement: dict):
        evidence, gaps, hard = evaluate_requirement(self.profile, requirement)
        return evidence, gaps, hard

    def test_requirement_subtype_contract_is_complete(self):
        self.assertEqual(
            REQUIREMENT_SUBTYPES,
            {"EXPERIENCE", "EDUCATION", "CREDENTIAL", "SKILL", "TOOL", "LOGISTICS", "WORK_AUTHORIZATION", "SCHEDULE", "TRAVEL", "LOCATION"},
        )
        for subtype in REQUIREMENT_SUBTYPES:
            normalized = _normalize_requirement({"capability": "Example", "level": "CORE", "requirement_subtype": subtype})
            self.assertEqual(normalized["requirement_subtype"], subtype)
            self.assertEqual(normalized["requirement_class"], "REQUIRED")

    def test_a_required_experience_without_direct_evidence_is_hard_gap(self):
        evidence, gaps, hard = self.classify({
            "capability": "Cybersecurity or security operations experience",
            "level": "HARD",
            "requirement_class": "REQUIRED",
            "requirement_subtype": "EXPERIENCE",
            "direct_experience": True,
        })
        self.assertTrue(hard)
        self.assertEqual(gaps[0]["match"], "HARD_GAP")
        self.assertTrue(all(item["experience_equivalence"] is False for item in evidence))

    def test_b_unresolved_rotating_shift_is_unknown_decision(self):
        _evidence, gaps, hard = self.classify({
            "capability": "Rotating shifts",
            "level": "HARD",
            "requirement_class": "REQUIRED",
            "requirement_subtype": "SCHEDULE",
        })
        self.assertFalse(hard)
        self.assertEqual(gaps[0]["match"], "UNKNOWN_DECISION")

    def test_c_unresolved_travel_is_unknown_decision(self):
        _evidence, gaps, hard = self.classify({
            "capability": "Travel up to 10%",
            "level": "HARD",
            "requirement_class": "REQUIRED",
            "requirement_subtype": "TRAVEL",
        })
        self.assertFalse(hard)
        self.assertEqual(gaps[0]["match"], "UNKNOWN_DECISION")

    def test_d_in_progress_bachelors_is_hard_gap(self):
        evidence, gaps, hard = self.classify({
            "capability": "IT-related bachelor's degree",
            "level": "HARD",
            "requirement_class": "REQUIRED",
            "requirement_subtype": "EDUCATION",
        })
        self.assertTrue(hard)
        self.assertEqual(evidence[0]["match"], "PARTIALLY_SUPPORTED")
        self.assertEqual(gaps[0]["match"], "HARD_GAP")

    def test_e_broad_requirement_aggregates_partial_evidence(self):
        evidence, gaps, hard = self.classify({
            "capability": "Security technology breadth",
            "level": "CORE",
            "requirement_class": "REQUIRED",
            "requirement_subtype": "TOOL",
            "sub_capabilities": ["IDS/IPS", "DLP", "EDR"],
        })
        self.assertFalse(hard)
        self.assertEqual(evidence[0]["match"], "PARTIALLY_SUPPORTED")
        self.assertEqual(gaps[0]["match"], "PARTIALLY_SUPPORTED")
        self.assertEqual(evidence[0]["supported_sub_capabilities"], ["IDS/IPS"])
        self.assertEqual(evidence[0]["missing_sub_capabilities"], ["DLP", "EDR"])

    def test_f_missing_preferred_requirement_is_non_disqualifying(self):
        _evidence, gaps, hard = self.classify({
            "capability": "Detection Engineering",
            "level": "PREFERRED",
            "requirement_class": "PREFERRED",
            "requirement_subtype": "SKILL",
        })
        self.assertFalse(hard)
        self.assertEqual(gaps[0]["match"], "PREFERRED_AND_MISSING")

    def test_missing_required_skill_is_unknown_evidence_not_hard_gap(self):
        _evidence, gaps, hard = self.classify({
            "capability": "Endpoint Detection and Response",
            "level": "CORE",
            "requirement_class": "REQUIRED",
            "requirement_subtype": "TOOL",
        })
        self.assertFalse(hard)
        self.assertEqual(gaps[0]["match"], "UNKNOWN_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
