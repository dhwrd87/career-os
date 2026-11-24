# Publishing Career OS

Career OS is public at [dhwrd87/career-os](https://github.com/dhwrd87/career-os). [v0.4.3 — Complete Application Journey](https://github.com/dhwrd87/career-os/releases/tag/v0.4.3) is the current release. Earlier releases remain unchanged.

For future releases, work from the public repository. Never push the private vault or old staging history. Merge only the exact owner-approved head after checks pass. Verify the merged source against the candidate manifest, retain its tested wheel and archives, and record any release-facing documentation changes separately. Use a public-safe Git identity.

After explicit release authorization, tag the verified release commit, confirm CI, then publish the release with its source ZIP, wheel, skill ZIP, release notes, checksums and manifests. Download the attachments anonymously and compare their hashes. Install the public wheel into a fresh environment outside any private workspace and exercise the documented setup and relevant workflows.

The v0.4.3 distribution files are the unchanged reviewed artifacts. Its Git tag includes release-facing README, installation, badge, notes and gallery updates; `publication-manifest.json` identifies those documentation-only differences from the source archive. Runtime, skill, fixtures and tested outputs are unchanged.

PyPI publication is a separate decision. Career OS is distributed through GitHub releases. Keep real career data outside the source checkout; public examples must remain fictional.
