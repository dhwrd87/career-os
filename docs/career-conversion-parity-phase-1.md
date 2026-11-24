# Career conversion parity phase 1

Career OS 0.3.14 adds a candidate-neutral conversion-intelligence layer between job evidence matching and recruiter-facing acceptance. The layer is derivative-only: it does not mutate canonical facts, infer qualifications, or introduce claims.

## Contracts

- `EmployerNeedTraceV1` source-locates each material need in the retained JD, combines top-third placement with responsibility, qualification, mission, repetition, ownership, and outcome signals, and distinguishes a candidate evidence gap from a resume omission.
- `StrongestEvidenceOmissionV1` compares selected evidence with the strongest public-usable evidence for each important need. A materially stronger omission must have an explicit bounded rationale.
- `RoleFactSetV1` derives the minimum role identity, responsibility, outcome, tool, scope, leadership, stakeholder, verification, and visibility facts required for faithful compression.
- `MaterialEvidenceLossV1` classifies loss as `NON_MATERIAL`, `ACCEPTABLE_COMPRESSION`, `MATERIAL_LOSS`, or `CRITICAL_LOSS` and records the page-budget policy used to avoid overcompression.
- `CareerConversionTraceV1` aggregates need coverage, strongest-evidence decisions, role-fact retention, loss decisions, and the six production gates.

## Ordering and summary behavior

Targeted bullet priority now combines the existing evidence utility and storyline tiers with employer-need importance, top-third relevance, and protected role facts. Within a role or project, the strongest supported match is rendered first. Chronological experience ordering remains authoritative. Targeted summaries consult the employer-need trace, but every substantive clause retains evidence IDs or an approved configuration source.

## Acceptance gates

Targeted resume acceptance includes `EMPLOYER_NEED_TRACE`, `TOP_THIRD_COVERAGE`, `STRONGEST_EVIDENCE_OMISSION`, `ROLE_FACT_PRESERVATION`, `MATERIAL_EVIDENCE_LOSS`, and `CRITICAL_EVIDENCE_LOSS`. Lane and master outputs apply the role-fact and loss gates without manufacturing an employer trace when no JD exists. Any critical loss blocks acceptance; material loss above the calibrated threshold requires review.

## Document budget

The conversion layer removes redundancy first, compresses optional or lower-priority content next, and protects material evidence. The existing two-page production allowance is preferred to deleting critical evidence. Typography minima and ATS structure remain unchanged.

## Privacy boundary

The contracts and tests contain fictional records only. Private reference systems may be used as read-only acceptance sources, but the package has no private-vault dependency and contains no private candidate fixtures.
