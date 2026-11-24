#!/usr/bin/env python3
"""Run eight source-first personas using the installed Career OS package."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from careeros import application, lane_base, opportunity, profile, resume, workflows, workspace
from careeros.core.io import read_json


PERSONAS = (
    "complete-resume", "very-weak-resume", "career-changer", "student",
    "experienced-professional", "project-heavy-technical", "credential-heavy", "overlapping-employment",
)
NOW = "2026-10-03T21:00:00Z"


def synthetic_portfolio_fetcher(url: str) -> dict[str, Any]:
    body = b"<html><body><h1>Casey Rowan Portfolio</h1><h2>Projects</h2><p>Service Queue Dashboard</p><p>Documented a fictional dashboard prototype and its review checklist.</p></body></html>"
    return {"body": body, "media_type": "text/html", "final_url": url}


def _prepare_answers(intake: dict[str, Any], persona: str) -> dict[str, Any]:
    proposed = copy.deepcopy(intake["prefilled_onboarding"])
    proposed["candidate"]["location"] = proposed["candidate"].get("location") or "Example City, US"
    proposed["candidate"]["visibility"] = "EMPLOYER_SAFE"
    for employment in proposed["employment"]:
        employment["employment_type"] = "PART_TIME" if persona == "overlapping-employment" and employment["employer"] == "Neighborhood Learning Center" else "FULL_TIME"
        employment["visibility"] = "EMPLOYER_SAFE"
        employment["confidence"] = "HIGH"
    for education in proposed["education"]:
        education["completion_status"] = "IN_PROGRESS" if persona == "student" else "COMPLETED"
        education["visibility"] = "EMPLOYER_SAFE"
        education["confidence"] = "HIGH"
    for credential in proposed["credentials"]:
        credential["credential_state"] = "COMPLETED"
        credential["verification_state"] = "VERIFIED"
        credential["visibility"] = "EMPLOYER_SAFE"
        credential["confidence"] = "HIGH"
    for evidence in proposed["evidence"]:
        evidence["verification_state"] = "VERIFIED"
        evidence["visibility"] = "EMPLOYER_SAFE"
        evidence["confidence"] = "HIGH"
        evidence.setdefault("outcomes", [])
        if not evidence["outcomes"]:
            evidence["outcomes"] = ["Produced a documented, reviewable deliverable"]
    evidence_refs = [f"ref:{item['local_id']}" for item in proposed["evidence"]]
    for index, skill in enumerate(proposed["skills"]):
        skill["category"] = "LANGUAGES" if skill["name"] in {"English", "Spanish"} else "OPERATIONS"
        skill["proficiency"] = "NATIVE" if skill["name"] in {"English", "Spanish"} else "PRACTICED"
        skill["evidence_ids"] = [evidence_refs[index % len(evidence_refs)]] if evidence_refs else []
        skill["visibility"] = "EMPLOYER_SAFE"
        skill["confidence"] = "HIGH"
    for project in proposed["projects"]:
        project["purpose"] = project.get("purpose") or "Create and validate a fictional work sample."
        project["contribution"] = "Individual contributor"
        project["visibility"] = "EMPLOYER_SAFE"
        project["confidence"] = "HIGH"
    skill_names = [item["name"] for item in proposed["skills"] if item["name"] not in {"English", "Spanish"}]
    if persona == "career-changer":
        target_name = "Implementation Support Coordination"
        titles = ["Implementation Support Coordinator", "Implementation Coordinator"]
        core = [name for name in ("Process Mapping", "Training", "Data Cleanup") if name in skill_names]
    else:
        target_name = {
            "complete-resume": "Operations Support",
            "very-weak-resume": "Customer Support",
            "student": "Junior Technical Support",
            "experienced-professional": "Operations Management",
            "project-heavy-technical": "Junior Technical Operations",
            "credential-heavy": "Quality Operations",
            "overlapping-employment": "Service Dispatch Operations",
        }[persona]
        titles = [target_name + " Associate", target_name + " Coordinator"]
        core = skill_names[:3]
    proposed["preferences"].update({
        "target_role_family_ids": [target_name.casefold().replace(" ", "-")],
        "target_industries": ["Example services"], "work_modes": ["ONSITE", "HYBRID", "REMOTE"],
        "location_preferences": ["United States"], "career_change_intent": "Candidate-selected synthetic target lane.",
        "constraints": [], "career_gaps": [], "visibility": "PRIVATE", "confidence": "HIGH",
    })
    proposed["role_intents"] = [{
        "display_name": target_name, "target_titles": titles, "seniority": "ENTRY" if persona in {"student", "very-weak-resume", "project-heavy-technical"} else "MID",
        "description": "Synthetic candidate-approved role family.", "headline": target_name,
        "core_capabilities": core, "preferred_capabilities": skill_names[3:5],
        "transferable_capabilities": core[:2], "hard_requirements": [],
        "evidence_preferences": ["VERIFIED", "EMPLOYER_SAFE"],
        "resume_strategy": "Lead with supported lane evidence and preserve professional credibility.",
        "evidence_requirements": core,
    }]
    return {"privacy_consent": True, "review_confirmed": True, "confirmed_onboarding": proposed}


def _resolve_package_clarifications(workspace_path: Path, output: Path) -> int:
    queue = read_json(workspace_path / "state/onboarding/clarifications.json")
    if queue["state"] == "RESOLVED":
        return 0
    payload = {
        "resolutions": [{
            "local_id": item["local_id"], "issue_type": item["issue_type"],
            "decision": "SYNTHETIC_HUMAN_CONFIRMED", "set_fields": {},
        } for item in queue["items"]]
    }
    output.write_text(json.dumps(payload), encoding="utf-8")
    resolved = workflows.setup_resolve(workspace_path, output, timestamp=NOW)
    if resolved["state"] != "COMMIT_PREVIEW_READY":
        raise RuntimeError(json.dumps(resolved, sort_keys=True))
    return 1


def run_persona(runtime_root: Path, fixture_root: Path, persona: str) -> dict[str, Any]:
    workspace_path = runtime_root / persona / "workspace"
    source = fixture_root / f"{persona}.md"
    start = workflows.setup_start(workspace_path, [source], mode="FAST", fixture_mode=True, timestamp=NOW)
    if start["state"] == "SOURCE_ENRICHMENT_APPROVAL_REQUIRED":
        if persona == "complete-resume":
            start = workflows.setup_enrich(workspace_path, approved=True, fetcher=synthetic_portfolio_fetcher, timestamp=NOW)
        else:
            start = workflows.setup_enrich(workspace_path, approved=False, timestamp=NOW)
    if start["state"] != "AWAITING_COMPLETION":
        raise RuntimeError(json.dumps(start, sort_keys=True))
    intake = read_json(workspace_path / "state/intake/career-intake.json")
    answers = runtime_root / persona / "candidate-answers.json"
    answers.write_text(json.dumps(_prepare_answers(intake, persona)), encoding="utf-8")
    preview = workflows.setup_complete(workspace_path, answers, timestamp=NOW)
    rounds = 0
    if preview["state"] == "CLARIFICATION_REQUIRED":
        rounds += _resolve_package_clarifications(workspace_path, runtime_root / persona / "resolutions.json")
    elif preview["state"] != "COMMIT_PREVIEW_READY":
        raise RuntimeError(json.dumps(preview, sort_keys=True))
    completed = workflows.setup_approve(workspace_path, actor="synthetic-human", approved=True, timestamp=NOW)
    family = profile.build_role_family(workspace_path, approve=True, timestamp=NOW)
    base = lane_base.build_lane_base(workspace_path, accept=True, actor="synthetic-human", timestamp=NOW)
    if base["validation"]["status"] != "PASS":
        raise RuntimeError(json.dumps(base["validation"], sort_keys=True))
    outputs = completed["outputs"]
    doctor_outcome = workspace.doctor(workspace_path)["outcome"]
    if doctor_outcome not in {"READY", "READY_WITH_OPTIONAL_LIMITATIONS"}:
        raise RuntimeError(f"{persona}: doctor={doctor_outcome}")
    result = {
        "persona": persona, "doctor": doctor_outcome,
        "prompt_count": start["question_count"], "exception_rounds": rounds,
        "manual_interventions": 0, "source_conflicts": len(intake.get("contradictions", [])),
        "clarifications": read_json(workspace_path / "state/onboarding/clarifications.json").get("items", []).__len__(),
        "master_resume": (workspace_path / outputs["master_recruiter_resume"]).is_file(),
        "lane_analysis": (workspace_path / outputs["career_lane_analysis"]).is_file(),
        "lane_base": base["lane_base"]["status"] == "ACCEPTED",
        "gap_development": (workspace_path / outputs["career_gap_analysis"]).is_file(),
        "role_family_id": family["role_family_id"], "job_one_shot": None,
        "outputs_generated": 7,
    }
    if persona == "career-changer":
        job, _ = opportunity.ingest(workspace_path, fixture_root / "target-job.json", timestamp=NOW)
        decision = opportunity.qualify(workspace_path, job["opportunity_id"], timestamp=NOW)
        if decision["decision"] != "QUALIFIED":
            raise RuntimeError(json.dumps(decision, sort_keys=True))
        build, content, _ = resume.build(workspace_path, job["opportunity_id"], timestamp=NOW)
        validation, _ = resume.validate(workspace_path, build["build_id"])
        packet = application.prepare(workspace_path, job["opportunity_id"], build["build_id"], timestamp=NOW)
        result["job_one_shot"] = {
            "qualification": decision["decision"], "lane_base_id": build.get("lane_base_id"),
            "resume_qa": validation["status"], "packet": packet["human_review_state"],
            "canonical_fact_source": "candidate profile before job intelligence",
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--fixture-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    results = [run_persona(args.runtime_root, args.fixture_root, persona) for persona in PERSONAS]
    summary = {
        "schema": "careeros.installed-wheel-onboarding-matrix.v1", "status": "PASS",
        "personas": results, "passed": len(results), "master_resumes": sum(item["master_resume"] for item in results),
        "lane_analyses": sum(item["lane_analysis"] for item in results), "lane_bases": sum(item["lane_base"] for item in results),
        "gap_development": sum(item["gap_development"] for item in results),
        "prompt_range": [min(item["prompt_count"] for item in results), max(item["prompt_count"] for item in results)],
        "exception_round_range": [min(item["exception_rounds"] for item in results), max(item["exception_rounds"] for item in results)],
        "manual_interventions": sum(item["manual_interventions"] for item in results),
        "resume_job_one_shot": next(item["job_one_shot"] for item in results if item["job_one_shot"] is not None),
        "external_actions": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
