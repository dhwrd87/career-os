from __future__ import annotations

import unittest
from pathlib import Path

from careeros.config import load_config
from careeros.core.errors import ExternalActionPolicyError, PathBoundaryError, UnsupportedConfigVersionError


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/config"


class CareerOSConfigTests(unittest.TestCase):
    def test_valid_minimal(self) -> None:
        config = load_config(FIXTURES / "valid-minimal.json")
        self.assertEqual(config.raw["schema"], "careeros.config.v1")

    def test_valid_full(self) -> None:
        config = load_config(FIXTURES / "valid-full.json")
        self.assertTrue(config.raw["discovery"]["enabled"])

    def test_invalid_absolute_path(self) -> None:
        with self.assertRaises(PathBoundaryError):
            load_config(FIXTURES / "invalid-path.json")

    def test_invalid_version(self) -> None:
        with self.assertRaises(UnsupportedConfigVersionError):
            load_config(FIXTURES / "invalid-version.json")

    def test_invalid_external_action_policy(self) -> None:
        with self.assertRaises(ExternalActionPolicyError):
            load_config(FIXTURES / "invalid-external-action.json")


if __name__ == "__main__":
    unittest.main()

