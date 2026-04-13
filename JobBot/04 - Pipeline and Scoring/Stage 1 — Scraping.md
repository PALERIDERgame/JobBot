---
tags:
  - pipeline
  - reference
  - current
stage: 1
related_code: scrapers/scraper_router.py
---

# Stage 1 — Scraping

The pipeline starts by fetching a batch of job listings from the configured provider.

## How it works

`ScraperRouter` reads `source.provider` from config and delegates to the appropriate scraper:

| Provider | Scraper | Method |
|---|---|---|
| `jobspy` | `scrapers/jobspy_scraper.py` | Web scraping via the python-jobspy library |
| `usajobs` | `scrapers/usajobs_api.py` | Official USAJobs REST API |
| `adzuna` | `scrapers/adzuna_api.py` | Official Adzuna REST API |

## What gets fetched

Each job is returned as a `Job` object with:
- `id` — SHA-256 hash of employer + title + location (used for deduplication)
- `title`, `employer`, `location`, `salary_range`
- `description_full` — full job description text
- `apply_method` (`email` or `board`) and `apply_url`
- `hiring_manager_email` — if found in the description
- `source` — which scraper produced it
- `posted_at`, `scraped_at`

A typical run fetches 100 jobs. This is controlled by `results_per_page` in config.

> [!note] Rate limiting
> JobSpy scraping uses a random delay between requests (`rate_limit_min_seconds` to `rate_limit_max_seconds`) to avoid being blocked. The default is 3–5 seconds per request.

## Related Notes

- [[Job Source Settings]]
- [[Stage 2 — Deterministic Filter]]
- [[Pipeline Overview]]
