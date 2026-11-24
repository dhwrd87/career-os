# Opportunity freshness and application state

Career OS 0.3.15 adds a candidate-neutral, local-only opportunity and application-state layer. It does not discover jobs, submit applications, send follow-ups, schedule interviews, or call external systems.

## OpportunityFreshnessV1

`OpportunityFreshnessV1` separates posting age from posting status. A recent, explicit source verification may produce `FRESH`; an old verification produces `STALE_REVERIFY`, never inferred closure. Explicit source evidence is required for `CLOSED`, `EXPIRED`, `REPOSTED`, or `SUPERSEDED`. Conflicting or absent verification produces `UNKNOWN` and fails closed.

The versioned `opportunity-freshness-v1` policy considers source type, captured and verified timestamps, explicit expiration/closure signals, source availability, repost/supersession evidence, and conflicts. Synthetic fixtures are current only inside deterministic fixture workflows.

Application packet preparation requires `FRESH`. A non-fresh state may proceed only through a separately supplied, human-confirmed override with actor and rationale. No override is inferred from qualification or resume acceptance.

## Opportunity identity and reposts

Identity comparison uses provider job ID, normalized canonical URL, normalized employer/title/location, JD similarity, timestamps when supplied, and explicit repost evidence. Results are `SAME_POSTING`, `REPOST`, `NEW_ROLE`, or `AMBIGUOUS`.

Only `SAME_POSTING` is automatically mergeable. `REPOST` creates a distinct opportunity linked by `supersedes` and `repost_group_id`. `AMBIGUOUS` requires human review. Existing applications remain bound to their original posting.

## ApplicationEventV1 and ApplicationStateV1

Application events are append-only JSON Lines records. `ApplicationStateV1` is rebuilt from the ordered event stream and is never treated as independent narrative truth. Every event records its previous and resulting state, actor, source, provenance/artifact references, confirmation state, and any correction target.

Corrections append a `CORRECTION` event and identify the superseded event; they do not alter history. A correction requires human confirmation.

## Submission lineage and immutability

A `SUBMITTED` event requires human confirmation and freezes:

- resume artifact ID and SHA-256;
- cover-letter hash when present;
- application-answer hashes when present;
- job/JD snapshot hash;
- submission time;
- external reference when known.

Later resume builds are independent artifacts and cannot replace the submitted lineage. Missing submission hashes, unknown external submission state, duplicate event IDs, or event-state contradictions fail the acceptance gates.

## Outcomes, follow-up, and interviews

Canonical outcomes are `UNKNOWN`, `ACTIVE`, `REJECTED`, `WITHDRAWN`, `OFFER_RECEIVED`, `OFFER_ACCEPTED`, `OFFER_DECLINED`, `HIRED`, `ROLE_CLOSED`, and `NO_RESPONSE_CLOSED`. Interview stages remain events rather than terminal outcomes.

`FollowUpV1` and `InterviewV1` are planning/state contracts only. Their defaults require human review. No sender, scheduler, email, calendar, or application adapter is enabled by this phase.

## Reconciliation and legacy migration

`ApplicationStateReconciliationV1` compares the event projection with the opportunity index, legacy run-folder state, outcome registry, and artifact manifests. It reports `CONSISTENT`, `RECONCILIATION_REQUIRED`, `LEGACY_ONLY`, or `EVENT_LOG_AUTHORITATIVE` and never silently resolves a contradiction.

Legacy migration generates provenance-marked `MIGRATED_LEGACY_STATE` seed events without deleting or rewriting legacy registries. Unknown historical timestamps remain null. Legacy submitted state without complete artifact and JD hashes remains `RECONCILIATION_REQUIRED`.

## QA gates

Application acceptance composes eight gates with existing truth, qualification, resume, and artifact gates:

- `OPPORTUNITY_FRESHNESS`;
- `OPPORTUNITY_IDENTITY`;
- `REPOST_RESOLUTION`;
- `APPLICATION_EVENT_INTEGRITY`;
- `SUBMISSION_ARTIFACT_HASH`;
- `STATE_RECONCILIATION`;
- `OUTCOME_CONSISTENCY`;
- `IMMUTABILITY`.

The package contains fictional synthetic fixtures only. Private reference and participant acceptance remain read-only and outside package dependencies.
