---
tags:
  - using-jobbot
  - reference
  - current
---

# Scheduled Runs

JobBot can run the pipeline automatically on a repeating schedule while the app is open.

## How it works

The scheduler uses APScheduler to fire runs at a configurable interval during a time window on selected weekdays. All times are **Eastern US time**.

> [!note] App must be running
> The scheduler is not a Windows Task Scheduler job — it only fires while the JobBot dashboard is open. If you close the app, scheduled runs stop.

## Configuration

Set these fields in the Config Tab under the Schedule section:

| Field | Description |
|---|---|
| Enable schedule | Turn scheduled runs on or off |
| Weekdays | Days the scheduler is active (default: Mon–Fri) |
| Start hour (EST) | Earliest hour a run can start (default: 7 AM) |
| End hour (EST) | Latest hour a run can start (default: 5 PM) |
| Interval minutes | How often to run within the window (default: every 120 minutes) |

## Recommended setup

For a daily automated search, a reasonable starting config is:
- Weekdays: Mon–Fri
- Window: 8 AM – 5 PM EST
- Interval: 180 minutes (3 hours)

This gives 3–4 runs per workday, each fetching the latest job postings from the past few days.

## Related Notes

- [[The Config Tab]]
- [[Automation Modes]]
- [[The Run Tab]]
