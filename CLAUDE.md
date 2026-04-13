# JobBot — Claude Instructions

## Commits
After every major update (new feature, bug fix, significant refactor), create a git commit. Do not batch unrelated changes into one commit.

## Project Overview
Personal job application automation tool. Python + Tkinter GUI, SQLite database, multi-stage AI pipeline.

## Key Files
- `config.py` — `JobBotConfig` dataclass + `load_or_create_config()` + `validate_config_for_run()`
- `pipeline.py` — `JobBotPipeline.run()` orchestrates scraping → filtering → AI scoring → delivery
- `match_scorer.py` — AI stages: `cheap_evaluate()`, `strong_evaluate()`, `tailor_documents_with_ai()`
- `database.py` — SQLite layer; all schema in `Database.initialize()`
- `dashboard.py` — Tkinter GUI; tabs: Run, Approval, Setup
- `doc_generator.py` — Resume + cover letter generation (DOCX + PDF)
- `portal_filler.py` — Playwright-based portal form autofill
- `scrapers/` — Job board scrapers (USAJobs, JobSpy, etc.)
- `tests/` — `unittest` test suite; run with `python -m unittest discover -s tests`

## AI Pipeline Stages
1. Pre-cheap TF-IDF gate (`deterministic_filter.py`)
2. Cheap stage — fast/cheap AI model (default: `ollama_local` / `qwen2.5:7b`)
3. Strong stage — capable AI model (default: `anthropic` / `claude-sonnet-4-20250514`)
4. Doc stage — document tailoring (default: `openai` / `gpt-5-mini`) via `_create_doc_tailoring_completion()`

## Coding Conventions
- No new files unless necessary; prefer editing existing ones
- No speculative abstractions or future-proofing
- Validate at system boundaries only; trust internal code
- Tests use `workspace_temp_dir()` from `test_support.py` for isolation
- When a test sets `cheap_stage_provider="openai"` and mocks the scorer, also set `config.openai_api_key = "test-key"`

## Config Defaults
Dataclass defaults in `JobBotConfig` must match `load_or_create_config()` fallback values:
- `scoring_threshold`: 70
- `cheap_reject_threshold`: 55
- `cheap_escalate_threshold`: 75
- `final_apply_threshold`: 80

## Known Deferred Work
- API key encryption (acceptable risk on personal machine)
- Pipeline checkpoint/resume
- Bulk approve/reject in dashboard
- Full portal autofill expansion

## Obsidian Vault Structure

The vault lives at `JobBot/` (the inner folder). Layout:

- `00 - Home/` — Root MOC (`JobBot Home.md`). Entry point; update when adding new sections.
- `01 - Getting Started/` — Install, first run, file locations.
- `02 - Using JobBot/` — Daily workflow, tabs, automation modes.
- `03 - Configuration Reference/` — Every config field documented.
- `04 - Pipeline and Scoring/` — One note per pipeline stage.
- `05 - Document Generation/` — Resume + cover letter generation.
- `06 - Delivery Methods/` — Gmail, portal autofill.
- `07 - Technical Reference/` — Codebase map, DB schema, cost tracking.
- `08 - Decisions and Config Log/` — ADRs and provider choices.
- `09 - Troubleshooting/` — Common errors and fixes.

Each folder has a MOC note (e.g. `Pipeline MOC.md`) as its hub.

## Documentation Rules

1. **Check before creating** — Before adding a vault note, check if one already exists for that topic. Update rather than duplicate.

2. **Atomic and linked** — One main idea per note. Always add [[wikilinks]] to related notes. Use descriptive titles.

3. **Synthesize** — When updating a note, integrate new info with what's already there. Remove duplication. Don't just append.

4. **Stay consistent**
   - YAML frontmatter on every note (tags, at minimum).
   - [[double brackets]] for all internal links.
   - Callouts (`> [!tip]`, `> [!warning]`) for important asides.
   - Never delete vault content without asking.

5. **Keep vault in sync** — After implementing a feature or fixing a bug, update the relevant vault notes without being asked:
   - The stage note in `04 - Pipeline and Scoring/` if pipeline logic changed.
   - The decision log in `08 - Decisions and Config Log/` for provider or threshold changes.
   - The relevant MOC if a new note was added.
