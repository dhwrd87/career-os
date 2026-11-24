from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from careeros.schemas import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "src/careeros/schemas"
CONFIG_FIXTURES = ROOT / "tests/fixtures/config"


def metadata(schema: str, record_id: str) -> dict[str, object]:
    return {
        "schema": schema,
        "schema_version": "1.0.0",
        "record_id": record_id,
        "created_at": "2026-01-15T00:00:00Z",
        "updated_at": "2026-01-15T00:00:00Z",
        "provenance": [{
            "source_id": f"source-{record_id}",
            "source_type": "SELF_REPORT",
            "source_reference": "fixture://contract-example",
            "source_record_id": None,
            "field": None,
            "source_hash": None,
            "captured_at": "2026-01-15T00:00:00Z",
        }],
        "verification_state": "VERIFIED",
        "confidence": "HIGH",
        "visibility": "INTERNAL",
        "status": "ACTIVE",
        "supersedes_record_id": None,
    }


def synthetic_profile() -> dict[str, object]:
    candidate = {
        **metadata("careeros.candidate-profile.v1", "candidate-contract-example"),
        "public_name": "Avery Rowan",
        "legal_name": None,
        "location": "Example City",
        "contact": {"email": "avery.rowan@example.invalid", "phone": None, "urls": []},
        "work_authorization": None,
    }
    employment = {
        **metadata("careeros.employment-record.v1", "employment-contract-example"),
        "employer": "Northstar Library Cooperative",
        "actual_title": "Service Desk Assistant",
        "normalized_title": "Support Assistant",
        "public_title": "Service Desk Assistant",
        "employment_type": "PART_TIME",
        "location": "Example City",
        "start_month": "January",
        "start_year": 2025,
        "end_month": None,
        "end_year": "PRESENT",
        "date_precision": "MONTH",
        "role_context": "Member support and records coordination",
        "evidence_ids": ["evidence-contract-example"],
        "claim_boundaries": [],
    }
    education = {
        **metadata("careeros.education-record.v1", "education-contract-example"),
        "institution": "Example Regional College",
        "program": "Diploma in Information Services",
        "field_of_study": "Information Services",
        "completion_status": "COMPLETED",
        "start_year": 2023,
        "end_year": 2025,
        "claim_boundaries": [],
    }
    skill = {
        **metadata("careeros.skill-record.v1", "skill-contract-example"),
        "name": "Issue triage",
        "category": "Support",
        "aliases": [],
        "proficiency": "PRACTICED",
        "most_recent_use": 2026,
        "contexts": ["member support"],
        "evidence_ids": ["evidence-contract-example"],
        "claim_boundaries": [],
    }
    credential = {
        **metadata("careeros.credential-record.v1", "credential-contract-example"),
        "title": "Foundations of Service Operations",
        "issuer": "Example Learning Institute",
        "platform": None,
        "credential_state": "COMPLETED",
        "issued_date": "2025-06",
        "expiration_date": None,
        "credential_identifier": None,
        "credential_url": None,
        "capability_ids": ["issue-triage"],
        "claim_boundaries": [],
    }
    evidence = {
        **metadata("careeros.evidence-record.v1", "evidence-contract-example"),
        "evidence_type": "WORK_SAMPLE",
        "summary": "Created a categorized request log for a fictional contract fixture.",
        "context": "Contract validation only",
        "ownership": "Individual contributor",
        "actions": ["Categorized requests"],
        "outcomes": ["Produced a reviewable log"],
        "skill_ids": ["skill-contract-example"],
        "employment_ids": ["employment-contract-example"],
        "project_ids": ["project-contract-example"],
        "metric_boundaries": ["No performance metric claimed"],
        "claim_boundaries": ["Synthetic contract fixture only"],
    }
    project = {
        **metadata("careeros.project-evidence-record.v1", "project-contract-example"),
        "name": "Community Catalog Cleanup",
        "purpose": "Normalize a fictional community catalog dataset.",
        "date_range": "2025",
        "contribution": "Defined categories and reviewed sample records.",
        "technologies": ["Spreadsheet"],
        "skill_ids": ["skill-contract-example"],
        "evidence_ids": ["evidence-contract-example"],
        "artifact_references": [],
        "claim_boundaries": ["Synthetic contract fixture only"],
    }
    preferences = {
        **metadata("careeros.career-preference.v1", "preference-contract-example"),
        "target_role_family_ids": ["role-family-contract-example"],
        "target_industries": ["Public services"],
        "work_modes": ["ONSITE", "HYBRID"],
        "location_preferences": ["Example City"],
        "compensation": None,
        "travel_preference": "NONE",
        "schedule_preferences": ["DAYTIME"],
        "career_change_intent": None,
        "constraints": [],
    }
    role_family = {
        **metadata("careeros.role-family.v1", "role-family-contract-example"),
        "family_id": "support-operations",
        "label": "Support Operations",
        "description": "Entry-level service and records support roles.",
        "headline": None,
        "target_titles": ["Support Assistant"],
        "skill_tags": ["issue-triage"],
        "evidence_requirements": ["service example"],
        "eligibility_rules": [],
    }
    return {
        "schema": "careeros.career-profile.v1",
        "schema_version": "1.0.0",
        "profile_id": "career-profile-contract-example",
        "generated_at": "2026-01-15T00:00:00Z",
        "source_snapshot_hash": hashlib.sha256(b"synthetic-contract-example").hexdigest(),
        "candidate": candidate,
        "employment": [employment],
        "education": [education],
        "skills": [skill],
        "credentials": [credential],
        "evidence": [evidence],
        "projects": [project],
        "preferences": preferences,
        "role_families": [role_family],
        "artifacts": [],
    }


class SchemaBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry(SCHEMAS)

    def test_required_schema_bundle_present(self) -> None:
        required = {
            "urn:careeros:schema:config:v1",
            "urn:careeros:schema:candidate-profile:v1",
            "urn:careeros:schema:employment-record:v1",
            "urn:careeros:schema:education-record:v1",
            "urn:careeros:schema:skill-record:v1",
            "urn:careeros:schema:credential-record:v1",
            "urn:careeros:schema:evidence-record:v1",
            "urn:careeros:schema:project-evidence-record:v1",
            "urn:careeros:schema:career-preference:v1",
            "urn:careeros:schema:role-family:v1",
            "urn:careeros:schema:artifact-reference:v1",
            "urn:careeros:schema:career-profile:v1",
            "urn:careeros:schema:compiler-input:v1",
            "urn:careeros:schema:resume-storyline:v1",
            "urn:careeros:schema:resume-bullet-candidate:v1",
            "urn:careeros:schema:public-display-policy:v1",
            "urn:careeros:schema:resume-editorial-quality:v1",
            "urn:careeros:schema:resume-completeness:v1",
            "urn:careeros:schema:lane-base-resume:v1",
            "urn:careeros:schema:lane-base-build-manifest:v1",
            "urn:careeros:schema:resume-header:v1",
            "urn:careeros:schema:recruiter-summary:v1",
            "urn:careeros:schema:ats-resume-round-trip:v1",
            "urn:careeros:schema:resume-visual-density:v1",
            "urn:careeros:schema:premium-resume-quality:v1",
            "urn:careeros:schema:masthead-geometry:v1",
            "urn:careeros:schema:employer-need-trace:v1",
            "urn:careeros:schema:strongest-evidence-omission:v1",
            "urn:careeros:schema:role-fact-set:v1",
            "urn:careeros:schema:material-evidence-loss:v1",
            "urn:careeros:schema:career-conversion-trace:v1",
            "urn:careeros:schema:opportunity-freshness:v1",
            "urn:careeros:schema:application-state:v1",
            "urn:careeros:schema:application-event:v1",
            "urn:careeros:schema:application-state-reconciliation:v1",
            "urn:careeros:schema:follow-up:v1",
            "urn:careeros:schema:interview:v1",
        }
        self.assertTrue(required.issubset(self.registry.by_id))

    def test_valid_config_fixtures_match_schema(self) -> None:
        for name in ("valid-minimal.json", "valid-full.json"):
            self.registry.validate(
                "urn:careeros:schema:config:v1",
                json.loads((CONFIG_FIXTURES / name).read_text(encoding="utf-8")),
            )

    def test_career_profile_contract(self) -> None:
        self.registry.validate("urn:careeros:schema:career-profile:v1", synthetic_profile())

    def test_working_and_package_config_contracts_match(self) -> None:
        from careeros.workspace import schema_dir
        working = SCHEMAS / "careeros-config.v1.schema.json"
        packaged = schema_dir() / "careeros-config.v1.schema.json"
        self.assertEqual(json.loads(working.read_text(encoding="utf-8")), json.loads(packaged.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
