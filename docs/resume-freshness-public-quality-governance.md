# Resume freshness and public-quality governance

Career OS 0.3.11 treats every recruiter-facing resume as an acceptance-gated derivative of the current approved canonical state. These controls add no candidate facts and do not weaken truth, provenance, privacy, or qualification boundaries.

## Build-input freshness

`CanonicalEvidenceFreshnessV1` records the candidate profile ID, canonical revision and profile hash, evidence/skill/credential hashes, role-family and storyline versions, optional job-snapshot hash, compiler version, editorial-policy version, and build timestamp. Acceptance recomputes the contract against current state. Any canonical, evidence, skill, credential, role-family, policy, or job-snapshot mismatch blocks production acceptance. Historical reproduction may inspect a stale artifact only when explicitly selected; it does not make the artifact current.

## Evidence propagation and routing

`EvidenceUtilityV1` is a routing model, never a candidate score. It weighs completeness, verification, professional context, lane/job relevance, outcome and metric strength, recency, distinctiveness, public usability, space cost, and redundancy risk.

`NewEvidenceUtilizationV1` compares a prior approved profile with the current one. New or strengthened evidence, metrics, verification, visibility, skills/tools, outcomes, and corrected employment facts receive either `USED` or one explicit omission disposition. Relevant, public-usable, high-value evidence cannot disappear silently.

## Professional history

`ProfessionalHistorySufficiencyV1` classifies displayed work as `FULL`, `COMPACT`, or `MINIMAL`, and omitted work as `OMITTED` with a rationale. A displayed role must contain at least one supported fact. Substantial roles with transferable evidence cannot be omitted solely because they are outside the target domain; compression is the default career-transition treatment.

## Public composition

Internal artifact kinds remain metadata. Visible titles are candidate positioning, target role, or specialty. Public documents reject workflow labels and system-state phrases. Education groups current degree programs before older credentials and may omit a GED when accurate postsecondary education already carries recruiter value. Unverified high-value credentials remain unpublished and create the internal diagnostic `HIGH_VALUE_CREDENTIAL_VERIFICATION_PENDING`.

## Targeted adaptation

`TargetedResumeDeltaV1` compares summary, bullet selection/rendering, skill order, project order, professional emphasis, and section order. Targeted acceptance requires `SUFFICIENT_DELTA` or `MATERIAL_DELTA`. Bullet variants may change emphasis—monitoring, investigation, documentation, escalation, remediation, networking, customer, compliance, automation, or quality—while retaining source evidence IDs and factual boundaries.

## Acceptance gates

Recruiter-facing acceptance includes truth, provenance, canonical freshness, new-evidence utilization, professional-history sufficiency, empty-role failure, continuity, relevance, storyline, evidence and outcome strength, metric policy, recruiter specificity, public naming, system-artifact leakage, lane differentiation, targeted delta where applicable, completeness, unused evidence, ATS, reading order, autofill, font, geometry, visual QA, filename, metadata, and lineage.

The Master Recruiter Resume is a comprehensive public presentation and may use two pages when the supported history warrants it. Lane bases remain recruiter-usable public documents while their internal lifecycle metadata stays invisible.
