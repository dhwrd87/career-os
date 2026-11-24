from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from careeros.resume import render_pdf
from careeros.resume_ats import (
    ATS_MINIMAL_FALLBACK,
    ats_resume_round_trip,
    build_recruiter_summary,
    build_resume_header,
    header_layout_decision,
    recruiter_safe_filename,
    validate_recruiter_summary,
)
from careeros.schemas import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]


def _candidate(name: str = "Avery Rowan", *, email: str = "avery.rowan@example.invalid", phone: str | None = "+1 312 555 0198", urls: list[str] | None = None) -> dict:
    return {
        "public_name": name,
        "location": "Chicago, IL",
        "contact": {
            "email": email,
            "phone": phone,
            "urls": urls if urls is not None else [
                "https://www.linkedin.com/in/avery-rowan-example",
                "https://averyrowan.example",
            ],
        },
    }


def _summary(target: str = "Security Operations") -> dict:
    text = (
        f"{target} candidate with evidence-supported alert review, network analysis, and incident documentation skills. "
        "Professional support work demonstrates time-sensitive communication, accurate records, and structured handoffs. "
        "Technical projects include log investigation, packet review, and remediation validation, while project work remains clearly separated from professional employment."
    )
    return {
        "schema": "careeros.recruiter-summary.v1",
        "schema_version": "1.0.0",
        "candidate_identity": "profile-synthetic-ats",
        "target_role_family": "security-operations",
        "text": text,
        "word_count": len(text.split()),
        "summary_type": "LANE",
        "clauses": [
            {
                "summary_clause": text,
                "source_evidence_ids": ["evidence-professional", "evidence-technical"],
                "approved_config_source": "RoleFamilyV1",
                "verification": "SOURCE_BOUND",
                "public_use": True,
                "job_relevance": "LANE",
            }
        ],
        "career_transition_boundary": True,
        "job_specific_emphasis": None,
    }


def _content(candidate: dict | None = None, *, target: str = "Security Operations | Monitoring & Escalation", two_page: bool = False, two_degrees: bool = False, promotion: bool = False, contract: bool = False, long_project: bool = False) -> dict:
    candidate = candidate or _candidate()
    header = build_resume_header(candidate, target)
    summary = _summary(target.split("|")[0].strip())
    employment = [
        {
            "actual_title": "Operations Support Specialist",
            "employer": "Example Services Cooperative",
            "location": "Chicago, IL",
            "start_month": "January",
            "start_year": 2023,
            "end_month": None,
            "end_year": "PRESENT",
            "date_precision": "MONTH",
            "bullets": [
                {"text": "Documented time-sensitive requests and routed complex cases through defined escalation paths."},
                {"text": "Maintained accurate records while handling privacy-sensitive customer information."},
            ],
        }
    ]
    if promotion:
        employment.insert(0, {
            "actual_title": "Senior Operations Support Specialist",
            "employer": "Example Services Cooperative",
            "location": "Chicago, IL",
            "start_month": "June",
            "start_year": 2025,
            "end_month": None,
            "end_year": "PRESENT",
            "date_precision": "MONTH",
            "bullets": [{"text": "Coordinated escalations and reviewed shift handoff notes for completeness."}],
        })
    if contract:
        employment.append({
            "actual_title": "Contract Documentation Specialist",
            "employer": "Independent Contract",
            "location": "Remote",
            "start_year": 2021,
            "end_year": 2022,
            "date_precision": "YEAR",
            "bullets": [{"text": "Prepared structured deliverables and maintained client-approved terminology."}],
        })
    if two_page:
        employment[0]["bullets"].extend(
            {"text": f"Recorded and validated operational detail {index} for a synthetic two-page layout check with traceable source context."}
            for index in range(42)
        )
    education = [{
        "institution": "Example State University",
        "program": "Bachelor of Science",
        "field_of_study": "Information Technology",
        "display_status": "In progress | Expected 2027",
    }]
    if two_degrees:
        education.append({
            "institution": "Example Community College",
            "program": "Associate of Science",
            "field_of_study": "Cybersecurity",
            "display_status": "In progress | Expected 2026",
        })
    project_name = "Network Monitoring, Packet Analysis, Escalation Documentation, and Service Continuity Validation Project" if long_project else "Network Monitoring Lab"
    return {
        "candidate": candidate,
        "target_role": target,
        "resume_header": header,
        "recruiter_summary": summary,
        "summary": summary["text"],
        "skills": [{"name": "Wireshark"}, {"name": "Incident documentation"}],
        "skill_groups": [{"group": "SECURITY & MONITORING", "skills": [{"name": "Wireshark"}, {"name": "Incident documentation"}]}],
        "employment": employment,
        "projects": [{
            "name": project_name,
            "contribution": "Analyzed synthetic traffic and documented escalation criteria.",
            "bullets": [{"text": "Reviewed packet captures and documented indicators for follow-up."}],
        }],
        "display_education": education,
        "display_credentials": [{"title": "Example Security Certificate", "issuer": "Example Institute"}],
        "section_order": ["SUMMARY", "SKILLS", "PROJECTS", "EXPERIENCE", "EDUCATION", "CREDENTIALS"],
    }


class HeaderSummaryATSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry(ROOT / "src/careeros/schemas")

    def _render_and_check(self, content: dict) -> dict:
        self.registry.validate("urn:careeros:schema:resume-header:v1", content["resume_header"])
        self.registry.validate("urn:careeros:schema:recruiter-summary:v1", content["recruiter_summary"])
        with tempfile.TemporaryDirectory() as temporary:
            pdf = Path(temporary) / recruiter_safe_filename(content["candidate"]["public_name"], content["target_role"])
            render_pdf(content, pdf)
            self.registry.validate("urn:careeros:schema:masthead-geometry:v1", content["masthead_geometry"])
            result = ats_resume_round_trip(content, pdf)
            self.registry.validate("urn:careeros:schema:ats-resume-round-trip:v1", result)
        self.assertEqual(result["status"], "ATS_SAFE_HIGH_CONFIDENCE", result)
        self.assertEqual(content["masthead_geometry"]["status"], "PASS")
        self.assertEqual(content["masthead_geometry"]["links_to_divider_gap"], content["masthead_geometry"]["divider_gap"])
        self.assertGreater(content["masthead_geometry"]["links_to_divider_gap"], 3.5)
        self.assertGreater(content["masthead_geometry"]["divider_to_summary_gap"], 0)
        self.assertGreater(content["masthead_geometry"]["divider_balance_ratio"], 0.45)
        self.assertLess(content["masthead_geometry"]["divider_balance_ratio"], 1.25)
        return result

    def test_synthetic_ats_matrix(self) -> None:
        cases = {
            "short-name": _content(_candidate("Li Wu")),
            "long-name": _content(_candidate("Alexandria Catherine Montgomery-Santiago")),
            "long-email": _content(_candidate(email="alexandria.montgomery.santiago+career@example.invalid")),
            "two-urls": _content(_candidate(urls=["https://www.linkedin.com/in/avery-rowan-example-with-long-slug", "https://averyrowan.example/portfolio/security-operations"])),
            "no-portfolio": _content(_candidate(urls=["https://www.linkedin.com/in/avery-rowan-example"])),
            "career-changer": _content(target="Network Operations | Monitoring & Escalation"),
            "two-current-degrees": _content(two_degrees=True),
            "multiple-employers": _content(contract=True),
            "promotion": _content(promotion=True),
            "contract-work": _content(contract=True),
            "long-project-name": _content(long_project=True),
            "two-page": _content(two_page=True),
        }
        results = {name: self._render_and_check(content) for name, content in cases.items()}
        self.assertEqual(set(results), set(cases))
        self.assertEqual(results["two-page"]["page_count"], 2)

    def test_header_variants_and_international_phone(self) -> None:
        cases = [
            _candidate(phone=None),
            _candidate(phone="+44 20 7946 0958", urls=["https://www.linkedin.com/in/avery-rowan-example"]),
            _candidate(email="long-address-for-ats-header-validation@example.invalid"),
        ]
        for candidate in cases:
            result = self._render_and_check(_content(candidate))
            self.assertTrue(result["gates"]["AUTOFILL"])

    def test_centered_header_width_modes_are_deterministic(self) -> None:
        standard = header_layout_decision(build_resume_header(_candidate(), "Security Operations | Monitoring & Escalation"))
        compact = header_layout_decision(build_resume_header(
            _candidate(email="alexandria.montgomery.santiago+career@example.invalid"),
            "Security Operations | SIEM Monitoring, Incident Investigation, Escalation, Reporting & Response Coordination",
        ))
        wrapped = header_layout_decision(build_resume_header(
            _candidate("Alexandria Catherine Montgomery-Santiago"),
            "Security Operations Monitoring Investigation Escalation Documentation Reporting Coordination Response Validation",
        ))
        self.assertEqual(standard["layout_mode"], "STANDARD_CENTERED")
        self.assertIn(compact["layout_mode"], {"COMPACT_CENTERED", "CONTROLLED_HEADLINE_WRAP"})
        self.assertEqual(wrapped["layout_mode"], "CONTROLLED_HEADLINE_WRAP")
        for decision in (standard, compact, wrapped):
            self.assertFalse(decision["clipping_risk"], decision)

    def test_minimal_linear_header_remains_available(self) -> None:
        content = _content()
        content["header_presentation"] = ATS_MINIMAL_FALLBACK
        with tempfile.TemporaryDirectory() as temporary:
            pdf = Path(temporary) / "Avery Rowan - Security Operations Resume.pdf"
            render_pdf(content, pdf)
            result = ats_resume_round_trip(content, pdf)
            self.registry.validate("urn:careeros:schema:masthead-geometry:v1", content["masthead_geometry"])
        self.assertEqual(content["masthead_geometry"]["status"], "NOT_APPLICABLE_FALLBACK")
        self.assertEqual(result["status"], "ATS_SAFE_HIGH_CONFIDENCE", result)

    def test_recruiter_summary_is_traced_and_job_adaptive(self) -> None:
        profile = {
            "profile_id": "profile-summary-test",
            "candidate": _candidate(),
            "preferences": {"schedule_preferences": ["NIGHT"]},
            "skills": [
                {"name": "SPL", "visibility": "PUBLIC", "evidence_ids": ["evidence-siem"]},
                {"name": "Wireshark", "visibility": "PUBLIC", "evidence_ids": ["evidence-network"]},
            ],
            "evidence": [
                {"record_id": "evidence-professional", "visibility": "PUBLIC", "employment_ids": ["employment-1"], "project_ids": [], "actions": ["Documented operational handoffs"], "tools_methods": []},
                {"record_id": "evidence-siem", "visibility": "PUBLIC", "employment_ids": [], "project_ids": ["project-siem"], "actions": ["Investigated indicators"], "tools_methods": ["SPL"]},
                {"record_id": "evidence-network", "visibility": "PUBLIC", "employment_ids": [], "project_ids": ["project-network"], "actions": ["Reviewed packet captures"], "tools_methods": ["Wireshark"]},
            ],
        }
        storyline = {"evidence_rankings": [
            {"evidence_id": "evidence-professional", "classification": "TRANSFERABLE_PROFESSIONAL"},
            {"evidence_id": "evidence-siem", "classification": "ANCHOR"},
            {"evidence_id": "evidence-network", "classification": "SUPPORTING"},
        ]}
        family = {"role_family_id": "security-operations", "display_name": "Security Operations"}
        lane = build_recruiter_summary(profile, storyline, family)
        targeted = build_recruiter_summary(profile, storyline, family, opportunity={
            "role_title": {"value": "Overnight SOC Monitoring Analyst", "source_reference": {"snapshot_id": "synthetic"}},
            "shift_schedule": {"value": "NIGHT", "source_reference": {"snapshot_id": "synthetic"}},
        })
        self.assertEqual(validate_recruiter_summary(lane)["status"], "PASS")
        self.assertEqual(validate_recruiter_summary(targeted)["status"], "PASS")
        self.assertNotEqual(lane["text"], targeted["text"])
        self.assertNotIn("source_reference", targeted["text"])
        self.assertTrue(all(item["source_evidence_ids"] or item["approved_config_source"] for item in targeted["clauses"]))

    def test_recruiter_safe_filename_rejects_internal_labels(self) -> None:
        filename = recruiter_safe_filename("Avery Rowan", "Career OS Base Resume - SOC Analyst")
        self.assertEqual(filename, "Avery Rowan - SOC Analyst Resume.pdf")
        self.assertNotRegex(filename.casefold(), r"career os|base|generated|internal|draft")


if __name__ == "__main__":
    unittest.main()
