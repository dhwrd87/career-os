# Complete workspace workflows

Use the chosen workspace in every command: `careeros --workspace <path> ...`.
The engine performs these actions; do not recreate its decisions in conversation.

| Request | Executable path | Required input |
|---|---|---|
| Show my dashboard and profile | `workspace dashboard` | Initialized workspace; approved profile for career detail |
| Find suitable jobs | `workflow jobs --request <json>` | Supported live employer boards or reviewed current postings; follow human-workflows.md |
| Evaluate this job | `opportunity ingest --input <json>`, `qualify --opportunity-id <id>` | Source text, source URL, timestamp and requirements |
| Prioritize opportunities | `workflow opportunities` and `report` | Current qualifications and recorded events |
| Export an editable resume | `resume export-docx --build-id <id>` | Passing, current resume build; docx extra |
| Write a cover letter | `application cover-letter --opportunity-id <id> --build-id <id>` | Qualified job and current, validated resume |
| Prepare my application | `application prepare --opportunity-id <id> --build-id <id>` | Validated resume and fresh qualified opportunity; creates a self-contained PDF/DOCX package and stops at REVIEW_REQUIRED |
| Save reusable answers | `application answer-bank --input <json> --approve --actor <person>` | Exact questions, reviewed answers and explicit reuse scope |
| Track my applications | `application list` | Existing packets |
| Record activity or an outcome | `application record --application-id <id> --input <event.json>` | Human-confirmed activity with actor, event_type, occurred_at and human_confirmed=true |
| I already applied | Same record command with event_type SUBMITTED | Human reports actual prior action; engine verifies PDF and records immutable PDF/JD hashes. Never infer submission from packet generation |
| Plan a follow up | `application follow-up --application-id <id> --due-at <ISO8601> --channel EMAIL` | Application and due date; creates local draft only |
| Prepare for my interview | `interview --opportunity-id <id> --stage TECHNICAL` | Qualified job and packet; other stages listed in `interview --help` |
| Review my career progress | `report --window-start <UTC> --window-end <UTC>` | Actual recorded events; insufficient samples remain insufficient |
| Build a learning plan / compare courses | `learning --catalog <courses.json>` | Approved family, qualification gaps, verified current course facts supplied by user or research |
| Check generated production queue | `workspace queue-audit` | Rehashes artifacts and runs object-level PDF preflight |

To record activity, propose this JSON from the user's statement and confirm it is accurate:

```json
{"event_type":"INTERVIEW_INVITED","actor":"workspace-owner","occurred_at":"2026-11-20T15:00:00Z","human_confirmed":true,"notes":"Invitation received"}
```

Use facts supplied by this user. Do not reuse example dates or infer events. Corrections require supersedes_event_id and correction_state. Recording an event performs no external action.

A discovery catalog is a JSON list of the same opportunity objects accepted by `opportunity ingest`; see the bundled synthetic opportunity fixtures. The command reconciles historical identities, ingests new or materially updated records, qualifies them, and reports known roles separately. The package includes a bounded Greenhouse read-only adapter; see the discover-source workflow below. With a separately available research tool, gather source-grounded facts first, disclose source time and then supply the catalog. Never label an unverified role fresh.

A course catalog is a JSON list containing provider, course_id, title, url, skill_topics, curriculum_topics, last_verified_at, availability, level, cost_state, estimated_duration, project_work and credential_type. Unknowns must remain unknown. Current course pricing and availability require current verification. No training purchase or automatic credential/skill promotion is supported.

Finish by rebuilding `workspace dashboard` so generated reports, interview materials, application trackers and documents are linked from `outputs/index.html`. Direct the user to that file, the key artifact and any failed quality gate. DOCX semantic export is distinct from rendered layout approval; the accepted PDF remains the canonical application artifact.

Use `prioritize` for an evidence-fit ranking. Optional `--assumptions <json>` accepts per-opportunity interview_probability, offer_given_interview, career_value_points, effort_hours and time_cost_points_per_hour. These are explicitly user-assumed scenarios, not predictions. Unqualified jobs remain below qualified jobs regardless of assumed value; freshness and final QA still gate preparation. Never invent probabilities to populate the report.


For a known Greenhouse board, use `discover-source --greenhouse-board <token> --employer <verified-name> --limit 25 --approve-network` after the user's read-only source decision. The command stores a proposal containing retained descriptions. Review and extract required/preferred requirements from those descriptions, then mark requirement_review_status REVIEWED and pass the proposal to `discover --catalog`. This never submits, creates credentials or transmits the candidate profile. Other boards/providers require a separately verified adapter or catalog.

## Learning Path Intelligence

For gap analysis, live resource discovery, preferences, comparisons, roadmaps, training progress, artifact-backed profile proposals or post-learning eligibility, read [Learning Path Intelligence](learning-path-intelligence.md) and execute its CLI actions. Open the actual `outputs/learning/index.html`; refresh workspace home after changes.
