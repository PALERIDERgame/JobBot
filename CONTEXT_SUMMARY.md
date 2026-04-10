# JobBot Session Summary

## Current State
- Workspace is [C:\Projects\JobBot](C:\Projects\JobBot).
- Main branch is clean after repo cleanup and branch/worktree pruning.
- Main entrypoint is [C:\Projects\JobBot\main.py](C:\Projects\JobBot\main.py).
- Desktop UI is Tkinter in [C:\Projects\JobBot\dashboard.py](C:\Projects\JobBot\dashboard.py).
- Persistence is SQLite in [C:\Projects\JobBot\database.py](C:\Projects\JobBot\database.py).
- Runtime user data lives under `%APPDATA%\JobBot\`.

## Recent Repo Cleanup
- Preserved current in-progress product work in commit `2f2cb862`.
- Cleaned repo dirt and ported the only useful remaining unmerged branch logic in commit `70cb054b`.
- All extra worktrees were pruned.
- No local branches remain unmerged into `main`.
- `gmail_client_secret.json` is intentionally kept local and ignored.

## Current Pipeline
- The app uses a funnel of:
  1. Scrape jobs
  2. Deterministic filter
  3. Cheap AI screening
  4. Strong AI scoring when needed
  5. Document generation
  6. Approval queue / assisted apply
- Semi-auto is still the intended default workflow.
- Full-auto mode still exists but is not the focus.

## Screening / Matching Behavior
- [C:\Projects\JobBot\deterministic_filter.py](C:\Projects\JobBot\deterministic_filter.py) now handles only truly deterministic rules such as duplicate/include/exclude/force-escalate behavior.
- Location and salary screening were moved out of the hard deterministic filter and into the cheap AI prompt in [C:\Projects\JobBot\match_scorer.py](C:\Projects\JobBot\match_scorer.py).
- Cheap AI prompt now includes explicit `screening_constraints` so jobs that clearly miss location or salary targets can still be screened early without brittle hardcoded matching.

## Review Queue / Approval Flow
- In `semi_auto`, jobs land in the Review Queue for human approval.
- `Approve and Send` now behaves as a true assisted-apply router:
  - email jobs with a validated HR/application email use Gmail
  - supported portals attempt autofill
  - unsupported or blocked portals open the application page and log the fallback honestly
- Approval flow reuses the existing Review Queue progress bar and status/context area.
- Per-job approval logs are shown in the details pane.

## Email Apply Behavior
- Email apply now uses `HR Email` semantics rather than “any email found in the posting.”
- A posting is email-apply only when it explicitly instructs the candidate to send materials and the detected address looks like a real HR/recruiting/application inbox.
- Unsafe or ambiguous addresses are blocked from sending even if a stale row was previously marked as `email`.
- Outbound employer email now:
  - uses cleaner body copy
  - signs with the candidate name
  - sends only `resume.pdf` and `cover_letter.pdf`

## Document Generation
- Resume generation is DOCX-first when the source resume is DOCX.
- Generated deliverables now include:
  - `resume.docx`
  - `resume.pdf`
  - `cover_letter.docx`
  - `cover_letter.pdf`
- Email sends use only the PDF resume and PDF cover letter.
- Existing tests were updated so default unit runs stub expensive DOCX/PDF export behavior.

## Portal / Playwright Behavior
- [C:\Projects\JobBot\portal_filler.py](C:\Projects\JobBot\portal_filler.py) supports a conservative first pass for:
  - Greenhouse
  - Lever
  - Indeed detection plus a limited Indeed-hosted form handler
- Desktop app runtime checks showed Playwright works in the real app session.
- Default automated tests stub Playwright readiness because this shell environment produces noisy `WinError 5` subprocess failures that do not reflect the real desktop app.
- Dedicated opt-in smoke test lives at [C:\Projects\JobBot\tests\test_playwright_smoke.py](C:\Projects\JobBot\tests\test_playwright_smoke.py).

## Testing Status
- Recent targeted verification passed for the imported screening change:
  - `python -m unittest discover -s tests -p "test_deterministic_filter.py"`
  - `python -m unittest discover -s tests -p "test_match_scorer.py"`
- Earlier verification also passed for the HR-email / Gmail / dashboard / pipeline cleanup suites.
- Default tests are now structured to avoid real Playwright startup and unnecessary real document export work.

## Repo Hygiene Notes
- [C:\Projects\JobBot\.gitignore](C:\Projects\JobBot\.gitignore) now ignores:
  - `__pycache__/`
  - `tests/_tmp/`
  - `*.pyc`
  - `gmail_client_secret.json`
  - `client_secret_*.json`
  - `.claude/worktrees/`
- Tracked cache junk and tracked `tests/_tmp` content were removed from git in the cleanup commit.

## Immediate Follow-Up Ideas
- Tighten or expand real portal support based on the most common sites encountered.
- Improve the user-facing distinction between “manual fallback” and “supported autofill submitted.”
- Consider adding a `Reset Gmail Login` control and live Gmail readiness refresh when Gmail settings change.
