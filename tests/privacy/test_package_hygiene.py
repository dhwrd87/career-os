from __future__ import annotations

import re
import json
import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEXT_EXTENSIONS = {".py", ".json", ".toml", ".md", ".txt", ".yaml", ".yml", ".sh"}
ABSOLUTE_HOME = re.compile(
    r"(?:/" + "Users" + r"/[^/\s]+|/" + "home" + r"/[^/\s]+|[A-Za-z]:\\\\" + "Users" + r"\\\\[^\\\s]+)"
)


class PackageHygieneTests(unittest.TestCase):
    def test_no_absolute_home_paths(self) -> None:
        findings = []
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if ABSOLUTE_HOME.search(text):
                findings.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(findings, [])

    def test_no_runtime_state_directories_in_package_root(self) -> None:
        self.assertFalse(any((ROOT / name).exists() for name in ("data", "state", "outputs", ".cache", "sources")))

    def test_no_generated_document_binaries(self) -> None:
        forbidden = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
        findings = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and p.suffix.lower() in forbidden]
        manifest_path = ROOT / 'docs/synthetic-assets.json'
        allowed = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        unexpected = [name for name in findings if name not in allowed or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != allowed[name]]
        self.assertEqual(unexpected, [])
        self.assertTrue(all(name.startswith(('docs/images/', 'examples/workspace/', 'examples/recruiter-copy-review/')) for name in allowed))

    def test_config_defaults_contain_no_identity_values(self) -> None:
        source = (ROOT / "tests/fixtures/config/valid-minimal.json").read_text(encoding="utf-8")
        self.assertNotIn("@example.invalid", source)
        self.assertNotIn("legal_name", source)
        self.assertNotIn("employer", source)


if __name__ == "__main__":
    unittest.main()
