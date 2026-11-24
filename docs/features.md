# Feature inventory

| Area | Implemented behavior | Main interface |
|---|---|---|
| Career truth | Candidate, employment, skills, credentials, education, project and evidence records; consent, visibility, provenance, clarification | `onboarding`, `profile`, `update`, `history` |
| Source intake | PDF, DOCX, text and Markdown extraction; FAST/DEEP intake; resumable evidence expansion; optional consented linked-source capture | `workflow setup`, `intake`, `evidence-expansion` |
| Career pathways | Capability-based lanes, title proposals, preferences, role-family approval and production-family inheritance | Initial outputs, `role-family` |
| Job intelligence | Retained JD snapshot, requirement semantics, employer needs, evidence mapping and qualification | `opportunity`, `qualify` |
| Discovery | Bounded read-only Greenhouse discovery, reviewed catalogs, cross-run identity, freshness and qualification | `discover-source`, `discover` |
| Resumes | Master, lane-base lifecycle and job tailoring; chronology, public-use and material-evidence-loss controls | `lane-base`, `resume` |
| Presentation | Premium centered masthead; single-column US Letter PDF; selectable text, links, independent extraction, geometry/density and object preflight | `resume validate`, `workspace queue-audit` |
| Editable output | Same semantic content in DOCX; content readback; external renderer required for layout approval | `resume export-docx` |
| Applications | Review packet, PDF/JD hashes, repeat-safe preparation, evidence-linked cover-letter Markdown/PDF | `application prepare`, `application cover-letter` |
| Pipeline | Append-only human-reported events, corrections, outcomes and immutable submission lineage | `application list`, `application record` |
| Follow-up | Dated local planning and review-only drafts | `application follow-up` |
| Interview | Evidence-linked story bank, question themes, answer boundaries, technical probes, checklist and report | `interview` |
| Career intelligence | Cohorts, descriptive conversion, confounding and sample maturity, recurring gaps, career-capital and observed-market signals | `report` |
| Learning Path Intelligence | Typed market-driven gaps; preferences; live public resource discovery; provider-neutral freshness/redundancy/four-value evaluation; aggregate budget/time/subscription-aware roadmap; original projects; completion journal; verified evidence/award proposals and role reassessment | `learning gaps/preferences/discover/build/progress/propose-update/reassess/status` |
| Workspace experience | HTML/Markdown home, career profile, opportunity/application tracker and artifact links | `workspace dashboard` |
| Portability | Relative roots, package doctor, backup-first migrations, canonical transaction recovery, export and isolation tests | `doctor`, `migrate`, `workspace verify`, `export` |

No external action is implied by any of these commands. Research catalogs and activity records must come from the user or a separately available read-only research source. Broad labor-market coverage, authenticated provider APIs and verified AI-host integrations beyond the tested router are not claimed.
