# Phase 2 generic resume vertical slice

## Boundary

The package reads candidate facts only from typed canonical records under `USER_DATA_ROOT`. Onboarding input first becomes proposed state under `STATE_ROOT`; only `careeros onboarding commit` may create canonical records. Package source is immutable at runtime. Resume files and QA renders belong to `OUTPUT_ROOT`; temporary work belongs to `CACHE_ROOT`.

External adapters are disabled. The last application state implemented in this repository is `REVIEW_REQUIRED`. There is deliberately no submission, email, outreach, scheduling, discovery, or public-profile mutation API.

## Deterministic command sequence

```text
careeros init --fixture-mode --workspace-id <stable-test-id>
careeros doctor --json
careeros onboarding start
careeros onboarding ingest --input <onboarding-input.json>
careeros clarification list
careeros clarification resolve --resolutions <resolutions.json>
careeros onboarding commit --actor <human-reviewer>
careeros profile build
careeros role-family build --approve
careeros opportunity ingest --input <synthetic-opportunity.json>
careeros qualify --opportunity-id <id>
careeros resume build --opportunity-id <qualified-id>
careeros resume validate --build-id <id>
careeros application prepare --opportunity-id <id> --build-id <id>
careeros status
```

`--timestamp` is available only to make fixture and regression outputs deterministic. Human review is represented explicitly by the commit actor and role-family approval flag.

## Typed exits

`0` means success, including `READY_WITH_OPTIONAL_LIMITATIONS`. Configuration, dependency, path, permission, migration, privacy-boundary, validation, clarification, approval, qualification, and unsafe-overwrite failures have separate nonzero codes in `careeros.core.exit_codes.ExitCode`.

## Qualification invariant

Matches are classified as `SUPPORTED_MATCH`, `TRANSFERABLE_MATCH`, `BRIDGEABLE_GAP`, `HARD_GAP`, or `UNKNOWN`. Project adjacency never creates employment-experience equivalence. Only `QUALIFIED` opportunities may enter resume compilation; borderline and unqualified opportunities stop before artifact creation.

## Rendering and validation

The one-column `generic-adaptive-depth-v1` template uses built-in Helvetica fonts. Candidate facts come from `CareerProfileV1`; tailoring changes evidence ranking, ordering, and expression, not truth. Validation retains all evidence-safety gates and adds editorial quality, system-artifact leakage, semantic-duplication, job-specific tailoring, completeness, and underfill gates.

Synthetic visual baselines are range-based JSON metrics, not private or pixel-perfect image copies.
