from __future__ import annotations

import re
from dataclasses import dataclass

from config import JobBotConfig
from database import Job


@dataclass(slots=True)
class FilterResult:
    outcome: str
    reason: str
    force_escalate: bool = False


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def apply_deterministic_filter(
    job: Job,
    config: JobBotConfig,
    *,
    seen_job_ids: set[str],
) -> FilterResult:
    title = _normalize(job.title)
    description = _normalize(job.description_full)

    if job.id in seen_job_ids:
        return FilterResult("filtered_out", "Duplicate job detected in current run.")
    seen_job_ids.add(job.id)

    if config.include_titles and not any(_normalize(term) in title for term in config.include_titles):
        return FilterResult("filtered_out", "Title did not match include list.")

    if config.exclude_titles and any(_normalize(term) in title for term in config.exclude_titles):
        return FilterResult("filtered_out", "Title matched exclude list.")

    force_escalate = False
    if config.force_escalate_keywords:
        haystack = f"{title} {description}"
        force_escalate = any(_normalize(keyword) in haystack for keyword in config.force_escalate_keywords)

    return FilterResult("force_escalate" if force_escalate else "eligible_for_stage2", "Passed deterministic filter.", force_escalate=force_escalate)
