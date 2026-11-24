# Source-first onboarding workflows

Career OS 0.3.10 provides a package-owned guided path for PDF, DOCX, Markdown, and plain-text career sources plus consent-gated LinkedIn, GitHub, and portfolio enrichment. Local source files remain inside the selected workspace. Each extraction records a SHA-256 hash, source reference, capture time, and page, paragraph, line, or linked-item locator. Extracted content is proposal material, never canonical truth.

Linked URLs are detected before the consolidated intake and are never fetched implicitly. The user approves or declines one read-only enrichment pass. `SourceEnrichmentManifestV1` records source type/location, approval, capture timestamp/hash, proposed records, conflicts, and enriched evidence blocks. GitHub/portfolio evidence remains project evidence; collaborative contribution and professional equivalence require explicit clarification.

For an approved GitHub profile, the package uses a bounded public API capture of at most ten owner repositories and inspects public root/README material for observable languages, activity, documentation, tests, and deployment/code links. No repository is attributed as the candidate's personal contribution without confirmation.

## Default journey

```text
UPLOAD SOURCES
→ AUTOMATIC EXTRACTION AND CLAIM DECOMPOSITION
→ PRE-FILLED CAREER INTAKE
→ ONE FAST OR DEEP COMPLETION PASS
→ EXCEPTION-ONLY CLARIFICATION
→ COMMIT PREVIEW
→ EXPLICIT HUMAN APPROVAL
→ CANONICAL PROFILE
→ INITIAL CAREER OUTPUTS
```

FAST asks nine consolidated candidate-facing prompts. DEEP adds two prompts for reusable story material and supporting artifacts. Both modes allow unknown answers and progressive later enrichment. Intake exceptions are capped at five; the ordinary schema/truth clarification queue remains authoritative when consequential conflicts survive completion.

## Safe inference boundary

Career OS may parse document structure, explicit dates, exact employer/title/institution/credential text, contact strings, and source-linked tool mentions. It may deduplicate exact source claims and decompose bullets into action, object, context, tool, result, metric, and stakeholder components.

Career OS does not infer responsibility level, skill proficiency, employment equivalence, credential completion, outcomes, metric validity, confidentiality, or permission for public use. Those require candidate confirmation or remain unknown.

## Package workflows

- `careeros intake compile --source <path> --mode FAST|DEEP` produces the pre-filled intake.
- `careeros intake complete --answers <path>` processes candidate-confirmed structured answers without committing them.
- `careeros intake preview` displays the candidate-review boundary.
- `careeros workflow setup --start|--complete|--resolve|--approve|--status` owns the complete source-first orchestration.

The user-facing skill translates ordinary conversation into workspace-local transports. A normal user does not edit JSON or run these commands.

After approved commit, the standard output manifest points to `CareerProfileV1`, `ProfileEvidenceReadinessV1`, the Master Recruiter Resume, proposed career lanes, the role-title universe, career gaps, and development priorities. Candidate lane preferences remain proposed until separately approved.

## Progressive enrichment

An initial profile may be useful before every historical record is rich. Later lane-aware, job-aware, outcome/metric, and interview-story expansion reuses canonical IDs and the changeset workflow; it does not repeat initial onboarding or mutate historical derivatives.
