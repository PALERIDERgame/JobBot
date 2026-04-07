from __future__ import annotations

from config import JobBotConfig
from scrapers.jobspy_scraper import JobSpyScraper
from scrapers.usajobs_api import USAJobsScraper


class ScraperRouter:
    def __init__(self, config: JobBotConfig) -> None:
        self.config = config

    def fetch_jobs(self):
        provider = self.config.source.provider.lower()
        if provider == "usajobs":
            return USAJobsScraper(self.config).fetch_jobs()
        if provider == "jobspy":
            return JobSpyScraper(self.config).fetch_jobs()
        raise ValueError(f"Unsupported source provider: {self.config.source.provider}")
