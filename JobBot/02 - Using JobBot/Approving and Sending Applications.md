---
tags:
  - using-jobbot
  - guide
  - current
---

# Approving and Sending Applications

What happens when you click **Approve and Send** in the Review Queue.

## How routing works

JobBot inspects the job's apply method and routes accordingly:

1. **Email apply** — if the job posting explicitly instructs applying by email and JobBot detected a valid HR/recruiting address, the application is sent via Gmail with `resume.pdf` and `cover_letter.pdf` attached.

2. **Supported portal** — if the apply URL points to Greenhouse, Lever, or a recognized Indeed-hosted form, JobBot opens a Playwright browser session and attempts to auto-fill the form.

3. **Unsupported portal / fallback** — for all other portals, JobBot opens the apply URL in your default browser and logs the fallback. You then apply manually, with the generated documents open alongside.

> [!warning] Email is not always sent automatically
> Email delivery only fires when all of these are true: Gmail is enabled in config, `sender_email` is set, and the job was marked as email-apply with a confirmed HR inbox. If any condition fails, JobBot falls back to opening the portal. Check the approval log in the detail pane to see what happened.

## Approval log

After you click Approve and Send, the detail pane shows an approval log entry recording:
- Which route was taken (gmail / portal / fallback)
- The timestamp
- Any error or fallback reason

## Related Notes

- [[Email Delivery via Gmail]]
- [[Portal Autofill]]
- [[Manual Apply Fallback]]
- [[The Review Queue]]
- [[Gmail Delivery Setup]]
