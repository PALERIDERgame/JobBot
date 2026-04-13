---
tags:
  - using-jobbot
  - guide
  - current
---

# The Review Queue

The Approval tab is where matched jobs land after a run. You review each one and decide whether to send an application.

## Reading the job list

Each row shows:
- **Job title** and **employer**
- **Score** (0–100) from the strong AI stage
- **Apply method** — `email` (can be sent directly) or `board` (opens a portal)
- **Status** — `pending_approval` until you act on it

Click a row to open the detail pane on the right.

## The detail pane

The detail pane shows:
- **AI rationale** — why the model scored this job the way it did
- **Strengths** — what matches well between the job and your resume
- **Gaps** — what the job requires that your resume doesn't clearly address
- **Apply URL** — link to the original job posting
- **Generated documents** — links to open or download the tailored resume and cover letter

> [!tip] What to check before approving
> Read the strengths and gaps. If the gaps are dealbreakers, click **Reject**. If the apply URL looks wrong (company job board vs the job you expected), open it before approving.

## Actions

| Button | What it does |
|---|---|
| Approve and Send | Routes the application — email, portal autofill, or browser fallback |
| Reject | Marks the job as rejected; removes it from the queue |
| Regenerate Docs | Re-runs document generation for this job |
| Open Job URL | Opens the original job posting in your browser |
| View Resume / Cover Letter | Opens the generated files |

## Related Notes

- [[Approving and Sending Applications]]
- [[Stage 5 — Strong AI Stage]]
- [[How Resume Tailoring Works]]
- [[How Cover Letters Are Generated]]
- [[Jobs Not Appearing in Queue]]
