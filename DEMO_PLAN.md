# Demo MVP Plan: End-to-End Job Review App

## Summary
Build a Windows-first demo that proves the core pipeline on one live job source: scrape jobs, normalize them into the shared `Job` model, score them against the user’s resume with live Claude, generate tailored resume/cover-letter outputs, and present results in a simple desktop review app with optional Gmail delivery. The demo will not perform autonomous portal or board submission; instead, it will hand the user a reviewed package with files and application links while preserving architecture that can later grow into full automation.

## Key Changes
### Product shape
- Scope the demo to one live source adapter behind `scraper_router.py`; use the router interface from day one so additional sources can be added later without changing downstream modules.
- Replace “auto-apply” in the demo with a review workflow: the app surfaces matched jobs, generated documents, apply URLs, and delivery status, and lets the user open links/files or optionally send the package by Gmail.
- Keep the runtime data model and `%APPDATA%\\JobBot\\` storage layout from the original plan so the demo is a subset of the final product, not a throwaway prototype.

### Desktop app architecture
- Use a simple native Python desktop UI suitable for PyInstaller packaging on Windows 11. Default assumption: `tkinter` for the demo to avoid adding a heavier GUI dependency unless the repo later establishes another UI toolkit.
- UI screens:
  - Setup: configure API keys, Gmail OAuth state, resume source, target titles, source settings, output folder, and schedule window.
  - Run monitor: show current stage, counts, last run time, errors, and log tail.
  - Review queue: list matched jobs with score, employer, title, source, generated file paths, apply URL, and delivery status.
- The UI does not own business logic; it calls service-layer functions used equally by scheduled runs and manual “Run now”.

### Interfaces and module expectations
- `config.py`
  - Define a strict config schema with defaults for schedule window, source enablement, rate limits, proxy list, Gmail enabled flag, output path, and scoring threshold.
  - Store secrets/tokens outside code in `%APPDATA%\\JobBot\\`.
- `database.py`
  - Keep the existing `Job` dataclass as the canonical normalized posting.
  - Add SQLite tables for `jobs`, `run_history`, `match_results`, `generated_documents`, and `deliveries`.
  - Record every stage outcome, including failures and fallbacks, so the UI and logs have a single source of truth.
- `resume_parser.py`
  - Convert the user’s source resume into structured JSON once and cache it as `resume_data.json`.
  - Fail loudly in logs and UI if parsing is incomplete, but do not crash the run.
- `match_scorer.py`
  - Use live Anthropic `claude-sonnet-4-20250514` with max tokens `1000`.
  - Return a structured result with numeric score, short rationale, key strengths/gaps, and a boolean `is_match` driven by configurable threshold.
  - If Claude fails, persist the job with error state and skip document generation for that job.
- `doc_generator.py`
  - Generate one tailored resume PDF and one cover letter text file per accepted match in `%APPDATA%\\JobBot\\output\\[Employer]_[YYYY-MM-DD]\\`.
  - Tailoring should be conservative: emphasize relevant experience from parsed resume data, never invent experience, and keep resume length to 1-2 pages.
- `gmail_client.py`
  - Support optional Gmail OAuth2 send for matched jobs.
  - Delivery payload includes job title, employer, score summary, apply link, and generated files as attachments.
  - If Gmail is not configured or send fails, mark delivery as failed and keep the local review package available.
- `scheduler.py`
  - Support manual runs plus APScheduler runs during the configured weekday/hour window.
  - Scheduled execution invokes the same pipeline as manual runs.
- `main.py`
  - Start the desktop app by default and initialize app-data folders, database, and logging on startup.

### Demo pipeline behavior
- Pipeline order:
  1. Load config and initialize storage.
  2. Fetch jobs from the single source with randomized 3-5 second delays and optional round-robin proxies.
  3. Normalize and dedupe into `Job`.
  4. Filter by target titles.
  5. Score with Claude.
  6. Generate documents for passing matches only.
  7. Save match package to DB and output folder.
  8. Show results in review queue and optionally send Gmail package.
- Fallback rules:
  - Scrape failure: record source error, preserve run record, and end run cleanly.
  - Scoring failure: record job as unscored with error reason; do not generate docs.
  - Document generation failure: retain scored job and mark docs as failed.
  - Gmail failure: retain local review package and mark email delivery failed.
- Explicitly defer `portal_filler.py`, `board_applier.py`, and full `applicator.py` behavior in the demo. Keep stubs/interfaces only if needed so later expansion does not require redesign.

## Test Plan
- Config tests for first-run defaults, missing keys, invalid paths, and `%APPDATA%` resolution on Windows.
- Database tests for schema creation, dedupe by job id, run history persistence, and status transitions across pipeline stages.
- Resume parsing tests for valid PDF input, malformed PDF input, and cached JSON reuse.
- Scraper tests for source normalization into `Job`, rate-limit timing wrapper behavior, and graceful handling of empty/blocked responses.
- Scoring tests with mocked Anthropic responses for pass/fail/error shapes, plus one integration path for live API behind an opt-in test marker.
- Document generation tests for file creation, expected output locations, and no fabricated content when source resume fields are missing.
- Gmail tests for disabled mode, successful message build/send, and send failure fallback to local-only review.
- UI smoke tests for app startup, manual run trigger, review queue rendering, and opening generated artifacts/URLs.
- End-to-end acceptance scenario: one manual run from the desktop app produces at least one normalized job record, one scored match, one output folder with docs, one review-queue entry, and optional Gmail delivery status without uncaught exceptions.

## Assumptions And Defaults
- The demo uses one live source adapter first; recommended default is the source that proves easiest to keep stable during implementation, while preserving router-based multi-source expansion.
- The desktop UI is intentionally simple and operational rather than polished; visual refinement is deferred until the core pipeline is proven.
- Gmail delivery is optional and additive; local review inside the app is the primary success path for the demo.
- Autonomous application submission is out of scope for the demo, but the data model and module boundaries should preserve a later path to email, board, and portal automation.
- The final full plan remains viable only if the live source stability, anti-bot friction, and application-path reliability prove acceptable during demo implementation.
