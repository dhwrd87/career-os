from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from careeros import intake, source_enrichment, workflows, workspace
from careeros.core.errors import SourceEnrichmentApprovalRequiredError
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import schema_dir


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/synthetic/intake"
RESUME = FIXTURES / "linked-career-resume.md"
NOW = "2026-10-03T18:00:00Z"


def fixture_fetcher(url: str):
    mapping = {
        "linkedin.com": ("linked-source-linkedin.html", "text/html"),
        "github.com": ("linked-source-github.json", "application/json"),
        "river-chen.example": ("linked-source-portfolio.html", "text/html"),
    }
    for host, (name, media_type) in mapping.items():
        if host in url:
            return {"body": (FIXTURES / name).read_bytes(), "media_type": media_type, "final_url": url}
    raise AssertionError(f"unexpected test URL: {url}")


class LinkedSourceEnrichmentTests(unittest.TestCase):
    def test_private_network_source_urls_are_rejected(self):
        for url in ("http://localhost/profile", "http://127.0.0.1/profile", "http://10.0.0.8/profile"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                source_enrichment.classify_url(url)

    def test_github_profile_uses_bounded_public_api_capture(self):
        def fake_get(url: str, *, accept: str):
            if "/users/" in url:
                value = [{
                    "name": "example-tool", "full_name": "river-example/example-tool",
                    "description": "Example repository", "language": "Python",
                    "pushed_at": "2026-09-01T00:00:00Z", "html_url": "https://github.com/river-example/example-tool",
                    "homepage": "https://example-tool.example", "fork": False,
                    "owner": {"login": "river-example"},
                }]
            elif url.endswith("/contents"):
                value = [{"name": "README.md"}, {"name": "tests"}, {"name": "docs"}]
            elif url.endswith("/readme"):
                return b"# Example Tool\nDocuments an observable deliverable.", "text/plain", url
            else:
                raise AssertionError(url)
            return json.dumps(value).encode(), "application/json", url

        with patch.object(source_enrichment, "_http_get", side_effect=fake_get):
            result = source_enrichment._github_api_capture("https://github.com/river-example")
        payload = json.loads(result["body"])
        repository = payload["repositories"][0]
        self.assertEqual(repository["programmingLanguage"], ["Python"])
        self.assertTrue(repository["has_tests"])
        self.assertTrue(repository["has_documentation"])
        self.assertIn("observable deliverable", repository["readme"])

    def test_detection_requires_one_decision_and_does_not_fetch(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            result = workflows.setup_start(target, [RESUME], mode="FAST", fixture_mode=True, timestamp=NOW)
            self.assertEqual(result["state"], "SOURCE_ENRICHMENT_APPROVAL_REQUIRED")
            self.assertEqual({item["source_type"] for item in result["linked_sources"]}, {"LINKEDIN", "GITHUB", "PORTFOLIO"})
            manifest = json.loads((target / "state/intake/source-enrichment-manifest.json").read_text())
            self.assertTrue(all(item["candidate_approval_state"] == "PENDING" for item in manifest["sources"]))
            self.assertTrue(all(item["capture_time"] is None for item in manifest["sources"]))
            self.assertFalse((target / "state/intake/career-intake.json").exists())

    def test_direct_compile_refuses_implicit_external_read(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workspace.init_workspace(target, fixture_mode=True, timestamp=NOW)
            with self.assertRaises(SourceEnrichmentApprovalRequiredError):
                intake.compile_intake(target, [RESUME], timestamp=NOW)

    def test_decline_builds_consolidated_intake_without_capture(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workflows.setup_start(target, [RESUME], fixture_mode=True, timestamp=NOW)
            result = workflows.setup_enrich(target, approved=False, timestamp=NOW)
            self.assertEqual(result["state"], "AWAITING_COMPLETION")
            self.assertEqual(result["linked_source_summary"], {"detected": 3, "authorized": 0, "captured": 0})
            self.assertEqual(result["question_count"], 9)
            manifest = json.loads((target / "state/intake/source-enrichment-manifest.json").read_text())
            self.assertTrue(all(item["capture_status"] == "DECLINED" for item in manifest["sources"]))
            self.assertFalse((target / "data/records/candidate.json").exists())

    def test_authorized_enrichment_is_richer_proposed_only_and_provenanced(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workflows.setup_start(target, [RESUME], fixture_mode=True, timestamp=NOW)
            result = workflows.setup_enrich(target, approved=True, fetcher=fixture_fetcher, timestamp=NOW)
            self.assertEqual(result["state"], "AWAITING_COMPLETION")
            self.assertEqual(result["linked_source_summary"], {"detected": 3, "authorized": 3, "captured": 3})
            self.assertEqual(result["question_count"], 8)
            compiled = json.loads((target / "state/intake/career-intake.json").read_text())
            SchemaRegistry(schema_dir()).validate("urn:careeros:schema:career-intake:v1", compiled)
            proposed = compiled["prefilled_onboarding"]
            self.assertGreaterEqual(len(proposed["projects"]), 3)
            self.assertIn("Python", {item["name"] for item in proposed["skills"]})
            self.assertTrue(next(item for item in proposed["skills"] if item["name"] == "Python")["evidence_ids"])
            self.assertTrue(any(item["evidence_type"] == "VOLUNTEER" for item in proposed["evidence"]))
            self.assertTrue(any("Conflicting date ranges" in item for item in compiled["contradictions"]))
            self.assertTrue(compiled["evidence_depth_assessments"])
            self.assertFalse((target / "data/records/candidate.json").exists())

            linked_records = [
                record for kind in ("employment", "education", "credentials", "skills", "projects", "evidence")
                for record in proposed[kind]
                if any(item["source_type"] == "PUBLIC_SOURCE" for item in record.get("source_provenance", []))
            ]
            self.assertTrue(linked_records)
            self.assertTrue(all(item.get("source_provenance") for item in linked_records))
            self.assertTrue(all(
                provenance.get("source_hash") and provenance.get("captured_at") and provenance.get("source_reference", "").startswith("http")
                for record in linked_records for provenance in record["source_provenance"]
                if provenance["source_type"] == "PUBLIC_SOURCE"
            ))

            # GitHub and portfolio evidence remains project/volunteer evidence;
            # repository existence never becomes professional employment.
            public_employment_sources = {
                provenance["source_reference"] for record in proposed["employment"]
                for provenance in record.get("source_provenance", []) if provenance["source_type"] == "PUBLIC_SOURCE"
            }
            self.assertTrue(all("linkedin.com" in value for value in public_employment_sources))
            github_projects = [
                record for record in proposed["projects"]
                if any("github.com" in item["source_reference"] for item in record.get("source_provenance", []))
            ]
            self.assertTrue(github_projects)
            self.assertTrue(all(item["contribution"] == "AMBIGUOUS" for item in github_projects))

            manifest = json.loads((target / compiled["source_enrichment_manifest"]).read_text())
            SchemaRegistry(schema_dir()).validate("urn:careeros:schema:source-enrichment-manifest:v1", manifest)
            self.assertTrue(all(item["records_proposed"] for item in manifest["sources"]))
            self.assertTrue(all(item["evidence_blocks_enriched"] for item in manifest["sources"]))
            self.assertTrue(any(item["conflicts_found"] for item in manifest["sources"]))

    def test_source_conflict_routes_to_exception_clarification(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workflows.setup_start(target, [RESUME], fixture_mode=True, timestamp=NOW)
            workflows.setup_enrich(target, approved=True, fetcher=fixture_fetcher, timestamp=NOW)
            compiled = json.loads((target / "state/intake/career-intake.json").read_text())
            answers = Path(root) / "answers.json"
            answers.write_text(json.dumps({
                "privacy_consent": True,
                "review_confirmed": True,
                "confirmed_onboarding": compiled["prefilled_onboarding"],
            }))
            result = workflows.setup_complete(target, answers, timestamp=NOW)
            self.assertEqual(result["state"], "EXCEPTION_CLARIFICATION")
            self.assertTrue(any(item["issue"] == "SOURCE_CONFLICT" for item in result["questions"]))


if __name__ == "__main__":
    unittest.main()
