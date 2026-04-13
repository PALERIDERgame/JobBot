---
tags:
  - technical
  - reference
  - current
---

# Running the Tests

How to run JobBot's test suite and what each test file covers.

## Run all tests

```
python -m unittest discover -s tests
```

## Run a single test file

```
python -m unittest discover -s tests -p "test_match_scorer.py"
```

## Test files

| File | What it tests |
|---|---|
| `test_config.py` | Config loading, validation, serialization |
| `test_database.py` | CRUD operations, queries, thread safety |
| `test_match_scorer.py` | TF-IDF gate, cheap/strong evaluation, scoring logic |
| `test_pipeline.py` | Full pipeline execution, filtering, routing |
| `test_doc_generator.py` | Resume/cover letter generation, DOCX templating, PDF export |
| `test_resume_parser.py` | Resume parsing (DOCX, PDF, TXT), caching |
| `test_portal_filler.py` | Playwright automation, platform detection |
| `test_gmail_client.py` | Email building, attachment handling, OAuth |
| `test_deterministic_filter.py` | Title matching, deduplication, escalation |
| `test_application_routing.py` | Email detection, HR email validation |
| `test_dashboard.py` | GUI configuration, run triggering, approval queue |
| `test_scraper.py` | JobSpy, USAJobs, Adzuna API mocking |
| `test_playwright_smoke.py` | Portal detection regex patterns (opt-in smoke test) |

## What the tests stub

By default, tests stub:
- Expensive AI API calls (Anthropic, OpenAI, Ollama)
- DOCX/PDF export operations (LibreOffice, ReportLab)
- Playwright browser startup

This makes the test suite fast and runnable without API keys or installed dependencies.

> [!note] Tests requiring real network access
> `test_playwright_smoke.py` is an opt-in smoke test that requires Playwright to be installed. Run it separately when you want to verify portal detection in a real browser session.

## Related Notes

- [[Codebase Map]]
- [[Pipeline Overview]]
