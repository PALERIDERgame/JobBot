---
tags:
  - troubleshooting
  - reference
  - current
symptoms:
  - "Review Queue empty"
  - "No jobs after run"
  - "0 jobs matched"
---

# Jobs Not Appearing in Queue

The most common issue: a run completes but nothing shows up in the Review Queue.

## How to diagnose

Read the Run tab log carefully — it shows exactly where jobs are dropping out. Look for lines like:
- `N candidates after deterministic filter` — how many survived title filtering
- `N passed precheap gate` — how many survived TF-IDF scoring
- `[title] → reject` — individual AI rejections

## Cause 1 — All jobs filtered by title rules

**Symptom:** "0 candidates after deterministic filter"
**Fix:** Check `include_titles` in the Config Tab. The job title must contain at least one of these substrings. If your list is too narrow, real jobs are filtered out.

Try temporarily emptying `include_titles` and running again — if jobs appear, the title list was too restrictive.

## Cause 2 — All jobs rejected by TF-IDF gate

**Symptom:** Candidates survive title filter but drop at the precheap gate
**Fix:** Lower `precheap_gate_reject_threshold` (try 15 instead of 30), or disable the pre-cheap gate entirely in the Config Tab.

This can happen if your resume and the job descriptions use different terminology for the same skills.

## Cause 3 — All jobs rejected at cheap AI stage

**Symptom:** Jobs pass the gate but are rejected by AI
**Fix:**
- Lower `cheap_reject_threshold` — try 15 or 10
- Or enable `skip_ai_scoring_in_semi_auto` — this queues jobs without AI scoring at all

## Cause 4 — Skip AI scoring is off in semi-auto

**Symptom:** Jobs should reach the queue but don't
**Fix:** In the Config Tab, enable **Skip AI scoring in semi_auto**. This queues all deterministically-eligible jobs without any AI evaluation — the fastest way to see results.

## Cause 5 — Scraper returned 0 jobs

**Symptom:** "Fetched 0 jobs" in the Run tab log
**Fix:** See [[Common Errors]] → Scraping errors section.

> [!tip] Start broad
> When testing a new configuration, temporarily use a very broad keyword (e.g., `developer`) and disable all filters. If jobs appear, add your filters back one at a time to find which one is too restrictive.

## Related Notes

- [[Stage 2 — Deterministic Filter]]
- [[Stage 3 — Precheap TF-IDF Gate]]
- [[Scoring Thresholds]]
- [[Title Filters]]
- [[Common Errors]]
