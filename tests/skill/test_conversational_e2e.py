from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = PACKAGE_ROOT / "skills" / "career-os"
FIXTURE_ROOT = PACKAGE_ROOT / "fixtures" / "synthetic"
CLI_WORDS = [sys.executable, "-m", "careeros"]
CLI = f"{sys.executable} -m careeros"
TIMESTAMP = "2026-10-02T12:00:00Z"


def load_script(name: str):
    path = SKILL_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"careeros_skill_e2e_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


router = load_script("route")
bootstrap = load_script("bootstrap")


def cli(workspace: Path, *args: str, allowed: tuple[int, ...] = (0,)) -> dict:
    completed = subprocess.run(
        [*CLI_WORDS, "--workspace", str(workspace), "--timestamp", TIMESTAMP, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in allowed:
        raise AssertionError(f"CLI {args} failed {completed.returncode}: {completed.stdout}\n{completed.stderr}")
    return json.loads(completed.stdout)


def split_sections(fixture: dict) -> dict[str, dict]:
    return {
        "workspace_privacy": {"privacy_consent": fixture["privacy_consent"]},
        "identity": {"candidate": fixture["candidate"]},
        "employment": {"employment": fixture["employment"]},
        "education": {"education": fixture["education"]},
        "credentials": {"credentials": fixture["credentials"]},
        "skills": {"skills": fixture["skills"]},
        "projects": {"projects": fixture["projects"]},
        "evidence": {"evidence": fixture["evidence"]},
        "preferences": {"preferences": fixture["preferences"]},
        "target_roles": {"role_intents": fixture["role_intents"]},
        "review": {"review_confirmed": fixture["review_confirmed"]},
    }


class ConversationalCleanRoomTests(unittest.TestCase):
    PROMPTS = {
        "early-career": "Set up Career OS for me from scratch.",
        "career-changer": "I want to change careers and need help organizing my experience.",
        "experienced-multi-role": "Here's a job I want. Am I qualified, and can you make the resume?",
    }

    def run_conversation(self, fixture_name: str) -> None:
        fixture_dir = FIXTURE_ROOT / fixture_name
        raw = json.loads((fixture_dir / "onboarding/input.json").read_text(encoding="utf-8"))
        expected = json.loads((fixture_dir / "expected/expectations.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix=f"careeros-skill-{fixture_name}-") as root:
            target = Path(root) / "career-workspace"
            initial = router.route(self.PROMPTS[fixture_name], target, CLI)
            self.assertEqual(initial["package"]["status"], "SUPPORTED")
            self.assertEqual(initial["workflow"], "GUIDED_BOOTSTRAP")
            cli(target, "init", "--fixture-mode", "--workspace-id", f"skill-{fixture_name}")
            doctor = cli(target, "doctor", "--json")
            self.assertEqual(doctor["outcome"], "READY")
            bootstrap.start(target, CLI)

            for section, payload in split_sections(raw).items():
                input_path = Path(root) / f"{section}.json"
                input_path.write_text(json.dumps(payload), encoding="utf-8")
                bootstrap.save_section(target, section, input_path)
            progress = bootstrap.progress(target)
            self.assertFalse(progress["missing_required_sections"])
            assembled = target / "sources" / "guided-onboarding-input.json"
            bootstrap.assemble(target, assembled)
            proposed = cli(target, "onboarding", "ingest", "--input", str(assembled), allowed=(0, 21))
            self.assertFalse((target / "data/records/candidate.json").exists())
            if proposed["state"] == "NEEDS_CLARIFICATION":
                cli(target, "clarification", "resolve", "--resolutions", str(fixture_dir / "onboarding/resolutions.json"))
            status_before_commit = cli(target, "status")
            self.assertIn(status_before_commit["state"]["onboarding"]["state"], {"REVIEW_READY", "NEEDS_CLARIFICATION"})

            human_approved = True
            self.assertTrue(human_approved)
            cli(target, "onboarding", "commit", "--actor", "fixture-human")
            profile = cli(target, "profile", "build")
            self.assertEqual(profile["profile"]["schema"], "careeros.career-profile.v1")
            role = cli(target, "role-family", "build", "--approve")
            self.assertEqual(role["approval_state"], "APPROVED")
            opportunity = cli(target, "opportunity", "ingest", "--input", str(fixture_dir / "opportunity/strong.json"))
            opportunity_id = opportunity["opportunity"]["opportunity_id"]
            qualification = cli(target, "qualify", "--opportunity-id", opportunity_id)
            self.assertEqual(qualification["decision"], expected["strong_decision"])
            built = cli(target, "resume", "build", "--opportunity-id", opportunity_id)
            build_id = built["build"]["build_id"]
            validation = cli(target, "resume", "validate", "--build-id", build_id)
            self.assertEqual(validation["validation"]["status"], "PASS")
            packet = cli(target, "application", "prepare", "--opportunity-id", opportunity_id, "--build-id", build_id)
            self.assertEqual(packet["human_review_state"], "REVIEW_REQUIRED")
            final_status = cli(target, "status")
            self.assertTrue(final_status["state"]["application"])
            self.assertFalse(any("submit" in path.name.casefold() for path in target.rglob("*")))

    def test_set_up_from_scratch(self):
        self.run_conversation("early-career")

    def test_career_change_bootstrap(self):
        self.run_conversation("career-changer")

    def test_job_first_bootstrap_and_resume(self):
        self.run_conversation("experienced-multi-role")


if __name__ == "__main__":
    unittest.main()
