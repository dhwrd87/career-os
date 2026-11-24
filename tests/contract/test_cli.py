from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from careeros.cli import main


class CliTests(unittest.TestCase):
    def test_init_doctor_status_commands(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "workspace"
            base = ["--workspace", str(target), "--timestamp", "2026-10-02T12:00:00Z"]
            self.assertEqual(main([*base, "init", "--fixture-mode", "--workspace-id", "workspace-cli"]), 0)
            self.assertEqual(main([*base, "doctor", "--json"]), 0)
            self.assertEqual(main([*base, "status"]), 0)


if __name__ == "__main__":
    unittest.main()
