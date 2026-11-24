# Cross-run opportunity deduplication

Career OS 0.3.22 treats opportunity identity as persistent candidate-workspace state. A live-search run must rebuild or load `OpportunityRegistryV1` across all historical run folders before it can label a posting `NEW`.

## Identity signals

Reconciliation uses, in descending confidence order:

1. explicit supersession or repost lineage;
2. provider/source job identifier;
3. normalized canonical URL;
4. employer, title, and exact JD hash across syndicated sources;
5. employer/title/location plus JD similarity;
6. ambiguous employer/title matches, which fail closed for human identity review.

A matching provider ID is only trusted across source namespaces when employer and title also agree. Tracking parameters and terminal `/apply` paths do not create a new identity.

## Result classes

Every discovered posting is classified before presentation:

- `NEW`
- `KNOWN_UNCHANGED`
- `KNOWN_UPDATED`
- `REPOST`
- `SUPERSEDED`
- `ALREADY_APPLIED`
- `PREVIOUSLY_REJECTED`
- `PREVIOUSLY_SKIPPED`
- `AMBIGUOUS_IDENTITY`

Only `NEW` contributes to the live-opportunity-discovered count. `KNOWN_UNCHANGED` and `KNOWN_UPDATED` are reported as reconfirmed known opportunities. A known record with an unsubmitted packet is surfaced as `KNOWN — APPLICATION PENDING` and cannot create another packet.

## Updates and reposts

An identity match with an unchanged JD hash is unchanged unless relevant metadata changed. Highly similar text changes are `MINOR_UPDATE`; materially changed text is `MATERIAL_UPDATE`. Material updates trigger freshness and requalification logic without presenting the role as unseen.

A repost is a separate opportunity record. It links to the historical record through `supersedes` and `repost_group_id`; the old record is retained.

## Historical retention

The registry is a derived index. Source opportunity records, snapshots, qualifications, application events, packets, and closed records remain immutable historical state. Rebuilding the index never deletes them.

## Packet suppression

Submitted, active, rejected, withdrawn/skipped, and pending-packet states suppress duplicate packet creation. Reposts may receive a new packet only after current freshness, qualification, and identity checks pass.
