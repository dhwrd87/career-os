# Interview evidence pack parity

Career OS 0.3.16 adds local-only, candidate-neutral interview preparation. It does not schedule interviews, send messages, contact employers, or submit applications.

`StoryBankV1` derives reusable factual story objects from approved evidence. Stories retain evidence IDs, verification, visibility, professional context, supported metrics, and prohibited inferences. They are not polished canonical answers. `InterviewAnswerBoundaryV1` defines what may be said, what must not be implied, safe bridge language, and when the candidate should answer that a detail is unknown or not yet experienced.

`InterviewEvidencePackV1` composes a qualified opportunity, `EmployerNeedTraceV1`, the current candidate profile, the current JD snapshot, interview stage, story selection, factual answer outlines, technical walkthroughs, follow-up probes, gap-safe notes, candidate questions, and a preparation checklist. The pack records hashes and IDs for the candidate profile, canonical revision, JD snapshot, qualification, employer-need trace, stories, and evidence. A changed profile, JD, or employer-need trace marks the derivative stale.

The eight gates are `STORY_EVIDENCE_TRACE`, `ANSWER_BOUNDARY`, `PROFESSIONAL_EQUIVALENCE`, `METRIC_SUPPORT`, `STORY_DUPLICATION`, `EMPLOYER_NEED_ALIGNMENT`, `GAP_DISCLOSURE`, and `PACK_FRESHNESS`. Human confirmation and all passing gates are required before a pack can become `ACCEPTED`.

Project, lab, simulation, coursework, and personal-project evidence always retain a non-professional boundary. Missing outcomes, metrics, tools, responsibility, or scale remain missing. The system supplies an honest response strategy rather than inventing a story.
