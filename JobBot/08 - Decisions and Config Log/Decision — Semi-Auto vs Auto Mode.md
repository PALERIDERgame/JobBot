---
tags:
  - decisions
  - decision
date: 2026-04-13
decision_status: active
related_notes:
  - "[[Automation Modes]]"
  - "[[Scoring Thresholds]]"
---

# Decision — Semi-Auto vs Auto Mode

## Context

JobBot can operate in two modes: semi-auto (everything goes to the Review Queue for approval) or auto (qualified jobs are sent without review). Which should be the default?

## Decision

Default to **semi-auto**. Auto mode is available but not the primary workflow.

## Rationale

At the start, there is no track record for whether the AI's scoring aligns with actual job fit. Semi-auto builds that track record: you see what the AI flags, whether it makes sense, and whether the cover letters are good before anything goes out under your name.

Auto mode makes sense only after:
- You've reviewed 20+ flagged jobs and the AI's judgment is consistently on-target
- Thresholds are calibrated so that `final_apply_threshold` only passes genuinely strong fits
- Gmail is configured and email-apply routing is working correctly

## Alternatives considered

- **Default to auto** — faster but risks sending poor-fit applications before the system is calibrated
- **Remove auto mode** — overly restrictive; there are legitimate cases for unattended operation

## Consequences

- Daily workflow requires checking the Review Queue after each run
- Scheduled runs in semi-auto accumulate jobs in the queue; it can grow stale if not checked regularly

## When to consider switching to auto

- AI scores consistently match your intuition
- Cover letter quality is consistently acceptable
- `final_apply_threshold` is at 80 or above

## Related Notes

- [[Automation Modes]]
- [[Scoring Thresholds]]
- [[The Review Queue]]
