# Installation

Requirements: Python 3.11 or 3.12, pip/setuptools, Poppler on PATH and a writable workspace outside the package. Version 0.4.1 was locally exercised on macOS with Python 3.12; The [GitHub Actions matrix](https://github.com/dhwrd87/career-os/actions/workflows/ci.yml) exercises Ubuntu/Python 3.11 and 3.12; consult its actual results. Windows and other AI hosts remain unverified.

From the reviewed source checkout:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install ".[resume,docx]"
careeros version --json
careeros doctor --json
careeros --workspace "$HOME/career-workspace" init
careeros --workspace "$HOME/career-workspace" workspace dashboard
```

Or install the reviewed wheel with its optional extras: `python -m pip install "/path/to/career_os-0.4.1-py3-none-any.whl[resume,docx]"`. No package-index publication is assumed. PDF generation and validation require the resume extra; editable exports require docx. Poppler must be installed using your platform package manager.

Copy the complete `skills/career-os` directory into Codex's skill directory, normally `~/.codex/skills/career-os`, then refresh skill discovery. Make `careeros` visible in the assistant shell. Do not copy your private workspace into that skill directory.

For source-first onboarding, use the skill or `careeros --workspace <path> workflow setup --start --source <resume-file> --mode FAST`. Review the proposed intake, provide consolidated answers, resolve clarifications and explicitly approve facts before the setup commit. With no resume, use the skill bootstrap helper and installed questionnaire.

Open `<workspace>/outputs/index.html` after `workspace dashboard`. Run doctor before troubleshooting generation; it checks actual versions and render dependencies. A missing optional integration is not evidence that it works.

Released wheel installation: `python -m pip install "career-os[resume,docx] @ https://github.com/dhwrd87/career-os/releases/download/v0.4.1/career_os-0.4.1-py3-none-any.whl"`. The wheel SHA-256 remains the approved value in the release manifest.
