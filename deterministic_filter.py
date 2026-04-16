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


def _location_is_compatible(job_location: str, target_location: str) -> bool:
    job_location = _normalize(job_location)
    target_location = _normalize(target_location)
    if not job_location or not target_location or "remote" in job_location:
        return True
    job_terms = set(re.findall(r"[a-z]{2,}", job_location))
    target_terms = set(re.findall(r"[a-z]{2,}", target_location))
    return bool(job_terms & target_terms)


def _salary_below_floor(salary_text: str, floor: int) -> bool:
    if floor <= 0:
        return False
    values = [int(match) for match in re.findall(r"\d{2,6}", (salary_text or "").replace(",", ""))]
    if not values:
        return False
    return min(values) < floor


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

    if config.source.location and not _location_is_compatible(job.location, config.source.location):
        return FilterResult("filtered_out", "Location did not match configured search area.")

    if _salary_below_floor(job.salary_range, int(config.salary_floor or 0)):
        return FilterResult("filtered_out", "Salary range was below the configured floor.")

    force_escalate = False
    if config.force_escalate_keywords:
        haystack = f"{title} {description}"
        force_escalate = any(_normalize(keyword) in haystack for keyword in config.force_escalate_keywords)

    return FilterResult("force_escalate" if force_escalate else "eligible_for_stage2", "Passed deterministic filter.", force_escalate=force_escalate)
