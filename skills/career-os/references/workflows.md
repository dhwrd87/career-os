# Workflow routing

Commands below are package calls. Supply the selected workspace with `--workspace <path>` and use JSON outputs for machine interpretation where supported.

## Intent map

| Intent | Package workflow |
|---|---|
| `SET_ME_UP` | workflow setup start → detect links → one linked-source permission decision → authorized read-only enrichment → consolidated FAST/DEEP completion → exception clarification if any → commit preview → explicit approval → workflow setup approve → initial outputs |
| `IMPROVE_MY_CAREER_PROFILE` | readiness → lane/job-aware evidence expansion → changeset preview → explicit approval → update commit |
| `FIND_MY_CAREER_PATHS` | profile → lane analysis → role-title universe → one candidate preference review |
| `BUILD_LANE_BASE` | approved role family → lane storyline → governed base build → QA → review → explicit acceptance |
| `HELP_ME_GET_A_JOB` | profile/readiness → supplied-job intelligence → qualification → qualified resume/packet path |
| `LIVE_OPPORTUNITY_SEARCH` | persistent opportunity registry → current discovery → identity reconciliation → NEW-only shortlist → freshness/qualification → bounded packet preparation |
| `TAILOR_FOR_THIS_JOB` | supplied job → JD intelligence → qualification → adaptive resume → QA |
| `SHOW_MY_GAPS` | profile readiness → general/recurring/job-specific gap separation → smallest credible development actions |
| `WHAT_SHOULD_I_LEARN_NEXT` | verified gaps → gap priority → current provider discovery → course evaluation → smallest evidence-producing step |
| `BUILD_MY_LEARNING_PATH` | verified gaps → objectives → current provider discovery → minimal course/lab/project sequence → evidence plan → review |
| `COMPARE_COURSES` | current course details → freshness → four-value comparison → redundancy/level fit → ROI |
| `IMPROVE_MY_SOC_RESUME` | SOC recurring gaps → learning objective → minimal learning/evidence path → expected resume impact |
| `IMPROVE_MY_NOC_RESUME` | NOC recurring gaps → learning objective → minimal learning/evidence path → expected resume impact |
| `IMPROVE_MY_VULNERABILITY_RESUME` | vulnerability recurring gaps → learning objective → minimal learning/evidence path → expected resume impact |
| `WHAT_CERTIFICATIONS_ARE_WORTH_IT` | observed market requirements → credential classification → ROI → course/certification boundary |
| `I_FINISHED_THIS_COURSE` | verify completion/artifacts → proposed evidence packet → canonical review; no automatic skill promotion |
| `WHAT_PROJECT_SHOULD_I_BUILD` | priority gap → evidence-creation potential → bounded project and verification plan |
| `SHOW_MY_HIGHEST_ROI_GAPS` | recurring gaps → qualification impact → breadth/effort/evidence analysis |
| `INITIALIZE_CAREER_OS` | version → Doctor → init → Doctor → onboarding start |
| `CHECK_SYSTEM` | version → Doctor → workspace verify when initialized |
| `CONTINUE_ONBOARDING` | status → bootstrap progress/questions/save-section → assemble → onboarding ingest |
| `UPDATE_CAREER_INFORMATION` | update propose → conflict/impact review → preview → explicit approval → update approve → update commit → history |
| `REVIEW_CLARIFICATIONS` | clarification list → collect factual decisions → clarification resolve |
| `BUILD_PROFILE` | profile build |
| `CREATE_ROLE_FAMILY` | role-family build; represent human approval |
| `ADD_JOB_OPPORTUNITY` | opportunity ingest using user-supplied input |
| `QUALIFY_JOB` | qualify after profile, role family, opportunity, and JD snapshot exist |
| `BUILD_RESUME` | resume build after a qualified decision |
| `VALIDATE_RESUME` | resume validate; failed gates block acceptance |
| `PREPARE_APPLICATION_PACKET` | application prepare; stop at `REVIEW_REQUIRED` |
| `CHECK_APPLICATION_PACKET` | status plus packet readback |
| `SHOW_STATUS` | status; recommend one next action from persisted state |
| `MIGRATE_WORKSPACE` | migrate plan → approval → migrate apply → workspace verify |
| `TROUBLESHOOT` | Doctor plus typed-error remediation |

## State overrides

- `NOT_FOUND` or `UNINITIALIZED`: route mutating workflows to guided bootstrap.
- `ONBOARDING_IN_PROGRESS`: “continue” resumes the first incomplete bootstrap section.
- `CLARIFICATION_REQUIRED`: complete clarification before profile, role, job, resume, or packet workflows.
- `REVIEW_READY`: show a commit preview and request approval; do not commit yet.
- `MIGRATION_REQUIRED`: pause the requested workflow and plan migration.
- `INVALID_CONFIG`, `CORRUPT`, or `UNSUPPORTED_VERSION`: stop mutations and recover.
- `READY` plus user-supplied job: opportunity → qualification → optional qualified resume path.

## Guided bootstrap

For a supplied PDF, DOCX, Markdown, or text source, prefer the package-owned one-shot workflow:

```text
careeros workflow setup --start --source <path> --mode FAST
careeros workflow setup --linked-sources APPROVE             # only after candidate approval
# or: careeros workflow setup --linked-sources DECLINE
careeros workflow setup --complete --answers <workspace-answer-transport>
careeros workflow setup --resolve --resolutions <path>    # only if exceptions remain
careeros workflow setup --approve --actor <human>         # only after explicit approval
careeros workflow setup --status
```

The start step never fetches detected links. When links exist it returns `SOURCE_ENRICHMENT_APPROVAL_REQUIRED`; ask once for all listed sources. An approval permits read-only capture only. `SourceEnrichmentManifestV1` records URLs, capture hashes/timestamps, proposed records, conflicts, enriched evidence, and approval state. A failed source is visible and cannot be treated as evidence.

FAST uses the minimum high-value completion pass. DEEP adds reusable story/artifact discovery. Source extraction, linked enrichment, prefill, claim decomposition, evidence-depth assessment, question ranking, and post-commit outputs belong to the package. The skill translates ordinary user answers into the workspace-local answer transport; users do not edit it.

The older section helper remains a recovery path for source-free or interrupted legacy workspaces:

Use `scripts/bootstrap.py` from the skill directory:

```text
bootstrap.py --workspace <path> start
bootstrap.py --workspace <path> progress
bootstrap.py --workspace <path> questions --section <section-id>
bootstrap.py --workspace <path> save-section --section <section-id> --input <agent-created-json>
bootstrap.py --workspace <path> assemble --output <workspace-source-path>
```

Collect only the missing sections. The helper reads the package questionnaire and stores section drafts under the workspace `sources/` tree. It never writes canonical data.

After assembly, run onboarding ingest. If the result is `NEEDS_CLARIFICATION`, resolve the queue. If `REVIEW_READY`, present a record-count/source summary and ask for explicit approval before `onboarding commit`.

## Immediate onboarding outputs

After approval, surface the package output manifest as one coherent result: CareerProfileV1, ProfileEvidenceReadinessV1, Master Recruiter Resume, proposed career lanes, role-title universe, career gaps, and development priorities. Lane preferences remain proposals until the candidate approves them. Once a lane is approved, create an approved RoleFamilyV1, run `careeros lane-base build`, surface the QA result, and obtain explicit acceptance with `careeros lane-base accept`. If a job source was supplied, continue with job intelligence and qualification; do not manufacture a role preference from the JD.

## Lane-base lifecycle

Use a lane base as the candidate's stable truthful default story for one approved role family. It requires no JD and must pass truth, provenance, continuity, completeness, editorial, ATS, autofill, visual, metadata, and underfill/overfill gates. An accepted base is immutable; canonical profile, role-family, policy, or template changes mark it stale and require a successor build. Job-specific tailoring may adapt ordering, emphasis, summary, skills, projects, and fact-preserving bullet variants, but it may not exceed the base's prohibited claims.

## User-supplied job path

Capture only what the user provides. Preserve the original text in the workspace source used by `opportunity ingest`; missing fields remain missing. Explain qualification as supported matches, transferable evidence, bridgeable gaps, hard gaps, and unknowns. Only a qualified decision proceeds to resume build.

## Live opportunity discovery path

Before surfacing results, build the persistent registry across all historical run folders and current application state. Reconcile every discovery as `NEW`, `KNOWN_UNCHANGED`, `KNOWN_UPDATED`, `REPOST`, `SUPERSEDED`, `ALREADY_APPLIED`, `PREVIOUSLY_REJECTED`, `PREVIOUSLY_SKIPPED`, or `AMBIGUOUS_IDENTITY`. Only `NEW` contributes to `LIVE OPPORTUNITIES DISCOVERED`; unchanged known jobs contribute to `KNOWN OPPORTUNITIES RECONFIRMED`. Material updates require freshness and qualification review. Reposts remain distinct records linked through supersession. Never create a duplicate packet for an applied, rejected, skipped, or pending opportunity.

## Resume and packet path

Build → EmployerNeedTraceV1 → RecruiterConversionStrategyV2 → evidence-shaped summary and bullets → PublicCopyBoundaryV1 → RecruiterCopyQualityV2 → TargetedEditorialRegressionV1 → compose → validate → surface PDF and gate summary. The lane parent is the editorial floor; job targeting may change emphasis but may not reintroduce disclaimers, weak future tense, system language, or unsupported claims. On validation failure, stop acceptance and route remediation. On pass, prepare the packet and report `External submission: NOT PERFORMED`.

## Canonical update path

Translate the user's correction into a workspace-local proposed-change source document. Run `careeros update propose`, explain any competing value and downstream staleness, and ask only the clarification needed to resolve the conflict. Run `careeros update preview` and request explicit approval. Approval and commit are separate commands and use the same human actor. After commit, surface the history event and whether profile, role family, qualification, resume, or packet rebuild is required. Existing derivative files remain immutable.

## Status response

Read `careeros status`; do not reconstruct state from chat. Summarize workspace, onboarding/clarification, profile, role family, current qualification, resume validation, and packet state. Recommend one next action.
