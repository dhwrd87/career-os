---
name: career-os
description: Operate Career OS through its installed package for private career setup, resume import and factual review, career paths, job evaluation, resumes and cover letters, application tracking, follow-up drafts, interview preparation, career progress and learning plans. Use when the user asks to set up or work in Career OS. It prepares local artifacts and records human-reported activity; it never submits applications or sends messages.
metadata:
  short-description: Your evidence-based career workspace
---

# Career OS

Use the installed package as the engine. Keep candidate information in the selected workspace, outside package and skill folders.

1. Resolve the intended workspace; ask only if the choice is ambiguous.
2. Run `python scripts/route.py --workspace <path> --request "<request>"` from this skill directory. If absent or incompatible, read [quickstart](references/quickstart.md). Require package compatibility SUPPORTED; stop only the dependent command on a typed failure.
3. For a new user, prefer an existing PDF, DOCX, Markdown or text resume. Use the [onboarding workflow](references/workflows.md) to extract a noncanonical proposal, show facts and uncertainties, capture corrections and obtain approval before committing candidate truth. With no source resume, use `scripts/bootstrap.py` and the package questionnaire to establish a profile. Never invent missing facts.
4. After approved setup, review career-path proposals with the user before approving a role family. Build a lane-base resume, run QA and obtain explicit acceptance before using it as a tailored-resume foundation.
5. For ongoing work, read only the matching row in [complete workflows](references/complete-workflows.md). Invoke the actual CLI commands, inspect their returned artifacts and QA, then run `careeros --workspace <path> workspace dashboard` to refresh the home page.
6. For learning, training completion, course comparisons, certifications, practical projects or eligibility after development, use [Learning Path Intelligence](references/learning-path-intelligence.md). Preserve resource types and require verified artifacts plus canonical approval before changing career truth.
7. Surface the useful document and concise result. Validation failure blocks acceptance; retain the failure and repair or request the missing fact. Read [troubleshooting](references/troubleshooting.md) for typed errors and migration recovery.

Never invent titles, dates, credentials, metrics, seniority or outcomes. Job requirements may prioritize evidence; they cannot become career facts. Keep project, coursework and professional contexts distinct. Canonical changes and migrations use package review/approval/commit workflows, never direct JSON edits. See [canonical updates](references/canonical-updates.md).

Use the bounded read-only Greenhouse adapter for a verified board, or consume a source-grounded catalog. Fetched descriptions require requirement review before ingestion; never qualify an empty extraction. The persistent opportunity registry must classify each result before calling it new. Do not fabricate provider availability, freshness or current course pricing.

Application preparation and cover letters stop at REVIEW_REQUIRED. Recording a submission or follow-up describes an action the user already performed; it does not perform it. Local follow-up drafts and interview packs do not send or schedule anything. Purchases, submissions, public-profile changes, outbound messages and commitments are not implemented. See [approval boundaries](references/approval-boundaries.md) when needed.

For evidence expansion, use the package resumable workflow. Course completion creates proposed evidence for review, not automatic competency or professional-experience credit. Keep factual constraints in internal traces; recruiter-facing copy must stay source-bound, clear and natural.

Other references: [artifact locations](references/artifact-map.md), [capabilities](references/capability-map.md).
