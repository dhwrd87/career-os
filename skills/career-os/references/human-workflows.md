# Find work and plan your next move

Use the commands below as the assistant's tools. The person should be able to ask in their own words; they do not need these command names or the package's internal terms.

## “Find jobs that fit me”

Read the approved profile, current career direction and preferences. Use the existing resume, skills, work examples, location, work arrangements and goals. Ask only for missing details that would change the search. Do not ask someone to supply a board token when you can identify a public employer source yourself.

Use available read-only web search to find actual employer postings, with generic job titles and broad location terms. Keep names, contact details, profile IDs and private career records out of external queries. Prefer the employer's own posting. A link or a search snippet alone is not enough to establish qualifications or current availability.

For a supported Greenhouse board, write a workspace-local request file and run:

```bash
careeros --workspace <path> workflow jobs --request <search-request.json> --approve-network
```

Request fields: `boards` (up to three `{board, employer}` objects), optional `titles`, `locations`, `work_modes` (`REMOTE`, `HYBRID`, `ONSITE`), `dream_roles`, `exclude_employers`, `prepare_top` (0–10, default 3), `selected_ids`, or a `catalog` path. Use the person's stated preferences; do not create goals for them. Board names and employer names must come from a verified public source.

The live reader saves current postings for requirement review. Read each full description, extract required versus preferred needs, and keep their wording or a source reference. Include experience, education, credentials, location, work permission and schedule rules, not just familiar skills. Mark unclear facts as unknown; ask the person only when their own history or preference is unclear. Set the returned proposal's `requirement_review_status` to `REVIEWED` only after this review, then call the same workflow with `catalog` pointing to it. Review is a necessary part of the search, not a reason to stop after fetching a file.

For other assistant/user-found postings, use the existing opportunity catalog format: employer, actual title, location, source URL, saved posting text, requirements, checked date and observed open/closed status. Preserve access restrictions. Do not describe an unverified posting as open. If no live source is available, say which sources were checked and offer to compare supplied postings.

The workflow deduplicates, compares, filters and ranks the jobs, then prepares up to three suitable resume drafts by default. `prepare_top: 0` shows results without preparing drafts. Read all source failures, skipped jobs and resume checks. Surface `outputs/job-search/index.html` and the actual PDF files. Report the scope of the search and do not imply that it covers every job board.

## “What else could I do?”

Run `workflow roles`. It uses the existing career engine with the person's history, stated goals and titles from checked postings. Explain the transferable skills and any gaps. Distinguish an idea to explore from an actual verified opening. If no useful market sample exists yet, find current postings before claiming a new role suits the person. Choosing a direction does not change their past titles or qualifications.

## “Make resumes for my top matches”

Run `workflow prepare --top <number>` or repeat `--opportunity-id <id>` for selected jobs. Resolve IDs from saved results privately; show role and employer names to the person. The same resume engine checks facts, evidence, layout, text extraction and current job details. Each job gets its own draft. An existing accepted base resume is reused where supported.

Only currently qualified, source-current jobs that fit the search can be prepared automatically. Review the returned held/failed items; do not bypass qualification or PDF checks. A Stretch Role with missing requirements gets a plan or a request for clarification, not an invented qualification. Link each draft with its employer and title and remind the person to review before applying. No application is sent.

## “Help me reach this stretch or dream role”

Use a saved, source-grounded posting that represents the target role. Find one if needed. Confirm the actual goal title when it is unknown. Add a title to `dream_roles` only when the person names it as a goal; Dream Roles are not automatically every job with a hard gap.

Run `workflow plan --opportunity-id <id> --catalog <current-learning-options.json>`. The learning catalog uses the existing Learning Path Intelligence reader/evaluation flow; see [learning](learning-path-intelligence.md). If no current course facts exist, omit `--catalog`: the engine can propose practical work and clearly identify missing training information without making up offers.

This scopes the plan to the chosen job, keeps other roles' gaps out, and saves a separate career-plan report and learning-plan PDF. Use the person's existing knowledge, budget, time and subscriptions. Review the proposed resources, original projects, actual credential requirements and experience-building steps. A short course does not replace a required degree, license or professional experience. State what remains open and avoid promises about hiring or salary.

Help the person choose a manageable first step. Keep completed work, record progress through `learning progress`, and review demonstrated skills or an actual award before using `learning propose-update`. Use the normal approval/commit process, then `learning reassess`. Training completion alone changes no career fact or qualification.

## Everyday replies

“Here are two openings where your experience fits the requirements we checked. I prepared a separate resume for each. This third role is a stretch because it asks for experience you have not yet shown. Its plan starts with a small project and explains what training could help.”

Use the actual counts, reasons and file links returned by the tools. Mention uncertainty plainly. A useful next step is more helpful than a report about the underlying system.
