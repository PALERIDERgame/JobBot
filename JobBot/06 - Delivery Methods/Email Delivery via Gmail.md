---
tags:
  - delivery
  - reference
  - current
related_code: gmail_client.py
---

# Email Delivery via Gmail

How JobBot sends applications via email using the Gmail API.

## How it works at runtime

1. JobBot loads the OAuth token from `%APPDATA%\JobBot\token.json`
2. Builds an email with:
   - **To:** the employer's detected HR/application email address
   - **From:** your configured `sender_email`
   - **Subject:** `Application for [Job Title] — [Your Name]`
   - **Body:** a clean plain-text message signed with your name
   - **Attachments:** `resume.pdf` and `cover_letter.pdf`
3. Sends via the Gmail API and records the message ID

## When email delivery fires

Email is sent automatically (in auto mode) or when you click Approve and Send (in semi-auto mode) **only when all of these conditions are met:**

- Gmail is enabled in config (`gmail.enabled: true`)
- `sender_email` is set in config
- The job was marked as email-apply with a confirmed HR inbox (not just any email found in the text)
- The detected address looks like a legitimate HR/recruiting/application inbox

> [!warning] Blocked conditions
> If the job description mentions an email but it looks like a personal address, a generic `info@` address, or a forwarding alias, JobBot will not send. It falls back to opening the portal instead. The approval log shows the exact reason.

## What is attached

Only PDFs are sent — `resume.pdf` and `cover_letter.pdf`. DOCX files are not attached.

## Related Notes

- [[Gmail Delivery Setup]]
- [[Gmail OAuth Problems]]
- [[Approving and Sending Applications]]
- [[Stage 7 — Delivery and Approval]]
