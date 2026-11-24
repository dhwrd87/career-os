# Publication instructions

Publication is a separate owner action after review. No remote, push, tag, package-index upload or public release is created by local release preparation.

1. Review `docs/release-readiness.md`, the functional/layout matrices, gallery and clean-install evidence. Confirm MIT licensing and the documented limitations. Select the exact release fingerprint.
2. Unpack `career-os-0.4.1-source.zip` into a new empty directory. This archive contains no `.git` folder or private history. Do not push the old staging repository or the enclosing development workspace.
3. Verify the archive against `release-manifest.json`, then run the documented tests and installed-wheel persona matrix in your environment. CI configuration exists; inspect its actual GitHub results after the first push.
4. Create an empty GitHub repository named `career-os` under the chosen owner, with no automatic README/license initialization. Use a private repository for final remote rehearsal if desired; changing visibility is an owner decision.
5. In the unpacked directory, initialize fresh history and set a public-safe identity:

```bash
git init -b main
git config user.name "Career OS Maintainers"
git config user.email "maintainers@example.invalid"
git add .
git diff --cached --stat
git commit -m "Release Career OS 0.4.1"
git remote add origin https://github.com/OWNER/career-os.git
# Only after explicit owner review and authorization:
git push -u origin main
```

6. Inspect CI, README rendering, gallery links and clone/install behavior from GitHub. Configure private vulnerability reporting if supported by the chosen repository/account.
7. After those results pass and the release is approved, tag the reviewed commit `v0.4.1`, push the tag and create a GitHub release using `docs/release-notes-0.4.1.md`. Attach the reviewed source archive, wheel, skill archive and manifest.
8. A PyPI publication is a separate decision. No package-index availability, account authority, repository owner or public support address is assumed here.

Keep your real career workspace outside the checkout. The synthetic example snapshot is for demonstration; do not replace it with your own data. Use a fresh workspace for personal onboarding.
