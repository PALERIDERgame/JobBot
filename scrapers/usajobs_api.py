from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timezone
from itertools import cycle
from typing import Any
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from application_routing import infer_application_routing
from config import JobBotConfig
from database import Job


LOGGER = logging.getLogger(__name__)


class USAJobsScraper:
    source_name = "usajobs"

    def __init__(self, config: JobBotConfig) -> None:
        self.config = config
        self.proxy_cycle = cycle(config.proxy_list) if config.proxy_list else None

    def fetch_jobs(self) -> list[tuple[Job, dict[str, Any]]]:
        if not self.config.source.enabled:
            return []

        params = {
            "Keyword": self.config.source.keyword,
            "LocationName": self.config.source.location,
            "ResultsPerPage": self.config.source.results_per_page,
            "DatePosted": min(self.config.source.days_back, 3),
            "WhoMayApply": "public",
            "RemoteIndicator": str(self.config.source.remote_only).lower(),
            "Fields": "Full",
        }
        url = f"{self.config.source.api_url}?{urlencode({k: v for k, v in params.items() if v not in ('', None)})}"
        headers = {"User-Agent": self.config.source.user_agent}
        if self.config.source.authorization_key:
            headers["Authorization-Key"] = self.config.source.authorization_key
            headers["Host"] = "data.usajobs.gov"

        opener = build_opener()
        if self.proxy_cycle:
            proxy = next(self.proxy_cycle)
            opener = build_opener(ProxyHandler({"http": proxy, "https": proxy}))

        delay = random.uniform(self.config.rate_limit_min_seconds, self.config.rate_limit_max_seconds)
        time.sleep(delay)
        request = Request(url, headers=headers, method="GET")
        LOGGER.info("Fetching jobs from %s", url)
        with opener.open(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        items = payload.get("SearchResult", {}).get("SearchResultItems", [])
        jobs: list[tuple[Job, dict[str, Any]]] = []
        for item in items:
            descriptor = item.get("MatchedObjectDescriptor", {})
            employer = descriptor.get("OrganizationName", "Unknown Employer")
            title = descriptor.get("PositionTitle", "Unknown Title")
            location = descriptor.get("PositionLocationDisplay", "")
            details = descriptor.get("UserArea", {}).get("Details", {})
            description = "\n".join(
                str(part)
                for part in [
                    details.get("JobSummary", ""),
                    details.get("MajorDuties", ""),
                    details.get("Requirements", ""),
                    details.get("HowToApply", ""),
                ]
                if part
            )
            remuneration = descriptor.get("PositionRemuneration", [])
            salary = ""
            if remuneration:
                first = remuneration[0]
                salary = f"{first.get('MinimumRange', '')}-{first.get('MaximumRange', '')}"
            apply_uris = descriptor.get("ApplyURI", [])
            apply_url = apply_uris[0] if apply_uris else descriptor.get("PositionURI", "")
            routing = infer_application_routing(description, apply_url)
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
                source=self.source_name,
                posted_at=descriptor.get("PublicationStartDate", ""),
                scraped_at=datetime.now(timezone.utc).isoformat(),
            )
            jobs.append((job, item))
        return jobs
