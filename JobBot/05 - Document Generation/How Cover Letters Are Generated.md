---
tags:
  - documents
  - reference
  - current
related_code: doc_generator.py
---

# How Cover Letters Are Generated

Every matched job gets a cover letter tailored to that specific role and employer.

## AI-generated cover letters

The `doc_stage_provider` model is given:
- The job title, employer, and full description
- Your resume's work experience entries
- Your key skills and summary

It drafts a cover letter that connects your experience to the job's requirements. The letter is signed with the name from your resume.

## Fallback — template-based cover letter

If the AI stage fails or is not configured, JobBot generates a simpler template-based cover letter that:
- States the role you're applying for
- Lists your most relevant skills for this job
- Includes a standard closing paragraph

The template version is always grammatically correct but less personalized.

## Output formats

Both AI and template cover letters are exported as:
- `cover_letter.docx` — formatted Word document
- `cover_letter.pdf` — PDF for email attachments

Email delivery sends only the PDF version.

> [!tip] Quality check before approving
> Always open the cover letter (via **View Cover Letter** in the Review Queue) before clicking Approve. AI cover letters are usually good but occasionally produce generic or slightly off content. A 30-second read catches anything worth editing.

## Related Notes

- [[How Resume Tailoring Works]]
- [[Stage 6 — Document Generation]]
- [[AI Provider Settings]]
- [[The Review Queue]]
