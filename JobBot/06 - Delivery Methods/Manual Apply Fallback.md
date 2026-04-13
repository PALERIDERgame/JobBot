---
tags:
  - delivery
  - reference
  - current
---

# Manual Apply Fallback

What happens when JobBot cannot send or auto-fill an application automatically.

## When the fallback triggers

- No Gmail configured, or email apply conditions not met
- Portal not in the supported list
- Portal autofill fails or encounters a page it cannot parse
- You choose to apply manually

## What JobBot does

1. Opens the apply URL in your default browser
2. Records `method: local` and `status: pending_approval` in the deliveries table
3. Logs the reason for the fallback in the approval log (visible in the detail pane)

## What you do

Apply manually in the opened browser. Your generated documents are accessible from the Review Queue:
- **View Resume** — opens `resume.pdf` or `resume.docx`
- **View Cover Letter** — opens `cover_letter.pdf`

You can copy-paste from the cover letter into the portal's text fields, or upload the PDF directly.

> [!tip] The Review Queue is built for this
> The detail pane shows the job description, AI rationale, and links to all generated documents side by side. Manual apply with JobBot's documents is still much faster than starting from scratch.

## Related Notes

- [[The Review Queue]]
- [[Portal Autofill]]
- [[Supported Job Portals]]
- [[Approving and Sending Applications]]
