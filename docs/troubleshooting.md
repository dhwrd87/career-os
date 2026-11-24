# When something does not work

Tell your assistant what you were trying to do and what happened. Keep the full error available, but you should get a plain explanation and a useful next step.

| Problem | What to try |
|---|---|
| Career OS is not found | Activate the environment where you installed it. Make sure the assistant can run `careeros version --json`. Use the matching v0.4.2 candidate skill. |
| PDF checks cannot run | Install the resume extras and Poppler. Run Doctor again. |
| A resume will not import | Keep the original file. Try PDF, DOCX, text or Markdown. Check whether the file is corrupt or protected. |
| Setup asks more questions | Check only the missing or unclear details. Dates, qualifications and results should not be guessed. |
| No jobs appear | Check the search sources, titles, location and working arrangements. A limited search is not proof that no jobs exist. |
| Job details need review | Read the employer posting, separate required and preferred needs and check unclear information. Empty requirements cannot establish fit. |
| A resume is held | Read the stated qualification, source or content issue. Correct facts through review; do not bypass the check. |
| A source cannot be reached | Try again or use another current employer posting. Do not call a failed fetch a checked opening. |
| A learning plan is out of date | Check selected resource details and your profile/preferences, then build a new plan. Old course completion evidence is still separately reviewable. |
| No course fits | Check budget, time, starting level, price and entry rules. A useful practice project may still be possible. |
| A completed-work file changed | Review the current file again before using it to support a new career claim. |
| An older workspace needs an update | Back it up, review the migration plan and approve the supported update. Do not edit its records by hand. |

Doctor is available with `careeros --workspace <path> doctor --json`. Keep generated work and private career data outside the package. If you need help, use a small fictional reproduction in [Issues](https://github.com/dhwrd87/career-os/issues), not your real resume or private work history.
