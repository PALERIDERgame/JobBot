---
tags:
  - using-jobbot
  - reference
  - current
---

# Automation Modes

JobBot has two modes that control how much happens automatically.

## Semi-auto (default, recommended)

Every job that passes AI scoring lands in the **Review Queue** for your approval before anything is sent. You decide, job by job, whether to apply.

Use semi-auto when:
- You are still learning what scores mean for your use case
- You want to check tailored documents before sending
- You are applying to roles where the cover letter matters a lot

> [!warning] Start with semi-auto
> Even if you eventually plan to run fully automatic, start with semi-auto for at least a few runs so you can see what kinds of jobs the AI is flagging and calibrate your thresholds.

## Auto mode

Jobs that score at or above `final_apply_threshold` **and** have an email apply method are sent automatically without landing in the Review Queue.

Jobs without a confirmed email apply method (portal-only jobs) still land in the queue even in auto mode, because auto-submitting to a portal requires human oversight.

## Skip AI scoring in semi-auto

When this option is enabled (the default), semi-auto mode skips all AI stages and queues every job that passes the deterministic filter directly. This is the fastest way to get a broad set of jobs in front of you for manual review without waiting for AI calls.

## Changing the mode

Set **Automation mode** in the Config Tab and click Save. Takes effect on the next run.

## Related Notes

- [[Scoring Thresholds]]
- [[The Review Queue]]
- [[Approving and Sending Applications]]
- [[Decision — Semi-Auto vs Auto Mode]]
