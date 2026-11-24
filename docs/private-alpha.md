# Supervised private-alpha protocol

## Preconditions

- Obtain affirmative participation and privacy consent before ingestion.
- Create a separate local workspace and workspace ID for each participant.
- Keep external-action adapters disabled.
- Record every explanation, manual repair, workaround, or recovery as an operator intervention.
- Never reuse participant data as a fixture, example, policy default, or package test.

## Observation labels

Use `USER_CONFUSION`, `OPERATOR_INTERVENTION`, `SYSTEM_FAILURE`, `DOCUMENTATION_GAP`, `UX_FRICTION`, and `POLICY_CONFUSION`. Intervention types are `INSTALL_HELP`, `QUESTION_EXPLANATION`, `DATA_REPAIR`, `WORKFLOW_RECOVERY`, `CLI_WORKAROUND`, `SKILL_ROUTING_FIX`, `DOCUMENTATION_HELP`, `BUG_WORKAROUND`, and `OTHER`.

## Feedback and interpretation

Validate redacted feedback records against `AlphaFeedbackV1`. Feedback categories are contract-controlled; qualitative feedback never changes product policy automatically. Classify exit findings as `ALPHA_BLOCKER`, `MUST_FIX_BEFORE_BETA`, `SHOULD_FIX`, `BACKLOG`, or `USER_DATA_ONLY`.

Track bootstrap completion, onboarding completion, vertical-slice completion, operator interventions per participant, clarification count and depth, unresolved blockers, truth errors, unsupported claims, privacy violations, resume QA failures, requested factual/presentation corrections, and abandonment points. Report raw counts only; do not imply statistical significance.

## Privacy closure

After each run scan package, skill, fixtures, logs, and Git changes for participant facts. Verify the participant workspace is the only authorized data location and run cross-workspace isolation tests. Reports use anonymized participant labels and aggregate/redacted observations.
