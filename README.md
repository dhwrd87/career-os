<p><img src="docs/images/career-os-wordmark.svg" width="690" alt="Career OS — evidence, opportunity, growth"></p>

# Find work that fits. Plan what comes next.

Career OS helps you turn your experience into a practical job search and career plan. Tell your AI assistant what you have done and where you would like to go. It can compare real openings, suggest other roles, prepare tailored resumes and help you build the skills for your next step.

**[v0.4.2 — Human Experience Update](https://github.com/dhwrd87/career-os/releases/tag/v0.4.2).** Natural, professional resume writing, integrated job discovery and tailored drafts, and personalized learning and career plans. The earlier [v0.4.1 release](https://github.com/dhwrd87/career-os/releases/tag/v0.4.1) remains available.

[![CI](https://github.com/dhwrd87/career-os/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/dhwrd87/career-os/actions)
[![Version](https://img.shields.io/badge/version-0.4.2-21618c)](https://github.com/dhwrd87/career-os/releases/tag/v0.4.2)
[![MIT](https://img.shields.io/badge/license-MIT-167d63)](LICENSE)

The **v0.4.3 candidate** on this development branch adds [complete application packages](docs/complete-application-journey.md), reusable screening answers and a connected master-to-application journey. The published v0.4.2 downloads below remain unchanged. To try the candidate, install this checkout with `python -m pip install ".[resume,docx]"`.

## Start with a conversation

| Ask in your own words | What Career OS does |
|---|---|
| “Find jobs that fit my experience.” | Searches supported employer boards or compares current postings found by your assistant. It checks your background and preferences, removes duplicates and prepares resumes for the best-fitting jobs. |
| “What other roles could I try?” | Suggests directions from your work history, goals and relevant requirements in checked postings. It explains what carries over and what still needs work. |
| “Make resumes for my top matches.” | Prepares a separate, checked draft for each suitable job. You review the drafts before applying. |
| “Help me reach this stretch role.” | Links the missing requirements to focused learning, credentials, practical projects or work experience. |
| “Make a plan for my dream job.” | Uses a real posting for the role you want and builds a plan around your starting point, time and budget. |

Your results use three groups:

- **Ready Now:** your recorded background fits the requirements we checked, the posting is current and it fits your search.
- **Stretch Roles:** some skills, qualifications or details need work or review.
- **Dream Roles:** roles you have chosen as longer-term goals. We show the steps still needed.

These groups help you decide where to focus. They do not predict a job offer. Missing information becomes a question to check, not an invented skill or qualification.

## See your next steps

<img src="docs/images/workspace.png" width="940" alt="Career home showing Ready Now, Stretch Roles and Dream Roles">

Your career home links your job matches, resume drafts, applications, interviews and learning plans. All people, employers and offers in these examples are fictional. The screenshots show actual generated workspaces.

<img src="docs/images/career-changer-pdf-docx.png" width="940" alt="A tailored resume PDF beside its editable DOCX version">

Resumes use natural, professional writing, clear summaries and specific accomplishments. Cover letters connect relevant examples to the role. Each document starts with career facts and examples you have approved. The checks help protect dates, job titles, qualifications, supported results and readable layout. If a required qualification or job detail is missing, Career OS holds the draft and explains what needs attention.

<img src="docs/images/learning-desktop.png" width="940" alt="A learning plan with practical next steps and options that fit the person's time and budget">

Learning Path Intelligence compares courses and other resources, checks what you already know and helps you create work you can show. It keeps courses, certifications, projects and employment separate. Completing a course never becomes professional experience.

See the [examples](examples/workspace/README.md), [before and after](docs/human-experience-update.md) and [visual gallery](docs/visual-gallery.md). See the [recruiter-copy review](docs/recruiter-copy-review-0.4.2.md) for actual eight-person resume and cover-letter comparisons.

## Install Career OS

Use Python **3.11 or 3.12**. Install Poppler for PDF checks: `brew install poppler` on macOS, or `sudo apt-get install poppler-utils` on Ubuntu.

Install the published wheel in a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install "career-os[resume,docx] @ https://github.com/dhwrd87/career-os/releases/download/v0.4.2/career_os-0.4.2-py3-none-any.whl"
careeros --workspace "$HOME/career-workspace" init
careeros --workspace "$HOME/career-workspace" doctor --json
```

Download the [matching skill ZIP](https://github.com/dhwrd87/career-os/releases/download/v0.4.2/career-os-0.4.2-skill.zip), extract it, and copy its complete `career-os` folder into `~/.codex/skills/career-os`. From a source checkout, copy the complete `skills/career-os` folder into `~/.codex/skills/career-os`, then refresh skill discovery. The assistant's shell needs access to the installed `careeros` command. Say, “Set up Career OS from my resume.” No resume? The assistant can help you build a profile from scratch.

You review the details before they are saved. The assistant asks about missing facts, then helps you choose a career direction. You do not need to learn the package's commands or internal terms.

Read the [setup guide](docs/installation.md) and [first steps](docs/onboarding-workflows.md). The CLI is also available for people who prefer it. Downloads are on the [v0.4.2 release page](https://github.com/dhwrd87/career-os/releases/tag/v0.4.2); Career OS is not published to PyPI.

## What else can you do?

Keep your career history, skills, education, credentials, projects and accomplishments together. Build a complete resume and reusable starting resumes for different kinds of work. Prepare cover letters and application documents, track applications and follow-ups, practise interview examples and review your progress over time.

Corrections stay traceable. Old application records keep the exact resume you used, even when your profile later changes. Backups and update checks help you recover from mistakes.

See the [feature guide](docs/features.md), [job-search guide](docs/find-your-next-role.md), [learning guide](docs/learning-path-intelligence.md) and [help with problems](docs/troubleshooting.md).

## Your information stays under your control

Your career workspace is a folder you choose, outside this repository and the skill folder. You approve changes to your career facts. You decide what may appear in a resume and what must stay private.

Your assistant may process information under its own host's terms. External searches use public sources with your permission; private names, contact details and career records do not belong in search queries. Never post a real resume, confidential employer information or private application records in a public issue.

Career OS prepares local drafts. It does not submit applications, send messages, buy training, enrol you in courses or edit public profiles. Read [privacy and review](docs/privacy-and-approvals.md).

## What to know before you use it

Live discovery supports bounded Greenhouse employer-board searches and reviewed postings from other sources. It does not search every job board. Your assistant needs access to a suitable public source or postings you supply. Current course details may need checking before they can be recommended. Roadmaps use practical estimates, not promises about jobs, pay or training results.

Python 3.11/3.12 on Ubuntu is covered by the [CI matrix](https://github.com/dhwrd87/career-os/actions). Local macOS/Python 3.12 has also been tested. Windows, Microsoft Word layout and other AI-host integrations remain unverified. Codex-style skill routing and real package commands are tested.

The writer still needs good factual input and human review. Thin profiles can produce sparse letters. No matched competitor comparison or independent blind human evaluation was completed; internal copy scores are heuristics, and competitive superiority or hiring outcomes are not established.

One premium, single-column resume design is supported. PDFs contain selectable text but are not tagged for PDF accessibility standards. Editable DOCX files may look different in Word or another editor. Broad non-Latin-script support and custom fonts/themes are not included. [More about formats and layout](docs/renderer-capabilities.md).

## Help improve Career OS

Ask questions in [Discussions](https://github.com/dhwrd87/career-os/discussions). Report a bug in [Issues](https://github.com/dhwrd87/career-os/issues), using a small fictional example. Include what you tried, what you expected and what happened. Keep personal information out of public reports. See [security](SECURITY.md).

Contributors can use [CONTRIBUTING.md](CONTRIBUTING.md), [architecture](docs/architecture.md), [configuration](docs/configuration.md) and the technical references linked there. Internal contracts keep their precise names and meanings.

Career OS uses the [MIT license](LICENSE). See [what changed in v0.4.2](docs/release-notes-0.4.2.md).
