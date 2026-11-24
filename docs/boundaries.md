# Package and runtime boundaries

| Boundary | Ownership | Runtime mutation |
|---|---|---|
| `PACKAGE_ROOT` | Generic code, schemas, policies, migrations, templates, docs | Forbidden during normal runtime |
| `USER_DATA_ROOT` | Candidate identity, career records, evidence, preferences, source references | Read-only except an explicit reviewed commit workflow |
| `STATE_ROOT` | Opportunities, decisions, builds, application/interview/follow-up/outcome state | Allowed through state services |
| `OUTPUT_ROOT` | Resumes, packets, reports, accepted generated artifacts | Allowed through output services |
| `CACHE_ROOT` | Disposable renders, temporary files, provider caches | Allowed and disposable |
| `RUNTIME_SERVICES` | Paths, clock, IDs, hashing, renderer/adapters/capability detection | Services, not candidate data |

All configured paths are relative to the configuration file by default. Runtime roots must be separate and outside `PACKAGE_ROOT`. Candidate data enters through `CareerProfileProvider`; package defaults contain no identity or career truth.

