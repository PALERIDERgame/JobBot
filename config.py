from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


APP_NAME = "JobBot"
DEFAULT_CONFIG_NAME = "config.yaml"
LOGGER = logging.getLogger(__name__)


def get_appdata_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME
    return Path.home() / "AppData" / "Roaming" / APP_NAME


def sanitize_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in value).strip()
    return safe or "untitled"


@dataclass(slots=True)
class SourceConfig:
    enabled: bool = True
    provider: str = "usajobs"
    keyword: str = "software engineer"
    location: str = ""
    results_per_page: int = 25
    days_back: int = 7
    remote_only: bool = False
    api_url: str = "https://data.usajobs.gov/api/search"
    user_agent: str = "jobbot-demo@example.com"
    authorization_key: str = ""


@dataclass(slots=True)
class GmailConfig:
    enabled: bool = False
    sender_email: str = ""
    recipient_email: str = ""
    client_secrets_file: str = ""


@dataclass(slots=True)
class ScheduleConfig:
    enabled: bool = False
    weekdays: list[str] = field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"])
    start_hour_est: int = 7
    end_hour_est: int = 17
    interval_minutes: int = 120


@dataclass(slots=True)
class JobBotConfig:
    source: SourceConfig = field(default_factory=SourceConfig)
    gmail: GmailConfig = field(default_factory=GmailConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    proxy_list: list[str] = field(default_factory=list)
    scoring_threshold: int = 70
    rate_limit_min_seconds: int = 3
    rate_limit_max_seconds: int = 5
    resume_source_path: str = ""
    output_dir: str = "output"
    target_titles: list[str] = field(default_factory=lambda: ["software engineer", "python developer"])
    anthropic_api_key: str = ""


@dataclass(slots=True)
class AppPaths:
    root: Path
    config_file: Path
    database_file: Path
    resume_json: Path
    token_file: Path
    logs_dir: Path
    output_dir: Path
    log_file: Path


def build_app_paths() -> AppPaths:
    root = get_appdata_root()
    logs_dir = root / "logs"
    output_dir = root / "output"
    return AppPaths(
        root=root,
        config_file=root / DEFAULT_CONFIG_NAME,
        database_file=root / "jobbot.db",
        resume_json=root / "resume_data.json",
        token_file=root / "token.json",
        logs_dir=logs_dir,
        output_dir=output_dir,
        log_file=logs_dir / "jobbot.log",
    )


def ensure_app_dirs(paths: AppPaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.output_dir.mkdir(parents=True, exist_ok=True)


def default_config() -> JobBotConfig:
    return JobBotConfig()


def _merge_dataclass(dc_type: type[Any], incoming: dict[str, Any] | None) -> Any:
    incoming = incoming or {}
    defaults = asdict(dc_type())
    defaults.update(incoming)
    return dc_type(**defaults)


def load_or_create_config(paths: AppPaths) -> JobBotConfig:
    ensure_app_dirs(paths)
    if not paths.config_file.exists():
        config = default_config()
        save_config(config, paths.config_file)
        return config

    with paths.config_file.open("r", encoding="utf-8") as handle:
        raw = _load_serialized_config(handle.read())

    config = JobBotConfig(
        source=_merge_dataclass(SourceConfig, raw.get("source")),
        gmail=_merge_dataclass(GmailConfig, raw.get("gmail")),
        schedule=_merge_dataclass(ScheduleConfig, raw.get("schedule")),
        proxy_list=list(raw.get("proxy_list", [])),
        scoring_threshold=int(raw.get("scoring_threshold", 70)),
        rate_limit_min_seconds=int(raw.get("rate_limit_min_seconds", 3)),
        rate_limit_max_seconds=int(raw.get("rate_limit_max_seconds", 5)),
        resume_source_path=str(raw.get("resume_source_path", "")),
        output_dir=str(raw.get("output_dir", "output")),
        target_titles=list(raw.get("target_titles", ["software engineer", "python developer"])),
        anthropic_api_key=str(raw.get("anthropic_api_key", "")),
    )
    validate_config(config)
    return config


def validate_config(config: JobBotConfig) -> None:
    if config.rate_limit_min_seconds < 0 or config.rate_limit_max_seconds < config.rate_limit_min_seconds:
        raise ValueError("Invalid rate limit range")
    if not 0 <= config.scoring_threshold <= 100:
        raise ValueError("scoring_threshold must be between 0 and 100")
    if config.schedule.start_hour_est < 0 or config.schedule.end_hour_est > 23:
        raise ValueError("Schedule hours must be between 0 and 23")
    if config.schedule.end_hour_est < config.schedule.start_hour_est:
        raise ValueError("Schedule end hour must be >= start hour")


def save_config(config: JobBotConfig, path: Path) -> None:
    payload = asdict(config)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(_dump_serialized_config(payload))


def resolve_output_dir(config: JobBotConfig, paths: AppPaths) -> Path:
    configured = Path(config.output_dir)
    if configured.is_absolute():
        return configured
    return paths.root / configured


def configure_logging(log_file: Path) -> None:
    if logging.getLogger().handlers:
        return

    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    LOGGER.info("Logging configured at %s", log_file)


def _load_serialized_config(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    if yaml is not None:
        return yaml.safe_load(text) or {}
    import json

    return json.loads(text)


def _dump_serialized_config(payload: dict[str, Any]) -> str:
    if yaml is not None:
        return yaml.safe_dump(payload, sort_keys=False)
    import json

    return json.dumps(payload, indent=2)
