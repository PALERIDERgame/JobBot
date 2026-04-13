---
tags:
  - delivery
  - reference
  - current
related_code: portal_filler.py
---

# Supported Job Portals

Portal support levels for Playwright-based autofill.

## Support levels

| Portal | URL pattern | Support level |
|---|---|---|
| Greenhouse | `boards.greenhouse.io` | Supported — form filling + submission |
| Lever | `jobs.lever.co` | Supported — form filling + submission |
| Indeed (hosted forms) | `indeed.com/apply` | Detected + limited form handling |
| Workday | `myworkdayjobs.com` | Detected — opens browser, limited fill |
| iCIMS | `icims.com` | Detected — opens browser only |
| Taleo | `taleo.net` | Detected — opens browser only |
| SmartRecruiters | `careers.smartrecruiters.com` | Detected — opens browser only |

**Supported** — JobBot fills and attempts to submit the form.
**Detected** — JobBot recognizes the portal and opens it in the browser, but does not attempt form fill.

> [!note] Everything else
> Any portal not in this table falls through to the manual fallback: JobBot opens the apply URL in your browser and logs the fallback.

## Related Notes

- [[Portal Autofill]]
- [[Manual Apply Fallback]]
- [[Approving and Sending Applications]]
