from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from careeros import __version__
from careeros.schemas.validation import SchemaRegistry
from careeros.versions import version_report
from careeros.workspace import init_workspace, schema_dir, verify_workspace


class Phase3PackageTests(unittest.TestCase):
    def test_independent_version_authorities(self):
        report = version_report()
        self.assertEqual(__version__, "0.4.1")
        self.assertEqual(report["supported_workspace_format"]["current"], "1.1.0")
        self.assertEqual(report["schema_bundle_version"], "1.24.0")
        self.assertIsNone(report["skill_version"])

    def test_formal_registry_covers_persisted_contracts(self):
        registry = SchemaRegistry(schema_dir())
        self.assertGreaterEqual(len(registry.by_id), 30)
        self.assertEqual(len(registry.list_entries()), len(registry.by_id))
        self.assertTrue(all({"schema_id", "schema_version", "status", "package_support_range",
                             "migration_available", "documentation"} <= set(item)
                            for item in registry.list_entries()))

    def test_init_writes_manifest_and_retention_policy(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            manifest = init_workspace(target, fixture_mode=True, workspace_id="workspace-phase3",
                                      timestamp="2026-10-02T12:00:00Z")
            self.assertEqual(manifest["workspace_format_version"], "1.1.0")
            self.assertEqual(manifest["created_by_package_version"], "0.4.1")
            self.assertEqual(manifest["migration_history"], [])
            self.assertIn("manifest_core_sha256", manifest["integrity"])
            ignores = (target / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".cache/", ignores)
            self.assertIn(".careeros-backups/", ignores)
            self.assertNotIn("data/", ignores)
            self.assertEqual(verify_workspace(target)["status"], "VALID")

    def test_schema_registry_validates_manifest_path(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            init_workspace(target, workspace_id="workspace-schema", timestamp="2026-10-02T12:00:00Z")
            result = SchemaRegistry(schema_dir()).validate_path(target / "workspace-manifest.json")
            self.assertEqual(result["status"], "VALID")

    def test_doctor_does_not_grow_workspace_filesystem(self):
        from careeros.workspace import doctor
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            init_workspace(target, workspace_id="workspace-growth", timestamp="2026-10-02T12:00:00Z")
            before = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
            doctor(target)
            doctor(target)
            after = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
            self.assertEqual(before, after)

    def test_export_without_disposable_cache_is_writable_without_doctor_mutation(self):
        from careeros.workspace import doctor
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/'workspace'
            init_workspace(target,timestamp='2026-10-02T12:00:00Z')
            (target/'.cache').rmdir()
            result=doctor(target)
            self.assertEqual(next(c['status'] for c in result['checks'] if c['check']=='writable_roots'),'PASS')
            self.assertFalse((target/'.cache').exists())


if __name__ == "__main__":
    unittest.main()
