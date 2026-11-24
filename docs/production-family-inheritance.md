# Production family inheritance

Career OS 0.3.18 resolves recruiter-facing resume behavior through one explicit chain:

`GLOBAL_PRODUCTION_STANDARD → MASTER → LANE / ROLE_FAMILY → TARGETED`

`ProductionFamilyV1` stores only local, rationale-backed overrides. `FamilyResolutionTraceV1` merges those settings and records every effective value as `GLOBAL_DEFAULT`, `PARENT_INHERITED`, `LOCAL_OVERRIDE`, or `JOB_ADAPTATION`. The trace is internal and must not be rendered into public documents.

Global truth, provenance, public sanitization, role-fact preservation, material-evidence-loss, professional-history, identity-header, and ATS requirements are protected. A child, job adaptation, or fallback cannot disable them. Job adaptations require a targeted family, a rationale, and source references.

The candidate-neutral registry includes a master and common lane defaults for project/operations, business analysis/process, implementation/business systems, technical support/IT operations, CRM/RevOps, security operations, network operations, vulnerability operations, cloud/infrastructure, and an other-generic family. These defaults contain no candidate facts.

`FallbackRoutingV1` makes failure handling explicit. A targeted family may fall back to its lane, a lane to master, and master to `ATS_STANDARD_SAFE_FALLBACK`; ATS failure routes directly to the safe terminal. Every fallback preserves core safety, records artifact impact and QA, and requires human authorization before production acceptance.

`ProductionFamilyPromotionV1` enforces `DRAFT → SHADOW → VALIDATED → PRODUCTION → RETIRED`. Validation and production require synthetic, ATS, visual, truth/provenance, and private-acceptance gates with no unresolved regression. Used versions are immutable; changes create a new version. Submitted artifacts retain the resolved family ID, version, and trace hash in immutable lineage.

Family freshness compares the validation baseline with current global, document, canonical-schema, summary, ATS, renderer, and role-family versions. A stale parent invalidates its child until revalidation.

`ProductionFamilyDeltaV1` compares rendered master-to-lane and lane-to-targeted content. Configuration intent alone is not a meaningful delta. The gate detects no meaningful delta, copy-only variation, excessive evidence removal, material loss, role-identity drift, and stale inheritance.
