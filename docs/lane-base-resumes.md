# Governed lane-base resumes

`LaneBaseResumeV1` is the immutable, reusable default resume for one approved role family. It is built from `CareerProfileV1`, an approved `RoleFamilyV1`, a lane storyline, editorial policy, and presentation policy. It does not require or copy a job description.

## Lifecycle

```text
approved role family
→ careeros lane-base build
→ PDF + manifest + QA + REVIEW_REQUIRED
→ explicit human review
→ careeros lane-base accept
→ ACCEPTED
```

The executable commands are `careeros lane-base build`, `careeros lane-base accept`, and `careeros lane-base status`. Build is deterministic for the same governed inputs. Acceptance is explicit and only succeeds after all required QA gates pass.

An accepted base remains an immutable historical artifact. A canonical-profile, role-family, editorial-policy, or template change changes its effective status to `STALE_PROFILE_CHANGE`, `STALE_ROLE_FAMILY_CHANGE`, `STALE_POLICY_CHANGE`, or `STALE_TEMPLATE_CHANGE`. Rebuilding creates a successor; it does not rewrite the accepted artifact.

## Tailoring boundary

Job-specific resume compilation may use a current accepted lane base plus `JobDescriptionIntelligenceV1` and `JobEvidenceMatrixV1`. It may reorder, select, compress, expand, adapt the summary, reorder skills/projects, and use fact-preserving bullet variants. It cannot change canonical facts, introduce unsupported keywords, or exceed lane-level prohibited claims.

## Quality contract

A lane base must pass schema, truth, provenance, chronology/continuity, professional credibility, storyline completeness, evidence sufficiency, editorial quality, lane differentiation, unsupported-metric, ATS, autofill, page geometry, visual, underfill/overfill, filename/metadata, and lineage checks. Relevant evidence is prioritized rather than deleted; professional continuity and project breadth remain explicit completeness requirements.
