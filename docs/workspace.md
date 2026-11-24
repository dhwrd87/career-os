# Workspace structure and retention

`WorkspaceManifestV1` is the compatibility authority. A workspace has separable `data/`, `sources/`, `state/`, `outputs/`, and `.cache/` roots. Package source is immutable and may not contain any of those runtime roots.

Canonical user data and accepted artifacts are retained. Migration backups live under `.careeros-backups/` and are retained until a human verifies the migrated workspace and intentionally applies local retention policy. Failed builds may be retained under `state/failed-builds/` for diagnosis. Caches, temporary renders, provider caches, temporary PDFs, and intermediate images are disposable. The generated `.gitignore` excludes caches, migration backups, temporary output, failed-build scratch, and interpreter caches; it does not ignore canonical data.

`careeros workspace verify` checks manifest/config presence, format/schema compatibility, integrity hashes, separated roots, migration-chain consistency, unique record IDs, evidence references, and immutable artifact hashes.
