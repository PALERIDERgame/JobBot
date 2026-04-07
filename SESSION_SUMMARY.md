# Job Bot Session Summary

## Current State
- Project is a Windows-first Python desktop app in `C:\Projects\Job Bot`.
- Main entrypoint is [main.py](C:\Projects\Job Bot\main.py).
- Desktop UI is built with `tkinter` in [dashboard.py](C:\Projects\Job Bot\dashboard.py).
- Persistence uses raw `sqlite3` in [database.py](C:\Projects\Job Bot\database.py).
- Runtime user data lives under `%APPDATA%\JobBot\`.

## Current Pipeline
- The app now uses a cost-minimized funnel:
  1. Scrape jobs
  2. Deterministic filter
  3. Cheap AI stage
  4. Strong AI stage
  5. Generate docs only for final apply candidates
  6. Hold in approval queue by default
- Semi-auto is the default mode.
- Full auto mode still exists and was intentionally preserved.

## Source / Product Choices
- Current live source is USAJobs via [scrapers/usajobs_api.py](C:\Projects\Job Bot\scrapers\usajobs_api.py).
- This was chosen as a technically stable demo source, not because it is the best real-world job source.
- The app supports reviewing job description, generated resume, and cover letter before sending.

## AI / Cost Architecture
- Deterministic filter logic is in [deterministic_filter.py](C:\Projects\Job Bot\deterministic_filter.py).
- Cheap stage defaults:
  - provider: `ollama_local`
  - model: `qwen2.5:7b`
- Cheap stage can fall back to hosted models if Ollama is unavailable and API keys are configured.
- Strong stage defaults:
  - provider: `anthropic`
  - model: `claude-sonnet-4-20250514`
- Doc stage is configurable separately.
- Provider support currently includes:
  - Anthropic
  - OpenAI
  - Ollama for the cheap stage
- Stage evaluations are cached by job/resume/model/prompt version.
- Estimated per-stage API cost is tracked and shown in the UI.

## Config Highlights
- Config file is created in `%APPDATA%\JobBot\config.yaml`.
- Important config fields now include:
  - `automation_mode`
  - `cheap_stage_provider`
  - `cheap_stage_model`
  - `strong_stage_provider`
  - `strong_stage_model`
  - `doc_stage_provider`
  - `doc_stage_model`
  - `ollama_base_url`
  - `include_titles`
  - `exclude_titles`
  - `force_escalate_keywords`
  - `salary_floor`
  - `cheap_reject_threshold`
  - `cheap_escalate_threshold`
  - `final_apply_threshold`
  - `anthropic_api_key`
  - `openai_api_key`

## Review / Approval Flow
- In `semi_auto`, matching jobs are saved with delivery status `pending_approval`.
- Review Queue lets the user:
  - inspect job description
  - open generated resume
  - open generated cover letter
  - click `Approve and Send`
- Gmail sending is optional and still requires Google OAuth client secrets plus sender/recipient config.

## What Was Implemented
- Multi-stage evaluator in [match_scorer.py](C:\Projects\Job Bot\match_scorer.py)
- Deterministic filter module
- Stage evaluation cache and cost tables in SQLite
- Expanded setup UI for stage providers/models and filter thresholds
- Cost summary display in the Run Monitor
- AI-assisted doc-note path with safe fallback to local template generation

## Validation Completed
- AST parse check across Python files passed.
- Unit test suite passed with:
  - `python -m unittest discover -s tests -v`
- Last passing count was 18 tests.

## First-Run Next Steps
1. Install dependencies:
   - `python -m pip install -r C:\Projects\Job Bot\requirements.txt`
2. If using cheapest path, install Ollama and pull:
   - `qwen2.5:7b`
3. Launch:
   - `python C:\Projects\Job Bot\main.py`
4. In Setup:
   - choose resume source
   - keep `automation_mode = semi_auto`
   - configure cheap/strong/doc stages
   - add Anthropic/OpenAI keys if using hosted models
5. Run a narrow first test search and inspect the Review Queue.

## Recommended First Test Settings
- `automation_mode = semi_auto`
- `cheap_stage_provider = ollama_local`
- `cheap_stage_model = qwen2.5:7b`
- `strong_stage_provider = openai` or `anthropic`
- `strong_stage_model = gpt-5-mini` or `claude-sonnet-4-20250514`
- `doc_stage_provider = openai`
- `doc_stage_model = gpt-5-mini`

## Known Follow-Up Work
- Real-world first boot has not been manually validated yet.
- `.exe` packaging has not been fully verified on a clean machine.
- USAJobs is still the only live source; switching to a more relevant private-sector source may be desirable later.
- Stage 2 / Stage 3 thresholds may need tuning after observing real runs.
