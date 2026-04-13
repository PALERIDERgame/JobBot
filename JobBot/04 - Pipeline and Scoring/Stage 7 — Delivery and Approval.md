---
tags:
  - pipeline
  - reference
  - current
stage: 7
related_code: pipeline.py, gmail_client.py
---

# Stage 7 — Delivery and Approval

The final stage — getting the application to the employer, or queuing it for your review.

## Semi-auto mode (default)

All jobs with generated documents land in the Review Queue with status `pending_approval`. Nothing is sent until you approve.

## Auto mode

Jobs marked `apply_candidate` with an email apply method are sent via Gmail automatically. Jobs without a confirmed email apply method still land in the queue.

## Apply routing (when you approve)

When you click **Approve and Send** in the Review Queue:

| Condition | Action |
|---|---|
| Email apply detected + Gmail configured | Send email with resume.pdf + cover_letter.pdf |
| Supported portal URL (Greenhouse, Lever, Indeed-hosted) | Open Playwright session and attempt autofill |
| Unsupported portal | Open browser to apply URL; log fallback |

## Delivery record

Every outcome is written to the `deliveries` table:
- `method` — `gmail_employer`, `portal`, `local` (browser fallback)
- `status` — `sent`, `pending_approval`, `failed`, `skipped`
- `approval_log` — timestamped log of what happened
- `message_id` — Gmail message ID if sent by email

## Related Notes

- [[Approving and Sending Applications]]
- [[Email Delivery via Gmail]]
- [[Portal Autofill]]
- [[Manual Apply Fallback]]
- [[Database Schema]]
- [[Pipeline Overview]]
