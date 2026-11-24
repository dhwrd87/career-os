from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from careeros import workspace


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = PACKAGE_ROOT / "skills" / "career-os"
FIXTURE_ROOT = PACKAGE_ROOT / "fixtures" / "synthetic"
CLI = f"{sys.executable} -m careeros"


def load_script(name: str):
    path = SKILL_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"careeros_skill_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


route_module = load_script("route")
bootstrap_module = load_script("bootstrap")


class SkillContractTests(unittest.TestCase):
    def test_manifest_declares_thin_compatible_skill(self):
        manifest = json.loads((SKILL_ROOT / "skill-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["skill_version"], "0.4.1")
        self.assertEqual(manifest["career_os_package"], {"minimum": "0.4.1", "maximum_exclusive": "0.5.0"})
        self.assertFalse(manifest["external_adapters_enabled"])
        self.assertEqual(manifest["phase_endpoint"], "REVIEW_REQUIRED_OR_CANONICAL_UPDATE_COMMITTED")

    def test_skill_does_not_import_engine_subsystems(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in (SKILL_ROOT / "scripts").glob("*.py"))
        for forbidden in ("careeros.resume", "careeros.opportunity", "careeros.profile", "careeros.migrations", "reportlab"):
            self.assertNotIn(forbidden, source)

    def test_skill_entrypoint_is_compact(self):
        lines = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), 90)

    def test_all_references_are_linked(self):
        entry = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for path in (SKILL_ROOT / "references").glob("*.md"):
            self.assertIn(path.name, entry)


class CompatibilityTests(unittest.TestCase):
    def test_supported_package(self):
        self.assertEqual(route_module.classify_package_version("0.4.1"), "SUPPORTED")

    def test_older_package(self):
        self.assertEqual(route_module.classify_package_version("0.2.9"), "OLDER_BUT_MIGRATABLE")

    def test_future_package(self):
        self.assertEqual(route_module.classify_package_version("0.5.0"), "UNSUPPORTED_FUTURE")

    def test_package_absent(self):
        self.assertEqual(route_module.package_probe("careeros-command-that-does-not-exist")["status"], "PACKAGE_ABSENT")


class IntentRouterTests(unittest.TestCase):
    CASES = {
        "set up career os": "INITIALIZE_CAREER_OS",
        "help me get started": "INITIALIZE_CAREER_OS",
        "run a fresh live job search": "LIVE_OPPORTUNITY_SEARCH",
        "update my resume": "BUILD_RESUME",
        "here's a job I want": "ADD_JOB_OPPORTUNITY",
        "am I qualified for this?": "QUALIFY_JOB",
        "make me a resume for this": "BUILD_RESUME",
        "check my career setup": "CHECK_SYSTEM",
        "continue where we left off": "CONTINUE_ONBOARDING",
        "build my career profile": "BUILD_PROFILE",
        "create a role family": "CREATE_ROLE_FAMILY",
        "build my lane base resume": "BUILD_LANE_BASE",
        "validate my resume": "VALIDATE_RESUME",
        "prepare my application packet": "PREPARE_APPLICATION_PACKET",
        "show my status": "SHOW_STATUS",
        "migrate my workspace": "MIGRATE_WORKSPACE",
        "troubleshoot this error": "TROUBLESHOOT",
        "what should I learn next": "WHAT_SHOULD_I_LEARN_NEXT",
        "build my learning path": "BUILD_MY_LEARNING_PATH",
        "compare these courses": "COMPARE_COURSES",
        "improve my SOC resume": "IMPROVE_MY_SOC_RESUME",
        "improve my NOC resume": "IMPROVE_MY_NOC_RESUME",
        "improve my vulnerability resume": "IMPROVE_MY_VULNERABILITY_RESUME",
        "what certifications are worth it": "WHAT_CERTIFICATIONS_ARE_WORTH_IT",
        "I finished this course": "I_FINISHED_THIS_COURSE",
        "what project should I build": "WHAT_PROJECT_SHOULD_I_BUILD",
        "show my highest ROI gaps": "SHOW_MY_HIGHEST_ROI_GAPS",
    }

    def test_supported_intents(self):
        for request, expected in self.CASES.items():
            with self.subTest(request=request):
                self.assertIn(expected, route_module.classify_intents(request))

    def test_multi_intent_request_preserves_workflow_order(self):
        intents = route_module.classify_intents("Here's a job I want. Am I qualified, and can you make me a resume?")
        self.assertEqual(intents, ["ADD_JOB_OPPORTUNITY", "QUALIFY_JOB", "BUILD_RESUME"])

    def test_resume_first_setup_routes_to_one_shot_package_workflow(self):
        with tempfile.TemporaryDirectory() as root:
            result = route_module.route("Here's my resume. Set up Career OS for me.", Path(root) / "workspace", CLI)
        self.assertEqual(result["effective_intent"], "SET_ME_UP")
        self.assertEqual(result["workflow"], "ONE_SHOT_SOURCE_BOOTSTRAP")
        self.assertEqual(result["next_commands"], ["careeros workflow setup --start --source <path> --mode FAST"])

    def test_canonical_update_conversation_examples(self):
        examples = (
            "I got my AWS certification today.",
            "My employment dates are wrong.",
            "I forgot a volunteer role.",
            "Don't use that project publicly.",
            "I'm no longer targeting PM jobs.",
        )
        for request in examples:
            with self.subTest(request=request):
                self.assertIn("UPDATE_CAREER_INFORMATION", route_module.classify_intents(request))


class WorkspaceStateRouterTests(unittest.TestCase):
    def test_not_found_routes_to_bootstrap(self):
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "career-workspace"
            result = route_module.route("Set up Career OS for me", missing, CLI)
            self.assertEqual(result["workspace"]["state"], "NOT_FOUND")
            self.assertEqual(result["workflow"], "GUIDED_BOOTSTRAP")

    def test_initialized_workspace_without_onboarding_is_uninitialized(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "career-workspace"
            workspace.init_workspace(target, fixture_mode=True, workspace_id="workspace-state", timestamp="2026-10-02T12:00:00Z")
            result = route_module.route("continue", target, CLI)
            self.assertEqual(result["workspace"]["state"], "UNINITIALIZED")
            self.assertEqual(result["workflow"], "GUIDED_BOOTSTRAP")

    def test_clarification_overrides_resume_request(self):
        supported = {"status": "SUPPORTED", "version": "0.4.1", "required": ["0.4.1", "0.4.1"]}
        with patch.object(route_module, "package_probe", return_value=supported), patch.object(
            route_module, "workspace_snapshot", return_value={"state": "CLARIFICATION_REQUIRED", "workspace": "/tmp/workspace"}
        ):
            result = route_module.route("make me a resume", Path("/tmp/workspace"))
        self.assertEqual(result["effective_intent"], "REVIEW_CLARIFICATIONS")

    def test_migration_overrides_resume_request(self):
        supported = {"status": "SUPPORTED", "version": "0.4.1", "required": ["0.4.1", "0.4.1"]}
        with patch.object(route_module, "package_probe", return_value=supported), patch.object(
            route_module, "workspace_snapshot", return_value={"state": "MIGRATION_REQUIRED", "workspace": "/tmp/workspace"}
        ):
            result = route_module.route("make me a resume", Path("/tmp/workspace"))
        self.assertEqual(result["workflow"], "MIGRATION_PLAN_THEN_APPROVAL")

    def test_linked_source_state_routes_to_one_permission_decision(self):
        supported = {"status": "SUPPORTED", "version": "0.4.1", "required": ["0.4.1", "0.4.1"]}
        with patch.object(route_module, "package_probe", return_value=supported), patch.object(
            route_module, "workspace_snapshot", return_value={
                "state": "SOURCE_ENRICHMENT_APPROVAL_REQUIRED", "workspace": "/tmp/workspace",
            },
        ):
            result = route_module.route("continue", Path("/tmp/workspace"))
        self.assertEqual(result["workflow"], "LINKED_SOURCE_PERMISSION_THEN_CONSOLIDATED_INTAKE")
        self.assertEqual(len(result["next_commands"]), 2)


class ProgressiveBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "career-workspace"
        workspace.init_workspace(self.workspace, fixture_mode=True, workspace_id="workspace-bootstrap", timestamp="2026-10-02T12:00:00Z")
        bootstrap_module.start(self.workspace, CLI)

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, name: str, value: dict) -> Path:
        path = Path(self.temp.name) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_interrupt_and_resume_reads_workspace_sources(self):
        bootstrap_module.save_section(self.workspace, "employment", self._write("employment.json", {"employment": []}))
        resumed = bootstrap_module.progress(self.workspace)
        self.assertIn("employment", resumed["completed_sections"])
        self.assertNotEqual(resumed["next_section"], "employment")

    def test_add_forgotten_credential_updates_workspace_source(self):
        first = {"credentials": []}
        second = {"credentials": [{"local_id": "credential-example"}]}
        bootstrap_module.save_section(self.workspace, "credentials", self._write("credential-1.json", first))
        bootstrap_module.save_section(self.workspace, "credentials", self._write("credential-2.json", second))
        stored = json.loads((self.workspace / "sources/guided-onboarding/credentials.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, second)

    def test_correct_employment_date_updates_proposed_source_only(self):
        corrected = {"employment": [{"local_id": "employment-example", "start_year": 2021}]}
        bootstrap_module.save_section(self.workspace, "employment", self._write("corrected.json", corrected))
        self.assertFalse((self.workspace / "data/records/employment.json").exists())
        self.assertEqual(json.loads((self.workspace / "sources/guided-onboarding/employment.json").read_text())["employment"][0]["start_year"], 2021)

    def test_change_target_career_updates_target_section(self):
        payload = {"role_intents": [{"display_name": "Operations Coordinator"}]}
        bootstrap_module.save_section(self.workspace, "target_roles", self._write("target.json", payload))
        stored = json.loads((self.workspace / "sources/guided-onboarding/target_roles.json").read_text())
        self.assertEqual(stored["role_intents"][0]["display_name"], "Operations Coordinator")

    def test_job_before_onboarding_routes_back_to_onboarding(self):
        result = route_module.route("Here's a job I want", self.workspace, CLI)
        self.assertEqual(result["workspace"]["state"], "ONBOARDING_IN_PROGRESS")
        self.assertEqual(result["effective_intent"], "CONTINUE_ONBOARDING")
        self.assertEqual(result["workflow"], "COMPLETE_REQUIRED_ONBOARDING_BEFORE_JOB_WORKFLOW")

    def test_questions_come_from_installed_package(self):
        value = bootstrap_module.questions("identity")
        self.assertTrue(value["questions"])
        self.assertTrue(all(item["section"] == "identity" for item in value["questions"]))

    def test_assemble_requires_review_and_never_commits(self):
        fixture = json.loads((FIXTURE_ROOT / "early-career/onboarding/input.json").read_text(encoding="utf-8"))
        sections = {
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
        for section, payload in sections.items():
            bootstrap_module.save_section(self.workspace, section, self._write(f"{section}.json", payload))
        output = self.workspace / "sources" / "guided-onboarding-input.json"
        result = bootstrap_module.assemble(self.workspace, output)
        self.assertEqual(result["state"], "READY_FOR_PROPOSAL_INGEST")
        self.assertFalse(result["canonical_mutation"])
        self.assertFalse((self.workspace / "data/records/candidate.json").exists())


class AdversarialTruthTests(unittest.TestCase):
    CASES = (
        "Make me look like I have 5 years of AWS.",
        "Change my title to Project Manager.",
        "Just fill in the missing dates.",
        "Say I increased revenue 40%.",
        "Mark the certification complete.",
    )

    def test_truth_attacks_are_blocked(self):
        supported = {"status": "SUPPORTED", "version": "0.3.10", "required": ["0.3.10", "0.4.1"]}
        for request in self.CASES:
            with self.subTest(request=request), patch.object(route_module, "package_probe", return_value=supported), patch.object(
                route_module, "workspace_snapshot", return_value={"state": "READY", "workspace": "/tmp/workspace"}
            ):
                result = route_module.route(request, Path("/tmp/workspace"))
                self.assertEqual(result["workflow"], "TRUTH_CLARIFICATION")
                self.assertTrue(result["boundaries"]["truth_risks"])
                self.assertFalse(result["external_action_performed"])


class ApprovalBoundaryTests(unittest.TestCase):
    CASES = (
        ("Apply for me.", "EXTERNAL_WRITE"),
        ("Send this recruiter a message.", "EXTERNAL_WRITE"),
        ("Update my LinkedIn.", "PUBLIC_MUTATION"),
        ("Schedule the interview.", "EXTERNAL_WRITE"),
        ("Accept the offer.", "COMMITMENT"),
        ("Tell them I'll take $85k.", "COMMITMENT"),
    )

    def test_consequential_actions_are_prepare_only(self):
        supported = {"status": "SUPPORTED", "version": "0.3.10", "required": ["0.3.10", "0.4.1"]}
        for request, action_class in self.CASES:
            with self.subTest(request=request), patch.object(route_module, "package_probe", return_value=supported), patch.object(
                route_module, "workspace_snapshot", return_value={"state": "READY", "workspace": "/tmp/workspace"}
            ):
                result = route_module.route(request, Path("/tmp/workspace"))
                self.assertEqual(result["workflow"], "PREPARE_ONLY")
                self.assertEqual(result["boundaries"]["external_actions"][0]["class"], action_class)
                self.assertFalse(result["external_action_performed"])


class SkillPrivacyTests(unittest.TestCase):
    def test_no_absolute_personal_home_paths(self):
        mac_prefix = "/" + "Users/"
        linux_prefix = "/" + "home/"
        windows_marker = ":" + "\\" + "Users" + "\\"
        for path in SKILL_ROOT.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                content = path.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn(mac_prefix, content, path)
                self.assertNotIn(linux_prefix, content, path)
                self.assertNotIn(windows_marker, content, path)

    def test_no_candidate_data_files(self):
        suffixes = {path.suffix.lower() for path in SKILL_ROOT.rglob("*") if path.is_file()}
        self.assertFalse(suffixes.intersection({".pdf", ".docx", ".csv"}))

    def test_no_engine_schema_copies(self):
        self.assertFalse(any(path.name.endswith(".schema.json") for path in SKILL_ROOT.rglob("*")))

    def test_no_workspace_runtime_directories(self):
        forbidden = {"data", "state", "outputs", ".cache"}
        self.assertFalse(forbidden.intersection({path.name for path in SKILL_ROOT.iterdir()}))

    def test_manifest_contains_no_identity_defaults(self):
        manifest = json.loads((SKILL_ROOT / "skill-manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("candidate", manifest)


if __name__ == "__main__":
    unittest.main()


class CompleteWorkflowRouteTests(unittest.TestCase):
    def test_multi_request_preserves_technical_stage_and_refreshes_home_last(self):
        with patch.object(route_module, 'package_probe', return_value={'status':'SUPPORTED','version':'0.4.1'}), patch.object(route_module, 'workspace_snapshot', return_value={'state':'READY'}):
            result = route_module.route('Show my applications, prepare me for a technical interview, show career progress and workspace home', Path('/tmp/synthetic-workspace'))
        commands = result['next_commands']
        self.assertTrue(any('--stage TECHNICAL' in c for c in commands))
        self.assertTrue(any('application list' in c for c in commands))
        self.assertTrue(any(c.endswith(' report') for c in commands))
        self.assertTrue(commands[-1].endswith('workspace dashboard'))


class LiveDiscoveryRoutingTests(unittest.TestCase):
    def test_explicit_current_job_request_uses_public_source_route(self):
        with patch.object(route_module, 'package_probe', return_value={'status':'SUPPORTED','version':'0.4.1'}), patch.object(route_module, 'workspace_snapshot', return_value={'state':'READY'}):
            result = route_module.route('Find current jobs for me', Path('/tmp/synthetic-workspace'))
        self.assertEqual(result['effective_intent'],'LIVE_OPPORTUNITY_SEARCH')
        self.assertTrue(any('discover-source' in c for c in result['next_commands']))
        self.assertFalse(result['external_action_performed'])

class LearningWorkflowRouteTests(unittest.TestCase):
    def test_complete_learning_intents_resolve_to_actual_cli_actions(self):
        cases={
            'Build my learning path':'learning build',
            'What certifications are worth it':'learning build',
            'What project should I build':'learning build',
            'Show my gaps':'learning gaps',
            'Set my learning budget':'learning preferences',
            'Find current courses':'learning discover',
            'I finished this course':'learning progress',
            'Reassess role eligibility after training':'learning reassess',
        }
        for request,command in cases.items():
            with self.subTest(request=request),patch.object(route_module,'package_probe',return_value={'status':'SUPPORTED','version':'0.4.1'}),patch.object(route_module,'workspace_snapshot',return_value={'state':'READY'}):
                result=route_module.route(request,Path('/tmp/synthetic-workspace'))
                self.assertTrue(any(command in value for value in result['next_commands']),result)
                self.assertFalse(result['external_action_performed'])
