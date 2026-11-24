# Set up Career OS

You need Python 3.11 or 3.12 and a private folder for your career workspace. Keep that folder outside the package checkout. Poppler is needed for PDF checks. Install it with `brew install poppler` on macOS or `sudo apt-get install poppler-utils` on Ubuntu.

Install [Career OS v0.4.2](https://github.com/dhwrd87/career-os/releases/tag/v0.4.2). The release includes the tested wheel, matching skill and history-free source archive. The earlier v0.4.1 release remains available.

## Install the published release

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install "career-os[resume,docx] @ https://github.com/dhwrd87/career-os/releases/download/v0.4.2/career_os-0.4.2-py3-none-any.whl"
careeros --workspace "$HOME/career-workspace" init
careeros --workspace "$HOME/career-workspace" doctor --json
```

The last command checks your setup. If something is missing, follow its message or use the [troubleshooting guide](troubleshooting.md). To install a downloaded release wheel instead, use `python -m pip install "/path/to/career_os-0.4.2-py3-none-any.whl[resume,docx]"` inside the virtual environment.

To install from source instead, use the v0.4.2 tag or the release source ZIP and run `python -m pip install ".[resume,docx]"` from its checkout. Career OS is not on PyPI. Verify downloaded files with the release's `SHA256SUMS.txt`.

## Connect your assistant

Download the [v0.4.2 skill ZIP](https://github.com/dhwrd87/career-os/releases/download/v0.4.2/career-os-0.4.2-skill.zip) and extract it. Copy its complete `career-os` folder into `~/.codex/skills/career-os`. Alternatively, from source, copy all of `skills/career-os` into `~/.codex/skills/career-os`, then refresh skill discovery. Make sure the assistant's shell can find the installed `careeros` command. The skill folder should contain its scripts and references, not your career data.

Say, “Set up Career OS from my resume.” You can use a PDF, DOCX, text or Markdown resume. Without one, the assistant can ask about your work and goals. It shows the details for review before saving them. See [your first steps](onboarding-workflows.md).

## Open your workspace

Ask, “Show my career home.” Or run:

```bash
careeros --workspace "$HOME/career-workspace" workspace dashboard
```

Open `$HOME/career-workspace/outputs/index.html`. It is a local page, not a hosted public website. It may contain private career details.

MacOS/Python 3.12 is tested locally. The [CI matrix](https://github.com/dhwrd87/career-os/actions) checks Ubuntu/Python 3.11 and 3.12. Windows and other AI hosts remain unverified. A Word or LibreOffice editor is useful for checking editable DOCX layout; it is not required to start.
