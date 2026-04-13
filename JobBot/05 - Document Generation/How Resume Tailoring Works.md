---
tags:
  - documents
  - reference
  - current
related_code: doc_generator.py
---

# How Resume Tailoring Works

JobBot produces a tailored version of your resume for each job — your source resume is never modified.

## Two-pass tailoring

### Pass 1 — Local heuristics (always runs, free)

Deterministic tailoring that requires no AI:
- **Keyword matching** — terms from the job description are matched against your resume text
- **Skills reordering** — skills most relevant to this job are moved to the top of the skills section
- **Experience filtering** — experience bullets that don't connect to the job are de-emphasized

This pass always produces a valid, submittable resume.

### Pass 2 — AI tailoring (conditional escalation)

If the local heuristic result is judged weak (based on match score and overlap quality), JobBot sends a request to the `doc_stage_provider` model asking for:
- Suggested revisions to specific experience bullets
- Reordered or rephrased skills entries
- Structured JSON output that JobBot validates before applying

If the AI returns invalid JSON, JobBot attempts to repair it. If repair fails, the local heuristic version is used instead.

## DOCX template preservation

When your source resume is a DOCX file (recommended), all original formatting is preserved:
- Fonts, styles, margins, and spacing carry through unchanged
- Only the text content of bullets, skills, and summary is modified
- The output DOCX looks like your original design

## What never changes

- Your contact information
- Company names, job titles, and dates in your work history
- Education section
- The overall structure and order of sections

> [!note] Resume cache
> JobBot parses your resume once and caches the result. If you update your resume file, delete `%APPDATA%\JobBot\resume_data.json` to force a fresh parse. See [[Resume Parser]].

## Related Notes

- [[Resume Parser]]
- [[How Cover Letters Are Generated]]
- [[Stage 6 — Document Generation]]
- [[Output Files and Where to Find Them]]
