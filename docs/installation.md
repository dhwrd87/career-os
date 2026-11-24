# Set up Career OS

You need Python 3.11 or 3.12 and a private folder for your career workspace. Keep that folder outside the package checkout. Poppler is needed for PDF checks. Install it with `brew install poppler` on macOS or `sudo apt-get install poppler-utils` on Ubuntu.

Install [Career OS v0.4.3](https://github.com/dhwrd87/career-os/releases/tag/v0.4.3). The release includes the tested wheel, matching skill and history-free source archive. Earlier v0.4.2 and v0.4.1 releases remain available.

## Install the published release

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install "career-os[resume,docx] @ https://github.com/dhwrd87/career-os/releases/download/v0.4.3/career_os-0.4.3-py3-none-any.whl"
careeros --workspace "$HOME/career-workspace" init
careeros --workspace "$HOME/career-workspace" doctor --json
```

The last command checks your setup. If something is missing, follow its message or use the [troubleshooting guide](troubleshooting.md). To install a downloaded release wheel instead, use `python -m pip install "/path/to/career_os-0.4.3-py3-none-any.whl[resume,docx]"` inside the virtual environment.

To install from source instead, use the v0.4.3 tag or the release source ZIP and run `python -m pip install ".[resume,docx]"` from its checkout. Career OS is not on PyPI. Verify downloaded files with the release's `SHA256SUMS.txt`.

## Start the complete journey

Say, “Build my master resume and help me choose a career direction.” After reviewing your history, choose career directions and ask the assistant to find current jobs and prepare complete packages for your strongest suitable matches. Open each Start Here page, review its PDF/DOCX documents and complete missing personal answers before applying yourself. See the [complete journey](complete-application-journey.md) and [fictional example](../examples/application-journey/README.md).

For an existing workspace, install the new wheel and matching skill, then run Doctor against that workspace. Keep its history and files; do not initialize over it.

## Connect your assistant

Download the [v0.4.3 skill ZIP](https://github.com/dhwrd87/career-os/releases/download/v0.4.3/career-os-0.4.3-skill.zip) and extract it. Copy its complete `career-os` folder into `~/.codex/skills/career-os`. Alternatively, from source, copy all of `skills/career-os` into `~/.codex/skills/career-os`, then refresh skill discovery. Make sure the assistant's shell can find the installed `careeros` command. The skill folder should contain its scripts and references, not your career data.

Say, “Set up Career OS from my resume.” You can use a PDF, DOCX, text or Markdown resume. Without one, the assistant can ask about your work and goals. It shows the details for review before saving them. See [your first steps](onboarding-workflows.md).

## Open your workspace

Ask, “Show my career home.” Or run:

```bash
careeros --workspace "$HOME/career-workspace" workspace dashboard
```

Open `$HOME/career-workspace/outputs/index.html`. It is a local page, not a hosted public website. It may contain private career details.

MacOS/Python 3.12 is tested locally. The [CI matrix](https://github.com/dhwrd87/career-os/actions) checks Ubuntu/Python 3.11 and 3.12. Windows and other AI hosts remain unverified. A Word or LibreOffice editor is useful for checking editable DOCX layout; it is not required to start.
