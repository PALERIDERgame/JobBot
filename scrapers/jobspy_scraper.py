from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from application_routing import infer_application_routing
from config import JobBotConfig
from database import Job


class JobSpyScraper:
    source_name = "jobspy"

    def __init__(self, config: JobBotConfig) -> None:
        self.config = config

    def fetch_jobs(self) -> list[tuple[Job, dict[str, Any]]]:
        try:
            from jobspy import scrape_jobs
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("JobSpy is not installed. Run 'python -m pip install python-jobspy'.") from exc

        results = scrape_jobs(
            site_name=self.config.source.jobspy_sites,
            search_term=self.config.source.keyword,
            google_search_term=f"{self.config.source.keyword} jobs in {self.config.source.location}".strip(),
            location=self.config.source.location or None,
            results_wanted=self.config.source.results_per_page,
            hours_old=max(min(self.config.source.days_back, 3) * 24, 24),
            country_indeed="USA",
        )
        rows = self._normalize_rows(results)
        jobs: list[tuple[Job, dict[str, Any]]] = []
        scraped_at = datetime.now(timezone.utc).isoformat()
        for row in rows:
            title = self._clean_value(row.get("title"), fallback="Unknown Title")
            employer = self._clean_value(row.get("company") or row.get("company_name"), fallback="Unknown Employer")
            location = self._clean_value(row.get("location"))
            description = self._clean_value(row.get("description") or row.get("job_description"))
            apply_url = self._clean_value(row.get("job_url") or row.get("job_url_direct") or row.get("url"))
            salary = self._format_salary(row)
            routing = infer_application_routing(description, apply_url)
            source = self._clean_value(row.get("site") or row.get("site_name"), fallback=self.source_name)
            posted_at = self._clean_value(row.get("date_posted") or row.get("date_ago"))
            job = Job(
                id=Job.build_id(employer, title, location),
                title=title,
                employer=employer,
                location=location,
                salary_range=salary,
                description_full=description,
                apply_method=routing.apply_method,
                apply_url=routing.apply_url,
                hiring_manager_email=routing.hiring_manager_email,
                source=source,
                posted_at=posted_at,
                scraped_at=scraped_at,
            )
            jobs.append((job, dict(row)))
        return jobs

    @staticmethod
    def _normalize_rows(results: Any) -> list[dict[str, Any]]:
        if hasattr(results, "to_dict"):
            return list(results.to_dict("records"))
        if isinstance(results, list):
            return [dict(item) for item in results]
        return []

    @staticmethod
    def _format_salary(row: dict[str, Any]) -> str:
        salary_fields = [
            row.get("min_amount"),
            row.get("max_amount"),
            row.get("salary_min"),
            row.get("salary_max"),
        ]
        if salary_fields[0] is not None or salary_fields[1] is not None:
            return f"{salary_fields[0] or ''}-{salary_fields[1] or ''}".strip("-")
        if salary_fields[2] is not None or salary_fields[3] is not None:
            return f"{salary_fields[2] or ''}-{salary_fields[3] or ''}".strip("-")
        return str(row.get("salary") or row.get("interval") or "")

    @staticmethod
    def _clean_value(value: Any, *, fallback: str = "") -> str:
        text = str(value or "").strip()
        if text.lower() in {"", "nan", "none", "null"}:
            return fallback
        return text
