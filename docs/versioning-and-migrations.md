# Version and migration model

The package follows semantic versioning while its public surface is pre-1.0. Persisted schemas and workspace format have explicit versions. Policies used in a persisted qualification or build are immutable identifiers. Every build records compiler, policy, template, and font-profile versions. Rendered workspaces record the compiler and renderer versions used most recently. Adapters declare compatibility through the adapter API version. The thin Codex skill is versioned separately from the package.

Career OS 0.4.1 writes Workspace Format 1.1.0 and accepts 1.0.0 only for explicit migration. The additive 1.23.0 schema bundle adds the persistent OpportunityRegistryV1 contract and cross-run discovery reconciliation without changing workspace format. Newer workspaces are reported as `FUTURE_WORKSPACE`; formats older than 1.0.0 are `UNSUPPORTED_WORKSPACE`.

| Package | Workspace | Config | Schema bundle | Compiler | Renderer | Migration |
|---|---|---|---|---|---|---|
| 0.2.x reference | 1.0.0 | 1.0.0 | 1.0.0 | 0.2.x | Phase 2 implicit | source fixture only |
| 0.3.0 | 1.0.0 | 1.0.0 | 1.0.0 | 0.3.0 | 0.3.0 | explicit 1.0.0 → 1.1.0 |
| 0.3.0 | 1.1.0 | 1.0.0 | 1.1.0 | 0.3.0 | 0.3.0 | current / no-op |
| 0.3.2 | 1.1.0 | 1.0.0 | 1.3.0 | 0.3.2 | 0.3.2 | compatible |
| 0.3.3 | 1.1.0 | 1.0.0 | 1.4.0 | 0.3.2 | 0.3.2 | current / no-op |
| 0.3.4 | 1.1.0 | 1.0.0 | 1.5.0 | 0.3.4 | 0.3.4 | current / no-op |
| 0.3.5 | 1.1.0 | 1.0.0 | 1.6.0 | 0.3.5 | 0.3.4 | compatible predecessor |
| 0.3.6 | 1.1.0 | 1.0.0 | 1.7.0 | 0.3.6 | 0.3.4 | current / no-op |
| 0.3.7 | 1.1.0 | 1.0.0 | 1.8.0 | 0.3.7 | 0.3.4 | current / no-op |
| 0.3.8 | 1.1.0 | 1.0.0 | 1.9.0 | 0.3.8 | 0.3.4 | compatible older package |
| 0.3.9 | 1.1.0 | 1.0.0 | 1.10.0 | 0.3.9 | 0.3.4 | current / no-op |
| 0.3.11 | 1.1.0 | 1.0.0 | 1.12.0 | 0.3.11 | 0.3.4 | current / no-op |
| 0.3.12 | 1.1.0 | 1.0.0 | 1.13.0 | 0.3.12 | 0.3.5 | current / no-op |
| 0.3.13 | 1.1.0 | 1.0.0 | 1.14.0 | 0.3.13 | 0.3.6 | current / no-op |
| 0.3.15 | 1.1.0 | 1.0.0 | 1.16.0 | 0.3.15 | 0.3.6 | current / additive application-state contracts |
| 0.3.16 | 1.1.0 | 1.0.0 | 1.17.0 | 0.3.16 | 0.3.6 | current / additive interview evidence contracts |
| 0.3.17 | 1.1.0 | 1.0.0 | 1.18.0 | 0.3.17 | 0.3.6 | current / additive conversion-learning contracts |
| 0.3.18 | 1.1.0 | 1.0.0 | 1.19.0 | 0.3.18 | 0.3.6 | current / additive production-family inheritance contracts |
| 0.3.19 | 1.1.0 | 1.0.0 | 1.20.0 | 0.3.19 | 0.3.7 | current / premium centered masthead and measured header geometry |
| 0.3.20 | 1.1.0 | 1.0.0 | 1.21.0 | 0.3.20 | 0.3.7 | current / provider-neutral learning-path intelligence |
| 0.3.21 | 1.1.0 | 1.0.0 | 1.22.0 | 0.3.21 | 0.3.7 | current / recruiter conversion copy engine V2 |
| 0.3.22 | 1.1.0 | 1.0.0 | 1.23.0 | 0.3.22 | 0.3.7 | current / cross-run opportunity registry and discovery dedupe |
| 0.3.14 | 1.1.0 | 1.0.0 | 1.15.0 | 0.3.14 | 0.3.6 | supported predecessor |
| 0.3.10 | 1.1.0 | 1.0.0 | 1.11.0 | 0.3.10 | 0.3.4 | supported predecessor |
| 0.3.1 | 1.1.0 | 1.0.0 | 1.2.0 | 0.3.1 | 0.3.1 | compatible; canonical head derived on first governed update |
| 0.3.0 | >1.1.0 | unknown | unknown | unknown | unknown | blocked as future |
| 0.3.0 | <1.0.0 | unknown | unknown | unknown | unknown | unsupported |

`careeros migrate --plan` is read-only. `--apply` validates the source, writes a hashed backup, applies ordered changes atomically where practical, validates the destination, and appends an auditable migration event. Doctor, profile compilation, qualification, resume compilation, and application preparation never migrate implicitly.

## 0.4.1 candidate upgrade

0.4.1 keeps workspace format 1.1.0 and config 1.0.0; additive schema bundle 1.24.0 adds optional course subscription/duration metadata and knowledge-resource/project classifications. It adds reachable workflows and human-readable derivatives without rewriting existing candidate records. Install the new package and matching 0.4 skill, run doctor and workspace verify, then regenerate derivatives you want to review. Historical or submitted artifacts remain unchanged. Back up your workspace before upgrading; no automatic migration or downgrade is performed. The existing explicit 1.0.0-to-1.1.0 migration and transaction rollback tests remain the migration authorities.
