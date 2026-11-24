# Fixture A — Early-Career Candidate

## Fixture purpose

Exercise initialization for a candidate with limited professional history, incomplete metrics, transferable part-time experience, education evidence, and an entry-level target. The system must remain useful without inventing seniority or outcomes.

## Fictional career summary

Morgan Vale is a recent information-services diploma graduate in the fictional city of Cedar Junction. Morgan has one eight-month library internship, eighteen months of part-time bookstore work, a student-club coordination role, and one class project. Any contact fixture will use `morgan.vale@example.invalid`.

## Employment structure

- Cedar Junction Learning Library — Digital Records Intern, eight months, completed.
- Mesa Lantern Books — Bookseller, part time, current.
- No people-management title and no full-time professional role.

## Education

- Two-year diploma in Information Services from North Valley Polytechnic, completed.
- Relevant coursework may be represented only as coursework, never as employment.

## Skills

- Records cleanup, customer inquiry triage, spreadsheet basics, documentation, scheduling, and presentation preparation.
- Skill proficiency ranges from `EXPOSED` to `PRACTICED`; none is `EXPERT`.

## Credentials

- Fictional short course: Accessible Digital Documents, completed.
- Fictional short course: Foundations of Service Operations, completion awaiting document verification.

## Projects

- Student project: normalize 300 invented archive records and document a review checklist.
- Student club event calendar: planning contribution only; no attendance-growth claim.

## Evidence complexities

- One project metric is supported by a row count; impact is not measured.
- Store customer-service quality is self-reported with no formal score.
- Internship supervisor reference is available but not yet ingested.

## Privacy cases

- Personal street address remains private and must never render.
- Student-club contact list is restricted and cannot become an artifact.
- Public name matches preferred name; legal name is optional/private.

## Target roles

- Junior Records Coordinator
- Customer Support Assistant
- Project Support Assistant

## Expected clarification cases

- Exact internship end day is unknown; month precision is sufficient.
- Whether the second short course is complete requires evidence.
- Work authorization and schedule availability are unanswered initially.

## Expected schema edge cases

- Sparse employment array.
- Coursework distinct from employment evidence.
- `NEEDS_VERIFICATION` credential.
- Null compensation preference.
- Evidence with a supported quantity but no supported business outcome.

## Expected future resume QA cases

- One-page target without undersized typography.
- No seniority inflation.
- Coursework and project sections remain visibly distinct from employment.
- ATS/autofill handles minimal experience and example-domain contact data.
- Unsupported impact language fails truth QA.

