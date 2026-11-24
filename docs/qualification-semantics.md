# Qualification semantics

Career OS qualification policy `evidence-preserving-v2` separates known non-satisfaction from unresolved decisions and missing evidence.

Every ingested requirement is persisted with one explicit `requirement_subtype`: `EXPERIENCE`, `EDUCATION`, `CREDENTIAL`, `SKILL`, `TOOL`, `LOGISTICS`, `WORK_AUTHORIZATION`, `SCHEDULE`, `TRAVEL`, or `LOCATION`. Legacy inputs are deterministically normalized during ingest or qualification.

`HARD_GAP` is allowed only when the requirement is mandatory, the relevant candidate fact is known, and that fact does not satisfy the requirement. Missing job-specific decisions use `UNKNOWN_DECISION`. Missing factual support uses `UNKNOWN_EVIDENCE`. Neither is an unfavorable answer or a hard disqualifier.

Requirements with enumerated `sub_capabilities` aggregate linked canonical evidence. Some supported and some missing sub-capabilities produce `PARTIALLY_SUPPORTED` with both lists preserved. A missing preferred requirement produces `PREFERRED_AND_MISSING`; it may make the opportunity borderline but cannot disqualify it.

Project, coursework, and adjacent evidence never receive professional-experience equivalence. A mandatory direct-experience requirement remains a hard gap when the reviewed canonical profile establishes no qualifying direct evidence.
