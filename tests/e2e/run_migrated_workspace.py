"""Prove Workspace Format 1.0 -> 1.1 migration and continued resume work."""

from __future__ import annotations

import argparse
from pathlib import Path

from careeros import application, migrations, onboarding, opportunity, profile, resume, workspace
from careeros.core.io import atomic_write_json, read_json, sha256_file

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/synthetic/early-career"
LEGACY = ROOT / "tests/fixtures/workspace-v1.0/workspace-manifest.json"
TIMESTAMP = "2026-10-02T12:00:00Z"


def run(target: Path) -> dict:
    target = target.resolve()
    workspace.init_workspace(target, fixture_mode=True, workspace_id="workspace-migrated-e2e", timestamp=TIMESTAMP)
    legacy = read_json(LEGACY)
    legacy["workspace_id"] = "workspace-migrated-e2e"
    atomic_write_json(target / "workspace-manifest.json", legacy)
    before = sha256_file(target / "workspace-manifest.json")
    diagnosis_before = workspace.doctor(target)
    plan = migrations.migration_plan(target)
    after_plan = sha256_file(target / "workspace-manifest.json")
    result = migrations.apply_migrations(target, timestamp=TIMESTAMP)
    diagnosis_after = workspace.doctor(target)

    onboarding.start(target, timestamp=TIMESTAMP)
    proposed = onboarding.ingest(target, FIXTURE / "onboarding/input.json", timestamp=TIMESTAMP)
    if proposed["state"] == "NEEDS_CLARIFICATION":
        onboarding.resolve(target, FIXTURE / "onboarding/resolutions.json", timestamp=TIMESTAMP)
    onboarding.commit(target, actor="fixture-human", timestamp=TIMESTAMP)
    _, profile_manifest = profile.build_profile(target, timestamp=TIMESTAMP)
    profile.build_role_family(target, approve=True, timestamp=TIMESTAMP)
    item, _ = opportunity.ingest(target, FIXTURE / "opportunity/strong.json", timestamp=TIMESTAMP)
    decision = opportunity.qualify(target, item["opportunity_id"], timestamp=TIMESTAMP)
    build, _, _ = resume.build(target, item["opportunity_id"], timestamp=TIMESTAMP)
    validation, artifact_manifest = resume.validate(target, build["build_id"])
    packet = application.prepare(target, item["opportunity_id"], build["build_id"], timestamp=TIMESTAMP)
    verified = workspace.verify_workspace(target)
    summary = {
        "schema": "careeros.migrated-workspace-e2e.v1",
        "status": "PASS" if all([
            diagnosis_before["outcome"] == "MIGRATION_REQUIRED", before == after_plan,
            result["status"] == "APPLIED", diagnosis_after["outcome"] == "READY",
            decision["decision"] == "QUALIFIED", validation["status"] == "PASS",
            packet["human_review_state"] == "REVIEW_REQUIRED", verified["status"] == "VALID",
        ]) else "FAIL",
        "doctor_before": diagnosis_before["outcome"], "plan_read_only": before == after_plan,
        "migration": result, "doctor_after": diagnosis_after["outcome"],
        "profile_hash": profile_manifest["profile_hash"], "qualification": decision["decision"],
        "validation": validation["status"], "artifact": artifact_manifest["artifacts"][0],
        "application_state": packet["human_review_state"], "workspace_verify": verified["status"],
    }
    atomic_write_json(target / "migration-e2e-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    result = run(args.target)
    print(result["status"])
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
