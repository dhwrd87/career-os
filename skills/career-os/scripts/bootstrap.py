#!/usr/bin/env python3
"""Workspace-local progressive onboarding helper for the Career OS skill."""

from __future__ import annotations

import argparse
import importlib.resources
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def _questionnaire() -> dict[str, Any]:
    target = importlib.resources.files("careeros.questionnaires").joinpath("onboarding.v1.json")
    return json.loads(target.read_text(encoding="utf-8"))


def _sections() -> list[str]:
    return [item["id"] for item in _questionnaire()["sections"]]


def _required_sections() -> list[str]:
    required = {item["section"] for item in _questionnaire()["questions"] if item["required"]}
    return [section for section in _sections() if section in required]


def _require_workspace(workspace: Path) -> Path:
    workspace = workspace.resolve()
    if not (workspace / "workspace-manifest.json").is_file() or not (workspace / "careeros.yaml").is_file():
        raise RuntimeError("Career OS workspace is not initialized")
    return workspace


def _section_root(workspace: Path) -> Path:
    return workspace / "sources" / "guided-onboarding"


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _run(command: str, *args: str) -> dict[str, Any]:
    completed = subprocess.run([*shlex.split(command), *args], capture_output=True, text=True, check=False)
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Career OS command failed") from exc
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    return result


def start(workspace: Path, command: str) -> dict[str, Any]:
    workspace = _require_workspace(workspace)
    session_path = workspace / "state" / "onboarding" / "session.json"
    if session_path.is_file():
        session = json.loads(session_path.read_text(encoding="utf-8"))
    else:
        session = _run(command, "--workspace", str(workspace), "onboarding", "start")
    return {"schema": "careeros.guided-bootstrap.v1", "state": session["state"], "progress": progress(workspace)}


def questions(section: str) -> dict[str, Any]:
    if section not in _sections():
        raise ValueError(f"unknown onboarding section: {section}")
    items = [item for item in _questionnaire()["questions"] if item["section"] == section]
    prompts={
        'privacy.consent':'May Career OS use the information you provide to build your private career workspace?',
        'identity.public_name':'What name would you like employers to see?',
        'identity.contact':'Which contact details and location would you like to use? Which should stay private?',
        'employment.records':'Tell me about your jobs: employer, actual title, dates, responsibilities and useful examples.',
        'education.records':'What education have you completed or started? Include the school, course and dates you know.',
        'credentials.records':'Which certificates or licenses have you earned? Who issued them, and are any still in progress or expired?',
        'skills.records':'Which skills and tools have you used, and where did you use them?',
        'projects.records':'Tell me about a project or volunteer role. What did you personally do, and what was the result?',
        'evidence.records':'Which examples best show what you can do? Include work samples or results you can support.',
        'preferences.record':'What matters for your next job: location, working arrangement, pay, hours, travel or other limits?',
        'target_roles.intents':'What kinds of jobs interest you now? Is there a longer-term role you would like to work toward?',
        'review.confirm':'Are these details accurate, and do you approve saving them to your career profile?',
    }
    items=[{**item,'prompt':prompts[item['question_id']]} for item in items]

    return {"schema": "careeros.guided-bootstrap-questions.v1", "section": section, "questions": items}


def save_section(workspace: Path, section: str, input_path: Path) -> dict[str, Any]:
    workspace = _require_workspace(workspace)
    if section not in _sections():
        raise ValueError(f"unknown onboarding section: {section}")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("section input must be a JSON object")
    target = _section_root(workspace) / f"{section}.json"
    _atomic_json(target, payload)
    result = progress(workspace)
    result["saved_section"] = section
    return result


def progress(workspace: Path) -> dict[str, Any]:
    workspace = _require_workspace(workspace)
    root = _section_root(workspace)
    ordered = _sections()
    completed = [section for section in ordered if (root / f"{section}.json").is_file()]
    missing = [section for section in ordered if section not in completed]
    missing_required = [section for section in _required_sections() if section not in completed]
    return {
        "schema": "careeros.guided-bootstrap-progress.v1",
        "state": "REVIEW_READY" if not missing_required else "IN_PROGRESS",
        "completed_sections": completed,
        "missing_sections": missing,
        "missing_required_sections": missing_required,
        "next_section": missing_required[0] if missing_required else (missing[0] if missing else None),
    }


def assemble(workspace: Path, output: Path) -> dict[str, Any]:
    workspace = _require_workspace(workspace)
    state = progress(workspace)
    if state["missing_required_sections"]:
        raise RuntimeError(f"required onboarding sections are incomplete: {state['missing_required_sections']}")
    combined: dict[str, Any] = {"schema": "careeros.onboarding-input.v1"}
    for section in _sections():
        path = _section_root(workspace) / f"{section}.json"
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key, value in payload.items():
            if key in combined and combined[key] != value:
                if key == "source_documents" and isinstance(combined[key], list) and isinstance(value, list):
                    combined[key] = [*combined[key], *value]
                    continue
                raise RuntimeError(f"conflicting onboarding field across sections: {key}")
            combined[key] = value
    if combined.get("privacy_consent") is not True or combined.get("review_confirmed") is not True:
        raise RuntimeError("privacy consent and final review confirmation are required before proposal ingestion")
    output = output.resolve()
    try:
        output.relative_to((workspace / "sources").resolve())
    except ValueError as exc:
        raise RuntimeError("assembled onboarding input must remain inside workspace sources") from exc
    _atomic_json(output, combined)
    return {
        "schema": "careeros.guided-bootstrap-assembly.v1",
        "state": "READY_FOR_PROPOSAL_INGEST",
        "output": str(output),
        "sections": state["completed_sections"],
        "canonical_mutation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--careeros-command", default="careeros")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("start")
    commands.add_parser("progress")
    question_cmd = commands.add_parser("questions")
    question_cmd.add_argument("--section", required=True)
    save_cmd = commands.add_parser("save-section")
    save_cmd.add_argument("--section", required=True)
    save_cmd.add_argument("--input", required=True, type=Path)
    assemble_cmd = commands.add_parser("assemble")
    assemble_cmd.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "start":
        result = start(args.workspace, args.careeros_command)
    elif args.command == "progress":
        result = progress(args.workspace)
    elif args.command == "questions":
        result = questions(args.section)
    elif args.command == "save-section":
        result = save_section(args.workspace, args.section, args.input)
    else:
        result = assemble(args.workspace, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
