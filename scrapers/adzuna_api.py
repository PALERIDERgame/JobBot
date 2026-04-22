from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from application_routing import infer_application_routing
from config import JobBotConfig
from database import Job
from scrapers import scrape_with_retry


class AdzunaScraper:
    source_name = "adzuna"

    def __init__(self, config: JobBotConfig) -> None:
        self.config = config

    def fetch_jobs(self, keyword: str | None = None) -> list[tuple[Job, dict[str, Any]]]:
        app_id = self.config.source.adzuna_app_id.strip()
        app_key = self.config.source.adzuna_app_key.strip()
        country = (self.config.source.adzuna_country or "us").strip().lower()
        if not app_id or not app_key:
            raise RuntimeError("Adzuna app_id/app_key are required. Configure them in Setup before running.")
        if not country:
            raise RuntimeError("Adzuna country is required (e.g., 'us'). Configure it in Setup.")

        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": self.config.source.results_per_page,
            "what": keyword or self.config.source.keyword,
            "where": self.config.source.location,
            "sort_by": self.config.source.adzuna_sort or "date",
            "content-type": "application/json",
        }
        if self.config.source.adzuna_category:
            params["category"] = self.config.source.adzuna_category

        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        response = scrape_with_retry(lambda: requests.get(url, params=params, timeout=30))
        response.raise_for_status()
        payload = response.json()

        rows = payload.get("results") or []
        jobs: list[tuple[Job, dict[str, Any]]] = []
        scraped_at = datetime.now(timezone.utc).isoformat()
        for row in rows:
            title = self._clean_value(row.get("title"), fallback="Unknown Title")
            company = row.get("company") or {}
            employer = self._clean_value(company.get("display_name"), fallback="Unknown Employer")
            location = self._clean_value(self._extract_location(row))
            description = self._clean_value(row.get("description"))
            apply_url = self._clean_value(row.get("redirect_url") or row.get("adref") or row.get("url"))
            salary = self._format_salary(row)
            routing = infer_application_routing(description, apply_url)
            posted_at = self._clean_value(row.get("created"))
            job_id = str(row.get("id") or "").strip()
            if job_id:
                job_id = f"adzuna:{job_id}"
            else:
                job_id = Job.build_id(employer, title, location)
            job = Job(
                id=job_id,
                title=title,
                employer=employer,
                location=location,
                salary_range=salary,
                description_full=description,
                apply_method=routing.apply_method,
                apply_url=routing.apply_url,
                hiring_manager_email=routing.hiring_manager_email,
                source=self.source_name,
                posted_at=posted_at,
                scraped_at=scraped_at,
            )
            jobs.append((job, dict(row)))
        return jobs

    @staticmethod
    def _extract_location(row: dict[str, Any]) -> str:
        location = row.get("location") or {}
        display_name = location.get("display_name")
        if display_name:
            return str(display_name)
        areas = location.get("area") or []
        if isinstance(areas, list):
            return ", ".join([str(item) for item in areas if item])
        return ""

    @staticmethod
    def _format_salary(row: dict[str, Any]) -> str:
        min_amount = row.get("salary_min")
        max_amount = row.get("salary_max")
        if min_amount is not None or max_amount is not None:
            return f"{min_amount or ''}-{max_amount or ''}".strip("-")
        return str(row.get("salary_is_predicted") or row.get("salary") or "")

    @staticmethod
    def _clean_value(value: Any, *, fallback: str = "") -> str:
        text = str(value or "").strip()
        if text.lower() in {"", "nan", "none", "null"}:
            return fallback
        return text
