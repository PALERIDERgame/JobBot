---
tags:
  - configuration
  - reference
  - current
related_code: scrapers/scraper_router.py
---

# Job Source Settings

Controls where and how jobs are fetched. All settings live under the `source:` key in `config.yaml`.

> [!note] Default provider
> JobBot defaults to `jobspy`, which scrapes Indeed and Google by keyword. No API key required.

## Provider options

| Provider | Value | Source | API key needed? |
|---|---|---|---|
| JobSpy | `jobspy` | Indeed, Google, LinkedIn (scraping) | No |
| USAJobs | `usajobs` | US federal government jobs (official API) | Yes |
| Adzuna | `adzuna` | Global job board (official API) | Yes |

## Common settings (all providers)

| Setting | Default | Description |
|---|---|---|
| `provider` | `jobspy` | Which scraper to use |
| `keyword` | `software engineer` | Primary search phrase |
| `location` | *(empty)* | Optional location filter. Leave blank for remote/broad |
| `results_per_page` | `100` | Jobs fetched per run. Start at 25 for testing |
| `days_back` | `3` | Only fetch jobs posted within this many days |
| `remote_only` | `false` | Filter for remote-only postings |

## JobSpy-specific

| Setting | Default | Description |
|---|---|---|
| `jobspy_sites` | `[indeed, google]` | Boards to query. Options: `indeed`, `google`, `linkedin` |

## USAJobs-specific

| Setting | Description |
|---|---|
| `user_agent` | Your email address — sent as the User-Agent header per USAJobs API requirements |
| `authorization_key` | API key from your USAJobs developer account |

## Adzuna-specific

| Setting | Description |
|---|---|
| `adzuna_app_id` | App ID from your Adzuna developer account |
| `adzuna_app_key` | App key from your Adzuna developer account |
| `adzuna_country` | Two-letter country code (e.g., `us`, `gb`, `ca`) |
| `adzuna_category` | Optional Adzuna job category filter |
| `adzuna_sort` | Sort order (`date` or `relevance`) |

## Related Notes

- [[Stage 1 — Scraping]]
- [[The Config Tab]]
- [[config.yaml Full Reference]]
