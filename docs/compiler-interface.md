# Candidate-neutral compiler seam

The Phase 1 compiler boundary is:

```text
CareerProfileV1
+ RoleFamilyV1
+ target context
+ presentation policy
-----------------------
CompilerInputV1
```

`CandidateNeutralCompiler.compile()` may use only that request and injected runtime services. It may not import candidate records, private record identifiers, a home-directory layout, or candidate-specific module constants.

The private reference implementation continues unchanged. A private compatibility shim may translate the generic request into the current legacy shape during migration. That shim is not part of this package and is not exportable.

