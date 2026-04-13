---
tags:
  - pipeline
  - reference
  - current
stage: 6
related_code: doc_generator.py
---

# Stage 6 — Document Generation

Creates a tailored resume and cover letter for each job that reaches the apply or review decision.

## Output files

Each job gets its own folder in the output directory:

```
Acme Corp — Python Developer/
├── resume.docx
├── resume.pdf
├── cover_letter.docx
└── cover_letter.pdf
```

Email delivery uses the PDF versions only.

## Tailoring process

### Step 1 — Local heuristic tailoring (always runs)

Deterministic tailoring based on keyword matching:
- Keywords from the job description are matched against your resume
- Skills section is reordered to surface the most relevant items
- Experience bullets are filtered and reordered

### Step 2 — AI tailoring (escalation)

If the local heuristic result is weak, JobBot escalates to the `doc_stage_provider` model. The AI:
- Suggests revised resume bullets tailored to the job description
- Drafts a cover letter specific to this role and employer
- Returns structured JSON that JobBot validates and applies

If AI tailoring fails or returns invalid output, the local heuristic result is used as fallback.

## DOCX template preservation

When the source resume is a DOCX file, JobBot preserves all original formatting (fonts, styles, margins) and edits only the content fields. The output DOCX looks like your original resume, not a plain reformatted version.

## PDF export

PDFs are generated via LibreOffice if installed, with ReportLab as fallback.

## Related Notes

- [[How Resume Tailoring Works]]
- [[How Cover Letters Are Generated]]
- [[Output Files and Where to Find Them]]
- [[AI Provider Settings]]
- [[Stage 7 — Delivery and Approval]]
- [[Pipeline Overview]]
