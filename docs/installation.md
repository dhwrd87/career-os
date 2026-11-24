# Set up Career OS

You need Python 3.11 or 3.12 and a private folder for your career workspace. Keep that folder outside the package checkout. Poppler is needed for PDF checks. Install it with `brew install poppler` on macOS or `sudo apt-get install poppler-utils` on Ubuntu.

This is the v0.4.2 review candidate. Use the PR branch or its candidate wheel. The public v0.4.1 release is unchanged; it does not include the new connected workflows.

## Install from this checkout

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install ".[resume,docx]"
careeros --workspace "$HOME/career-workspace" init
careeros --workspace "$HOME/career-workspace" doctor --json
```

The last command checks your setup. If something is missing, follow its message or use the [troubleshooting guide](troubleshooting.md). To install a downloaded candidate wheel instead, use `python -m pip install "/path/to/career_os-0.4.2-py3-none-any.whl[resume,docx]"` inside the virtual environment.

## Connect your assistant

For Codex, copy all of `skills/career-os` into `~/.codex/skills/career-os`, then refresh skill discovery. Make sure the assistant's shell can find the installed `careeros` command. The skill folder should contain its scripts and references, not your career data.

Say, “Set up Career OS from my resume.” You can use a PDF, DOCX, text or Markdown resume. Without one, the assistant can ask about your work and goals. It shows the details for review before saving them. See [your first steps](onboarding-workflows.md).

## Open your workspace

Ask, “Show my career home.” Or run:

```bash
careeros --workspace "$HOME/career-workspace" workspace dashboard
```

Open `$HOME/career-workspace/outputs/index.html`. It is a local page, not a hosted public website. It may contain private career details.

MacOS/Python 3.12 is tested locally. The [CI matrix](https://github.com/dhwrd87/career-os/actions) checks Ubuntu/Python 3.11 and 3.12. Windows and other AI hosts remain unverified. A Word or LibreOffice editor is useful for checking editable DOCX layout; it is not required to start.
