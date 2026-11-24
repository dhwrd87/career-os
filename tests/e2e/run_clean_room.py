"""Run all synthetic vertical slices into a caller-owned clean-room root."""

from __future__ import annotations

import argparse
from pathlib import Path

from careeros import application, onboarding, opportunity, profile, resume, workspace
from careeros.core.io import atomic_write_json, read_json


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures/synthetic"
FIXTURES = ("early-career", "career-changer", "experienced-multi-role")
TIMESTAMP = "2026-10-02T12:00:00Z"


def run(target_root: Path) -> dict:
    target_root = target_root.resolve()
    if target_root.exists() and any(target_root.iterdir()):
        raise FileExistsError(f"clean-room target must be empty: {target_root}")
    target_root.mkdir(parents=True, exist_ok=True)
    results = []
    for fixture_name in FIXTURES:
        fixture = FIXTURE_ROOT / fixture_name
        expected = read_json(fixture / "expected/expectations.json")
        target = target_root / fixture_name
        workspace.init_workspace(target, fixture_mode=True, workspace_id=f"workspace-{fixture_name}", timestamp=TIMESTAMP)
        diagnosis = workspace.doctor(target)
        if diagnosis["outcome"] != "READY":
            raise RuntimeError(diagnosis)
        onboarding.start(target, timestamp=TIMESTAMP)
        proposed = onboarding.ingest(target, fixture / "onboarding/input.json", timestamp=TIMESTAMP)
        if proposed["state"] == "NEEDS_CLARIFICATION":
            onboarding.resolve(target, fixture / "onboarding/resolutions.json", timestamp=TIMESTAMP)
        onboarding.commit(target, actor="fixture-human", timestamp=TIMESTAMP)
        compiled, profile_manifest = profile.build_profile(target, timestamp=TIMESTAMP)
        role = profile.build_role_family(target, approve=True, timestamp=TIMESTAMP)
        decisions = {}
        for kind in ("strong", "borderline"):
            item, _ = opportunity.ingest(target, fixture / f"opportunity/{kind}.json", timestamp=TIMESTAMP)
            decisions[kind] = opportunity.qualify(target, item["opportunity_id"], timestamp=TIMESTAMP)
        if decisions["strong"]["decision"] != expected["strong_decision"] or decisions["borderline"]["decision"] != expected["borderline_decision"]:
            raise AssertionError(decisions)
        strong_id = decisions["strong"]["opportunity_id"]
        build_record, content, artifact = resume.build(target, strong_id, timestamp=TIMESTAMP)
        validation, artifact_manifest = resume.validate(target, build_record["build_id"])
        if validation["status"] != "PASS":
            raise AssertionError(validation)
        packet = application.prepare(target, strong_id, build_record["build_id"], timestamp=TIMESTAMP)
        results.append({
            "fixture": fixture_name, "doctor": diagnosis["outcome"], "profile_schema": compiled["schema"],
            "profile_hash": profile_manifest["profile_hash"], "role_family_id": role["role_family_id"],
            "strong_decision": decisions["strong"]["decision"], "borderline_decision": decisions["borderline"]["decision"],
            "build_id": build_record["build_id"], "artifact": artifact_manifest["artifacts"][0],
            "gate_count": len(validation["gates"]), "gates_passed": sum(item["status"] == "PASS" for item in validation["gates"]),
            "render_paths": validation["render_paths"], "application_state": packet["human_review_state"],
            "career_changer_direct_experience_equivalence": any(item.get("experience_equivalence") is True for item in decisions["borderline"]["evidence"]),
        })
    summary = {
        "schema": "careeros.clean-room-e2e.v1", "status": "PASS", "created_at": TIMESTAMP,
        "fixture_bundle_root": "fixtures/synthetic", "private_reference_access": False,
        "external_actions": 0, "fixtures_passed": len(results), "fixtures_total": len(FIXTURES), "results": results,
    }
    atomic_write_json(target_root / "clean-room-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target_root", type=Path)
    args = parser.parse_args()
    result = run(args.target_root)
    print(result["status"], f"{result['fixtures_passed']}/{result['fixtures_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
