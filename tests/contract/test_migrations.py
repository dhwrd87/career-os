from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from careeros import migrations, profile, workspace
from careeros.core.errors import MigrationFailedError, MigrationRequiredError, WorkspaceFormatUnsupportedError
from careeros.core.io import atomic_write_json, read_json, sha256_file


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "tests/fixtures/workspace-v1.0/workspace-manifest.json"
NOW = "2026-10-02T12:00:00Z"


class MigrationMatrixTests(unittest.TestCase):
    def legacy_workspace(self, root: str) -> Path:
        target = Path(root) / "workspace"
        workspace.init_workspace(target, fixture_mode=True, workspace_id="workspace-legacy-fixture", timestamp=NOW)
        atomic_write_json(target / "workspace-manifest.json", read_json(LEGACY))
        return target

    def test_old_workspace_doctor_requires_migration(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(workspace.doctor(self.legacy_workspace(root))["outcome"], "MIGRATION_REQUIRED")

    def test_plan_is_read_only(self):
        with tempfile.TemporaryDirectory() as root:
            target = self.legacy_workspace(root)
            before = sha256_file(target / "workspace-manifest.json")
            plan = migrations.migration_plan(target)
            self.assertEqual(plan["state"], "MIGRATION_REQUIRED")
            self.assertEqual(before, sha256_file(target / "workspace-manifest.json"))
            self.assertFalse((target / ".careeros-backups").exists())

    def test_apply_creates_backup_and_history(self):
        with tempfile.TemporaryDirectory() as root:
            target = self.legacy_workspace(root)
            result = migrations.apply_migrations(target, timestamp=NOW)
            manifest = read_json(target / "workspace-manifest.json")
            self.assertEqual(result["status"], "APPLIED")
            self.assertTrue((target / result["backup_path"] / "workspace-manifest.json").is_file())
            self.assertEqual(manifest["migration_history"][0]["migration_id"], migrations.MIGRATION_ID)
            self.assertEqual(workspace.verify_workspace(target)["status"], "VALID")

    def test_already_current_is_noop(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workspace.init_workspace(target, timestamp=NOW)
            before = sha256_file(target / "workspace-manifest.json")
            self.assertEqual(migrations.apply_migrations(target, timestamp=NOW)["status"], "NO_CHANGES")
            self.assertEqual(before, sha256_file(target / "workspace-manifest.json"))

    def test_future_workspace_is_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workspace.init_workspace(target, timestamp=NOW)
            manifest = read_json(target / "workspace-manifest.json")
            manifest["workspace_format_version"] = "9.0.0"
            atomic_write_json(target / "workspace-manifest.json", manifest)
            self.assertEqual(workspace.doctor(target)["outcome"], "FUTURE_WORKSPACE")

    def test_unsupported_old_workspace_is_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            target = self.legacy_workspace(root)
            manifest = read_json(target / "workspace-manifest.json")
            manifest["workspace_format_version"] = "0.9.0"
            atomic_write_json(target / "workspace-manifest.json", manifest)
            self.assertEqual(workspace.doctor(target)["outcome"], "UNSUPPORTED_WORKSPACE")

    def test_corrupted_workspace_is_reported(self):
        with tempfile.TemporaryDirectory() as root:
            target = self.legacy_workspace(root)
            (target / "workspace-manifest.json").write_text("{", encoding="utf-8")
            with self.assertRaises(WorkspaceFormatUnsupportedError):
                migrations.migration_plan(target)

    def test_partially_migrated_workspace_is_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            target = self.legacy_workspace(root)
            manifest = read_json(target / "workspace-manifest.json")
            manifest["migration_history"] = []
            atomic_write_json(target / "workspace-manifest.json", manifest)
            self.assertTrue(migrations.migration_plan(target)["blockers"])

    def test_failure_rolls_back_to_source_hash(self):
        with tempfile.TemporaryDirectory() as root:
            target = self.legacy_workspace(root)
            before = sha256_file(target / "workspace-manifest.json")
            with self.assertRaises(MigrationFailedError):
                migrations.apply_migrations(target, timestamp=NOW, fail_after_write_for_test=True)
            self.assertEqual(before, sha256_file(target / "workspace-manifest.json"))

    def test_repeated_invocation_is_safe(self):
        with tempfile.TemporaryDirectory() as root:
            target = self.legacy_workspace(root)
            migrations.apply_migrations(target, timestamp=NOW)
            self.assertEqual(migrations.apply_migrations(target, timestamp=NOW)["status"], "NO_CHANGES")

    def test_workflows_never_silently_migrate(self):
        with tempfile.TemporaryDirectory() as root:
            target = self.legacy_workspace(root)
            before = sha256_file(target / "workspace-manifest.json")
            with self.assertRaises(MigrationRequiredError):
                profile.build_profile(target, timestamp=NOW)
            self.assertEqual(before, sha256_file(target / "workspace-manifest.json"))


if __name__ == "__main__":
    unittest.main()
