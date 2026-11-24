from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from careeros.config import load_config, validate_config
from careeros.core.errors import MutationBoundaryError, PathBoundaryError


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/config/valid-minimal.json"


class RootBoundaryTests(unittest.TestCase):
    def test_package_write_is_forbidden(self) -> None:
        layout = load_config(FIXTURE).roots
        with self.assertRaises(MutationBoundaryError):
            layout.assert_write_allowed(layout.package_root / "generated.json", "state")

    def test_state_output_and_cache_have_owned_write_roots(self) -> None:
        layout = load_config(FIXTURE).roots
        self.assertEqual(layout.assert_write_allowed(layout.state_root / "record.json", "state"), layout.state_root / "record.json")
        self.assertEqual(layout.assert_write_allowed(layout.output_root / "resume.pdf", "output"), layout.output_root / "resume.pdf")
        self.assertEqual(layout.assert_write_allowed(layout.cache_root / "page.png", "cache"), layout.cache_root / "page.png")

    def test_user_data_requires_explicit_commit_intent(self) -> None:
        layout = load_config(FIXTURE).roots
        with self.assertRaises(MutationBoundaryError):
            layout.assert_write_allowed(layout.user_data_root / "profile.json", "state")
        self.assertEqual(
            layout.assert_write_allowed(layout.user_data_root / "profile.json", "user_data_commit"),
            layout.user_data_root / "profile.json",
        )

    def test_runtime_root_inside_package_is_rejected(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["workspace"]["user_data_root"] = "../../../src/careeros/private-data"
        with self.assertRaises(PathBoundaryError):
            validate_config(data, FIXTURE)

    def test_overlapping_runtime_roots_are_rejected(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["workspace"]["output_root"] = data["workspace"]["state_root"]
        with self.assertRaises(PathBoundaryError):
            validate_config(data, FIXTURE)

    def test_validation_does_not_create_directories(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "career-os.json"
            validate_config(data, config_path)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()

