# Configuration

Initialization writes JSON to `careeros.yaml`; this is deliberate and requires no YAML library. Keep package_root, user_data_root, state_root, output_root and cache_root relative to that file and non-overlapping. The package root must not contain runtime data.

Defaults include locale and timezone, candidate visibility/contact policy, career preferences, qualification weights and resume template/font policy. Identity, career data, role families, evidence and naming are configurable. The released premium template uses fixed, tested Helvetica geometry; arbitrary font/theme overrides are not supported.

Use `careeros schemas list` and `careeros schemas validate <json>` for the exact contracts. Do not store passwords, tokens or API keys in configuration. External-action adapters stay disabled. Changes to canonical career facts use `update propose/preview/approve/commit`, preserving revisions and derivative staleness.

The dashboard and reports are regenerated local derivatives. You can edit their presentation copies, but rebuilding replaces them. Keep source corrections in the canonical update workflow.
