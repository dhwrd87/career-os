# Functional parity reconciliation

The historical 110-capability assessment is reconciled to actual 0.4.1 implementation. `RECONCILED_GENERIC` means the portable behavior now has an executable public implementation and linked regression coverage; it does not claim byte-for-byte replication. Public advantages are preserved. Candidate-specific references and legacy monolithic behavior are not imported.

Counts: PUBLIC_ADVANTAGE: 37, EQUIVALENT: 26, RECONCILED_GENERIC: 31, REGRESSION_REPAIRED: 3, INTENTIONAL_DIFFERENCE: 5, PERSONAL_CONFIG_ONLY: 5, NOT_PORTED_LEGACY: 3.

The full source/persona/clean-install results are in [release readiness](release-readiness.md). Other provider connectors, arbitrary font themes, external action adapters and certified accessible PDFs are outside the shipped candidate; see the exact limitations there.

| ID | Capability | Current assessment | Implementation and verification | Notes |
|---|---|---|---|---|
| 1 | Canonical truth separation | PUBLIC_ADVANTAGE | `profile.py`; `test_phase2_contracts.py` | Retained generic implementation and regression coverage. |
| 2 | Canonical revisions | PUBLIC_ADVANTAGE | `updates.py`; `test_phase5b_transactions.py` | Revisioned canonical truth, recovery, staleness and immutable derivative checks. |
| 3 | Transactional changesets | PUBLIC_ADVANTAGE | `updates.py`; `test_phase5b_transactions.py` | Revisioned canonical truth, recovery, staleness and immutable derivative checks. |
| 4 | End-to-end provenance | EQUIVALENT | `profile.py`; `test_phase2_contracts.py` | Retained generic implementation and regression coverage. |
| 5 | Evidence atomization | PUBLIC_ADVANTAGE | `profile.py`; `test_phase2_contracts.py` | Retained generic implementation and regression coverage. |
| 6 | Public/private evidence boundary | EQUIVALENT | `profile.py`; `test_phase2_contracts.py` | Retained generic implementation and regression coverage. |
| 7 | Immutable historical derivatives | PUBLIC_ADVANTAGE | `updates.py`; `test_phase5b_transactions.py` | Revisioned canonical truth, recovery, staleness and immutable derivative checks. |
| 8 | Consented source enrichment | PUBLIC_ADVANTAGE | `workflows.py`; `test_onboarding_portable_workflows.py` | Source-first approval flow plus eight source-first synthetic personas. |
| 9 | Source-first onboarding | PUBLIC_ADVANTAGE | `workflows.py`; `test_onboarding_portable_workflows.py` | Source-first approval flow plus eight source-first synthetic personas. |
| 10 | Question-value optimization | PUBLIC_ADVANTAGE | `workflows.py`; `test_onboarding_portable_workflows.py` | Source-first approval flow plus eight source-first synthetic personas. |
| 11 | Clean-room setup | PUBLIC_ADVANTAGE | `workflows.py`; `test_onboarding_portable_workflows.py` | Source-first approval flow plus eight source-first synthetic personas. |
| 12 | Workspace migrations | PUBLIC_ADVANTAGE | `workflows.py`; `test_onboarding_portable_workflows.py` | Source-first approval flow plus eight source-first synthetic personas. |
| 13 | Doctor/compatibility | PUBLIC_ADVANTAGE | `workflows.py`; `test_onboarding_portable_workflows.py` | Source-first approval flow plus eight source-first synthetic personas. |
| 14 | Thin skill routing | PUBLIC_ADVANTAGE | `workflows.py`; `test_onboarding_portable_workflows.py` | Source-first approval flow plus eight source-first synthetic personas. |
| 15 | Role-family configuration | EQUIVALENT | `production_family.py`; `test_production_family_inheritance.py` | Explicit family inheritance and protected policies; lane acceptance remains separate. |
| 16 | Lane discovery | EQUIVALENT | `production_family.py`; `test_production_family_inheritance.py` | Explicit family inheritance and protected policies; lane acceptance remains separate. |
| 17 | Accepted lane lifecycle | PUBLIC_ADVANTAGE | `production_family.py`; `test_production_family_inheritance.py` | Explicit family inheritance and protected policies; lane acceptance remains separate. |
| 18 | Production-family inheritance | RECONCILED_GENERIC | `production_family.py`; `test_production_family_inheritance.py` | Explicit family inheritance and protected policies; lane acceptance remains separate. |
| 19 | Deterministic fallback routing | RECONCILED_GENERIC | `production_family.py`; `test_production_family_inheritance.py` | Explicit family inheritance and protected policies; lane acceptance remains separate. |
| 20 | Project inclusion decision | RECONCILED_GENERIC | `production_family.py`; `test_production_family_inheritance.py` | Explicit family inheritance and protected policies; lane acceptance remains separate. |
| 21 | JD requirement extraction | EQUIVALENT | `job_intelligence.py`; `test_job_description_intelligence.py` | Retained requirements, source locators, evidence matching, qualifications and adaptive tailoring. |
| 22 | Required vs preferred requirements | EQUIVALENT | `job_intelligence.py`; `test_job_description_intelligence.py` | Retained requirements, source locators, evidence matching, qualifications and adaptive tailoring. |
| 23 | JD false-positive suppression | RECONCILED_GENERIC | `job_intelligence.py`; `test_job_description_intelligence.py` | Retained requirements, source locators, evidence matching, qualifications and adaptive tailoring. |
| 24 | Employer-need inference and trace | REGRESSION_REPAIRED | `career_conversion.py`; `test_career_conversion_parity.py` | Employer needs, role fact sets, omission accounting and material-loss gates. |
| 25 | Job evidence matrix | PUBLIC_ADVANTAGE | `job_intelligence.py`; `test_job_description_intelligence.py` | Retained requirements, source locators, evidence matching, qualifications and adaptive tailoring. |
| 26 | Truthful fit/qualification | EQUIVALENT | `job_intelligence.py`; `test_job_description_intelligence.py` | Retained requirements, source locators, evidence matching, qualifications and adaptive tailoring. |
| 27 | Targeted resume delta | PUBLIC_ADVANTAGE | `job_intelligence.py`; `test_job_description_intelligence.py` | Retained requirements, source locators, evidence matching, qualifications and adaptive tailoring. |
| 28 | Application expected value | RECONCILED_GENERIC | `prioritization.py`; `test_prioritization.py` | Evidence-fit ranking and explicit user-assumed value scenarios; no invented hiring probabilities. |
| 29 | Job discovery freshness | RECONCILED_GENERIC | `job_intelligence.py`; `test_job_description_intelligence.py` | Retained requirements, source locators, evidence matching, qualifications and adaptive tailoring. |
| 30 | Evidence utility scoring | PUBLIC_ADVANTAGE | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 31 | Bullet construction | EQUIVALENT | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 32 | Fact-preserving bullet variants | EQUIVALENT | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 33 | Outcome/metric rendering | EQUIVALENT | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 34 | Semantic deduplication | EQUIVALENT | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 35 | Role fact-set preservation | REGRESSION_REPAIRED | `career_conversion.py`; `test_career_conversion_parity.py` | Employer needs, role fact sets, omission accounting and material-loss gates. |
| 36 | Material-evidence-loss gate | REGRESSION_REPAIRED | `career_conversion.py`; `test_career_conversion_parity.py` | Employer needs, role fact sets, omission accounting and material-loss gates. |
| 37 | Commercial/responsibility truth | RECONCILED_GENERIC | `career_conversion.py`; `test_career_conversion_parity.py` | Employer needs, role fact sets, omission accounting and material-loss gates. |
| 38 | Professional-history sufficiency | PUBLIC_ADVANTAGE | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 39 | Long-running role protection | PUBLIC_ADVANTAGE | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 40 | Multiple roles, overlaps, precision | RECONCILED_GENERIC | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 41 | Public title normalization | EQUIVALENT | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 42 | Reverse chronology | EQUIVALENT | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 43 | Skill-evidence linkage | PUBLIC_ADVANTAGE | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 44 | Skill aliases and lane/JD routing | RECONCILED_GENERIC | `job_intelligence.py`; `test_job_description_intelligence.py` | Retained requirements, source locators, evidence matching, qualifications and adaptive tailoring. |
| 45 | Credential verification/routing | EQUIVALENT | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 46 | Education composition | PUBLIC_ADVANTAGE | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 47 | Comprehensive master resume | PUBLIC_ADVANTAGE | `editorial.py`; `test_resume_editorial_intelligence.py` | Source-bound evidence, history retention, visibility and claim controls; overlap persona included. |
| 48 | Public-quality lane base | PUBLIC_ADVANTAGE | `production_family.py`; `test_production_family_inheritance.py` | Explicit family inheritance and protected policies; lane acceptance remains separate. |
| 49 | Job-targeted resume | EQUIVALENT | `job_intelligence.py`; `test_job_description_intelligence.py` | Retained requirements, source locators, evidence matching, qualifications and adaptive tailoring. |
| 50 | Content routing by production family | RECONCILED_GENERIC | `production_family.py`; `test_production_family_inheritance.py` | Explicit family inheritance and protected policies; lane acceptance remains separate. |
| 51 | Clause-level summary trace | PUBLIC_ADVANTAGE | `recruiter_conversion.py`; `test_recruiter_conversion_copy_engine_v2.py` | Traced clauses, source-sentence repair, deduplicated outcomes and readable role/employer bridge. |
| 52 | Summary naturalness | EQUIVALENT | `recruiter_conversion.py`; `test_recruiter_conversion_copy_engine_v2.py` | Traced clauses, source-sentence repair, deduplicated outcomes and readable role/employer bridge. |
| 53 | Employer-need/top-third summary | RECONCILED_GENERIC | `career_conversion.py`; `test_career_conversion_parity.py` | Employer needs, role fact sets, omission accounting and material-loss gates. |
| 54 | Cross-resume formula repetition | RECONCILED_GENERIC | `recruiter_conversion.py`; `test_recruiter_conversion_copy_engine_v2.py` | Per-document formula checks, repeated-sentence suppression and cross-target sentence-frame review in the production queue; factual skills remain distinct. |
| 55 | ATS-safe header contract | PUBLIC_ADVANTAGE | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 56 | Header visual hierarchy | EQUIVALENT | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 57 | Long contact/international variants | PUBLIC_ADVANTAGE | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 58 | Public naming sanitization | PUBLIC_ADVANTAGE | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 59 | ATS section contract/order | PUBLIC_ADVANTAGE | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 60 | Single-column default | INTENTIONAL_DIFFERENCE | `resume.py`; `test_header_summary_ats.py` | One premium single-column production template. Compact renderer is not shipped; no silent template fallback. |
| 61 | Compact two-column default | INTENTIONAL_DIFFERENCE | `resume.py`; `test_header_summary_ats.py` | One premium single-column production template. Compact renderer is not shipped; no silent template fallback. |
| 62 | Typography/geometry tokens | EQUIVALENT | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 63 | Visual density/page utilization | EQUIVALENT | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 64 | Widows/orphans/near-empty pages | RECONCILED_GENERIC | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 65 | Featured/additional project hierarchy | PUBLIC_ADVANTAGE | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 66 | One/two-page logic | EQUIVALENT | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 67 | Template fallback authorization | INTENTIONAL_DIFFERENCE | `resume.py`; `test_header_summary_ats.py` | One premium single-column production template. Compact renderer is not shipped; no silent template fallback. |
| 68 | Dual PDF extraction | EQUIVALENT | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 69 | Structured ATS round trip | PUBLIC_ADVANTAGE | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 70 | General autofill QA | PUBLIC_ADVANTAGE | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 71 | Employer/title/date parsing | EQUIVALENT | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 72 | Link extraction/clickability | EQUIVALENT | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 73 | PDF object-level preflight | RECONCILED_GENERIC | `document_quality.py`; `../e2e/test_complete_experience.py` | Object/font inspection, geometry drift comparator, semantic accessibility and hash queue audit. No PDF/UA certification. |
| 74 | Font embedding/ToUnicode/core-font QA | RECONCILED_GENERIC | `document_quality.py`; `../e2e/test_complete_experience.py` | Object/font inspection, geometry drift comparator, semantic accessibility and hash queue audit. No PDF/UA certification. |
| 75 | Recruiter-safe PDF metadata | PUBLIC_ADVANTAGE | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 76 | Filename/hash/packet manifest | EQUIVALENT | `resume.py`; `test_header_summary_ats.py` | Actual PDF generation, independent extraction, visual density and ATS reconstruction. |
| 77 | Per-family visual goldens | RECONCILED_GENERIC | `resume.py`; `test_header_summary_ats.py` | Three preserved synthetic visual goldens plus eight persona outputs; candidate geometry and contact sheets support release review. No private goldens copied. |
| 78 | Geometry-signature regression | RECONCILED_GENERIC | `document_quality.py`; `../e2e/test_complete_experience.py` | Object/font inspection, geometry drift comparator, semantic accessibility and hash queue audit. No PDF/UA certification. |
| 79 | Contact sheets/human acceptance | RECONCILED_GENERIC | `resume.py`; `test_header_summary_ats.py` | Three actual synthetic reference/public render comparisons, DOCX/PDF comparisons, dashboard and report contact sheets; owner visual acceptance pending release review. |
| 80 | Candidate-specific visual goldens | PERSONAL_CONFIG_ONLY | User configuration / intentionally excluded | Private identities, market universe, accepted artifacts or career voice corpus remain private; configure equivalents in user data. |
| 81 | Source/engine release lock | RECONCILED_GENERIC | `../../scripts/package_release.py`; `test_phase5b_transactions.py` | Hash inventory and source/wheel/skill fingerprint; history-free source export. Publication uses the reviewed fingerprint. |
| 82 | Canonical evidence freshness | PUBLIC_ADVANTAGE | `updates.py`; `test_phase5b_transactions.py` | Revisioned canonical truth, recovery, staleness and immutable derivative checks. |
| 83 | New evidence propagation | PUBLIC_ADVANTAGE | `updates.py`; `test_phase5b_transactions.py` | Revisioned canonical truth, recovery, staleness and immutable derivative checks. |
| 84 | Accepted/submitted hash exactness | RECONCILED_GENERIC | `application_state.py`; `test_opportunity_application_state_parity.py` | Reachable append-only human-reported activity, immutable PDF/JD lineage and local follow-ups. |
| 85 | Typed errors/remediation | PUBLIC_ADVANTAGE | `updates.py`; `test_phase5b_transactions.py` | Revisioned canonical truth, recovery, staleness and immutable derivative checks. |
| 86 | Transaction rollback/recovery | PUBLIC_ADVANTAGE | `updates.py`; `test_phase5b_transactions.py` | Revisioned canonical truth, recovery, staleness and immutable derivative checks. |
| 87 | Review-only application packet | EQUIVALENT | `application_state.py`; `test_opportunity_application_state_parity.py` | Reachable append-only human-reported activity, immutable PDF/JD lineage and local follow-ups. |
| 88 | Application workflow/outcome state | RECONCILED_GENERIC | `application_state.py`; `test_opportunity_application_state_parity.py` | Reachable append-only human-reported activity, immutable PDF/JD lineage and local follow-ups. |
| 89 | Interview evidence pack | RECONCILED_GENERIC | `interview_prep.py`; `test_interview_evidence_pack_parity.py` | Reachable evidence stories, answer boundaries, technical walkthroughs and readable preparation report. |
| 90 | Career-capital analysis | RECONCILED_GENERIC | `conversion_learning.py`; `test_career_conversion_learning.py` | Observed-cohort career capital, market signals and descriptive conversion; insufficient samples remain insufficient. |
| 91 | Capability/market mapping | RECONCILED_GENERIC | `conversion_learning.py`; `test_career_conversion_learning.py` | Observed-cohort career capital, market signals and descriptive conversion; insufficient samples remain insufficient. |
| 92 | Live gaps and course ROI | RECONCILED_GENERIC | `learning_path.py`, `learning_workflow.py`, `learning_sources.py`; V1 and learning workflow tests | Typed gaps, saved personalization, bounded live discovery, constrained roadmap, evidence projects, completion, reviewed awards/profile updates and eligibility reassessment. |
| 93 | Promotion/readiness progression | RECONCILED_GENERIC | `conversion_learning.py`; `test_career_conversion_learning.py` | Observed-cohort career capital, market signals and descriptive conversion; insufficient samples remain insufficient. |
| 94 | Conversion/outcome learning | RECONCILED_GENERIC | `conversion_learning.py`; `test_career_conversion_learning.py` | Observed-cohort career capital, market signals and descriptive conversion; insufficient samples remain insufficient. |
| 95 | Job discovery/funnel runtime | RECONCILED_GENERIC | `discovery_sources.py`; `test_discovery_sources.py` | Bounded read-only Greenhouse adapter, actual public GET observed, reviewed requirement proposals, catalog dedupe/freshness/qualification. Other provider adapters and scheduled alerts are unverified. |
| 96 | Concrete private role-title universe | PERSONAL_CONFIG_ONLY | User configuration / intentionally excluded | Private identities, market universe, accepted artifacts or career voice corpus remain private; configure equivalents in user data. |
| 97 | Private voice/positioning corpus | PERSONAL_CONFIG_ONLY | User configuration / intentionally excluded | Private identities, market universe, accepted artifacts or career voice corpus remain private; configure equivalents in user data. |
| 98 | Historical provider/job regressions | PERSONAL_CONFIG_ONLY | User configuration / intentionally excluded | Private identities, market universe, accepted artifacts or career voice corpus remain private; configure equivalents in user data. |
| 99 | Studio identity in public PDF metadata | NOT_PORTED_LEGACY | User configuration / intentionally excluded | Private hardcoded/monolithic behavior deliberately excluded; generic contracts retained. |
| 100 | Hard-coded candidate phrase guards | NOT_PORTED_LEGACY | User configuration / intentionally excluded | Private hardcoded/monolithic behavior deliberately excluded; generic contracts retained. |
| 101 | Mixed code/data monolith | NOT_PORTED_LEGACY | User configuration / intentionally excluded | Private hardcoded/monolithic behavior deliberately excluded; generic contracts retained. |
| 102 | No external submission API | INTENTIONAL_DIFFERENCE | `profile.py`; `test_phase2_contracts.py` | Retained generic implementation and regression coverage. |
| 103 | Portable runtime roots | INTENTIONAL_DIFFERENCE | `profile.py`; `test_phase2_contracts.py` | Retained generic implementation and regression coverage. |
| 104 | Privacy/package hygiene | EQUIVALENT | `updates.py`; `test_phase5b_transactions.py` | Revisioned canonical truth, recovery, staleness and immutable derivative checks. |
| 105 | Installed-wheel/clean-room matrix | PUBLIC_ADVANTAGE | `updates.py`; `test_phase5b_transactions.py` | Revisioned canonical truth, recovery, staleness and immutable derivative checks. |
| 106 | Gold fixture refresh governance | RECONCILED_GENERIC | `resume.py`; `test_header_summary_ats.py` | Unchanged existing goldens; geometry compare is read-only. New candidate baselines require human visual review before promotion. |
| 107 | Candidate-neutral synthetic personas | PUBLIC_ADVANTAGE | `workflows.py`; `test_onboarding_portable_workflows.py` | Source-first approval flow plus eight source-first synthetic personas. |
| 108 | Actual accepted-family regression | PERSONAL_CONFIG_ONLY | User configuration / intentionally excluded | Private identities, market universe, accepted artifacts or career voice corpus remain private; configure equivalents in user data. |
| 109 | Accessibility review | RECONCILED_GENERIC | `document_quality.py`; `../e2e/test_complete_experience.py` | Object/font inspection, geometry drift comparator, semantic accessibility and hash queue audit. No PDF/UA certification. |
| 110 | Production queue audit | RECONCILED_GENERIC | `document_quality.py`; `../e2e/test_complete_experience.py` | Object/font inspection, geometry drift comparator, semantic accessibility and hash queue audit. No PDF/UA certification. |

Additional 0.4 surfaces beyond the historical row list: generated workspace home/profile/tracker; editable DOCX; evidence-linked cover letters; readable opportunity/interview/progress reports; reachable learning workflow; source/wheel/skill release packaging and CI. Verified by the complete-experience e2e path and rendered synthetic artifacts.

## Mandatory learning subsystem reconciliation

Historical row 92 is expanded by the [Learning Path Intelligence parity matrix](learning-parity.md). The V1 contracts and scoring engine are retained. New workspace connections are verified through actual progress, approval, canonical commit and role reassessment; the prior CLI wrapper alone was insufficient evidence of full workflow parity.
