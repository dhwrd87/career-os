# Canonical updates

Use package state, not chat memory, to identify the record. A user's statement creates a proposal, not an immediate edit.

1. Write the smallest proposed-change JSON under the selected workspace `sources/` directory.
2. Run `careeros update propose --input <path>`.
3. If conflicts exist, show the competing canonical and proposed values without choosing. Resolve them through `careeros update resolve`.
4. Run `careeros update preview --changeset-id <id>` and summarize record changes, privacy effects, and stale derivatives.
5. Obtain explicit human approval.
6. Run `careeros update approve`, then `careeros update commit`, using the same human actor.
7. Run `careeros history <record-id>` and report the resulting rebuild/review requirement.

Visibility becoming more restrictive blocks reuse of affected derivatives. Historical and submitted artifacts remain immutable. Rebuilds create new derivatives; they never rewrite old ones.

`careeros export --output <zip>` excludes source documents by default. `careeros workspace reset-generated` requires the exact workspace ID and archives generated state before reset. `careeros workspace delete` requires the exact ID plus `DELETE WORKSPACE` and moves the workspace to a recoverable archive destination.
