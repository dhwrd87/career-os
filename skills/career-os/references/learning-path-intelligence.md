# Learning Path Intelligence

Use the existing V1 engine through `careeros --workspace <path> learning <action>`. Read returned gaps, exclusions, evidence plans and freshness; show the actual HTML/PDF roadmap from `outputs/learning/`. This is a first-class module, linked from workspace home even before a plan exists.

| User intent | Executable action |
|---|---|
| What should I learn? What am I missing? | `learning gaps`; review current role family and observed job sample |
| Set learning budget, time and subscriptions | `learning preferences --input <json>`; omit `--input` to inspect |
| Find current resources | After read-only network consent: `learning discover --source <https-index-or-course-url> --query <generic-capability> --approve-network --limit 3` |
| Compare resources / build a roadmap / choose projects | `learning build --catalog <verified-catalog.json>`; discovered catalog path is returned by discovery |
| I started / finished this course or project | `learning status`; then `learning progress --input <event.json>` |
| Review demonstrated learning for my profile | `learning propose-update --input <reviewed-claims.json>` |
| Did approved learning improve my role eligibility? | After the canonical update workflow: `learning reassess` |

Before recommendations, inspect and ask for material missing preferences: existing knowledge by capability, target roles, budget/currency, weekly hours and horizon, owned subscriptions, prerequisites and preferred learning formats. Save only user-supplied values. Preferences JSON accepts `budget`, `currency`, `weekly_hours`, `weeks_available`, `max_duration_hours`, `candidate_level`, `knowledge_levels`, `current_knowledge`, `subscriptions_owned`, `learning_styles`, `preferred_providers`, `self_paced_preference`, `credential_preference`, `satisfied_prerequisites`, `available_tools`, `project_hours`, `urgency`. Treat project hours as a planning estimate, not a source fact.

Read-only discovery uses public HTTPS sitemaps, course URLs and Course/LearningResource page metadata. Generic queries match locally; candidate profile data is not sent. Do not invent prices, duration, prerequisites, credentials or current curriculum when absent. Save any separately verified details with source references before ranking. Coursera, LinkedIn Learning and Udemy adapters accept supplied catalog snapshots; authenticated provider search is not implemented. Affiliate metadata never changes ranking. A subscription must explicitly cover the resource or matching plan; owning an account is insufficient.

Progress events have `step_id`, `state`, `actor`, optional `source`, `artifacts` (workspace-relative files) and `human_confirmed`. Enforce NOT_STARTED → IN_PROGRESS → COMPLETED → VERIFIED. Never backfill a transition or artifact without asking for the fact. VERIFIED requires human review and actual files. Completion changes no canonical skill, credential or employment record.

For promotion provide `step_id`, `actor`, reviewed `summary`, actual `actions`, optional `outcomes` and explicit `skill_claims` (`name`, bounded `proficiency`: AWARENESS/FOUNDATIONAL/PRACTICED). The command creates a changeset only. Show its preview and obtain canonical approval using [canonical updates](canonical-updates.md), then rebuild/reassess. An optional `credential` requires `kind`, `title`, `issuer`, `issued_date`, `award_confirmed` and the actual verified award artifact. COMPLETION_CERTIFICATE and INDUSTRY_CERTIFICATION are distinct; a preparation step cannot award an industry certification. Never infer professional experience or seniority from training.

Keep knowledge resources, courses, practical projects, certification preparation/attempts and real professional experience separate. Explain uncovered gaps and constrained-out options. A plan's projected coverage is a development hypothesis; current eligibility changes only after approved evidence and a fresh qualification run. Small observed job samples are not the entire market. ROI is descriptive, without salary or hiring guarantees.
