# Architecture

Career OS separates immutable package code from user data, workflow state, generated output and cache. Every selected workspace resolves those roots from its JSON-compatible `careeros.yaml` configuration.

```text
Source resumes / notes -> proposed records -> clarification -> human approval
    -> canonical records -> compiled profile -> approved role family / lane base
        -> job snapshot -> qualification -> evidence matrix / employer needs
            -> tailored semantic resume -> PDF / ATS / visual QA
                -> review packet -> human-reported application activity
                    -> interview / follow-up / conversion / learning reports
```

`onboarding`, `intake` and `evidence_expansion` preserve source provenance and keep extracted material noncanonical until review. `updates` applies revision-checked canonical changesets with journaled recovery. `profile`, `editorial`, `career_conversion`, `production_family` and `job_intelligence` own truth-preserving selection and expression.

`resume`, `resume_ats`, `resume_premium` and `document_quality` compose and inspect actual PDFs. `document_exports` creates editable DOCX from the same semantic content. `application_state`, `interview_prep`, `conversion_learning` and `learning_path` own the longitudinal workflow. `experience` connects those engines to CLI commands and human-readable output. It does not duplicate their decision algorithms.

The skill discovers state and invokes CLI paths. It never edits canonical JSON directly or supplies fictitious success. Typed schemas and version authorities live in `src/careeros/schemas` and `versions.py`. Candidate-specific source files and Git history are not package dependencies.

Learning Path Intelligence preserves the V1 `learning_path` engine and contracts. `learning_workflow` connects gaps, preferences, constrained paths, evidence plans, progress and governed canonical proposals; `learning_sources` handles bounded public retrieval behind the provider-neutral boundary. The cycle closes through approved updates and fresh profile/role/qualification compilation, never course-completion inference.
