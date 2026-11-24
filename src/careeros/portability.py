"""Workspace export and recoverable reset/archive operations."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config
from careeros.core.io import atomic_write_json, read_json, sha256_file
from careeros.workspace import require_current_workspace, utc_now


EXPORT_PATHS = (
    "careeros.yaml",
    "workspace-manifest.json",
    "data/records",
    "data/history",
    "state/canonical-history",
    "state/changesets",
    "state/derivative-status.json",
    "state/profile",
    "state/role-families",
    "state/opportunities",
    "state/qualifications",
    "state/resume-builds",
    "state/application-packets",
    "outputs",
)


def _selected_files(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for relative in EXPORT_PATHS:
        path = workspace / relative
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in sorted(path.rglob("*")) if item.is_file())
    return sorted(set(files))


def export_workspace(workspace: Path, output: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    manifest = require_current_workspace(workspace)
    workspace = workspace.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite export: {output}")
    files = _selected_files(workspace)
    export_manifest = {
        "schema": "careeros.portable-export-manifest.v1",
        "workspace_id": manifest["workspace_id"],
        "created_at": utc_now(timestamp),
        "categories": {
            "portable_structured_data": ["data/records", "data/history", "state/canonical-history", "state/changesets"],
            "generated_documents": ["outputs"],
            "source_documents": "EXCLUDED_BY_DEFAULT",
        },
        "files": [{"path": str(path.relative_to(workspace)), "sha256": sha256_file(path)} for path in files],
    }
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, str(path.relative_to(workspace)))
        archive.writestr("export-manifest.json", __import__("json").dumps(export_manifest, indent=2, sort_keys=True) + "\n")
    export_manifest["archive"] = str(output)
    export_manifest["archive_sha256"] = sha256_file(output)
    return export_manifest


def reset_generated(workspace: Path, *, confirm_workspace_id: str, timestamp: str | None = None) -> dict[str, Any]:
    manifest = require_current_workspace(workspace)
    if confirm_workspace_id != manifest["workspace_id"]:
        raise PermissionError("exact workspace ID confirmation is required")
    workspace = workspace.resolve()
    roots = load_config(workspace / "careeros.yaml").roots
    stamp = utc_now(timestamp).replace(":", "").replace("-", "")
    archive_root = workspace / ".careeros-archives" / f"generated-reset-{stamp}"
    moved: list[str] = []
    for path in (
        roots.state_root / "profile", roots.state_root / "role-families", roots.state_root / "qualifications",
        roots.state_root / "resume-builds", roots.state_root / "application-packets", roots.state_root / "derivative-status.json",
        roots.output_root, roots.cache_root,
    ):
        if not path.exists():
            continue
        relative = path.relative_to(workspace)
        destination = archive_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        path.replace(destination)
        moved.append(str(relative))
    roots.output_root.mkdir(parents=True, exist_ok=True)
    roots.cache_root.mkdir(parents=True, exist_ok=True)
    result = {"schema": "careeros.generated-reset.v1", "workspace_id": manifest["workspace_id"], "archived_at": utc_now(timestamp), "archive_path": str(archive_root), "moved": moved, "canonical_data_preserved": True}
    atomic_write_json(archive_root / "reset-manifest.json", result)
    return result


def archive_workspace(workspace: Path, destination: Path, *, confirm_workspace_id: str, confirm_phrase: str, timestamp: str | None = None) -> dict[str, Any]:
    manifest = require_current_workspace(workspace)
    if confirm_workspace_id != manifest["workspace_id"] or confirm_phrase != "DELETE WORKSPACE":
        raise PermissionError("exact workspace ID and confirmation phrase are required")
    workspace = workspace.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"archive destination already exists: {destination}")
    if destination == workspace or workspace in destination.parents:
        raise ValueError("archive destination must be outside the workspace")
    destination.parent.mkdir(parents=True, exist_ok=True)
    workspace.replace(destination)
    return {"schema": "careeros.workspace-archive.v1", "workspace_id": manifest["workspace_id"], "archived_at": utc_now(timestamp), "archive_path": str(destination), "recoverable": True, "deleted_in_place": True}
