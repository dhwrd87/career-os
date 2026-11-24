"""Career OS command surface, offline by default with consented public readers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from careeros import application, evidence_expansion, intake, lane_base, migrations, onboarding, opportunity, opportunity_registry, portability, profile, resume, updates, workflows, workspace as workspace_api
from careeros.config.loader import load_config
from careeros.core.errors import CareerOSError
from careeros.core.exit_codes import ERROR_EXIT_CODES, ExitCode
from careeros.core.io import read_json
from careeros.schemas.validation import SchemaRegistry
from careeros.versions import version_report


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _emit_human(result: dict[str, Any]) -> None:
    if result.get("schema") == "careeros.doctor-result.v2":
        print(f"Career OS doctor: {result['outcome']}")
        for item in result.get("checks", []):
            print(f"[{item['status']}] {item['check']}: {item['detail']}")
        return
    if result.get("schema") == "careeros.version-report.v1":
        supported = result["supported_workspace_format"]
        print(f"Career OS {result['package_version']}")
        print(f"Workspace formats: {supported['minimum']}..{supported['maximum']} (current {supported['current']})")
        print(f"Schema bundle: {result['schema_bundle_version']}")
        print(f"Compiler: {result['compiler_version']}; renderer: {result['renderer_version']}")
        return
    _emit(result)


def _workspace(args: argparse.Namespace) -> Path:
    return Path(args.workspace).resolve()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="careeros")
    root.add_argument("--workspace", default=".")
    root.add_argument("--timestamp", default=None, help="Deterministic UTC timestamp for tests")
    commands = root.add_subparsers(dest="command", required=True)
    version = commands.add_parser("version")
    version.add_argument("--json", action="store_true")
    init = commands.add_parser("init")
    init.add_argument("--fixture-mode", action="store_true")
    init.add_argument("--workspace-id")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    onboarding_cmd = commands.add_parser("onboarding")
    onboarding_sub = onboarding_cmd.add_subparsers(dest="onboarding_command", required=True)
    onboarding_sub.add_parser("start")
    ingest = onboarding_sub.add_parser("ingest")
    ingest.add_argument("--input", required=True)
    commit = onboarding_sub.add_parser("commit")
    commit.add_argument("--actor", required=True)
    intake_cmd = commands.add_parser("intake")
    intake_sub = intake_cmd.add_subparsers(dest="intake_command", required=True)
    intake_compile = intake_sub.add_parser("compile")
    intake_compile.add_argument("--source", action="append", required=True)
    intake_compile.add_argument("--mode", choices=("FAST", "DEEP"), default="FAST")
    intake_compile.add_argument("--linked-source-decision", choices=("APPROVE", "DECLINE"))
    intake_complete = intake_sub.add_parser("complete")
    intake_complete.add_argument("--answers", required=True)
    intake_sub.add_parser("preview")
    workflow = commands.add_parser("workflow")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_route = workflow_sub.add_parser("route")
    workflow_route.add_argument("intent", choices=workflows.HIGH_LEVEL_WORKFLOWS)
    search = workflow_sub.add_parser('jobs')
    search.add_argument('--request', required=True)
    search.add_argument('--approve-network', action='store_true')
    workflow_sub.add_parser('roles')
    workflow_sub.add_parser('strategy')
    directions=workflow_sub.add_parser('directions')
    directions.add_argument('--intent-index',type=int,action='append',required=True)
    directions.add_argument('--approve',action='store_true');directions.add_argument('--actor')
    workflow_sub.add_parser('opportunities')
    batch = workflow_sub.add_parser('prepare')
    batch.add_argument('--top', type=int, default=3)
    batch.add_argument('--opportunity-id', action='append')
    batch.add_argument('--resume-only',action='store_true')
    batch.add_argument('--cover-letter',choices=['AUTO','REQUESTED','OMIT'],default='AUTO')
    plan = workflow_sub.add_parser('plan')
    plan.add_argument('--opportunity-id', required=True)
    plan.add_argument('--catalog')
    setup = workflow_sub.add_parser("setup")
    setup_mode = setup.add_mutually_exclusive_group(required=True)
    setup_mode.add_argument("--start", action="store_true")
    setup_mode.add_argument("--linked-sources", choices=("APPROVE", "DECLINE"))
    setup_mode.add_argument("--complete", action="store_true")
    setup_mode.add_argument("--resolve", action="store_true")
    setup_mode.add_argument("--approve", action="store_true")
    setup_mode.add_argument("--status", action="store_true")
    setup.add_argument("--source", action="append", default=[])
    setup.add_argument("--answers")
    setup.add_argument("--resolutions")
    setup.add_argument("--mode", choices=("FAST", "DEEP"), default="FAST")
    setup.add_argument("--actor")
    setup.add_argument("--fixture-mode", action="store_true")
    clarification = commands.add_parser("clarification")
    clarification_sub = clarification.add_subparsers(dest="clarification_command", required=True)
    clarification_sub.add_parser("list")
    resolve = clarification_sub.add_parser("resolve")
    resolve.add_argument("--resolutions", required=True)
    expansion = commands.add_parser("evidence-expansion")
    expansion_sub = expansion.add_subparsers(dest="evidence_expansion_command", required=True)
    expansion_start = expansion_sub.add_parser("start")
    expansion_start.add_argument("--lane-context", action="append", default=[])
    expansion_start.add_argument("--job-context", action="append", default=[])
    expansion_resolve = expansion_sub.add_parser("resolve")
    expansion_resolve.add_argument("--answers", required=True)
    expansion_approve = expansion_sub.add_parser("approve")
    expansion_approve.add_argument("--actor", required=True)
    expansion_sub.add_parser("promote")
    expansion_sub.add_parser("status")
    profile_cmd = commands.add_parser("profile")
    profile_sub = profile_cmd.add_subparsers(dest="profile_command", required=True)
    profile_sub.add_parser("build")
    role = commands.add_parser("role-family")
    role_sub = role.add_subparsers(dest="role_command", required=True)
    role_build = role_sub.add_parser("build")
    role_build.add_argument("--intent-index", type=int, default=0)
    role_build.add_argument("--approve", action="store_true")
    lane = commands.add_parser("lane-base")
    lane_sub = lane.add_subparsers(dest="lane_base_command", required=True)
    lane_build = lane_sub.add_parser("build")
    lane_build.add_argument("--accept", action="store_true")
    lane_build.add_argument("--actor")
    lane_accept = lane_sub.add_parser("accept")
    lane_accept.add_argument("--lane-base-id", required=True)
    lane_accept.add_argument("--actor", required=True)
    lane_status = lane_sub.add_parser("status")
    lane_status.add_argument("--lane-base-id", required=True)
    opp = commands.add_parser("opportunity")
    opp_sub = opp.add_subparsers(dest="opportunity_command", required=True)
    opp_ingest = opp_sub.add_parser("ingest")
    opp_ingest.add_argument("--input", required=True)
    opp_sub.add_parser("registry")
    opp_reconcile = opp_sub.add_parser("reconcile")
    opp_reconcile.add_argument("--input", required=True)
    qualify = commands.add_parser("qualify")
    qualify.add_argument("--opportunity-id", required=True)
    resume_cmd = commands.add_parser("resume")
    resume_sub = resume_cmd.add_subparsers(dest="resume_command", required=True)
    resume_build = resume_sub.add_parser("build")
    resume_build.add_argument("--opportunity-id", required=True)
    resume_validate = resume_sub.add_parser("validate")
    resume_validate.add_argument("--build-id", required=True)
    app = commands.add_parser("application")
    app_sub = app.add_subparsers(dest="application_command", required=True)
    app_prepare = app_sub.add_parser("prepare")
    app_prepare.add_argument("--opportunity-id", required=True)
    app_prepare.add_argument("--build-id", required=True)
    app_prepare.add_argument('--cover-letter',choices=['AUTO','REQUESTED','OMIT'],default='AUTO')
    bank=app_sub.add_parser('answer-bank')
    bank.add_argument('--input');bank.add_argument('--approve',action='store_true');bank.add_argument('--actor')
    update = commands.add_parser("update")
    update_sub = update.add_subparsers(dest="update_command", required=True)
    update_propose = update_sub.add_parser("propose")
    update_propose.add_argument("--input", required=True)
    update_preview = update_sub.add_parser("preview")
    update_preview.add_argument("--changeset-id", required=True)
    update_resolve = update_sub.add_parser("resolve")
    update_resolve.add_argument("--changeset-id", required=True)
    update_resolve.add_argument("--resolutions", required=True)
    update_approve = update_sub.add_parser("approve")
    update_approve.add_argument("--changeset-id", required=True)
    update_approve.add_argument("--actor", required=True)
    update_commit = update_sub.add_parser("commit")
    update_commit.add_argument("--changeset-id", required=True)
    update_commit.add_argument("--actor", required=True)
    history = commands.add_parser("history")
    history.add_argument("record_id", nargs="?")
    export = commands.add_parser("export")
    export.add_argument("--output", required=True)
    commands.add_parser("status")
    migrate = commands.add_parser("migrate")
    migrate_mode = migrate.add_mutually_exclusive_group(required=True)
    migrate_mode.add_argument("--plan", action="store_true")
    migrate_mode.add_argument("--apply", action="store_true")
    migrate_mode.add_argument("--status", action="store_true")
    schemas = commands.add_parser("schemas")
    schemas_sub = schemas.add_subparsers(dest="schemas_command", required=True)
    schemas_sub.add_parser("list")
    schema_validate = schemas_sub.add_parser("validate")
    schema_validate.add_argument("path")
    workspace = commands.add_parser("workspace")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)
    workspace_sub.add_parser("verify")
    workspace_sub.add_parser("dashboard")
    workspace_sub.add_parser("queue-audit")
    export_docx = resume_sub.add_parser("export-docx")
    export_docx.add_argument("--build-id", required=True)
    geometry = resume_sub.add_parser("geometry")
    geometry.add_argument("--build-id", required=True)
    geometry.add_argument("--golden")
    cover = app_sub.add_parser("cover-letter")
    cover.add_argument("--opportunity-id", required=True)
    cover.add_argument("--build-id", required=True)
    app_sub.add_parser("list")
    event = app_sub.add_parser("record")
    event.add_argument("--application-id", required=True)
    event.add_argument("--input", required=True)
    follow = app_sub.add_parser("follow-up")
    follow.add_argument("--application-id", required=True)
    follow.add_argument("--due-at", required=True)
    follow.add_argument("--channel", choices=("EMAIL", "PHONE", "PORTAL", "OTHER"), default="EMAIL")
    interview_cmd = commands.add_parser("interview")
    interview_cmd.add_argument("--opportunity-id", required=True)
    interview_cmd.add_argument("--stage", choices=("RECRUITER_SCREEN", "HIRING_MANAGER", "TECHNICAL", "PANEL", "FINAL", "OTHER"), default="RECRUITER_SCREEN")
    report = commands.add_parser("report")
    report.add_argument("--window-start", default="2000-01-01T00:00:00Z")
    report.add_argument("--window-end")
    discover = commands.add_parser("discover")
    discover.add_argument("--catalog", required=True)
    discover.add_argument("--limit", type=int, default=25)
    source_discovery = commands.add_parser('discover-source')
    source_discovery.add_argument('--greenhouse-board', required=True)
    source_discovery.add_argument('--employer', required=True)
    source_discovery.add_argument('--approve-network', action='store_true')
    source_discovery.add_argument('--limit', type=int, default=25)
    source_discovery.add_argument('--query')
    source_discovery.add_argument('--job-id')
    priority = commands.add_parser("prioritize")
    priority.add_argument("--assumptions")
    learning_cmd = commands.add_parser("learning")
    learning_cmd.add_argument('learning_action', nargs='?', choices=('build','gaps','preferences','discover','progress','propose-update','reassess','status'), default='build')
    learning_cmd.add_argument("--catalog")
    learning_cmd.add_argument('--input')
    learning_cmd.add_argument('--source', action='append', default=[])
    learning_cmd.add_argument('--query')
    learning_cmd.add_argument('--approve-network', action='store_true')
    learning_cmd.add_argument('--limit', type=int, default=3)
    reset = workspace_sub.add_parser("reset-generated")
    reset.add_argument("--confirm-workspace-id", required=True)
    archive = workspace_sub.add_parser("delete")
    archive.add_argument("--archive-destination", required=True)
    archive.add_argument("--confirm-workspace-id", required=True)
    archive.add_argument("--confirm-phrase", required=True)
    return root


def run(args: argparse.Namespace) -> tuple[Any, ExitCode]:
    target = _workspace(args)
    timestamp = args.timestamp
    from careeros import experience
    if args.command == 'workflow' and args.workflow_command in {'jobs','roles','opportunities','prepare','plan','strategy','directions'}:
        from careeros import journey
        if args.workflow_command=='jobs':return journey.find_jobs(target,read_json(Path(args.request)),approved=args.approve_network,timestamp=timestamp),ExitCode.OK
        if args.workflow_command=='strategy':
            from careeros.career_outputs import write_search_strategy
            return write_search_strategy(target,timestamp=timestamp),ExitCode.OK
        if args.workflow_command=='directions':return journey.career_directions(target,args.intent_index,approved=args.approve,actor=args.actor,timestamp=timestamp),ExitCode.OK
        if args.workflow_command=='roles':return journey.suggest_roles(target,timestamp=timestamp),ExitCode.OK
        if args.workflow_command=='opportunities':return journey.overview(target,timestamp=timestamp),ExitCode.OK
        if args.workflow_command=='prepare':return journey.prepare(target,top=args.top,selected_ids=args.opportunity_id,resume_only=args.resume_only,cover_letter_policy=args.cover_letter,timestamp=timestamp),ExitCode.OK
        return journey.plan(target,args.opportunity_id,catalog=Path(args.catalog) if args.catalog else None,timestamp=timestamp),ExitCode.OK
    if args.command == 'discover-source':
        from careeros.discovery_sources import fetch_greenhouse, fetch_greenhouse_job
        from careeros.core.io import atomic_write_json
        roots = experience.context(target)
        result = fetch_greenhouse_job(board=args.greenhouse_board,job_id=args.job_id,employer=args.employer,approved=args.approve_network,timestamp=timestamp) if args.job_id else fetch_greenhouse(board=args.greenhouse_board, employer=args.employer, approved=args.approve_network, limit=args.limit, query=args.query, timestamp=timestamp)
        path = roots.assert_write_allowed(roots.state_root / 'discovery/provider-proposal.json', 'state')
        atomic_write_json(path, result)
        return {'status':'REQUIREMENT_REVIEW_REQUIRED','proposal':str(path),'selected_posts':result['selected_posts'],'network_requests':result['network_requests'],'external_writes':0}, ExitCode.OK
    if args.command == "prioritize":
        return experience.prioritize(target, read_json(Path(args.assumptions)) if args.assumptions else None), ExitCode.OK
    if args.command == "discover":
        return experience.discovery(target, Path(args.catalog), limit=args.limit, timestamp=timestamp), ExitCode.OK
    if args.command == "interview":
        return experience.interview(target, args.opportunity_id, stage=args.stage, timestamp=timestamp), ExitCode.OK
    if args.command == "report":
        return experience.analytics(target, window_start=args.window_start, window_end=args.window_end, timestamp=timestamp), ExitCode.OK
    if args.command == "learning":
        from careeros import learning_workflow
        if args.learning_action == 'preferences':
            return learning_workflow.preferences(target, read_json(Path(args.input)) if args.input else None), ExitCode.OK
        if args.learning_action == 'gaps':
            return learning_workflow.analyze_gaps(target, timestamp=timestamp), ExitCode.OK
        if args.learning_action == 'status':
            return learning_workflow.status(target), ExitCode.OK
        if args.learning_action == 'discover':
            from careeros.learning_sources import discover
            if not args.source or not args.query:raise ValueError('learning discover requires --source and --query')
            return discover(target,sources=args.source,query=args.query,approved=args.approve_network,limit=args.limit,timestamp=timestamp), ExitCode.OK
        if args.learning_action == 'reassess':
            return learning_workflow.reassess(target,timestamp=timestamp), ExitCode.OK
        if args.learning_action in {'progress','propose-update'}:
            if not args.input:raise ValueError('This learning action requires --input')
            function = learning_workflow.record_progress if args.learning_action == 'progress' else learning_workflow.propose_profile_update
            return function(target, read_json(Path(args.input)), timestamp=timestamp), ExitCode.OK
        if not args.catalog:raise ValueError('learning build requires --catalog')
        return experience.learning(target, Path(args.catalog), timestamp=timestamp), ExitCode.OK
    if args.command == "resume" and args.resume_command == "export-docx":
        return experience.export_resume(target, args.build_id), ExitCode.OK
    if args.command == "resume" and args.resume_command == "geometry":
        roots = experience.context(target)
        from careeros.document_quality import inspect_pdf, compare_geometry
        build = next((p for p in (roots.state_root / 'resume-builds').glob('*/build.json') if read_json(p).get('build_id') == args.build_id), None)
        if not build:
            raise ValueError('Unknown resume build')
        artifact = read_json(build.parent / 'artifact.json')
        pdf_path = (roots.output_root / artifact['path']).resolve()
        if not pdf_path.is_relative_to(roots.output_root.resolve()):
            raise PermissionError('Artifact path is outside output root')
        actual = inspect_pdf(pdf_path)
        result = compare_geometry(actual, read_json(Path(args.golden))) if args.golden else actual
        return result, ExitCode.OK if result['status'] == 'PASS' else ExitCode.VALIDATION_FAILURE
    if args.command == "workspace" and args.workspace_command == "dashboard":
        return experience.dashboard(target), ExitCode.OK
    if args.command == "workspace" and args.workspace_command == "queue-audit":
        result = experience.queue_audit(target)
        return result, ExitCode.OK if result['status'] == 'PASS' else ExitCode.VALIDATION_FAILURE
    if args.command == "application" and args.application_command != "prepare":
        if args.application_command == 'answer-bank':
            from careeros.application_answers import save_bank,load_bank
            return (save_bank(target,read_json(Path(args.input)),approved=args.approve,actor=args.actor,timestamp=timestamp) if args.input else load_bank(experience.context(target))),ExitCode.OK
        if args.application_command == "list":
            return {"applications": experience.records(experience.context(target).state_root / 'applications')}, ExitCode.OK
        if args.application_command == "record":
            return experience.record_event(target, args.application_id, read_json(Path(args.input)), timestamp=timestamp), ExitCode.OK
        if args.application_command == "follow-up":
            return experience.follow_up(target, args.application_id, due_at=args.due_at, channel=args.channel), ExitCode.OK
        return experience.cover_letter(target, args.opportunity_id, args.build_id), ExitCode.OK
    if args.command == "version":
        return version_report(), ExitCode.OK
    if args.command == "init":
        return workspace_api.init_workspace(target, fixture_mode=args.fixture_mode, workspace_id=args.workspace_id, timestamp=timestamp), ExitCode.OK
    if args.command == "doctor":
        result = workspace_api.doctor(target)
        mapping = {
            "READY": ExitCode.OK, "READY_WITH_OPTIONAL_LIMITATIONS": ExitCode.OK,
            "CONFIG_INVALID": ExitCode.CONFIG_INVALID, "DEPENDENCY_MISSING": ExitCode.DEPENDENCY_MISSING,
            "DEPENDENCY_INCOMPATIBLE": ExitCode.DEPENDENCY_INCOMPATIBLE, "PATH_INVALID": ExitCode.PATH_INVALID,
            "PERMISSION_FAILURE": ExitCode.PERMISSION_FAILURE, "MIGRATION_REQUIRED": ExitCode.MIGRATION_REQUIRED,
            "PRIVACY_BOUNDARY_FAILURE": ExitCode.PRIVACY_BOUNDARY_FAILURE,
            "UNSUPPORTED_WORKSPACE": ExitCode.WORKSPACE_FORMAT_UNSUPPORTED,
            "FUTURE_WORKSPACE": ExitCode.WORKSPACE_FORMAT_UNSUPPORTED,
            "WORKSPACE_CORRUPT": ExitCode.WORKSPACE_CORRUPT,
        }
        return result, mapping.get(result["outcome"], ExitCode.VALIDATION_FAILURE)
    if args.command == "onboarding":
        if args.onboarding_command == "start":
            return onboarding.start(target, timestamp=timestamp), ExitCode.OK
        if args.onboarding_command == "ingest":
            result = onboarding.ingest(target, Path(args.input), timestamp=timestamp)
            code = ExitCode.CLARIFICATION_REQUIRED if result["state"] == "NEEDS_CLARIFICATION" else ExitCode.OK
            return result, code
        return onboarding.commit(target, actor=args.actor, timestamp=timestamp), ExitCode.OK
    if args.command == "intake":
        if args.intake_command == "compile":
            decision = None if args.linked_source_decision is None else args.linked_source_decision == "APPROVE"
            return intake.compile_intake(
                target, [Path(path) for path in args.source], mode=args.mode,
                linked_source_decision=decision, timestamp=timestamp,
            ), ExitCode.OK
        if args.intake_command == "complete":
            result = intake.apply_completion(target, Path(args.answers), timestamp=timestamp)
            code = ExitCode.CLARIFICATION_REQUIRED if result["intake"]["exception_questions"] else ExitCode.OK
            return result, code
        return intake.review_preview(target), ExitCode.OK
    if args.command == "workflow":
        if args.workflow_command == "route":
            return workflows.route_high_level(args.intent), ExitCode.OK
        if args.start:
            if not args.source:
                raise ValueError("workflow setup --start requires at least one --source")
            return workflows.setup_start(target, [Path(path) for path in args.source], mode=args.mode,
                                         fixture_mode=args.fixture_mode, timestamp=timestamp), ExitCode.OK
        if args.linked_sources:
            return workflows.setup_enrich(
                target, approved=args.linked_sources == "APPROVE", timestamp=timestamp,
            ), ExitCode.OK
        if args.complete:
            if not args.answers:
                raise ValueError("workflow setup --complete requires --answers")
            result = workflows.setup_complete(target, Path(args.answers), timestamp=timestamp)
            code = ExitCode.CLARIFICATION_REQUIRED if result["state"] in {"EXCEPTION_CLARIFICATION", "CLARIFICATION_REQUIRED"} else ExitCode.OK
            return result, code
        if args.resolve:
            if not args.resolutions:
                raise ValueError("workflow setup --resolve requires --resolutions")
            result = workflows.setup_resolve(target, Path(args.resolutions), timestamp=timestamp)
            code = ExitCode.CLARIFICATION_REQUIRED if result["state"] == "CLARIFICATION_REQUIRED" else ExitCode.OK
            return result, code
        if args.approve:
            if not args.actor:
                raise ValueError("workflow setup --approve requires --actor")
            return workflows.setup_approve(target, actor=args.actor, approved=True, timestamp=timestamp), ExitCode.OK
        return workflows.setup_status(target), ExitCode.OK
    if args.command == "clarification":
        if args.clarification_command == "list":
            return onboarding.list_clarifications(target), ExitCode.OK
        result = onboarding.resolve(target, Path(args.resolutions), timestamp=timestamp)
        return result, ExitCode.OK if result["state"] == "RESOLVED" else ExitCode.CLARIFICATION_REQUIRED
    if args.command == "evidence-expansion":
        if args.evidence_expansion_command == "start":
            result = evidence_expansion.start_workspace_session(
                target, lane_context=args.lane_context, job_context=args.job_context, timestamp=timestamp,
            )
            return result, ExitCode.OK
        if args.evidence_expansion_command == "resolve":
            result = evidence_expansion.resolve_workspace_session(target, Path(args.answers), timestamp=timestamp)
            return result, ExitCode.OK if result["state"] == "REVIEW_READY" else ExitCode.CLARIFICATION_REQUIRED
        if args.evidence_expansion_command == "approve":
            return evidence_expansion.approve_workspace_session(target, actor=args.actor, timestamp=timestamp), ExitCode.OK
        if args.evidence_expansion_command == "promote":
            result = evidence_expansion.promote_workspace_session(target, timestamp=timestamp)
            return result, ExitCode.OK if result["state"] == "REVIEW_READY" else ExitCode.CLARIFICATION_REQUIRED
        roots = load_config(target / "careeros.yaml").roots
        return read_json(roots.state_root / "evidence-expansion/session.json"), ExitCode.OK
    if args.command == "profile":
        value, manifest = profile.build_profile(target, timestamp=timestamp)
        return {"profile": value, "manifest": manifest}, ExitCode.OK
    if args.command == "role-family":
        return profile.build_role_family(target, intent_index=args.intent_index, approve=args.approve, timestamp=timestamp), ExitCode.OK
    if args.command == "lane-base":
        if args.lane_base_command == "build":
            if args.accept and not args.actor:
                raise ValueError("lane-base build --accept requires --actor")
            result = lane_base.build_lane_base(target, accept=args.accept, actor=args.actor, timestamp=timestamp)
            return result, ExitCode.OK if result["validation"]["status"] == "PASS" else ExitCode.VALIDATION_FAILURE
        if args.lane_base_command == "accept":
            return lane_base.accept_lane_base(target, args.lane_base_id, actor=args.actor, timestamp=timestamp), ExitCode.OK
        return lane_base.effective_status(target, args.lane_base_id), ExitCode.OK
    if args.command == "opportunity":
        if args.opportunity_command == "registry":
            roots = load_config(target / "careeros.yaml").roots
            return opportunity_registry.build_persistent_registry(roots.state_root, timestamp=timestamp), ExitCode.OK
        if args.opportunity_command == "reconcile":
            payload = read_json(Path(args.input))
            discovered = payload.get("opportunities") if isinstance(payload, dict) else payload
            if not isinstance(discovered, list):
                raise ValueError("opportunity reconcile input must be an array or contain an opportunities array")
            return opportunity_registry.reconcile_workspace_discovery(target, discovered, timestamp=timestamp), ExitCode.OK
        value, snapshot = opportunity.ingest(target, Path(args.input), timestamp=timestamp)
        return {"opportunity": value, "jd_snapshot": snapshot}, ExitCode.OK
    if args.command == "qualify":
        decision = opportunity.qualify(target, args.opportunity_id, timestamp=timestamp)
        code = ExitCode.QUALIFICATION_BLOCKED if decision["decision"] != "QUALIFIED" else ExitCode.OK
        return decision, code
    if args.command == "resume":
        if args.resume_command == "build":
            build_record, content, artifact = resume.build(target, args.opportunity_id, timestamp=timestamp)
            return {"build": build_record, "content": content, "artifact": artifact}, ExitCode.OK
        result, manifest = resume.validate(target, args.build_id)
        return {"validation": result, "manifest": manifest}, ExitCode.OK if result["status"] == "PASS" else ExitCode.VALIDATION_FAILURE
    if args.command == "application":
        return application.prepare(target, args.opportunity_id, args.build_id, cover_letter_policy=args.cover_letter, timestamp=timestamp), ExitCode.OK
    if args.command == "update":
        if args.update_command == "propose":
            result = updates.propose(target, Path(args.input), timestamp=timestamp)
            code = ExitCode.RECORD_CONFLICT if result["approval_state"] == "NEEDS_CLARIFICATION" else ExitCode.OK
            return result, code
        if args.update_command == "preview":
            return updates.preview(target, args.changeset_id), ExitCode.OK
        if args.update_command == "resolve":
            result = updates.resolve_conflicts(target, args.changeset_id, Path(args.resolutions), timestamp=timestamp)
            code = ExitCode.RECORD_CONFLICT if result["approval_state"] == "NEEDS_CLARIFICATION" else ExitCode.OK
            return result, code
        if args.update_command == "approve":
            return updates.approve(target, args.changeset_id, actor=args.actor, timestamp=timestamp), ExitCode.OK
        return updates.commit(target, args.changeset_id, actor=args.actor, timestamp=timestamp), ExitCode.OK
    if args.command == "history":
        return updates.history(target, args.record_id), ExitCode.OK
    if args.command == "export":
        return portability.export_workspace(target, Path(args.output), timestamp=timestamp), ExitCode.OK
    if args.command == "migrate":
        if args.apply:
            return migrations.apply_migrations(target, timestamp=timestamp), ExitCode.OK
        plan = migrations.migration_plan(target)
        return plan, ExitCode.MIGRATION_REQUIRED if plan["migrations"] else ExitCode.OK
    if args.command == "schemas":
        registry = SchemaRegistry(workspace_api.schema_dir())
        if args.schemas_command == "list":
            return {"schema": "careeros.schema-registry-result.v1", "entries": registry.list_entries()}, ExitCode.OK
        return registry.validate_path(Path(args.path).resolve()), ExitCode.OK
    if args.command == "workspace":
        if args.workspace_command == "reset-generated":
            return portability.reset_generated(target, confirm_workspace_id=args.confirm_workspace_id, timestamp=timestamp), ExitCode.OK
        if args.workspace_command == "delete":
            return portability.archive_workspace(target, Path(args.archive_destination), confirm_workspace_id=args.confirm_workspace_id,
                                                 confirm_phrase=args.confirm_phrase, timestamp=timestamp), ExitCode.OK
        result = workspace_api.verify_workspace(target)
        return result, ExitCode.OK if result["status"] == "VALID" else ExitCode.WORKSPACE_CORRUPT
    return workspace_api.status(target), ExitCode.OK


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result, code = run(args)
        if args.command in {"doctor", "version"} and not args.json:
            _emit_human(result)
        else:
            _emit(result)
        return int(code)
    except CareerOSError as exc:
        _emit({"error": exc.to_dict()})
        return int(ERROR_EXIT_CODES.get(exc.code, ExitCode.VALIDATION_FAILURE))
    except FileExistsError as exc:
        _emit({"error": "UNSAFE_OVERWRITE", "message": str(exc)})
        return int(ExitCode.UNSAFE_OVERWRITE)
    except PermissionError as exc:
        _emit({"error": "HUMAN_OR_POLICY_GATE", "message": str(exc)})
        return int(ExitCode.QUALIFICATION_BLOCKED)
    except Exception as exc:
        _emit({"error": exc.__class__.__name__, "message": str(exc)})
        return int(ExitCode.VALIDATION_FAILURE)


if __name__ == "__main__":
    sys.exit(main())
