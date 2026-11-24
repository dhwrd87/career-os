#!/usr/bin/env python3
"""Read-only intent, compatibility, and workspace-state router for Career OS."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any


MIN_PACKAGE = "0.4.3"
MAX_PACKAGE_EXCLUSIVE = "0.5.0"

INTENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("SHOW_OPPORTUNITIES", (r"show.*(?:ready now|stretch roles|dream roles)", r"my job matches")),
    ("PLAN_DREAM_ROLE", (r"dream (?:role|job|career)", r"(?:work|plan).*towards?", r"(?:become|want to be) (?:a|an) ")),
    ("PLAN_STRETCH_ROLE", (r"(?:training|learn|plan).*(?:stretch|this role|that role|target role)", r"close.*(?:skill gaps|gaps for)")),
    ("SUGGEST_OTHER_ROLES", (r"other job titles", r"other roles", r"what else could i do", r"jobs i haven.t considered", r"additional career paths")),
    ("PREPARE_TOP_MATCHES", (r"(?:resumes?|applications?).*(?:top|best|selected|strongest)", r"(?:top|best|selected|strongest).*(?:resumes?|applications?)")),
    ("FIND_ACTUAL_JOBS", (r"find.*(?:jobs|openings|work)", r"search.*(?:jobs|openings)")),
    ("DISCOVER_LEARNING_RESOURCES", (r"find.*(?:current|live).*(?:courses|learning resources)", r"discover.*(?:courses|learning resources)")),
    ("SET_LEARNING_PREFERENCES", (r"learning budget", r"learning preferences", r"subscriptions.*learning", r"hours.*learn")),
    ("REASSESS_AFTER_LEARNING", (r"reassess.*(?:learning|training|eligibility|roles)", r"update.*profile.*(?:course|training|learning)")),
    ("SHOW_DASHBOARD", (r"dashboard", r"home page", r"workspace navigation", r"workspace home")),
    ("PREPARE_INTERVIEW", (r"interview prep", r"prepare.*interview", r"practice.*interview")),
    ("PLAN_FOLLOW_UP", (r"follow.up", r"follow up")),
    ("TRACK_APPLICATIONS", (r"track.*application", r"show my applications", r"application pipeline", r"already applied", r"record.*outcome")),
    ("CAREER_PROGRESS", (r"career progress", r"conversion report", r"outcome report", r"career capital")),
    ("COVER_LETTER", (r"cover letter",)),
    ("EXPORT_DOCX", (r"editable resume", r"docx", r"word resume")),
    ("SET_ME_UP", (r"build my master resume", r"establish.*professional history", r"here(?:'|’)s my (?:resume|cv).*(?:set up|career os)", r"set me up from (?:my )?(?:resume|cv)", r"build my career os from")),
    ("IMPROVE_MY_CAREER_PROFILE", (r"improve my career profile", r"deepen my career evidence")),
    ("FIND_MY_CAREER_PATHS", (r"find my career paths", r"what career paths", r"career lane")),
    ("BUILD_LANE_BASE", (r"resumes for.*(?:types|families|directions)", r"career.specific.*resumes", r"build (?:my |a )?lane base", r"base resume", r"resume for (?:this |my )?role family")),
    ("LIVE_OPPORTUNITY_SEARCH", (r"live (?:job|opportunity) search", r"fresh (?:job|role|opportunity) search", r"find (?:me )?(?:current|live) (?:jobs|roles|opportunities)")),
    ("CATALOG_DISCOVERY", (r"discover.*opportunit", r"find.*jobs", r"find.*opportunit")),
    ("HELP_ME_GET_A_JOB", (r"help me get a job", r"start my job search")),
    ("TAILOR_FOR_THIS_JOB", (r"tailor .* for this job", r"tailor my resume")),
    ("WHAT_SHOULD_I_LEARN_NEXT", (r"what should i learn next", r"next skill to learn")),
    ("BUILD_MY_LEARNING_PATH", (r"build my learning path", r"learning roadmap")),
    ("COMPARE_COURSES", (r"compare (?:these )?courses", r"which course (?:is|would be) better")),
    ("IMPROVE_MY_SOC_RESUME", (r"improve my soc resume", r"learn.*soc resume")),
    ("IMPROVE_MY_NOC_RESUME", (r"improve my noc resume", r"learn.*noc resume")),
    ("IMPROVE_MY_VULNERABILITY_RESUME", (r"improve my vulnerability resume", r"learn.*vulnerability resume")),
    ("WHAT_CERTIFICATIONS_ARE_WORTH_IT", (r"what certifications? are worth it", r"which certification should i")),
    ("I_FINISHED_THIS_COURSE", (r"i finished this course", r"i completed this course")),
    ("WHAT_PROJECT_SHOULD_I_BUILD", (r"what project should i build", r"project should i build next")),
    ("SHOW_MY_HIGHEST_ROI_GAPS", (r"highest roi gaps", r"highest value gaps")),
    ("SHOW_MY_GAPS", (r"show my gaps", r"development priorit", r"career gaps")),
    ("CHECK_SYSTEM", (r"check (?:my )?(?:career )?(?:os|setup|system)", r"run doctor", r"is .* ready")),
    ("MIGRATE_WORKSPACE", (r"migrat", r"upgrade (?:my )?workspace")),
    ("REVIEW_CLARIFICATIONS", (r"clarification", r"unresolved", r"what do you need from me")),
    ("INITIALIZE_CAREER_OS", (r"set up career os", r"setup career os", r"help me get started", r"use career os")),
    ("CONTINUE_ONBOARDING", (r"continue where we left off", r"continue onboarding", r"finish (?:my )?setup", r"continue$")),
    ("UPDATE_CAREER_INFORMATION", (
        r"update my career", r"add a forgotten", r"forgot (?:a|to add)", r"correct .*employment", r"dates? (?:are|is) wrong",
        r"change .*career", r"new credential", r"got my .*certification", r"certification is (?:finished|complete)",
        r"don't use .*public", r"do not use .*public", r"no longer targeting", r"learned [a-z0-9]", r"actually led",
    )),
    ("BUILD_PROFILE", (r"build (?:my )?(?:career )?profile", r"compile (?:my )?profile")),
    ("CREATE_ROLE_FAMILY", (r"role famil", r"target role strategy")),
    ("ADD_JOB_OPPORTUNITY", (r"here(?:'|’)s a job", r"job i want", r"add (?:this )?job", r"job description")),
    ("QUALIFY_JOB", (r"am i qualified", r"qualify (?:me|this job)", r"how well do i fit", r"job fit")),
    ("VALIDATE_RESUME", (r"validate (?:my |the )?resume", r"check (?:my |the )?resume")),
    ("BUILD_RESUME", (r"make me a resume", r"build (?:my |a )?resume", r"update my resume", r"targeted resume")),
    ("PREPARE_APPLICATION_PACKET", (r"prepare (?:my |an )?application", r"application packet")),
    ("CHECK_APPLICATION_PACKET", (r"check (?:my |the )?application packet", r"packet status")),
    ("SHOW_STATUS", (r"where am i", r"what(?:'|’)s next", r"show (?:my )?status", r"career os status")),
    ("TROUBLESHOOT", (r"troubleshoot", r"fix career os", r"why (?:did|is) .* fail", r"error")),
)

TRUTH_RISKS: tuple[tuple[str, str], ...] = (
    (r"make me look like i have .*years", "UNSUPPORTED_EXPERIENCE"),
    (r"change my title to", "TITLE_INFLATION"),
    (r"(?:just )?fill in (?:the )?missing dates", "INVENTED_DATES"),
    (r"say i (?:increased|improved|reduced).*(?:%|percent)", "UNSUPPORTED_METRIC"),
    (r"mark (?:the |my )?certification complete", "UNVERIFIED_CREDENTIAL"),
)

EXTERNAL_ACTIONS: tuple[tuple[str, str, str], ...] = (
    (r"apply for me|submit (?:the |my )?application", "EXTERNAL_WRITE", "PREPARE_APPLICATION_PACKET"),
    (r"send (?:this |the )?recruiter|message (?:the |this )?recruiter", "EXTERNAL_WRITE", "DRAFT_RECRUITER_MESSAGE"),
    (r"update my linkedin|edit my linkedin", "PUBLIC_MUTATION", "DRAFT_PROFILE_CHANGES"),
    (r"schedule (?:the |my )?interview", "EXTERNAL_WRITE", "PREPARE_SCHEDULING_REPLY"),
    (r"accept (?:the |this )?offer", "COMMITMENT", "DRAFT_OFFER_RESPONSE"),
    (r"tell them i(?:'|’)ll take|tell them i will take", "COMMITMENT", "DRAFT_COMPENSATION_RESPONSE"),
)


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError(f"invalid semantic version: {value!r}")
    return tuple(int(part) for part in match.groups())


def classify_package_version(value: str) -> str:
    current = version_tuple(value)
    if current < version_tuple(MIN_PACKAGE):
        return "OLDER_BUT_MIGRATABLE"
    if current >= version_tuple(MAX_PACKAGE_EXCLUSIVE):
        return "UNSUPPORTED_FUTURE"
    return "SUPPORTED"


def _run(command: str, *args: str) -> tuple[int, dict[str, Any]]:
    words = shlex.split(command)
    if not words or shutil.which(words[0]) is None:
        return 127, {"error": {"code": "PACKAGE_ABSENT", "message": "careeros command not found"}}
    completed = subprocess.run([*words, *args], capture_output=True, text=True, check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"error": {"code": "INVALID_CLI_OUTPUT", "message": completed.stderr.strip() or completed.stdout.strip()}}
    return completed.returncode, payload


def package_probe(command: str) -> dict[str, Any]:
    code, report = _run(command, "version", "--json")
    if code == 127:
        return {"status": "PACKAGE_ABSENT", "required": [MIN_PACKAGE, MAX_PACKAGE_EXCLUSIVE]}
    version = report.get("package_version")
    if code != 0 or not isinstance(version, str):
        return {"status": "PACKAGE_UNREADABLE", "required": [MIN_PACKAGE, MAX_PACKAGE_EXCLUSIVE], "diagnostic": report}
    return {"status": classify_package_version(version), "version": version, "required": [MIN_PACKAGE, MAX_PACKAGE_EXCLUSIVE]}


def classify_intents(request: str) -> list[str]:
    lowered = request.casefold().strip()
    found = [intent for intent, patterns in INTENT_PATTERNS if any(re.search(pattern, lowered) for pattern in patterns)]
    return found or ["TROUBLESHOOT"]


def assess_boundaries(request: str) -> dict[str, Any]:
    lowered = request.casefold()
    truth = [code for pattern, code in TRUTH_RISKS if re.search(pattern, lowered)]
    external = [
        {"class": action_class, "safe_alternative": alternative}
        for pattern, action_class, alternative in EXTERNAL_ACTIONS
        if re.search(pattern, lowered)
    ]
    return {"truth_risks": truth, "external_actions": external}


def workspace_snapshot(workspace: Path, command: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = workspace / "workspace-manifest.json"
    config = workspace / "careeros.yaml"
    if not workspace.exists():
        return {"state": "NOT_FOUND", "workspace": str(workspace)}
    if not manifest.exists() and not config.exists():
        return {"state": "UNINITIALIZED", "workspace": str(workspace)}
    if manifest.exists() != config.exists():
        return {"state": "CORRUPT", "workspace": str(workspace), "detail": "partial initialization"}

    _, doctor = _run(command, "--workspace", str(workspace), "doctor", "--json")
    outcome = doctor.get("outcome")
    outcome_map = {
        "MIGRATION_REQUIRED": "MIGRATION_REQUIRED",
        "CONFIG_INVALID": "INVALID_CONFIG",
        "WORKSPACE_CORRUPT": "CORRUPT",
        "UNSUPPORTED_WORKSPACE": "UNSUPPORTED_VERSION",
        "FUTURE_WORKSPACE": "UNSUPPORTED_VERSION",
        "PRIVACY_BOUNDARY_FAILURE": "CORRUPT",
    }
    if outcome in outcome_map:
        return {"state": outcome_map[outcome], "workspace": str(workspace), "doctor": doctor}
    if outcome not in {"READY", "READY_WITH_OPTIONAL_LIMITATIONS"}:
        return {"state": "CORRUPT", "workspace": str(workspace), "doctor": doctor}

    status_code, status = _run(command, "--workspace", str(workspace), "status")
    if status_code != 0 or "state" not in status:
        return {"state": "CORRUPT", "workspace": str(workspace), "doctor": doctor, "status": status}
    _, setup_status = _run(command, "--workspace", str(workspace), "workflow", "setup", "--status")
    if setup_status.get("state") == "SOURCE_ENRICHMENT_APPROVAL_REQUIRED":
        return {
            "state": "SOURCE_ENRICHMENT_APPROVAL_REQUIRED", "workspace": str(workspace),
            "doctor": doctor, "status": status, "setup": setup_status,
        }
    onboarding = status["state"].get("onboarding")
    if onboarding is None:
        state = "UNINITIALIZED"
    else:
        session_state = onboarding.get("state")
        state = {
            "STARTED": "ONBOARDING_IN_PROGRESS",
            "NEEDS_CLARIFICATION": "CLARIFICATION_REQUIRED",
            "REVIEW_READY": "REVIEW_READY",
            "APPROVED": "READY",
        }.get(session_state, "ONBOARDING_IN_PROGRESS")
    return {"state": state, "workspace": str(workspace), "doctor": doctor, "status": status}


def route(request: str, workspace: Path, command: str = "careeros") -> dict[str, Any]:
    package = package_probe(command)
    intents = classify_intents(request)
    boundaries = assess_boundaries(request)
    snapshot = {"state": "UNKNOWN", "workspace": str(workspace.resolve())}
    effective = intents[0]
    workflow = effective
    next_commands: list[str] = []
    stop_reason = None

    if package["status"] != "SUPPORTED":
        stop_reason = package["status"]
        workflow = "PACKAGE_COMPATIBILITY_RECOVERY"
    else:
        snapshot = workspace_snapshot(workspace, command)
        state = snapshot["state"]
        if boundaries["external_actions"]:
            action = boundaries["external_actions"][0]
            effective = action["safe_alternative"]
            workflow = "PREPARE_ONLY"
            stop_reason = f"{action['class']}_NOT_IMPLEMENTED"
        elif boundaries["truth_risks"]:
            effective = "REVIEW_CLARIFICATIONS"
            workflow = "TRUTH_CLARIFICATION"
            stop_reason = "UNSUPPORTED_FACTUAL_MUTATION"
        elif state == "MIGRATION_REQUIRED" and effective not in {"CHECK_SYSTEM", "MIGRATE_WORKSPACE", "TROUBLESHOOT"}:
            effective = "MIGRATE_WORKSPACE"
            workflow = "MIGRATION_PLAN_THEN_APPROVAL"
            next_commands = ["careeros migrate --plan"]
        elif state in {"NOT_FOUND", "UNINITIALIZED"} and effective not in {"CHECK_SYSTEM", "TROUBLESHOOT"}:
            source_first = effective == "SET_ME_UP" or bool(re.search(
                r"(?:here(?:'|’)s|attached|uploaded|use) (?:my |this )?(?:resume|cv)|career history (?:file|source|notes)",
                request.casefold(),
            ))
            effective = "SET_ME_UP" if source_first else "INITIALIZE_CAREER_OS"
            workflow = "ONE_SHOT_SOURCE_BOOTSTRAP" if source_first else "GUIDED_BOOTSTRAP"
            next_commands = (["careeros workflow setup --start --source <path> --mode FAST"] if source_first else ["careeros version --json", "careeros doctor --json", "careeros init", "careeros doctor --json", "careeros onboarding start"])
        elif state == "SOURCE_ENRICHMENT_APPROVAL_REQUIRED":
            effective = "CONTINUE_ONBOARDING"
            workflow = "LINKED_SOURCE_PERMISSION_THEN_CONSOLIDATED_INTAKE"
            next_commands = [
                "show detected linked sources and request one read-only decision",
                "careeros workflow setup --linked-sources APPROVE|DECLINE",
            ]
        elif state == "CLARIFICATION_REQUIRED" and effective not in {"CHECK_SYSTEM", "REVIEW_CLARIFICATIONS", "SHOW_STATUS", "TROUBLESHOOT"}:
            effective = "REVIEW_CLARIFICATIONS"
            workflow = "CLARIFICATION_BEFORE_CONTINUING"
            next_commands = ["careeros clarification list"]
        elif state == "REVIEW_READY" and effective == "CONTINUE_ONBOARDING":
            workflow = "COMMIT_PREVIEW_THEN_APPROVAL"
            next_commands = ["careeros status", "request explicit approval", "careeros onboarding commit --actor <human>"]
        elif state == "ONBOARDING_IN_PROGRESS" and effective == "CONTINUE_ONBOARDING":
            workflow = "RESUME_PROGRESSIVE_ONBOARDING"
            next_commands = ["bootstrap.py progress", "bootstrap.py questions --section <next>"]
        elif state == "ONBOARDING_IN_PROGRESS" and effective in {
            "ADD_JOB_OPPORTUNITY", "QUALIFY_JOB", "BUILD_RESUME", "VALIDATE_RESUME", "PREPARE_APPLICATION_PACKET"
        }:
            effective = "CONTINUE_ONBOARDING"
            workflow = "COMPLETE_REQUIRED_ONBOARDING_BEFORE_JOB_WORKFLOW"
            next_commands = ["bootstrap.py progress", "bootstrap.py questions --section <next>"]
        elif state == "READY" and effective == "UPDATE_CAREER_INFORMATION":
            workflow = "CANONICAL_UPDATE_PREVIEW_APPROVAL_COMMIT"
            next_commands = [
                "careeros update propose --input <workspace-source-json>",
                "careeros update preview --changeset-id <id>",
                "request explicit approval",
                "careeros update approve --changeset-id <id> --actor <human>",
                "careeros update commit --changeset-id <id> --actor <human>",
                "careeros history <record-id>",
            ]
        elif state == "READY" and effective in {
            "WHAT_SHOULD_I_LEARN_NEXT", "BUILD_MY_LEARNING_PATH", "COMPARE_COURSES",
            "IMPROVE_MY_SOC_RESUME", "IMPROVE_MY_NOC_RESUME", "IMPROVE_MY_VULNERABILITY_RESUME",
            "WHAT_CERTIFICATIONS_ARE_WORTH_IT", "WHAT_PROJECT_SHOULD_I_BUILD", "SHOW_MY_HIGHEST_ROI_GAPS",
        }:
            workflow = "LEARNING_PATH_ANALYSIS_REVIEW_ONLY"
            next_commands = ["load current profile, role family, observed job gaps, and learning preferences", "discover and reverify current provider candidates", "rank minimal evidence-producing path", "present recommendation for human review"]
        elif state == "READY" and effective == "I_FINISHED_THIS_COURSE":
            workflow = "LEARNING_COMPLETION_EVIDENCE_REVIEW"
            next_commands = ["verify completion and artifacts", "create proposed evidence review packet", "request canonical review; do not promote skills automatically"]
        elif state == "READY" and effective == "LIVE_OPPORTUNITY_SEARCH":
            workflow = "PERSISTENT_REGISTRY_LIVE_DISCOVERY"
            next_commands = [
                "build/load OpportunityRegistryV1 across all historical runs",
                "careeros discover-source --greenhouse-board <board> --employer <verified-name> --approve-network",
                "review source-grounded requirements in the saved proposal; set requirement_review_status REVIEWED",
                "careeros discover --catalog <reviewed-proposal.json>",
                "reconcile every result before NEW classification",
                "count only NEW; report known opportunities separately",
                "freshness and qualification for NEW or materially updated opportunities",
            ]

    command_routes = {
        'SHOW_DASHBOARD': ['workspace dashboard'],
        'PREPARE_INTERVIEW': ['interview --opportunity-id <id> --stage RECRUITER_SCREEN'],
        'PLAN_FOLLOW_UP': ['application follow-up --application-id <id> --due-at <UTC> --channel EMAIL'],
        'TRACK_APPLICATIONS': ['application list'],
        'CAREER_PROGRESS': ['report'],
        'COVER_LETTER': ['application cover-letter --opportunity-id <id> --build-id <id>'],
        'EXPORT_DOCX': ['resume export-docx --build-id <id>'],
        'CATALOG_DISCOVERY': ['discover --catalog <json> --limit 25'],
        'SHOW_MY_GAPS': ['learning gaps'],
        'SET_LEARNING_PREFERENCES': ['learning preferences --input <reviewed-preferences.json>'],
        'DISCOVER_LEARNING_RESOURCES': ['learning discover --source <public-https-index-or-course-url> --query <generic-capability> --approve-network'],
        'I_FINISHED_THIS_COURSE': ['learning status', 'learning progress --input <reviewed-progress-event.json>'],
        'REASSESS_AFTER_LEARNING': ['learning propose-update --input <reviewed-artifact-claims.json>', 'learning reassess'],
    }
    if snapshot['state'] == 'READY' and not boundaries['external_actions'] and not boundaries['truth_risks']:
        if effective in command_routes:
            selected_routes = [c for intent in intents if intent in command_routes for c in command_routes[intent]]
            selected_routes = [c for c in selected_routes if c != 'workspace dashboard'] + ([c for c in selected_routes if c == 'workspace dashboard'])
            if 'technical' in request.casefold():
                selected_routes = [c.replace('--stage RECRUITER_SCREEN', '--stage TECHNICAL') for c in selected_routes]
            next_commands = ['careeros --workspace ' + shlex.quote(str(workspace.resolve())) + ' ' + c for c in selected_routes]
            workflow = 'LOCAL_WORKSPACE_WORKFLOW'
        elif effective in {'WHAT_SHOULD_I_LEARN_NEXT', 'BUILD_MY_LEARNING_PATH', 'COMPARE_COURSES', 'SHOW_MY_HIGHEST_ROI_GAPS', 'IMPROVE_MY_SOC_RESUME', 'IMPROVE_MY_NOC_RESUME', 'IMPROVE_MY_VULNERABILITY_RESUME', 'WHAT_CERTIFICATIONS_ARE_WORTH_IT', 'WHAT_PROJECT_SHOULD_I_BUILD'}:
            next_commands = ['careeros --workspace ' + shlex.quote(str(workspace.resolve())) + ' ' + c for c in ['learning gaps','learning preferences','learning build --catalog <verified-course-catalog.json>']]
            workflow = 'LEARNING_PATH_ANALYSIS_REVIEW_ONLY'

    connected={
        'FIND_ACTUAL_JOBS':'workflow jobs --request <search-request.json> --approve-network',
        'LIVE_OPPORTUNITY_SEARCH':'workflow jobs --request <search-request.json> --approve-network',
        'HELP_ME_GET_A_JOB':'workflow jobs --request <search-request.json> --approve-network',
        'SUGGEST_OTHER_ROLES':'workflow roles', 'FIND_MY_CAREER_PATHS':'workflow roles',
        'PREPARE_TOP_MATCHES':'workflow prepare --top 3',
        'SHOW_OPPORTUNITIES':'workflow opportunities',
        'PLAN_DREAM_ROLE':'workflow plan --opportunity-id <target-posting-id> --catalog <verified-learning-options.json>',
        'PLAN_STRETCH_ROLE':'workflow plan --opportunity-id <target-posting-id> --catalog <verified-learning-options.json>',
    }
    if snapshot['state']=='READY' and effective in connected and not boundaries['external_actions'] and not boundaries['truth_risks']:
        selected=[connected[intent] for intent in intents if intent in connected]
        if any('workflow jobs' in command for command in selected):selected=[command for command in selected if 'workflow prepare' not in command]
        selected=list(dict.fromkeys(selected))
        next_commands=['careeros --workspace '+shlex.quote(str(workspace.resolve()))+' '+command for command in selected]
        workflow='CONNECTED_CAREER_WORKFLOW'

    return {
        "schema": "careeros.skill-route.v1",
        "request": request,
        "package": package,
        "workspace": snapshot,
        "requested_intents": intents,
        "effective_intent": effective,
        "workflow": workflow,
        "next_commands": next_commands,
        "boundaries": boundaries,
        "stop_reason": stop_reason,
        "external_action_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--request", required=True)
    parser.add_argument("--careeros-command", default="careeros")
    args = parser.parse_args()
    print(json.dumps(route(args.request, args.workspace, args.careeros_command), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
