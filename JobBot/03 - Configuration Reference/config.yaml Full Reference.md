---
tags:
  - configuration
  - reference
  - current
---

# config.yaml Full Reference

Complete field-by-field reference for `%APPDATA%\JobBot\config.yaml`. Edit via the Config Tab; this file is the source of truth.

## source section

| Key | Type | Default | Valid values / notes |
|---|---|---|---|
| `enabled` | bool | `true` | Enable/disable scraping |
| `provider` | str | `jobspy` | `jobspy`, `usajobs`, `adzuna` |
| `keyword` | str | `software engineer` | Main search phrase. Fit to Resume now fills this with the combined query preview |
| `location` | str | *(empty)* | Optional city/state or blank |
| `jobspy_sites` | list | `[indeed, google]` | `indeed`, `google`, `linkedin` |
| `results_per_page` | int | `100` | Must be > 0 |
| `days_back` | int | `3` | Must be > 0 |
| `remote_only` | bool | `false` | Filter remote-only |
| `user_agent` | str | *(example email)* | USAJobs: your registered email |
| `authorization_key` | str | *(empty)* | USAJobs API key |
| `adzuna_app_id` | str | *(empty)* | Adzuna app ID |
| `adzuna_app_key` | str | *(empty)* | Adzuna app key |
| `adzuna_country` | str | `us` | Two-letter country code |
| `adzuna_category` | str | *(empty)* | Adzuna category filter |
| `adzuna_sort` | str | `date` | `date` or `relevance` |

## gmail section

| Key | Type | Default | Notes |
|---|---|---|---|
| `enabled` | bool | `false` | Enable Gmail delivery |
| `sender_email` | str | *(empty)* | Your Gmail address |
| `recipient_email` | str | *(empty)* | Fallback/test inbox |
| `client_secrets_file` | str | *(empty)* | Path to `client_secret_*.json` |

## schedule section

| Key | Type | Default | Notes |
|---|---|---|---|
| `enabled` | bool | `false` | Enable scheduled runs |
| `weekdays` | list | `[mon,tue,wed,thu,fri]` | Days of the week |
| `start_hour_est` | int | `7` | 0–23, Eastern time |
| `end_hour_est` | int | `17` | 0–23, must be >= start |
| `interval_minutes` | int | `120` | Minutes between runs |

## Top-level settings

| Key | Type | Default | Valid values / notes |
|---|---|---|---|
| `automation_mode` | str | `semi_auto` | `semi_auto`, `auto` |
| `cheap_stage_provider` | str | `ollama_local` | `ollama_local`, `openai`, `anthropic` |
| `cheap_stage_model` | str | `qwen2.5:7b` | Any model name for the provider |
| `strong_stage_provider` | str | `anthropic` | `openai`, `anthropic` |
| `strong_stage_model` | str | `claude-sonnet-4-20250514` | Any model name |
| `doc_stage_provider` | str | `openai` | `openai`, `anthropic`, `ollama_local` |
| `doc_stage_model` | str | `gpt-5-mini` | Any model name |
| `ollama_base_url` | str | `http://localhost:11434` | URL of local Ollama server |
| `scoring_threshold` | int | `30` | 0–100; display cutoff in dashboard |
| `resume_source_path` | str | *(empty)* | Absolute path to resume file |
| `output_dir` | str | `output` | Absolute or relative path |
| `include_titles` | list | `[software engineer, python developer]` | Adjacent-fit titles; substring match, case-insensitive |
| `exclude_titles` | list | `[principal, sales, designer]` | Substring match, case-insensitive |
| `force_escalate_keywords` | list | `[python, automation, llm, agent]` | Bypass AI, go straight to queue |
| `target_titles` | list | `[software engineer, python developer]` | Direct-fit titles used by fast-rank title scoring |
| `salary_floor` | int | `0` | Min annual salary; 0 to disable |
| `cheap_reject_threshold` | int | `25` | 0–100; must be <= cheap_escalate |
| `cheap_escalate_threshold` | int | `35` | 0–100 |
| `final_apply_threshold` | int | `80` | 0–100 |
| `precheap_gate_enabled` | bool | `true` | Enable TF-IDF pre-screening |
| `precheap_gate_reject_threshold` | int | `30` | 0–100 |
| `skip_ai_scoring_in_semi_auto` | bool | `true` | Queue without AI in semi-auto |
| `enable_cost_tracking` | bool | `true` | Track and display API costs |
| `anthropic_api_key` | str | *(empty)* | Anthropic API key |
| `openai_api_key` | str | *(empty)* | OpenAI API key |
| `rate_limit_min_seconds` | int | `3` | Min delay between scrape requests |
| `rate_limit_max_seconds` | int | `5` | Max delay; must be >= min |

## Related Notes

- [[Job Source Settings]]
- [[AI Provider Settings]]
- [[Scoring Thresholds]]
- [[Title Filters]]
- [[Gmail Delivery Setup]]
- [[The Config Tab]]
