# Your career workspace

Your workspace holds your career information, job search and documents. Keep it in a private folder you control, separate from the installed Career OS package.

- `data/` holds the career facts you have reviewed and approved.
- `sources/` keeps the resumes, notes and other files you choose to bring in.
- `state/` tracks job comparisons, applications and work in progress.
- `outputs/` contains your dashboard, resumes and reports. Open `outputs/index.html` to start.
- `.cache/` holds temporary files that can be rebuilt.

Career OS keeps your accepted documents and approved career records. An upgrade backup stays in `.careeros-backups/` until you decide it is safe to remove. Keep your own backup before an upgrade or major correction.

For a technical check, run `careeros --workspace <path> workspace verify`. It checks the workspace format, saved records, references and protected document hashes. See [architecture](architecture.md) for the developer details.
