from __future__ import annotations

from config import JobBotConfig
from scrapers.adzuna_api import AdzunaScraper
from scrapers.jobspy_scraper import JobSpyScraper
from scrapers.usajobs_api import USAJobsScraper


class ScraperRouter:
    def __init__(self, config: JobBotConfig) -> None:
        self.config = config

    def fetch_jobs(self, keyword: str | None = None):
        provider = self.config.source.provider.lower()
        if provider == "adzuna":
            return AdzunaScraper(self.config).fetch_jobs(keyword=keyword)
        if provider == "usajobs":
            return USAJobsScraper(self.config).fetch_jobs(keyword=keyword)
        if provider == "jobspy":
            return JobSpyScraper(self.config).fetch_jobs(keyword=keyword)
        raise ValueError(f"Unsupported source provider: {self.config.source.provider}")
