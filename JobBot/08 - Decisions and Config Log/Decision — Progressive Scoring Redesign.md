---
tags:
  - decisions
  - decision
date: 2026-04-14
decision_status: proposed
related_notes:
  - "[[Pipeline Overview]]"
  - "[[Scoring Thresholds]]"
  - "[[The Review Queue]]"
  - "[[Design Weaknesses and Remediation Plan]]"
---

# Decision — Progressive Scoring Redesign

## Context

The current pipeline can spend too much time scoring jobs before the review queue becomes useful. Even with caching and parallel workers, end-to-end latency is dominated by evaluating too many jobs too deeply.

The product priority is now:
- fast end-to-end runs
- jobs appearing in the queue quickly
- relatively accurate triage rather than exhaustive perfect scoring

## Decision

Adopt a progressive scoring architecture:

1. Run deterministic filtering first.
2. Run a fast local ranker on all surviving jobs.
3. Queue likely-good jobs immediately with provisional scores.
4. Run cheap AI only on a small top slice.
5. Run strong AI only on the best shortlist from that slice.
6. Allow only strongly verified finalists to auto-apply.

## Rationale

This design moves AI from “evaluate most candidates” to “verify the shortlist.” That cuts latency sharply while preserving quality where it matters most.

It also improves UX:
- the queue becomes useful early
- users can review while deeper scoring continues
- strong AI capacity is focused on the jobs most likely to matter

## Consequences

- Queue rows need a score source / verification stage
- config should shift from threshold-heavy controls toward shortlist controls
- auto mode should require strong verification before send
- some borderline jobs may be less precisely ranked, but obvious good and bad fits should be handled faster

## Planned controls

- `fast_rank_min_score`
- `cheap_ai_top_n`
- `strong_ai_top_n`
- `progressive_queue_enabled`

## Notes

The existing thresholds may be kept temporarily for compatibility, but they will no longer be the primary tuning surface.

## Related Notes

- [[Pipeline Overview]]
- [[The Review Queue]]
- [[Scoring Thresholds]]
- [[Design Weaknesses and Remediation Plan]]
