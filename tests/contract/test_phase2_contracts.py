from __future__ import annotations

import json
import unittest
from importlib.resources import files

from careeros.schemas.validation import SchemaRegistry


class Phase2ContractTests(unittest.TestCase):
    def setUp(self):
        self.schema_dir = files("careeros.schemas")
        self.registry = SchemaRegistry(self.schema_dir)

    def test_required_phase2_contracts_registered(self):
        required = {
            "urn:careeros:schema:opportunity:v1", "urn:careeros:schema:job-description-snapshot:v1",
            "urn:careeros:schema:qualification-decision:v1", "urn:careeros:schema:resume-build:v1",
            "urn:careeros:schema:resume-artifact:v1", "urn:careeros:schema:artifact-manifest:v1",
            "urn:careeros:schema:application-packet:v1",
        }
        self.assertTrue(required <= set(self.registry.by_id))

    def test_questionnaire_metadata_complete(self):
        questionnaire = json.loads(files("careeros.questionnaires").joinpath("onboarding.v1.json").read_text())
        required = {"question_id", "schema_version", "section", "conditional_rule", "required", "answer_type", "target_contract", "target_field", "source_type", "confidence", "visibility", "evidence_refs"}
        self.assertTrue(questionnaire["questions"])
        self.assertTrue(all(required <= set(item) for item in questionnaire["questions"]))
        self.assertEqual(len(questionnaire["sections"]), 11)

    def test_role_family_schema_defines_phase2_fields(self):
        schema = self.registry.by_id["urn:careeros:schema:role-family:v1"]
        expected = {"role_family_id", "display_name", "seniority", "core_capabilities", "preferred_capabilities", "transferable_capabilities", "hard_requirements", "common_gaps", "evidence_preferences", "resume_strategy", "qualification_policy_ref", "approval_state"}
        self.assertTrue(expected <= set(schema["properties"]))


if __name__ == "__main__":
    unittest.main()
