# Troubleshooting and recovery

Use typed package output. Give the remediation first and keep the full diagnostic available on request.

| Condition | User-facing recovery |
|---|---|
| Package absent | Explain that Career OS `>=0.4.2,<0.5.0` is required. Install the approved package with the resume extra, then rerun `careeros version` and Doctor. Do not download an unapproved package. |
| Source extraction failed | Preserve the source, name the unsupported/corrupt file, and offer PDF, DOCX, Markdown, or text. Never transcribe silently or discard provenance. |
| `SOURCE_ENRICHMENT_APPROVAL_REQUIRED` | List detected LinkedIn/GitHub/portfolio URLs once. Ask whether to perform a read-only proposal-only enrichment pass. Approve or decline explicitly; never fetch implicitly. |
| Linked-source capture failed | Keep the failed URL visible, continue only with successful/local sources, and offer retry or decline. Never treat failed capture as evidence. |
| Older package | Stop workflows and explain the package upgrade path. A workspace migration does not upgrade the package. |
| Future package | Stop because the skill has not been validated with that package line. |
| `DEPENDENCY_MISSING` | Name the failed Doctor check and its remediation; rerun Doctor. |
| `DEPENDENCY_INCOMPATIBLE` | Show actual and supported versions; change the environment, not workspace data. |
| `MIGRATION_REQUIRED` | Run `migrate --plan`, summarize, request approval, apply, verify, then resume. |
| `SCHEMA_INVALID` | Identify the record/path and route factual issues to clarification. Do not patch canonical JSON manually. |
| `PRIVACY_BOUNDARY_VIOLATION` | Stop. Correct root/config separation before retrying. |
| `WORKSPACE_CORRUPT` | Stop mutations, run workspace verification, and preserve diagnostics for recovery. |
| `VALIDATION_FAILED` | Show failed resume gates; do not accept or package the artifact. |
| `RECORD_CONFLICT` | Present both facts and request a human decision. |
| `EXTERNAL_ACTION_NOT_ALLOWED` | Prepare locally if useful and state that nothing was sent or changed externally. |

Do not silently migrate, retry canonical commits, or bypass a failed validation gate. Detailed stack traces are debug-only.

For stale learning plans, review preferences and run `learning reassess` after approved canonical changes, then rebuild from a current catalog. Missing source facts and excluded courses remain visible; do not fill them with guesses. Training progress replays its append-only journal if a projection is absent; an invalid journal transition requires inspection rather than silent reset.
