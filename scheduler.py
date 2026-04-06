from __future__ import annotations

from config import JobBotConfig


class JobScheduler:
    def __init__(self, config: JobBotConfig) -> None:
        self.config = config
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:  # pragma: no cover
            self.scheduler = None
            return
        self.scheduler = BackgroundScheduler(timezone="America/New_York")

    def start(self, callback) -> None:
        if not self.config.schedule.enabled or self.scheduler is None:
            return
        from apscheduler.triggers.cron import CronTrigger

        weekdays = ",".join(self.config.schedule.weekdays)
        self.scheduler.add_job(
            callback,
            trigger=CronTrigger(
                day_of_week=weekdays,
                hour=f"{self.config.schedule.start_hour_est}-{self.config.schedule.end_hour_est}",
                minute="0",
            ),
            id="jobbot_run",
            replace_existing=True,
        )
        self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler is not None and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
