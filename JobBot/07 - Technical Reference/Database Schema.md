---
tags:
  - technical
  - reference
  - current
related_code: database.py
---

# Database Schema

JobBot stores all data in a SQLite database at `%APPDATA%\JobBot\jobbot.db`. WAL (Write-Ahead Logging) mode is enabled for thread safety.

## Table relationships

```mermaid
erDiagram
    jobs ||--o| match_results : "has"
    jobs ||--o| generated_documents : "has"
    jobs ||--o| deliveries : "has"
    jobs ||--o{ ai_evaluations : "has many"
    run_history {
        int id PK
        text started_at
        text ended_at
        text status
        text stage
        text message
        int jobs_seen
        int jobs_matched
    }
    jobs {
        text id PK
        text title
        text employer
        text location
        text salary_range
        text description_full
        text apply_method
        text apply_url
        text hiring_manager_email
        text source
        text posted_at
        text scraped_at
    }
    match_results {
        text job_id PK
        int score
        text rationale
        text strengths
        text gaps
        int is_match
        text status
        text scored_at
    }
    generated_documents {
        text job_id PK
        text output_dir
        text resume_docx_path
        text resume_pdf_path
        text cover_letter_path
        text cover_letter_pdf_path
        text status
        text tailoring_route
    }
    deliveries {
        text job_id PK
        text method
        text status
        text message_id
        text approval_log
        text approval_route
    }
    ai_evaluations {
        text job_id PK
        text stage_name PK
        text resume_hash PK
        text provider PK
        text model PK
        text prompt_version PK
        text decision
        int score
        real estimated_cost_usd
        int cached
    }
```

## Table descriptions

### jobs
Every scraped job posting. ID is `SHA-256(employer | title | location)` — guarantees deduplication across runs.

### run_history
One row per pipeline run. Tracks start/end time, pipeline stage, and job counts.

### match_results
One row per job. Stores the final match score, rationale, strengths, gaps, and decision status from the strong AI stage.

### generated_documents
Paths to the generated resume and cover letter files for each job. Also records which tailoring route was used and any AI validation attempts.

### deliveries
Delivery status and routing for each job. `status` is `pending_approval`, `sent`, `failed`, or `skipped`. `approval_log` contains the timestamped history of approval actions.

### ai_evaluations
One row per unique combination of job + stage + resume + model. The composite primary key means cached results are automatically reused when the same job is evaluated again with the same resume and model.

## Concurrency

WAL mode allows multiple readers with a single writer. The `Database` class uses a threading lock to serialize writes. Safe for the dashboard's background pipeline thread.

## Related Notes

- [[File Locations on Your Computer]]
- [[Stage 5 — Strong AI Stage]]
- [[AI Cost Tracking]]
