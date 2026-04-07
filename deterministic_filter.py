from __future__ import annotations

import re
from dataclasses import dataclass

from config import JobBotConfig
from database import Job

STATE_ALIASES = {
    "ny": "new york",
    "nj": "new jersey",
    "ca": "california",
    "tx": "texas",
}

NYC_ALIASES = {
    "new york",
    "new york city",
    "nyc",
    "manhattan",
    "brooklyn",
    "queens",
    "bronx",
    "staten island",
}


@dataclass(slots=True)
class FilterResult:
    outcome: str
    reason: str
    force_escalate: bool = False


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_salary_floor(salary_text: str) -> int | None:
    if not salary_text:
        return None
    digits = re.findall(r"\d[\d,]*", salary_text)
    if not digits:
        return None
    values = [int(value.replace(",", "")) for value in digits]
    if not values:
        return None

    salary_text = _normalize(salary_text)
    lower_bound = min(values)

    if "part time" in salary_text or "part-time" in salary_text:
        return None
    if any(token in salary_text for token in ("per hour", "/hour", "/hr", "hourly", " an hour", " hr ")):
        return lower_bound * 2080
    if any(token in salary_text for token in ("per month", "/month", "/mo", "monthly")):
        return lower_bound * 12
    if any(token in salary_text for token in ("per week", "/week", "weekly")):
        return lower_bound * 52
    if any(token in salary_text for token in ("per day", "/day", "daily")):
        return lower_bound * 260
    return lower_bound


def _split_location_parts(text: str) -> tuple[str, str]:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    city = parts[0] if parts else ""
    state = parts[1] if len(parts) > 1 else ""
    state = STATE_ALIASES.get(state, state)
    return city, state


def _location_matches(requested: str, actual: str) -> bool:
    if "remote" in actual:
        return True
    requested_city, requested_state = _split_location_parts(requested)
    actual_city, actual_state = _split_location_parts(actual)

    if requested_city in NYC_ALIASES:
        if actual_city in NYC_ALIASES:
            if not requested_state or not actual_state:
                return True
            return requested_state == actual_state
        return False

    if requested_city and actual_city and requested_city != actual_city:
        return False

    if requested_state:
        return requested_state == actual_state or requested_state in actual

    return requested in actual


def apply_deterministic_filter(
    job: Job,
    config: JobBotConfig,
    *,
    seen_job_ids: set[str],
) -> FilterResult:
    title = _normalize(job.title)
    location = _normalize(job.location)
    description = _normalize(job.description_full)

    if job.id in seen_job_ids:
        return FilterResult("filtered_out", "Duplicate job detected in current run.")
    seen_job_ids.add(job.id)

    if config.include_titles and not any(_normalize(term) in title for term in config.include_titles):
        return FilterResult("filtered_out", "Title did not match include list.")

    if config.exclude_titles and any(_normalize(term) in title for term in config.exclude_titles):
        return FilterResult("filtered_out", "Title matched exclude list.")

    if config.source.location and config.source.location.strip():
        requested_location = _normalize(config.source.location)
        if not _location_matches(requested_location, location):
            return FilterResult("filtered_out", "Location did not match requested area.")

    parsed_salary_floor = _extract_salary_floor(job.salary_range)
    if config.salary_floor > 0 and parsed_salary_floor is not None and parsed_salary_floor < config.salary_floor:
        return FilterResult("filtered_out", "Salary floor below configured minimum.")

    force_escalate = False
    if config.force_escalate_keywords:
        haystack = f"{title} {description}"
        force_escalate = any(_normalize(keyword) in haystack for keyword in config.force_escalate_keywords)

    return FilterResult("force_escalate" if force_escalate else "eligible_for_stage2", "Passed deterministic filter.", force_escalate=force_escalate)
