---
tags:
  - pipeline
  - reference
  - current
stage: 4
related_code: match_scorer.py
---

# Stage 4 — Cheap AI Stage

Bulk screening using a low-cost AI model. Runs on every job that passes the TF-IDF gate.

## Purpose

The cheap stage processes many jobs at low cost to separate clear mismatches from candidates worth a more expensive look. It uses a fast, inexpensive model — ideally Ollama running locally for zero cost.

## What the AI sees

The prompt contains:
- A condensed candidate summary (name, skills, recent roles)
- The job posting (title, employer, location, salary, description excerpt)
- Explicit screening constraints: location preferences, salary floor
- Instructions to return a structured JSON response

## What the AI returns

```
score: 0–100
decision: reject | escalate | pass_direct
rationale: one-sentence explanation
strengths: [list of matching factors]
gaps: [list of missing requirements]
confidence: 0.0–1.0
```

## Decision logic

| Score range | Decision | Next step |
|---|---|---|
| Below `cheap_reject_threshold` (default 25) | `reject` | Job filtered out |
| `cheap_reject_threshold` to below `cheap_escalate_threshold` | `escalate` | Send to strong AI stage |
| At or above `cheap_escalate_threshold` (default 35) | `pass_direct` | Skip strong stage, use as final |

## Skip AI in semi-auto

When `skip_ai_scoring_in_semi_auto` is enabled, semi-auto mode skips the cheap stage entirely and queues all deterministically-eligible jobs directly. Useful for a fast review without API costs.

## Caching

Results are cached in the `ai_evaluations` table by job ID, resume hash, provider, model, and prompt version. Re-running a pipeline on the same jobs uses cached scores instead of making new API calls.

## Fallback

If the configured cheap provider is unavailable (Ollama not running, API key invalid), JobBot logs an error and marks the job as errored. It does not silently skip to the next stage.

## Related Notes

- [[AI Provider Settings]]
- [[Scoring Thresholds]]
- [[Stage 5 — Strong AI Stage]]
- [[AI Cost Tracking]]
- [[Ollama Not Responding]]
- [[Pipeline Overview]]
