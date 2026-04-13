---
tags:
  - pipeline
  - moc
  - current
---

# Pipeline MOC

The pipeline is JobBot's core engine — the sequence of stages that turns raw job listings into queued applications.

## Notes in this section

- [[Pipeline Overview]] — Full pipeline flowchart and stage summary
- [[Stage 1 — Scraping]] — Fetching jobs from the source provider
- [[Stage 2 — Deterministic Filter]] — Deduplication, title matching, force-escalate
- [[Stage 3 — Precheap TF-IDF Gate]] — Fast keyword overlap screening before AI
- [[Stage 4 — Cheap AI Stage]] — Low-cost AI bulk triage
- [[Stage 5 — Strong AI Stage]] — Premium AI final scoring
- [[Stage 6 — Document Generation]] — Tailored resume and cover letter creation
- [[Stage 7 — Delivery and Approval]] — Sending or queuing applications

## Related

- [[Configuration MOC]] — Settings that control pipeline behavior
- [[JobBot Home]]
