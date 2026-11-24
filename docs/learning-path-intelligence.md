# Learning Path Intelligence V1

Introduced in 0.3.20 and connected end-to-end in 0.4.1, Career OS converts verified career gaps into the smallest defensible sequence of learning and evidence-creation steps. Course availability never creates demand: `CareerGapPriorityV1` must trace each recommendation to candidate evidence, a role family, observed employer needs, qualification gaps, or approved career-capital priorities.

## Contracts and flow

`CareerGapPriorityV1` ranks observed gaps transparently. `LearningObjectiveV1` turns each selected gap into a bounded competency outcome. Current provider records normalize through `ProviderAdapterV1` into `CourseCandidateV1`; `CourseEvaluationV1` keeps learning value, credential signal, employer relevance, and evidence-creation value separate. `LearningROIV1` estimates descriptive career value without promising employment. `LearningPathV1` minimizes course count and may combine courses, labs, projects, portfolio artifacts, review, or certification steps. `EvidenceCreationPlanV1` defines what can be built and verified. `LearningPathImpactV1` records possible lane, resume, interview, and qualification effects without mutating canonical evidence.

## Provider boundary

The V1 scoring core has no provider scraper and no static canonical course ranking. A separate bounded public source reader retrieves HTTPS indexes and source pages. Adapters expose supported subsets of search, detail, curriculum, credential type, duration, cost, and freshness. Discovery queries must use generic skill language and must not send candidate PII. Coursera, LinkedIn Learning, and Udemy adapters normalize supplied catalog snapshots; authenticated searches against those providers are not implemented. All candidates use the same evaluation contract. Affiliate relationships never affect ranking.

Current production recommendations must store provider URL, catalog identifier, source references, verification time, curriculum snapshot, availability, duration, credential type, and time-sensitive cost state. `CourseFreshnessV1` blocks stale, removed, replaced, or unknown candidates from ranking until reverified.

## Ranking and safety

Gap priority considers recurrence, job frequency, requirement importance, top employer needs, hard-gap frequency, current evidence weakness, candidate proximity, lane breadth, urgency, effort, and evidence-creation potential. One fashionable or isolated preferred requirement cannot become high priority on availability alone.

Course evaluation reports seventeen dimensions and the four-value model before any routing score. It checks redundancy against canonical skills, evidence, projects, coursework, credentials, and learning history. Candidate-level and prerequisite mismatches fail closed. A completion certificate is not an industry certification.

The optimizer penalizes course hoarding, redundant certificates, duplicate introductions, excessive time, and excessive cost. It prefers course → lab/project → inspectable artifact when that is the shortest evidence-producing path.

## Learn → prove → review

Every selected step answers what will be learned, what can be built, what Career OS can verify, what evidence may be proposed, and what gap may improve. Completion creates a review packet only. It never changes canonical skills, credentials, qualification, resume claims, or public portfolio state automatically.

Mandatory professional experience remains unsatisfied unless the employer explicitly permits equivalent education or projects. Learning can improve readiness and adjacent evidence but cannot manufacture professional context.

## User preferences

Owned subscriptions, budget, weekly time, learning style, provider preference, credential preference, self-paced preference, and urgency may break ties or constrain options. They cannot waive prerequisites, freshness, qualification boundaries, privacy, or evidence review.

## Conversational routes

The skill recognizes `WHAT_SHOULD_I_LEARN_NEXT`, `BUILD_MY_LEARNING_PATH`, `COMPARE_COURSES`, `IMPROVE_MY_SOC_RESUME`, `IMPROVE_MY_NOC_RESUME`, `IMPROVE_MY_VULNERABILITY_RESUME`, `WHAT_CERTIFICATIONS_ARE_WORTH_IT`, `I_FINISHED_THIS_COURSE`, `WHAT_PROJECT_SHOULD_I_BUILD`, and `SHOW_MY_HIGHEST_ROI_GAPS`. These routes prepare local analysis or evidence proposals only; they do not purchase courses, contact providers, publish artifacts, or modify canonical truth.

## Executable workspace flow (0.4.1)

```bash
careeros --workspace <path> learning gaps
careeros --workspace <path> learning preferences --input <preferences.json>
careeros --workspace <path> learning discover --source https://ocw.mit.edu/sitemap.xml --query python --approve-network --limit 1
careeros --workspace <path> learning build --catalog <returned-catalog-path>
careeros --workspace <path> learning status
careeros --workspace <path> learning progress --input <progress-event.json>
careeros --workspace <path> learning propose-update --input <reviewed-artifact-claims.json>
# Review/approve/commit the returned changeset through the normal update flow.
careeros --workspace <path> learning reassess
careeros --workspace <path> workspace dashboard
```

The reader stores the actual URL, body hash and retrieval time, preserves unknown price/duration/level and does not infer a certification. Current retrieval does not prove current curriculum. Under strict constraints, unknown level/cost/time cannot become an eligible recommendation. Verify missing facts with source references before building a recommendation. HTTP redirects, private hosts and oversized responses fail closed. Provider availability is not promised.

The roadmap is in `outputs/learning/index.html`, `learning-roadmap.md` and `learning-roadmap.pdf`; state, progress events, immutable run snapshots and proposals live under `state/learning/`. The synthetic fixtures in `fixtures/synthetic/learning/` are examples, not real course offers. The synthetic workspace includes a verified original project and a pending canonical changeset; its old submitted resume remains historical.

Preferences and JSON payload details are in the skill's [learning workflow reference](../skills/career-os/references/learning-path-intelligence.md). Fresh paid prices are required within 30 days and in the selected currency. Subscription coverage requires explicit plan membership. Aggregate education cost/time and estimated project hours are constrained; unpriced project materials remain a disclosed expense to verify. No automatic currency conversion occurs. A greedy minimal path reuses resources across objectives; it is not a claim of a globally optimal mathematical schedule.

Live verification: a read-only retrieval from [MIT OpenCourseWare](https://ocw.mit.edu/sitemap.xml) returned a real Python learning resource using two GET requests, zero candidate data and no commercial adjustment. This validates the public reader, not authenticated course search or the current suitability of every historical OCW syllabus. [Course metadata](https://schema.org/Course) is used when actually present. See [subsystem reconciliation](learning-parity.md) and the release validation record.

Saved plans are checked against the current clock as well as current profile/preferences. Expired selected-resource or strict-budget price facts require reverification and rebuilding. Historical completion evidence remains separately reviewable.
