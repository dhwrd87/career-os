"""Explicit, backup-first workspace migrations."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from careeros.core.errors import MigrationFailedError, WorkspaceFormatUnsupportedError
from careeros.core.io import atomic_write_json, read_json, sha256_file, sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.versions import (
    ACTIVE_POLICY_VERSIONS,
    CONFIG_SCHEMA_VERSION,
    PACKAGE_VERSION,
    SCHEMA_BUNDLE_VERSION,
    WORKSPACE_FORMAT_VERSION,
)
from careeros.workspace import MANIFEST_SCHEMA_ID, compatibility, refresh_manifest_integrity, schema_dir, utc_now

MIGRATION_ID = "workspace-1.0.0-to-1.1.0"


def migration_plan(workspace: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest_path = workspace / "workspace-manifest.json"
    if not manifest_path.is_file():
        raise WorkspaceFormatUnsupportedError("workspace manifest is missing")
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        raise WorkspaceFormatUnsupportedError("workspace manifest is unreadable", cause=exc) from exc
    version = str(manifest.get("workspace_format_version", ""))
    state = compatibility(version)
    blockers: list[str] = []
    migrations: list[dict[str, Any]] = []
    if state == "MIGRATION_REQUIRED" and version == "1.0.0":
        partial_keys = {"schema_version", "created_by_package_version", "integrity", "migration_history"}
        if partial_keys.intersection(manifest):
            blockers.append("manifest mixes Workspace Format 1.0.0 with 1.1.0 fields")
        migrations.append({
            "migration_id": MIGRATION_ID,
            "from_version": "1.0.0", "to_version": WORKSPACE_FORMAT_VERSION,
            "affected_files": ["workspace-manifest.json"], "backup_required": True,
            "description": "Formalize manifest authorities, component versions, integrity metadata, and migration history.",
        })
    elif state in {"FUTURE", "UNSUPPORTED", "CORRUPT"}:
        blockers.append(f"workspace format state is {state}")
    return {
        "schema": "careeros.migration-plan.v1", "mode": "READ_ONLY", "workspace_format_version": version,
        "target_workspace_format_version": WORKSPACE_FORMAT_VERSION, "state": state,
        "migrations": migrations, "affected_files": sorted({p for m in migrations for p in m["affected_files"]}),
        "backup_required": bool(migrations), "blockers": blockers,
        "source_manifest_sha256": sha256_file(manifest_path),
    }


def _migrate_manifest(manifest: dict[str, Any], config_path: Path, *, timestamp: str, backup_path: str,
                      before_sha256: str) -> dict[str, Any]:
    migrated = {
        "schema": "careeros.workspace-manifest.v1", "schema_version": "1.0.0",
        "workspace_id": manifest["workspace_id"], "workspace_format_version": WORKSPACE_FORMAT_VERSION,
        "created_at": manifest["created_at"],
        "created_by_package_version": manifest.get("package_version", "0.2.0.dev0"),
        "last_migrated_at": timestamp, "last_migrated_by_package_version": PACKAGE_VERSION,
        "config_schema_version": CONFIG_SCHEMA_VERSION, "schema_bundle_version": SCHEMA_BUNDLE_VERSION,
        "active_policy_versions": dict(ACTIVE_POLICY_VERSIONS),
        "compiler_version_at_last_build": None, "renderer_version_at_last_build": None,
        "migration_history": [], "fixture_mode": bool(manifest.get("fixture_mode", False)),
        "external_adapters_enabled": False,
        "canonical_head": {"revision": 0, "canonical_sha256": sha256_value({}),
                           "last_event_id": None, "updated_at": None},
    }
    provisional = dict(migrated)
    provisional["migration_history"] = [{
        "migration_id": MIGRATION_ID, "from_version": "1.0.0", "to_version": WORKSPACE_FORMAT_VERSION,
        "applied_at": timestamp, "applied_by_package_version": PACKAGE_VERSION,
        "before_sha256": before_sha256, "after_sha256": "0" * 64,
        "affected_files": ["workspace-manifest.json"], "backup_path": backup_path, "status": "APPLIED",
    }]
    # The event hash covers the migrated semantic payload before its own after-hash is filled.
    after_sha256 = sha256_value(provisional)
    provisional["migration_history"][0]["after_sha256"] = after_sha256
    return refresh_manifest_integrity(provisional, config_path, timestamp=timestamp)


def apply_migrations(workspace: Path, *, timestamp: str | None = None,
                     fail_after_write_for_test: bool = False) -> dict[str, Any]:
    workspace = workspace.resolve()
    plan = migration_plan(workspace)
    if plan["blockers"]:
        raise MigrationFailedError("migration is blocked", context={"blockers": plan["blockers"]})
    if not plan["migrations"]:
        return {"schema": "careeros.migration-result.v1", "status": "NO_CHANGES", "plan": plan}
    applied_at = utc_now(timestamp)
    manifest_path = workspace / "workspace-manifest.json"
    config_path = workspace / "careeros.yaml"
    if not config_path.is_file():
        raise MigrationFailedError("configuration is missing; migration cannot derive integrity metadata")
    backup_relative = f".careeros-backups/{MIGRATION_ID}/{applied_at.replace(':', '').replace('-', '')}"
    backup_dir = workspace / backup_relative
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_manifest = backup_dir / "workspace-manifest.json"
    shutil.copy2(manifest_path, backup_manifest)
    before_sha256 = sha256_file(manifest_path)
    atomic_write_json(backup_dir / "backup-manifest.json", {
        "schema": "careeros.migration-backup.v1", "migration_id": MIGRATION_ID,
        "created_at": applied_at, "files": [{"path": "workspace-manifest.json", "sha256": before_sha256}],
    })
    original = read_json(manifest_path)
    try:
        migrated = _migrate_manifest(original, config_path, timestamp=applied_at,
                                     backup_path=backup_relative, before_sha256=before_sha256)
        SchemaRegistry(schema_dir()).validate(MANIFEST_SCHEMA_ID, migrated)
        atomic_write_json(manifest_path, migrated)
        if fail_after_write_for_test:
            raise RuntimeError("injected migration failure")
        if sha256_file(backup_manifest) != before_sha256:
            raise RuntimeError("backup hash changed")
        return {
            "schema": "careeros.migration-result.v1", "status": "APPLIED", "migration_id": MIGRATION_ID,
            "from_version": "1.0.0", "to_version": WORKSPACE_FORMAT_VERSION,
            "backup_path": backup_relative, "before_sha256": before_sha256,
            "after_sha256": sha256_file(manifest_path), "history_count": 1,
        }
    except Exception as exc:
        shutil.copy2(backup_manifest, manifest_path)
        if sha256_file(manifest_path) != before_sha256:
            raise MigrationFailedError("migration failed and automatic restore could not be verified", cause=exc) from exc
        raise MigrationFailedError("migration failed; original manifest restored from verified backup", cause=exc,
                                   context={"backup_path": backup_relative}) from exc
