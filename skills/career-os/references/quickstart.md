# First use

Install the reviewed Career OS checkout with Python 3.11/3.12 and `python -m pip install ".[resume,docx]"`; ensure Poppler is on PATH. This release is not assumed to exist on a package index. Run `careeros version --json` and `careeros doctor --json`.

Resolve a private workspace outside the package. With an existing resume, run `careeros --workspace <path> workflow setup --start --source <file> --mode FAST`. Present the extracted draft and uncertainties, capture corrections and use the package setup completion/clarification/review flow. Obtain explicit approval before `workflow setup --approve --actor <human>`.

Without a resume, initialize the workspace and use `scripts/bootstrap.py` with the installed questionnaire. Do not require the user to hand-author schemas. Read [workflows](workflows.md) only for the selected onboarding stage.

Review proposed career pathways and approve a role family. Build and review a lane base. Use [complete workflows](complete-workflows.md) for jobs, resumes, applications, interviews, follow-ups, learning and reports. Finish with `careeros --workspace <path> workspace dashboard` and open `outputs/index.html`.
