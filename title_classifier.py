from __future__ import annotations

from database import Job


def is_target_title(job: Job, target_titles: list[str]) -> bool:
    if not target_titles:
        return True
    title = job.title.lower()
    return any(target.lower() in title for target in target_titles)
