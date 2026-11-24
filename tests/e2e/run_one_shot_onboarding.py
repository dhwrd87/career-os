#!/usr/bin/env python3
"""Clean-installed source-first onboarding harness using synthetic data only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from careeros import workflows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--confirmed-onboarding", required=True, type=Path)
    args = parser.parse_args()
    start = workflows.setup_start(args.workspace, [args.source], mode="FAST", fixture_mode=True, timestamp="2026-10-03T16:00:00Z")
    if start["state"] == "SOURCE_ENRICHMENT_APPROVAL_REQUIRED":
        start = workflows.setup_enrich(args.workspace, approved=False, timestamp="2026-10-03T16:00:30Z")
    raw = json.loads(args.confirmed_onboarding.read_text(encoding="utf-8"))
    answer_path = args.workspace.parent / "candidate-answers.json"
    answer_path.write_text(json.dumps({
        "privacy_consent": True,
        "review_confirmed": True,
        "confirmed_onboarding": {key: raw[key] for key in (
            "candidate", "employment", "education", "credentials", "skills",
            "evidence", "projects", "preferences", "role_intents",
        )},
    }), encoding="utf-8")
    preview = workflows.setup_complete(args.workspace, answer_path, timestamp="2026-10-03T16:01:00Z")
    if preview["state"] != "COMMIT_PREVIEW_READY":
        raise RuntimeError(json.dumps(preview, sort_keys=True))
    completed = workflows.setup_approve(args.workspace, actor="synthetic-human", approved=True, timestamp="2026-10-03T16:02:00Z")
    outputs = completed["outputs"]
    required = (
        "career_profile", "profile_readiness", "master_recruiter_resume",
        "career_lane_analysis", "role_title_universe", "career_gap_analysis", "development_priorities",
    )
    if not all((args.workspace / outputs[key]).exists() for key in required):
        raise RuntimeError("one or more immediate onboarding outputs are missing")
    print(json.dumps({
        "schema": "careeros.clean-room-one-shot-result.v1",
        "status": "PASS", "package_state": completed["state"],
        "prompt_count": start["question_count"], "clarification_rounds": 0,
        "manual_json_edits": 0, "manual_cli_steps": 0, "operator_interventions": 0,
        "outputs": outputs, "external_actions": completed["external_actions"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
