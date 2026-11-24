from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from careeros import onboarding, workspace


class Phase2BoundaryTests(unittest.TestCase):
    def test_init_refuses_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            target.mkdir()
            (target / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                workspace.init_workspace(target)
            self.assertEqual((target / "keep.txt").read_text(), "keep")

    def test_init_writes_only_documented_structure(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workspace.init_workspace(target, fixture_mode=True, workspace_id="workspace-boundary", timestamp="2026-10-02T12:00:00Z")
            self.assertEqual({path.name for path in target.iterdir()}, {"careeros.yaml", "workspace-manifest.json", ".gitignore", "data", "sources", "state", "outputs", ".cache"})

    def test_onboarding_does_not_commit_canonical_data(self):
        fixture = Path(__file__).resolve().parents[2] / "fixtures/synthetic/early-career/onboarding/input.json"
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            workspace.init_workspace(target, fixture_mode=True, workspace_id="workspace-proposal", timestamp="2026-10-02T12:00:00Z")
            onboarding.start(target, timestamp="2026-10-02T12:00:00Z")
            onboarding.ingest(target, fixture, timestamp="2026-10-02T12:00:00Z")
            self.assertFalse((target / "data/records").exists())
            self.assertTrue((target / "state/onboarding/proposed-records.json").exists())

    def test_no_submission_api_exists(self):
        from careeros import application
        self.assertFalse(hasattr(application, "submit"))


if __name__ == "__main__":
    unittest.main()
