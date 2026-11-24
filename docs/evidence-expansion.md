# Canonical Evidence Expansion V1

Career OS 0.3.7 separates source wording from canonical evidence depth:

```text
source documents
→ basic proposed records
→ EvidenceBlockV1 proposals
→ EvidenceDepthAssessmentV1
→ value-ranked clarification
→ human review and approval
→ onboarding promotion
→ explicit canonical commit
```

`EvidenceBlockV1` records what happened: context, need, responsibility level, actions, tools and methods, stakeholders, scope, scale, frequency, deliverables, outcomes, metrics, constraints, quality/risk, leadership, handoffs, demonstrated skills, artifacts, verification, visibility, and public-use policy. Unknown values stay unknown. Source wording is preserved separately and is never treated as polished resume authority.

## Progressive workflow

After ordinary onboarding has created proposed records:

```bash
careeros --workspace ./career-workspace evidence-expansion start
careeros --workspace ./career-workspace evidence-expansion status
careeros --workspace ./career-workspace evidence-expansion resolve --answers answers.json
careeros --workspace ./career-workspace evidence-expansion approve --actor human-user
careeros --workspace ./career-workspace evidence-expansion promote
careeros --workspace ./career-workspace onboarding commit --actor human-user
```

`start` and `resolve` write only workflow state. `approve` records explicit human approval. `promote` moves approved rich proposals back into the onboarding review bundle. Only the separate onboarding commit writes canonical user data.

Lane and job context may prioritize questions:

```bash
careeros --workspace ./career-workspace evidence-expansion start \
  --lane-context "network monitoring" \
  --job-context "ticket escalation"
```

The context affects question priority only. It is never copied into candidate facts.

## Metric reconstruction

Reconstructed metrics retain inputs, formula, sources, and `RECONSTRUCTABLE` state. They default to `public_use_allowed: false` until separately reviewed. Coursework, labs, simulations, projects, volunteer work, contracts, and employment remain distinct evidence contexts.

## Readiness

`ProfileEvidenceReadinessV1` returns one of:

- `PROFILE_READY`
- `PROFILE_READY_WITH_GAPS`
- `EVIDENCE_EXPANSION_RECOMMENDED`
- `CLARIFICATION_REQUIRED`

Thin older records do not automatically block resume work. Recent-role gaps, missing skill evidence, privacy, verification, and target-lane depth determine whether clarification is required.

