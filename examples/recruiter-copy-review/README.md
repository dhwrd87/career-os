# Eight fictional career backgrounds

Included in [Career OS v0.4.2](https://github.com/dhwrd87/career-os/releases/tag/v0.4.2). [Open the visual comparison gallery](../../docs/recruiter-copy-review-0.4.2.md).

These files are actual generated documents, using the existing synthetic persona matrix. All people, employers, work examples, postings and recorded activity are fictional. No applications were sent.

Each person has a master resume, a career-specific starting resume, a resume for the supplied job, and a short cover letter. Extracted text and an editable tailored resume are included beside each PDF.

| Background | Master | Career-specific | Tailored | Cover letter |
|---|---|---|---|---|
| complete-resume | [PDF](complete-resume/master.pdf) | [PDF](complete-resume/career-specific.pdf) | [PDF](complete-resume/tailored.pdf) | [PDF](complete-resume/cover-letter.pdf) |
| very-weak-resume | [PDF](very-weak-resume/master.pdf) | [PDF](very-weak-resume/career-specific.pdf) | [PDF](very-weak-resume/tailored.pdf) | [PDF](very-weak-resume/cover-letter.pdf) |
| student | [PDF](student/master.pdf) | [PDF](student/career-specific.pdf) | [PDF](student/tailored.pdf) | [PDF](student/cover-letter.pdf) |
| experienced-professional | [PDF](experienced-professional/master.pdf) | [PDF](experienced-professional/career-specific.pdf) | [PDF](experienced-professional/tailored.pdf) | [PDF](experienced-professional/cover-letter.pdf) |
| career-changer | [PDF](career-changer/master.pdf) | [PDF](career-changer/career-specific.pdf) | [PDF](career-changer/tailored.pdf) | [PDF](career-changer/cover-letter.pdf) |
| project-heavy-technical | [PDF](project-heavy-technical/master.pdf) | [PDF](project-heavy-technical/career-specific.pdf) | [PDF](project-heavy-technical/tailored.pdf) | [PDF](project-heavy-technical/cover-letter.pdf) |
| credential-heavy | [PDF](credential-heavy/master.pdf) | [PDF](credential-heavy/career-specific.pdf) | [PDF](credential-heavy/tailored.pdf) | [PDF](credential-heavy/cover-letter.pdf) |
| overlapping-employment | [PDF](overlapping-employment/master.pdf) | [PDF](overlapping-employment/career-specific.pdf) | [PDF](overlapping-employment/tailored.pdf) | [PDF](overlapping-employment/cover-letter.pdf) |

The [review and visual gallery](../../docs/recruiter-copy-review-0.4.2.md) explain the changes and limitations. [Results](results.json) include page counts and internal checks. Internal copy scores are heuristics, not human opinions or evidence of hiring results.

## Reproduce the current outputs

From a source checkout with the resume and DOCX extras installed and Poppler available, use fresh output directories:

```bash
python tests/e2e/run_installed_wheel_matrix.py --runtime-root /tmp/careeros-personas --fixture-root fixtures/synthetic/onboarding-matrix --output /tmp/careeros-personas.json
python scripts/review_recruiter_copy.py --matrix-root /tmp/careeros-personas --jobs examples/recruiter-copy-review/jobs.json --output /tmp/careeros-copy-review
```

The script uses the same approved records and exact fictional jobs, and checks that canonical career facts stay unchanged. The example uses synthetic review actions; do not substitute private data into a public checkout. Use your own private workspace for your career.

The earlier comparison is from commit `ca18865` on the same PR. The source fixtures and confirmed profiles are unchanged. Some source records contain little detail, so concise output is preferable to invented achievements or padded letters.
