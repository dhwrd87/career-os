# Capability map

The skill routes to Career OS package `>=0.4.1,<0.5.0`. It does not implement the engine.

| User capability | Package authority | Availability |
|---|---|---|
| Environment check | `careeros version`, `careeros doctor` | Supported |
| Workspace initialization | `careeros init` | Supported |
| PDF/DOCX/text/Markdown source ingestion | `careeros intake compile` / `careeros workflow setup` | Supported; source hash and locator provenance retained |
| LinkedIn/GitHub/portfolio enrichment | `careeros workflow setup --linked-sources` | Supported read-only after one explicit candidate decision; proposed records only |
| Career intake compilation | `careeros intake compile` | Supported; pre-filled and non-canonical |
| Consolidated FAST/DEEP completion | `careeros workflow setup` | Supported; 9 FAST / 11 DEEP default prompts |
| Exception-only clarification | package intake + onboarding clarification | Supported; maximum five intake exceptions before package truth queue |
| Progressive answer capture | Skill bootstrap helper + installed package questionnaire | Supported; workspace-local source drafts only |
| Proposal creation | `careeros onboarding ingest` | Supported |
| Clarification | `careeros clarification` | Supported |
| Canonical commit | `careeros onboarding commit` | Supported after explicit approval |
| Career profile | `careeros profile build` | Supported |
| Master recruiter resume | package initial-output workflow | Supported after approved canonical commit |
| Career lanes and role titles | package initial-output workflow | Supported as proposals requiring preference review |
| Governed lane-base resumes | `careeros lane-base build/accept/status` | Supported after approved role-family selection |
| Gap/development intelligence | package initial-output workflow | Supported; general, recurring-market, and job gaps remain distinct |
| Role family | `careeros role-family build` | Supported; approval represented by package |
| User-supplied opportunity | `careeros opportunity ingest` | Supported |
| Qualification | `careeros qualify` | Supported |
| Resume and QA | `careeros resume build/validate` | Supported |
| Application packet | `careeros application prepare` | Supported only through `REVIEW_REQUIRED` |
| State and integrity | `careeros status`, `careeros workspace verify` | Supported |
| Migration | `careeros migrate` | Plan then explicit approval then apply |
| Live discovery reconciliation | `OpportunityRegistryV1` and package discovery reconciliation | Supported when a read-only discovery adapter/operator is available; cross-run dedupe is mandatory before `NEW` |
| Submission/outreach/public edits/scheduling/negotiation | None | Not implemented |

The package owns source extraction, consent-gated linked enrichment, source hashing, provenance, prefill, evidence-depth assessment, question ranking, proposal, validation, clarification, commit, and governed lane-base lifecycle. The skill owns only conversation and routing.

Complete application, interview, follow-up, DOCX, learning and reporting commands are maintained in [complete-workflows.md](complete-workflows.md). Discovery supports a bounded read-only Greenhouse adapter and reviewed catalogs. Other providers and scheduled alerts remain unverified.

Learning is first-class: `learning gaps/preferences/discover/build/progress/propose-update/reassess/status`. See [Learning Path Intelligence](learning-path-intelligence.md) for constraints, verified evidence and award boundaries.
