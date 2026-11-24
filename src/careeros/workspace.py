"""Workspace initialization, compatibility, diagnostics, and integrity."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config, validate_config
from careeros.core.errors import (
    MigrationRequiredError,
    WorkspaceAlreadyInitializedError,
    WorkspaceFormatUnsupportedError,
    WorkspaceNotInitializedError,
)
from careeros.core.io import atomic_write_json, read_json, sha256_file, sha256_value
from careeros.schemas.validation import SchemaRegistry
from careeros.versions import (
    ACTIVE_POLICY_VERSIONS,
    COMPILER_VERSION,
    CONFIG_SCHEMA_VERSION,
    FONT_PROFILE_VERSION,
    PACKAGE_VERSION,
    RENDERER_VERSION,
    SCHEMA_BUNDLE_VERSION,
    SUPPORTED_WORKSPACE_FORMAT_MAX,
    SUPPORTED_WORKSPACE_FORMAT_MIN,
    TEMPLATE_VERSION,
    WORKSPACE_FORMAT_VERSION,
)

SUPPORTED_PYTHON = ((3, 11), (3, 12))
MANIFEST_SCHEMA_ID = "urn:careeros:schema:workspace-manifest:v1"


def utc_now(timestamp: str | None = None) -> str:
    return timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def package_root() -> Path:
    return Path(__file__).resolve().parent


def schema_dir() -> Path:
    return package_root() / "schemas"


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        raise ValueError(f"invalid semantic version: {value!r}")
    return tuple(int(part) for part in match.groups())


def compatibility(version: str) -> str:
    try:
        current = _version_tuple(version)
    except ValueError:
        return "CORRUPT"
    minimum = _version_tuple(SUPPORTED_WORKSPACE_FORMAT_MIN)
    maximum = _version_tuple(SUPPORTED_WORKSPACE_FORMAT_MAX)
    target = _version_tuple(WORKSPACE_FORMAT_VERSION)
    if current > maximum:
        return "FUTURE"
    if current < minimum:
        return "UNSUPPORTED"
    if current < target:
        return "MIGRATION_REQUIRED"
    return "CURRENT"


def make_config(workspace: Path) -> dict[str, Any]:
    package_relative = os.path.relpath(package_root(), workspace)
    return {
        "schema": "careeros.config.v1", "config_version": CONFIG_SCHEMA_VERSION,
        "workspace": {"package_root": package_relative, "user_data_root": "data", "state_root": "state",
                      "output_root": "outputs", "cache_root": ".cache", "timezone": "UTC", "locale": "en-US"},
        "candidate": {"profile_id": "candidate-uninitialized", "profile_path": "data/records/candidate.json",
                      "public_identity_policy_path": None},
        "privacy": {"default_visibility": "PRIVATE", "source_document_retention": "USER_MANAGED",
                    "generated_artifact_retention_days": None, "allow_network_enrichment": False,
                    "allow_sensitive_data_in_logs": False,
                    "require_human_approval_for_external_actions": True},
        "career": {"preferences_path": "data/records/preferences.json",
                   "role_families_path": "state/role-families", "market_map_path": None},
        "discovery": {"enabled": False, "adapters": [], "freshness_policy": None, "dedupe_policy": None},
        "qualification": {"policy": ACTIVE_POLICY_VERSIONS["qualification"], "compensation_is_hard_gate": False},
        "resume": {"page_target": 2, "template": TEMPLATE_VERSION, "renderer": "reportlab",
                   "font_profile": FONT_PROFILE_VERSION, "compact_fallback": False,
                   "output_naming": "{public_name} - Resume - {target_role}.pdf",
                   "gates": ["truth", "provenance", "ats", "autofill", "visual", "lineage"]},
        "applications": {"approval_policy": "human_before_external_action", "submitted_artifacts_immutable": True,
                         "follow_up_policy": None, "interview_workflow": None},
        "adapters": {
            "email": {"enabled": False, "external_actions": True, "require_human_approval": True,
                      "credential_reference": None},
            "calendar": {"enabled": False, "external_actions": True, "require_human_approval": True,
                         "credential_reference": None},
            "crm": {"enabled": False, "external_actions": True, "require_human_approval": True,
                    "credential_reference": None},
        },
        "runtime": {"poppler_bin": "auto", "office_converter": "disabled",
                    "network_timeout_seconds": 20, "log_level": "info", "fixture_mode": False},
    }


def _manifest_core(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "integrity"}


def canonical_state_hash(workspace: Path) -> str:
    """Hash canonical record collections without including generated state."""
    records_root = load_config(workspace / "careeros.yaml").roots.user_data_root / "records"
    payload: dict[str, Any] = {}
    if records_root.is_dir():
        for path in sorted(records_root.glob("*.json")):
            payload[path.name] = read_json(path)
    return sha256_value(payload)


def canonical_head(manifest: dict[str, Any], workspace: Path) -> dict[str, Any]:
    """Return a compatible canonical head, deriving it for pre-0.3.2 workspaces."""
    existing = manifest.get("canonical_head")
    if isinstance(existing, dict):
        return dict(existing)
    return {
        "revision": 1 if (workspace / "data/records/candidate.json").is_file() else 0,
        "canonical_sha256": canonical_state_hash(workspace),
        "last_event_id": None,
        "updated_at": None,
    }


def update_canonical_head(workspace: Path, *, revision: int, canonical_sha256: str,
                          last_event_id: str | None, timestamp: str) -> dict[str, Any]:
    manifest_path = workspace / "workspace-manifest.json"
    manifest = read_json(manifest_path)
    manifest["schema_bundle_version"] = SCHEMA_BUNDLE_VERSION
    manifest["canonical_head"] = {
        "revision": revision,
        "canonical_sha256": canonical_sha256,
        "last_event_id": last_event_id,
        "updated_at": timestamp,
    }
    refresh_manifest_integrity(manifest, workspace / "careeros.yaml", timestamp=timestamp)
    SchemaRegistry(schema_dir()).validate(MANIFEST_SCHEMA_ID, manifest)
    atomic_write_json(manifest_path, manifest)
    return manifest


def refresh_manifest_integrity(manifest: dict[str, Any], config_path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    manifest["integrity"] = {
        "algorithm": "sha256",
        "config_sha256": sha256_file(config_path),
        "manifest_core_sha256": sha256_value(_manifest_core(manifest)),
        "last_verified_at": utc_now(timestamp),
    }
    return manifest


def build_manifest(config_path: Path, *, workspace_id: str, fixture_mode: bool, created_at: str) -> dict[str, Any]:
    manifest = {
        "schema": "careeros.workspace-manifest.v1", "schema_version": "1.0.0",
        "workspace_id": workspace_id, "workspace_format_version": WORKSPACE_FORMAT_VERSION,
        "created_at": created_at, "created_by_package_version": PACKAGE_VERSION,
        "last_migrated_at": None, "last_migrated_by_package_version": None,
        "config_schema_version": CONFIG_SCHEMA_VERSION, "schema_bundle_version": SCHEMA_BUNDLE_VERSION,
        "active_policy_versions": dict(ACTIVE_POLICY_VERSIONS),
        "compiler_version_at_last_build": None, "renderer_version_at_last_build": None,
        "migration_history": [], "fixture_mode": fixture_mode, "external_adapters_enabled": False,
        "canonical_head": {"revision": 0, "canonical_sha256": sha256_value({}),
                           "last_event_id": None, "updated_at": None},
    }
    return refresh_manifest_integrity(manifest, config_path, timestamp=created_at)


def init_workspace(target: Path, *, fixture_mode: bool = False, workspace_id: str | None = None,
                   timestamp: str | None = None) -> dict[str, Any]:
    target = target.resolve()
    if target.exists() and any(target.iterdir()):
        raise WorkspaceAlreadyInitializedError(f"refusing to overwrite non-empty workspace: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{target.name}.init-", dir=target.parent))
    created_at = utc_now(timestamp)
    try:
        config = make_config(temp)
        config["runtime"].pop("fixture_mode", None)
        validate_config(config, temp / "careeros.yaml")
        SchemaRegistry(schema_dir()).validate("urn:careeros:schema:config:v1", config)
        for name in ("data", "sources", "state", "outputs", ".cache"):
            (temp / name).mkdir()
        atomic_write_json(temp / "careeros.yaml", config)
        manifest = build_manifest(temp / "careeros.yaml", workspace_id=workspace_id or f"workspace-{uuid.uuid4()}",
                                  fixture_mode=fixture_mode, created_at=created_at)
        atomic_write_json(temp / "workspace-manifest.json", manifest)
        (temp / ".gitignore").write_text(
            ".cache/\n.careeros-backups/\noutputs/.tmp/\nstate/failed-builds/\n**/*.tmp\n**/__pycache__/\n",
            encoding="utf-8",
        )
        if target.exists():
            target.rmdir()
        temp.replace(target)
        return manifest
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def require_initialized(workspace: Path) -> dict[str, Any]:
    path = workspace.resolve() / "workspace-manifest.json"
    if not path.is_file():
        raise WorkspaceNotInitializedError(f"workspace manifest not found: {path}")
    try:
        return read_json(path)
    except Exception as exc:
        raise WorkspaceFormatUnsupportedError("workspace manifest is unreadable", cause=exc) from exc


def require_current_workspace(workspace: Path) -> dict[str, Any]:
    manifest = require_initialized(workspace)
    state = compatibility(str(manifest.get("workspace_format_version", "")))
    if state == "MIGRATION_REQUIRED":
        raise MigrationRequiredError("workspace format requires explicit migration",
                                     context={"current": manifest.get("workspace_format_version"),
                                              "target": WORKSPACE_FORMAT_VERSION})
    if state != "CURRENT":
        raise WorkspaceFormatUnsupportedError("workspace format is not supported",
                                              context={"state": state, "version": manifest.get("workspace_format_version")})
    return manifest


def update_last_build_versions(workspace: Path, *, timestamp: str | None = None) -> None:
    manifest_path = workspace.resolve() / "workspace-manifest.json"
    manifest = require_current_workspace(workspace)
    manifest["compiler_version_at_last_build"] = COMPILER_VERSION
    manifest["renderer_version_at_last_build"] = RENDERER_VERSION
    refresh_manifest_integrity(manifest, workspace / "careeros.yaml", timestamp=timestamp)
    SchemaRegistry(schema_dir()).validate(MANIFEST_SCHEMA_ID, manifest)
    atomic_write_json(manifest_path, manifest)


def _module_check(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _command_version(command: str) -> str | None:
    path = shutil.which(command)
    if not path:
        return None
    result = subprocess.run([path, "-v"], capture_output=True, text=True, timeout=5, check=False)
    text = (result.stdout + result.stderr).strip().splitlines()
    return text[0] if text else Path(path).name


def verify_workspace(workspace: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    findings: list[dict[str, Any]] = []

    def add(check: str, passed: bool, detail: str) -> None:
        findings.append({"check": check, "status": "PASS" if passed else "FAIL", "detail": detail})

    manifest_path = workspace / "workspace-manifest.json"
    config_path = workspace / "careeros.yaml"
    add("manifest_exists", manifest_path.is_file(), str(manifest_path))
    add("config_exists", config_path.is_file(), str(config_path))
    if not manifest_path.is_file() or not config_path.is_file():
        return {"schema": "careeros.workspace-verification.v1", "status": "INVALID", "checks": findings}
    try:
        manifest = read_json(manifest_path)
        config = load_config(config_path)
    except Exception as exc:
        add("load", False, str(exc))
        return {"schema": "careeros.workspace-verification.v1", "status": "INVALID", "checks": findings}
    current = compatibility(str(manifest.get("workspace_format_version", ""))) == "CURRENT"
    add("workspace_format", current, str(manifest.get("workspace_format_version")))
    try:
        SchemaRegistry(schema_dir()).validate(MANIFEST_SCHEMA_ID, manifest)
        add("manifest_schema", True, MANIFEST_SCHEMA_ID)
    except Exception as exc:
        add("manifest_schema", False, str(exc))
    integrity = manifest.get("integrity", {})
    add("config_hash", integrity.get("config_sha256") == sha256_file(config_path), "sha256")
    add("manifest_hash", integrity.get("manifest_core_sha256") == sha256_value(_manifest_core(manifest)), "sha256")
    try:
        config.roots.validate_separation()
        add("root_separation", True, "package/data/state/output/cache separated")
    except Exception as exc:
        add("root_separation", False, str(exc))
    history = manifest.get("migration_history", [])
    chain_ok = all(item.get("status") == "APPLIED" and item.get("to_version") for item in history)
    if history:
        chain_ok = chain_ok and history[-1].get("to_version") == manifest.get("workspace_format_version")
    add("migration_history", chain_ok, f"{len(history)} event(s)")
    transactions = config.roots.state_root / "canonical-transactions"
    incomplete: list[str] = []
    if transactions.is_dir():
        for journal_path in transactions.glob("*/transaction.json"):
            try:
                journal = read_json(journal_path)
                if journal.get("status") not in {"COMMITTED", "ROLLED_BACK"}:
                    incomplete.append(journal.get("transaction_id", journal_path.parent.name))
            except Exception:
                incomplete.append(journal_path.parent.name)
    add("canonical_transactions", not incomplete, f"incomplete={incomplete}")

    records_root = config.roots.user_data_root / "records"
    record_ids: list[str] = []
    evidence_ids: set[str] = set()
    references: set[str] = set()
    if records_root.exists():
        for path in sorted(records_root.glob("*.json")):
            value = read_json(path)
            values = value if isinstance(value, list) else [value]
            for record in values:
                if not isinstance(record, dict):
                    continue
                if isinstance(record.get("record_id"), str):
                    record_ids.append(record["record_id"])
                if record.get("schema") in {
                    "careeros.evidence-record.v1",
                    "careeros.evidence-block.v1",
                }:
                    evidence_ids.add(record.get("record_id", ""))
                for ref in record.get("evidence_ids", []):
                    references.add(ref)
        add("record_ids_unique", len(record_ids) == len(set(record_ids)), f"{len(record_ids)} record(s)")
        add("evidence_references", references.issubset(evidence_ids), f"missing={sorted(references - evidence_ids)}")
    else:
        add("record_ids_unique", True, "no canonical records yet")
        add("evidence_references", True, "no canonical records yet")

    artifact_failures: list[str] = []
    for path in sorted(config.roots.state_root.glob("resume-builds/*/artifact.json")):
        artifact = read_json(path)
        target = config.roots.output_root / artifact.get("path", "")
        if not target.is_file() or sha256_file(target) != artifact.get("sha256"):
            artifact_failures.append(str(path.relative_to(workspace)))
    add("artifact_hashes", not artifact_failures, f"failures={artifact_failures}")
    status = "VALID" if all(item["status"] == "PASS" for item in findings) else "INVALID"
    return {"schema": "careeros.workspace-verification.v1", "status": status, "checks": findings}


def doctor(workspace: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    checks: list[dict[str, Any]] = []
    outcome = "READY"

    def check(name: str, passed: bool, detail: Any, failure: str, *, optional: bool = False) -> None:
        nonlocal outcome
        status = "PASS" if passed else ("OPTIONAL_LIMITATION" if optional else "FAIL")
        checks.append({"check": name, "status": status, "detail": detail})
        if not passed:
            if optional and outcome == "READY":
                outcome = "READY_WITH_OPTIONAL_LIMITATIONS"
            elif not optional and outcome in {"READY", "READY_WITH_OPTIONAL_LIMITATIONS"}:
                outcome = failure

    initialized = (workspace / "workspace-manifest.json").is_file() or (workspace / "careeros.yaml").is_file()
    check("package_version", True, PACKAGE_VERSION, "DEPENDENCY_INCOMPATIBLE")
    check("python", sys.version_info[:2] in SUPPORTED_PYTHON,
          {"actual": f"{sys.version_info.major}.{sys.version_info.minor}", "supported": ["3.11", "3.12"]},
          "DEPENDENCY_INCOMPATIBLE")
    modules = {name: _module_check(name) for name in ("reportlab", "pypdf", "pdfplumber", "PIL")}
    module_versions = {name: _distribution_version("Pillow" if name == "PIL" else name) for name in modules}
    check("resume_python_packages", all(modules.values()),
          module_versions,
          "DEPENDENCY_MISSING", optional=not initialized)
    if all(modules.values()):
        version_compatible = (
            _version_tuple(module_versions["reportlab"])[0] == 4
            and _version_tuple(module_versions["pypdf"])[0] == 6
            and _version_tuple(module_versions["pdfplumber"])[:2] == (0, 11)
            and _version_tuple(module_versions["PIL"])[0] == 12
        )
        check("resume_package_versions", version_compatible, module_versions, "DEPENDENCY_INCOMPATIBLE",
              optional=not initialized)
    poppler_version = _command_version("pdftoppm")
    check("poppler", poppler_version is not None, poppler_version or "pdftoppm not found",
          "DEPENDENCY_MISSING", optional=not initialized)
    check("font_profile", True, {"profile": FONT_PROFILE_VERSION, "fonts": ["Helvetica", "Helvetica-Bold"]},
          "DEPENDENCY_MISSING")
    registry = SchemaRegistry(schema_dir())
    check("schema_registry", len(registry.by_id) >= 23,
          {"count": len(registry.by_id), "bundle_version": SCHEMA_BUNDLE_VERSION}, "DEPENDENCY_MISSING")
    check("free_disk_space", shutil.disk_usage(workspace if workspace.exists() else workspace.parent).free >= 50 * 1024 * 1024,
          shutil.disk_usage(workspace if workspace.exists() else workspace.parent).free, "PATH_INVALID")

    if not initialized:
        check("workspace", False, "not initialized; run careeros init", "READY_WITH_OPTIONAL_LIMITATIONS", optional=True)
        return {"schema": "careeros.doctor-result.v2", "outcome": outcome, "package_version": PACKAGE_VERSION,
                "workspace_state": "NOT_INITIALIZED", "checks": checks}
    if not (workspace / "workspace-manifest.json").is_file() or not (workspace / "careeros.yaml").is_file():
        return {"schema": "careeros.doctor-result.v2", "outcome": "WORKSPACE_CORRUPT",
                "workspace_state": "PARTIAL", "checks": checks}
    try:
        manifest = read_json(workspace / "workspace-manifest.json")
    except Exception as exc:
        check("workspace_manifest", False, str(exc), "WORKSPACE_CORRUPT")
        return {"schema": "careeros.doctor-result.v2", "outcome": "WORKSPACE_CORRUPT", "checks": checks}
    compat = compatibility(str(manifest.get("workspace_format_version", "")))
    compat_outcomes = {"CURRENT": None, "MIGRATION_REQUIRED": "MIGRATION_REQUIRED", "FUTURE": "FUTURE_WORKSPACE",
                       "UNSUPPORTED": "UNSUPPORTED_WORKSPACE", "CORRUPT": "WORKSPACE_CORRUPT"}
    check("workspace_format", compat == "CURRENT",
          {"actual": manifest.get("workspace_format_version"), "state": compat,
           "supported": [SUPPORTED_WORKSPACE_FORMAT_MIN, SUPPORTED_WORKSPACE_FORMAT_MAX]},
          compat_outcomes[compat] or "WORKSPACE_CORRUPT")
    try:
        validated = load_config(workspace / "careeros.yaml")
        registry.validate("urn:careeros:schema:config:v1", validated.raw)
        check("config_schema", True, CONFIG_SCHEMA_VERSION, "CONFIG_INVALID")
        writable = all(path.is_dir() and os.access(path, os.W_OK) for path in
                       (validated.roots.user_data_root, validated.roots.state_root,
                        validated.roots.output_root))
        # Cache is disposable and deliberately absent from exports. Check that
        # it can be recreated without mutating the filesystem during Doctor.
        cache = validated.roots.cache_root
        ancestor = cache
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        writable = writable and ancestor.is_dir() and os.access(ancestor, os.W_OK | os.X_OK)
        check("writable_roots", writable, "data/state/output/cache", "PERMISSION_FAILURE")
        validated.roots.validate_separation()
        check("package_boundary", True, "runtime roots outside immutable package source", "PRIVACY_BOUNDARY_FAILURE")
    except Exception as exc:
        check("config_schema", False, str(exc), "CONFIG_INVALID")
    if compat == "CURRENT":
        verification = verify_workspace(workspace)
        check("workspace_integrity", verification["status"] == "VALID", verification, "WORKSPACE_CORRUPT")
    check("optional_adapters", manifest.get("external_adapters_enabled") is False,
          "external adapters disabled", "PRIVACY_BOUNDARY_FAILURE")
    if all(modules.values()):
        from reportlab.pdfgen.canvas import Canvas
        from pypdf import PdfReader
        buffer = io.BytesIO()
        canvas = Canvas(buffer)
        canvas.drawString(72, 720, "Career OS synthetic render smoke test")
        canvas.save()
        check("synthetic_render_smoke", len(PdfReader(io.BytesIO(buffer.getvalue())).pages) == 1,
              {"renderer": RENDERER_VERSION}, "DEPENDENCY_INCOMPATIBLE")
    return {"schema": "careeros.doctor-result.v2", "outcome": outcome, "package_version": PACKAGE_VERSION,
            "workspace_state": compat, "checks": checks}


def status(workspace: Path) -> dict[str, Any]:
    require_current_workspace(workspace)
    states: dict[str, Any] = {"workspace": read_json(workspace / "workspace-manifest.json")}
    candidates = {
        "onboarding": workspace / "state/onboarding/session.json", "profile": workspace / "state/profile/profile-build-manifest.json",
        "role_family": workspace / "state/role-families/active.json", "qualification": workspace / "state/qualifications",
        "resume": workspace / "state/resume-builds", "application": workspace / "state/application-packets",
        "changesets": workspace / "state/changesets", "derivative_status": workspace / "state/derivative-status.json",
    }
    for key, path in candidates.items():
        if path.is_file(): states[key] = read_json(path)
        elif path.is_dir(): states[key] = sorted(child.name for child in path.glob("*.json"))
        else: states[key] = None
    return {"schema": "careeros.status.v1", "state": states}
