---
tags:
  - pipeline
  - reference
  - current
stage: 5
related_code: match_scorer.py
---

# Stage 5 — Strong AI Stage

The final, highest-quality AI scoring pass. Runs only on candidates that escalated from the cheap stage.

## Purpose

The strong stage uses a more capable (and more expensive) model to make a definitive apply/review/reject decision. Because few jobs reach this stage, the added cost is manageable.

## What the AI sees

Same structure as the cheap stage prompt, plus:
- The cheap stage rationale (as context)
- More detailed instructions for identifying strengths and gaps

## What the AI returns

```
score: 0–100
decision: reject | review | apply_candidate
rationale: explanation
strengths: [list]
gaps: [list]
```

## Decision logic

| Decision | Score | Next step |
|---|---|---|
| `reject` | any | Job filtered out |
| `review` | below `final_apply_threshold` | Job queued for manual review |
| `apply_candidate` | at or above `final_apply_threshold` (default 80) | Documents generated; auto-sent in auto mode |

## Caching

Results cached in `ai_evaluations` table — same cache key as the cheap stage but with `stage_name = "strong"`. Re-running on the same job with the same resume uses the cached score.

> [!note] Cost at this stage
> Strong stage uses Claude Sonnet or GPT-4-class models. Expect $0.01–0.05 per evaluated job. Because only a small fraction of jobs reach this stage, total run cost is usually under $0.50.

## Related Notes

- [[AI Provider Settings]]
- [[Scoring Thresholds]]
- [[AI Cost Tracking]]
- [[Database Schema]]
- [[Stage 6 — Document Generation]]
- [[Pipeline Overview]]
