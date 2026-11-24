+# Header, summary, and ATS production standard

Career OS 0.3.12 adds three candidate-neutral contracts to every recruiter-facing resume path:

- `ResumeHeaderV1` for public identity, contacts, role-aware positioning, deterministic NAME → CONTACT → HEADLINE order, and plain-text links.
- `RecruiterSummaryV1` for 40–80 word lane/job summaries with clause-level evidence or approved-configuration trace.
- `ATSResumeRoundTripV1` for render, extract, reconstruct, and compare checks across required identity, employment, project, education, credential, and skill fields.

The production renderer uses a single normal-flow column, approved public section names, flat title/employer/location/date lines, canonical date precision, plain-text skills, selectable links, recruiter-safe metadata, and sanitized filenames. Multi-column output is disabled until a separately validated template passes the same extraction and autofill gates.

Primary extraction uses pypdf and pdfplumber. Poppler is used for raster/visual QA where available. Required identity and employment fields have a zero material-loss threshold. Acceptance is reported as `ATS_SAFE_HIGH_CONFIDENCE`, never universal ATS compatibility.

The generic synthetic matrix covers short and long names, long email, two URLs, missing portfolio, career transition, two current degree programs, multiple employers, promotion, contract work, long project names, and a two-page resume. Candidate-specific acceptance data is retained only in the private workspace and external acceptance report.

