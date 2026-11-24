# Canonical update workflow

Canonical truth changes follow: proposed change → conflict and impact analysis → clarification → commit preview → explicit approval → prepare/validate → lock/snapshot → apply → validate → chained audit event → derivative staleness → transaction commit → optional rebuild/review.

`CanonicalChangeSetV1` records each operation, typed target record, before/after value, source references, confidence, privacy and verification impact, expected record/collection/workspace hashes, conflicts, approval, and resulting commit event. Proposal and approval do not mutate canonical data. Commit rechecks optimistic-concurrency hashes, validates the complete resulting schema bundle, captures only affected transaction participants, and holds an exclusive workspace transaction lock.

The transaction includes affected canonical collection files, their history snapshots, the canonical event chain, the workspace canonical-head reference, derivative-staleness metadata, and the changeset. Any failure before the commit point restores every participant and verifies the prior canonical hash. An interrupted journal is recovered before the next commit attempt. Failures after the canonical commit point—including optional derivative rebuild failure—do not roll back canonical truth. Reapplying a committed changeset returns `ALREADY_COMMITTED` without adding records, events, snapshots, or staleness entries.

Every event links the previous and resulting canonical revision/hash, the immutable changeset hash, and the previous event hash. `careeros history` includes chain-verification status. History corrections create new events; prior events are never rewritten.

Existing profiles, decisions, builds, artifacts, and packets are never rewritten by staleness handling. The overlay marks them `STALE`, preserves their paths and identities, and forbids reuse. Submitted or accepted documents remain immutable historical artifacts. A later rebuild creates a new derivative.

Visibility values are ordered for restriction analysis: `PUBLIC`, `EMPLOYER_SAFE`, `INTERNAL`, `PRIVATE`, `RESTRICTED`. Employer-facing compilation excludes `PRIVATE` and `RESTRICTED`. Restriction changes commit even when later rendering fails; affected reusable derivatives are immediately stale and forbidden from reuse, while historical artifacts remain immutable.

Commands:

```text
careeros update propose --input <proposal.json>
careeros update resolve --changeset-id <id> --resolutions <resolutions.json>
careeros update preview --changeset-id <id>
careeros update approve --changeset-id <id> --actor <human>
careeros update commit --changeset-id <id> --actor <human>
careeros history [record-id]
careeros export --output <archive.zip>
careeros workspace reset-generated --confirm-workspace-id <id>
careeros workspace delete --archive-destination <path> --confirm-workspace-id <id> --confirm-phrase "DELETE WORKSPACE"
```

The delete command is deliberately recoverable: it moves the complete workspace to the specified archive destination rather than erasing files.
