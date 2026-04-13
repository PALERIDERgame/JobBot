---
tags:
  - documents
  - reference
  - current
related_code: resume_parser.py
---

# Resume Parser

How JobBot reads your resume and what it extracts for scoring and tailoring.

## Supported formats

| Format | Quality | Notes |
|---|---|---|
| DOCX | Best | Full formatting preserved in output; paragraph styles extracted |
| PDF | Good | Text extracted with pdfplumber |
| Plain text (.txt) | Basic | Works but no formatting preservation in output |

DOCX is strongly recommended — it enables the highest-quality tailored output.

## What gets extracted

- **Name, email, phone** — from the top of the resume
- **Summary / objective** — opening paragraph or section
- **Skills** — from the skills section
- **Work experience** — each role's company, title, dates, and bullet points
- **Experience lines** — all experience text as a flat list (used for TF-IDF and AI prompts)

For DOCX files, paragraph styles (heading levels, bullet styles) are also captured so tailored output can preserve the same visual structure.

## Caching

After the first parse, results are stored as JSON in `%APPDATA%\JobBot\resume_data.json`. Subsequent runs load from cache and skip the parse step.

> [!warning] Update your resume? Clear the cache.
> If you modify your source resume file, delete `resume_data.json` before the next run. Otherwise JobBot will continue scoring and tailoring against the old cached version. The cache is invalidated automatically only if the resume file path changes.

## Resume hash

Each cached resume gets a hash computed from the summary, skills, and experience lines. This hash is used as part of the AI evaluation cache key — changing your resume invalidates all cached AI scores.

## Related Notes

- [[File Locations on Your Computer]]
- [[How Resume Tailoring Works]]
- [[Stage 4 — Cheap AI Stage]]
