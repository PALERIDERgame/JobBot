---
tags:
  - using-jobbot
  - guide
  - current
---

# The Run Tab

How to start a job search run and interpret what you see while it runs.

## Starting a run

1. Make sure your config is saved ([[The Config Tab]])
2. Switch to the **Run** tab
3. Click **Start Run**

The pipeline runs on a background thread — the dashboard stays responsive while it works.

## What you see during a run

**Progress bar** — advances as each pipeline stage completes.

**Stage label** — shows the current stage: `scraping`, `filtering`, `cheap_scoring`, `strong_scoring`, `document_generation`, `delivery`.

**Log output** — scrollable text area showing real-time messages. Key things to watch for:
- `Fetched N jobs from [provider]` — scrape complete
- `N candidates after filter` — how many survived deterministic filtering
- `[job title] → reject` / `escalate` / `apply_candidate` — individual AI decisions
- `Documents generated for [employer]` — a match is ready for review
- `Run complete` — pipeline finished

**Cost display** — shows estimated USD spent on AI API calls for this run. Updates as each AI stage completes.

## After the run

When the run finishes, the status bar shows `completed` with a summary (jobs seen, jobs matched). Switch to the **Approval tab** to review queued matches.

> [!tip] Empty queue after a run?
> If no jobs appear in the queue, the most common cause is all jobs being filtered out before reaching the queue. See [[Jobs Not Appearing in Queue]] for how to diagnose this.

## Related Notes

- [[Pipeline Overview]]
- [[AI Cost Tracking]]
- [[The Review Queue]]
- [[Jobs Not Appearing in Queue]]
