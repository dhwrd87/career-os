# Troubleshooting

- `MIGRATION_REQUIRED`: run `careeros migrate --plan`; review the files and backup requirement before `--apply`.
- `FUTURE_WORKSPACE`: use the package version that created the workspace; do not downgrade or edit the manifest manually.
- `WORKSPACE_CORRUPT`: run `careeros workspace verify` and inspect failed integrity/reference checks. Restore only from a verified backup.
- `DEPENDENCY_MISSING`: install `career-os[resume]` and ensure Poppler is on `PATH`.
- `DEPENDENCY_INCOMPATIBLE`: use Python 3.11 or 3.12 and the documented dependency ranges.
- `PRIVACY_BOUNDARY_FAILURE`: move data, state, outputs, or cache outside installed package source.
- `SCHEMA_INVALID`: use `careeros schemas validate <path>` for field-level details.
- `CHANGESET_CONFLICT`: canonical truth changed after proposal; regenerate, review, and approve a fresh changeset.
- `CHANGESET_TRANSACTION_FAILED`: inspect the transaction ID and failure event. Pre-commit failures restore and verify the previous canonical hash; a `canonical_committed: true` context means only a post-commit operation failed.

Typed engine errors include code, message, retryability, remediation and context. CLI usage and ordinary policy/input errors also produce nonzero exits; inspect their message and correct the input before retrying.

| Exit | Meaning |
|---:|---|
| 0 | success / ready |
| 2 | CLI usage error |
| 10–19 | configuration, dependency, path, permission, migration, boundary, or workspace bootstrap failure |
| 20–24 | validation, clarification, approval, qualification, or safe-overwrite stop |
| 25 | migration failed and recovery information is available |
| 26–30 | schema, integrity, renderer, conflict, or external-action failure |
| 31–33 | workspace missing, already initialized, or unsupported |
| 34 | changeset optimistic-concurrency conflict |
| 35 | canonical changeset transaction failed |

The exact stable mapping is defined by `careeros.core.exit_codes.ExitCode` and is part of the 0.4 compatibility surface.
