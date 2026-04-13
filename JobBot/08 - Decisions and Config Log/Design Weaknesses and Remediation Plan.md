---
tags:
  - decisions
  - reference
  - current
date: 2026-04-13
---

# Design Weaknesses and Remediation Plan

Analysis based on: deep codebase audit, competitive research (LazyApply, Simplify, Jobscan), AI pipeline best-practices literature, and job application effectiveness research.

---

## What competitors do better

- **LazyApply's biggest failure:** 6% callback rate because automated applications contain errors — wrong details, stale info. Human review before send is essential. JobBot's semi-auto mode is correctly designed; the risk is in auto mode.
- **Application outcome tracking:** Competing tools track whether applications led to responses, interviews, or offers. JobBot has none — meaning there's no feedback loop on whether it's working.
- **Cover letter quality:** 83% of hiring managers read cover letters; 49% would interview an otherwise weak candidate based on a strong one. The **problem-solution format** (identify company challenge → present yourself as the solution with quantified results) dominates.
- **The sameness problem:** AI-generated applications are becoming indistinguishable. Quality > volume; differentiation matters.

---

## Weaknesses identified (prioritized)

| #   | Issue                                                                                     | Severity            | File               |
| --- | ----------------------------------------------------------------------------------------- | ------------------- | ------------------ |
| 1   | Threshold config footgun: `final_apply_threshold` can be below `cheap_escalate_threshold` | High                | `config.py`        |
| 2   | No validation that API keys are set for configured providers — fails silently at runtime  | High                | `config.py`        |
| 3   | AI response not validated — score of 999 or invalid decision enum accepted silently       | High                | `match_scorer.py`  |
| 4   | No exponential backoff/retry for AI API calls — transient failures kill the entire run    | High                | `match_scorer.py`  |
| 5   | AI tailoring fallback invisible in UI — user doesn't know they got degraded output        | High                | `pipeline.py`      |
| 6   | No database indexes on foreign keys — O(n) scans as job history grows                     | Medium              | `database.py`      |
| 7   | ThreadPoolExecutor max_workers=10 hardcoded — can trigger API rate limits                 | Medium              | `pipeline.py`      |
| 8   | `playwright` not in `requirements.txt` — silent install failure                           | Medium              | `requirements.txt` |
| 9   | No version pinning in requirements.txt                                                    | Medium              | `requirements.txt` |
| 10  | No application outcome tracking — no way to know if applications are working              | Medium              | missing feature    |
| 11  | Cover letter prompt doesn't use problem-solution format                                   | Medium              | `doc_generator.py` |
| 12  | Bare `except Exception` blocks in `portal_filler.py` (15+ locations)                      | Medium              | `portal_filler.py` |
| 13  | API keys stored in plaintext `config.yaml`                                                | Low (personal tool) | `config.py`        |
| 14  | No bulk approve/reject in dashboard                                                       | Low                 | `dashboard.py`     |

---

## Remediation packages (implemented)

### Package A — Config & Startup Hardening
- Extended `validate_config()` to enforce `cheap_reject < cheap_escalate < final_apply` ordering
- Added `validate_config_for_run()`: checks resume exists on disk, API keys present for configured providers, output dir writable
- Called at pipeline start before any scraping begins
- Added `playwright` to `requirements.txt` and pinned all dep versions

### Package B — AI Resilience
- Added exponential backoff retry (`_call_with_retry`) — retries on 429, 500, 502, 503, timeout; fails fast on 400/401/403
- Added AI response validation — score clamped to [0,100], decision checked against valid enum, rationale non-empty required
- Made `scoring_max_workers` configurable in config (default 4, was hardcoded 10)
- Surfaced AI tailoring fallback as a visible warning badge in the Approval tab

### Package C — Database Indexes
- Added indexes on `deliveries(status)`, `jobs(scraped_at)`, `match_results(status)`, `ai_evaluations(job_id, stage_name)`
- Directly speeds up review queue loading and AI cache lookups

### Package D — Application Outcome Tracking
- New `outcomes` table: records `no_response | rejected | phone_screen | interview | offer | withdrew` per job
- Outcome dropdown added to each delivered job in the Approval tab
- Metrics summary added to Run tab: total applied, response rate %, breakdown by outcome, average score of interviews vs no-response

### Package E — Cover Letter Quality
- Cover letter prompt switched to problem-solution format: identify company challenge from JD → present candidate as solution with quantified examples → specific call to action
- Cover letter quality signals added to Approval detail pane: company name present, metric/number present, word count

---

## Explicitly deferred

- **API key encryption** — plaintext on a personal local machine is acceptable risk; OS credential store adds complexity for negligible gain
- **Pipeline checkpoint/resume** — significant architecture change; current model is fine for personal use
- **Bulk approve/reject** — low usage frequency; not worth UI complexity now
- **Full portal autofill expansion** — track which portals appear in outcomes data first, then prioritize

---

## Related Notes

- [[Decision — AI Provider Choice]]
- [[Decision — Semi-Auto vs Auto Mode]]
- [[Decision — Scoring Threshold Values]]
- [[Scoring Thresholds]]
- [[AI Provider Settings]]
- [[The Review Queue]]
