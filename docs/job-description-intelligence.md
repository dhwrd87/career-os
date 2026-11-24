# Job Description Intelligence and Adaptive Tailoring

Career OS 0.3.7 converts each retained `JobDescriptionSnapshotV1` plus its structured opportunity requirements into `JobDescriptionIntelligenceV1`. Every extracted requirement retains the source snapshot, locator, and quoted source text. The extractor does not turn unstated employer preferences into requirements.

Adaptive selection treats job relevance as ordering and emphasis rather than a hard deletion rule. `ResumeCompletenessV1` independently checks evidence breadth, professional credibility, career continuity, project breadth, languages, and underfill before acceptance.

`JobEvidenceMatrixV1` is the governed bridge between qualification and resume production. Each material requirement records its classification, subtype, importance, candidate evidence IDs, coverage class, evidence context, allowed public claims, prohibited equivalence, resume priority, and gap action. `UNKNOWN` remains neutral and a hard gap is only inherited from qualification when a known candidate fact fails a mandatory requirement.

The adaptive compiler keeps the role-family storyline as its foundation, then uses source-grounded job signals and the evidence matrix to:

- rank evidence for the exact job;
- select non-redundant bullets;
- choose a fact-preserving bullet variant;
- adapt the summary and skills;
- order projects and sections;
- retain professional transferable evidence without claiming domain equivalence.

`JobTailoringTraceV1` is internal. It records signals, matched and omitted evidence, bullet variants, project order, coverage, duplicate suppression, and the truth-gate result. It is written into the resume-build state directory and is not rendered into the public resume.

Job-specific validation adds nine gates: important requirement coverage, unsupported keyword insertion, job-story coherence, lane-story coherence, project-order relevance, bullet relevance, summary relevance, hard-gap disguise, and transferable-evidence overreach. These supplement, and never replace, truth, provenance, qualification, metric, title, credential, ATS, visual, and artifact-lineage gates.

Synthetic regression data under `fixtures/synthetic/job-tailoring/` proves that one unchanged fictional profile produces materially different SIEM-heavy, vulnerability-heavy, overnight-monitoring, and NOC outputs. Private candidate calibration data is not packaged.
