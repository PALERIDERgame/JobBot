---
tags:
  - delivery
  - reference
  - current
related_code: portal_filler.py
---

# Portal Autofill

JobBot can attempt to fill and submit job application forms automatically using Playwright.

## How it works

When you click **Approve and Send** for a portal-apply job on a supported platform:

1. JobBot detects the portal type from the apply URL
2. Opens a Playwright (Chromium) browser session
3. Fills standard form fields: name, email, phone, resume upload
4. Submits the form

The approach is conservative — JobBot fills what it can reliably detect and logs what was completed. It does not guess on ambiguous fields.

> [!note] Playwright must be installed
> Portal autofill requires Playwright with Chromium:
> ```
> playwright install chromium
> ```
> Without it, JobBot falls back to opening the portal in your browser manually.

## What happens after autofill

The approval log in the detail pane records:
- Which portal was detected
- Which fields were filled
- Whether submission completed or required manual intervention

You may still need to log in to the portal, complete additional questions, or confirm the submission manually. JobBot handles the repetitive form-fill; you handle the judgment calls.

## Related Notes

- [[Supported Job Portals]]
- [[Manual Apply Fallback]]
- [[Approving and Sending Applications]]
- [[Stage 7 — Delivery and Approval]]
