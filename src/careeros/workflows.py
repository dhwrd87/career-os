"""High-level package workflows consumed by the thin Career OS skill."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from careeros import onboarding, profile, workspace as workspace_api
from careeros.career_outputs import generate_initial_outputs
from careeros.core.io import atomic_write_json, read_json
from careeros.intake import apply_completion, compile_prepared_intake, prepare_source_stage, review_preview
from careeros.workspace import utc_now


HIGH_LEVEL_WORKFLOWS = (
    "SET_ME_UP", "IMPROVE_MY_CAREER_PROFILE", "FIND_MY_CAREER_PATHS",
    "HELP_ME_GET_A_JOB", "TAILOR_FOR_THIS_JOB", "UPDATE_MY_CAREER", "SHOW_MY_GAPS",
    "BUILD_LANE_BASE", "WHAT_SHOULD_I_LEARN_NEXT", "BUILD_MY_LEARNING_PATH",
    "COMPARE_COURSES", "IMPROVE_MY_SOC_RESUME", "IMPROVE_MY_NOC_RESUME",
    "IMPROVE_MY_VULNERABILITY_RESUME", "WHAT_CERTIFICATIONS_ARE_WORTH_IT",
    "I_FINISHED_THIS_COURSE", "WHAT_PROJECT_SHOULD_I_BUILD", "SHOW_MY_HIGHEST_ROI_GAPS",
)


def setup_start(workspace: Path, source_paths: list[Path], *, mode: str = "FAST",
                fixture_mode: bool = False, timestamp: str | None = None) -> dict[str, Any]:
    workspace = workspace.resolve()
    if not (workspace / "workspace-manifest.json").is_file():
        workspace_api.init_workspace(workspace, fixture_mode=fixture_mode, timestamp=timestamp)
    doctor = workspace_api.doctor(workspace)
    if doctor["outcome"] not in {"READY", "READY_WITH_OPTIONAL_LIMITATIONS"}:
        return {"schema": "careeros.workflow-result.v1", "workflow": "SET_ME_UP", "state": "BLOCKED", "doctor": doctor}
    if not (workspace / "state/onboarding/session.json").is_file():
        onboarding.start(workspace, timestamp=timestamp)
    manifest = prepare_source_stage(workspace, source_paths, mode=mode, timestamp=timestamp)
    if manifest["sources"]:
        status = {
            "schema": "careeros.workflow-result.v1", "workflow": "SET_ME_UP",
            "state": "SOURCE_ENRICHMENT_APPROVAL_REQUIRED", "mode": mode.upper(),
            "doctor": doctor["outcome"],
            "linked_sources": [
                {"source_type": item["source_type"], "source_location": item["source_location"]}
                for item in manifest["sources"]
            ],
            "approval_scope": "One read-only capture of the listed public career sources; proposed records only.",
            "canonical_mutation": False,
        }
        atomic_write_json(workspace / "state/intake/workflow-status.json", status)
        return status
    intake = compile_prepared_intake(workspace, approved_linked_sources=False, timestamp=timestamp)
    status = {
        "schema": "careeros.workflow-result.v1", "workflow": "SET_ME_UP", "state": "AWAITING_COMPLETION",
        "mode": mode.upper(), "doctor": doctor["outcome"], "question_count": intake["question_count"],
        "questions": intake["questions"], "canonical_mutation": False,
    }
    atomic_write_json(workspace / "state/intake/workflow-status.json", status)
    return status


def setup_enrich(
    workspace: Path, *, approved: bool, fetcher: Callable[[str], Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Apply one linked-source decision, then generate the consolidated intake."""
    intake = compile_prepared_intake(
        workspace, approved_linked_sources=approved, fetcher=fetcher, timestamp=timestamp,
    )
    status = {
        "schema": "careeros.workflow-result.v1", "workflow": "SET_ME_UP", "state": "AWAITING_COMPLETION",
        "mode": intake["mode"], "question_count": intake["question_count"],
        "questions": intake["questions"], "linked_source_summary": intake["linked_source_summary"],
        "evidence_expansion_question_count": intake["evidence_expansion_question_count"],
        "canonical_mutation": False,
    }
    atomic_write_json(workspace / "state/intake/workflow-status.json", status)
    return status


def setup_complete(workspace: Path, answers_path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    result = apply_completion(workspace, answers_path, timestamp=timestamp)
    if result["intake"]["exception_questions"]:
        return {
            "schema": "careeros.workflow-result.v1", "workflow": "SET_ME_UP", "state": "EXCEPTION_CLARIFICATION",
            "questions": result["intake"]["exception_questions"], "clarification_round": 1,
            "canonical_mutation": False,
        }
    proposed = onboarding.ingest(workspace, Path(result["output"]), timestamp=timestamp)
    preview = review_preview(workspace)
    preview["proposal_state"] = proposed["state"]
    preview["package_clarification_count"] = sum(1 for item in proposed["records"] if item["proposal_state"] == "NEEDS_CLARIFICATION")
    preview["state"] = "CLARIFICATION_REQUIRED" if proposed["state"] == "NEEDS_CLARIFICATION" else "COMMIT_PREVIEW_READY"
    return preview


def setup_resolve(workspace: Path, resolutions_path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    queue = onboarding.resolve(workspace, resolutions_path, timestamp=timestamp)
    preview = review_preview(workspace)
    preview["state"] = "COMMIT_PREVIEW_READY" if queue["state"] == "RESOLVED" else "CLARIFICATION_REQUIRED"
    preview["package_clarification_count"] = sum(1 for item in queue["items"] if item.get("required_for_commit") and not item.get("resolution"))
    return preview


def setup_approve(workspace: Path, *, actor: str, approved: bool,
                  timestamp: str | None = None) -> dict[str, Any]:
    if approved is not True:
        raise PermissionError("explicit human approval is required for canonical commit")
    event = onboarding.commit(workspace, actor=actor, timestamp=timestamp)
    compiled_profile, build_manifest = profile.build_profile(workspace, timestamp=timestamp)
    role_families = []
    for index, _ in enumerate(compiled_profile.get("preferences", {}).get("target_role_intents", [])):
        role_families.append(profile.build_role_family(workspace, intent_index=index, approve=False, timestamp=timestamp))
    outputs = generate_initial_outputs(workspace, timestamp=timestamp)
    status = {
        "schema": "careeros.workflow-result.v1", "workflow": "SET_ME_UP", "state": "COMPLETE",
        "commit_event": event, "profile_id": compiled_profile["profile_id"],
        "profile_hash": build_manifest["profile_hash"], "role_family_proposals": [item["role_family_id"] for item in role_families],
        "outputs": outputs, "external_actions": 0,
    }
    atomic_write_json(workspace / "state/intake/workflow-status.json", status)
    return status


def setup_status(workspace: Path) -> dict[str, Any]:
    path = workspace / "state/intake/workflow-status.json"
    if path.is_file():
        return read_json(path)
    return {"schema": "careeros.workflow-result.v1", "workflow": "SET_ME_UP", "state": "NOT_STARTED"}


def route_high_level(intent: str) -> dict[str, Any]:
    intent = intent.upper()
    if intent not in HIGH_LEVEL_WORKFLOWS:
        raise ValueError(f"unsupported high-level workflow: {intent}")
    routes = {
        "SET_ME_UP": ["intake compile", "intake complete", "commit preview", "explicit approval", "initial outputs"],
        "IMPROVE_MY_CAREER_PROFILE": ["evidence-expansion", "canonical update"],
        "FIND_MY_CAREER_PATHS": ["career lanes", "role title universe", "candidate preference review"],
        "HELP_ME_GET_A_JOB": ["profile readiness", "job intake", "qualification", "tailoring", "packet"],
        "TAILOR_FOR_THIS_JOB": ["job intelligence", "qualification", "resume build", "validation"],
        "UPDATE_MY_CAREER": ["changeset propose", "impact", "preview", "approval", "transactional commit"],
        "SHOW_MY_GAPS": ["profile readiness", "career gaps", "development priorities"],
        "BUILD_LANE_BASE": ["approved role family", "lane storyline", "lane evidence selection", "PDF", "QA", "human review"],
        "WHAT_SHOULD_I_LEARN_NEXT": ["verified gaps", "gap priority", "current provider discovery", "course evaluation", "smallest evidence-producing step"],
        "BUILD_MY_LEARNING_PATH": ["verified gaps", "learning objectives", "current provider discovery", "minimal path", "evidence creation", "human review"],
        "COMPARE_COURSES": ["current course details", "freshness", "four-value comparison", "redundancy", "ROI", "bounded recommendation"],
        "IMPROVE_MY_SOC_RESUME": ["SOC evidence gaps", "recurring employer needs", "learning path", "evidence plan", "resume impact"],
        "IMPROVE_MY_NOC_RESUME": ["NOC evidence gaps", "recurring employer needs", "learning path", "evidence plan", "resume impact"],
        "IMPROVE_MY_VULNERABILITY_RESUME": ["vulnerability evidence gaps", "recurring employer needs", "learning path", "evidence plan", "resume impact"],
        "WHAT_CERTIFICATIONS_ARE_WORTH_IT": ["market requirement trace", "credential classification", "course versus certification boundary", "ROI", "human review"],
        "I_FINISHED_THIS_COURSE": ["completion evidence", "credential verification", "artifact review", "proposed evidence", "canonical review required"],
        "WHAT_PROJECT_SHOULD_I_BUILD": ["priority gap", "evidence creation potential", "bounded project plan", "verification plan"],
        "SHOW_MY_HIGHEST_ROI_GAPS": ["verified gaps", "recurrence", "qualification impact", "career breadth", "effort", "evidence creation"],
    }
    return {"schema": "careeros.high-level-workflow-route.v1", "intent": intent, "steps": routes[intent], "external_actions": 0}
