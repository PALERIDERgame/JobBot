---
tags:
  - decisions
  - decision
date: 2026-04-13
decision_status: active
related_notes:
  - "[[Scoring Thresholds]]"
---

# Decision — Scoring Threshold Values

## Current values

| Threshold | Value | Set on |
|---|---|---|
| `precheap_gate_reject_threshold` | 30 | 2026-04-13 |
| `cheap_reject_threshold` | 25 | 2026-04-13 |
| `cheap_escalate_threshold` | 35 | 2026-04-13 |
| `final_apply_threshold` | 80 | 2026-04-13 |

## Context

Thresholds control how aggressive the funnel is. Too tight → few jobs reach the queue and good fits are missed. Too loose → too many irrelevant jobs to review.

## Rationale for current values

- **cheap_reject_threshold = 25:** A low bar — only obvious non-fits are cut here. Better to let borderline jobs through to the strong stage.
- **cheap_escalate_threshold = 35:** A slightly higher bar to limit strong-stage API costs. Anything above 35 is worth a real look.
- **final_apply_threshold = 80:** Conservative. Only jobs the AI is very confident about are marked for direct apply. Errs on the side of manual review.
- **precheap_gate = 30:** Catches very low TF-IDF matches before any AI call. Low enough to avoid false rejects on vocabulary-mismatch jobs.

## Tuning history

*Record threshold changes here with date and reason:*

| Date | Threshold | Old value | New value | Reason |
|---|---|---|---|---|
| 2026-04-13 | All | defaults | (above) | Initial configuration |

## Related Notes

- [[Scoring Thresholds]]
- [[Stage 3 — Precheap TF-IDF Gate]]
- [[Stage 4 — Cheap AI Stage]]
- [[Stage 5 — Strong AI Stage]]
