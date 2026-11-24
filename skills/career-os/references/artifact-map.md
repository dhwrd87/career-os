# Artifact map

Prefer the artifact that answers the user's question. Paths must come from Career OS output or the selected workspace.

| Artifact | User value | Surface by default |
|---|---|---|
| `DOCTOR_REPORT` | Whether the environment is ready | Outcome plus failed/limited checks |
| `CLARIFICATION_QUEUE` | Facts that need a human answer | Required items first |
| `CAREER_PROFILE` | Compiled career truth | Completion state and profile hash; not the full record set |
| `PREFILLED_CAREER_INTAKE` | Source facts plus the smallest useful completion pass | Known facts, corrections requested, question count, and mode |
| `SOURCE_ENRICHMENT_MANIFEST` | Consent and provenance for linked career sources | Detected/approved URLs, captures, proposals, conflicts, and failures |
| `PROFILE_EVIDENCE_READINESS` | Whether evidence is sufficient for useful outputs | Ready/gaps state and highest-value enrichment next step |
| `MASTER_RECRUITER_RESUME` | Immediate recruiter-facing value after onboarding | Clickable local PDF and provenance-safe status |
| `CAREER_LANE_ANALYSIS` | Defensible current/bridge/development paths | Three to six options when evidence supports them; candidate review required |
| `ROLE_TITLE_UNIVERSE` | Searchable title families for proposed lanes | Candidate-friendly titles without canonical preference mutation |
| `LANE_BASE_RESUME` | Reusable governed default resume for one approved role family | Accepted PDF, QA, storyline, manifest, and staleness status |
| `CAREER_GAP_DEVELOPMENT` | Evidence, skill, experience, education, credential, and portfolio gaps | Smallest credible interventions; no automatic certification push |
| `ROLE_FAMILY` | Target-role strategy | Display name, approval state, major capability/gap themes |
| `QUALIFICATION_REPORT` | Honest job-fit view | Supported, transferable, bridgeable, hard gaps, unknowns |
| `RESUME_PDF` | Reviewable targeted resume | Clickable local artifact path |
| `RESUME_BUILD_REPORT` | Why evidence was selected or excluded | QA summary and warnings; details on request |
| `APPLICATION_PACKET` | Review-ready application materials | Contents, gate summary, `REVIEW_REQUIRED` state |
| `MIGRATION_PLAN` | Proposed workspace upgrade | Versions, affected files, backup, blockers |
| `CANONICAL_CHANGESET` | Proposed factual update | Delta, conflicts, impact, and approval state |
| `CANONICAL_HISTORY` | Durable update trail | Committed event and prior-value snapshot for the selected record |
| `DERIVATIVE_STATUS` | Reuse safety after a truth change | Stale profiles, decisions, resumes, and packets plus rebuild action |
| `PORTABLE_EXPORT` | Participant-owned workspace copy | Structured data, generated documents, and explicit source-document exclusion |

Never describe an artifact as accepted when a required gate failed. Do not expose raw source documents or sensitive logs unless the user specifically requests them and privacy policy permits it.
