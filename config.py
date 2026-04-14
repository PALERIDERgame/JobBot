from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
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
    provider: str = "jobspy"
    keyword: str = "software engineer"
    location: str = ""
    jobspy_sites: list[str] = field(default_factory=lambda: ["indeed", "google"])
    results_per_page: int = 100
    days_back: int = 3
    remote_only: bool = False
    api_url: str = "https://data.usajobs.gov/api/search"
    user_agent: str = "jobbot-demo@example.com"
    authorization_key: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "us"
    adzuna_category: str = ""
    adzuna_sort: str = "date"


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
    automation_mode: str = "semi_auto"
    llm_provider: str = "anthropic"
    cheap_stage_provider: str = "openai"
    cheap_stage_model: str = "gpt-5-nano"
    strong_stage_provider: str = "anthropic"
    strong_stage_model: str = "claude-sonnet-4-20250514"
    doc_stage_provider: str = "openai"
    doc_stage_model: str = "gpt-5-mini"
    ollama_base_url: str = "http://localhost:11434"
    proxy_list: list[str] = field(default_factory=list)
    scoring_threshold: int = 70
    rate_limit_min_seconds: int = 3
    rate_limit_max_seconds: int = 5
    resume_source_path: str = ""
    output_dir: str = "output"
    target_titles: list[str] = field(default_factory=lambda: ["software engineer", "python developer"])
    include_titles: list[str] = field(default_factory=lambda: ["software engineer", "python developer"])
    exclude_titles: list[str] = field(default_factory=lambda: ["principal", "sales", "designer"])
    force_escalate_keywords: list[str] = field(default_factory=lambda: ["python", "automation", "llm", "agent"])
    salary_floor: int = 0
    cheap_reject_threshold: int = 55
    cheap_escalate_threshold: int = 75
    final_apply_threshold: int = 80
    precheap_gate_enabled: bool = True
    precheap_gate_reject_threshold: int = 30
    skip_ai_scoring_in_semi_auto: bool = True
    fast_rank_min_score: int = 20
    cheap_ai_top_n: int = 8
    strong_ai_top_n: int = 3
    progressive_queue_enabled: bool = True
    enable_cost_tracking: bool = True
    scoring_max_workers: int = 4
    anthropic_api_key: str = ""
    openai_api_key: str = ""


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


def _normalize_stage_provider(value: Any, *, fallback: str, cheap_stage_provider: str, strong_stage_provider: str) -> str:
    normalized = str(value or fallback).strip().lower()
    aliases = {
        "cheap_stage": cheap_stage_provider,
        "strong_stage": strong_stage_provider,
        "doc_stage": fallback,
        "local": "ollama_local",
        "ollama": "ollama_local",
        "claude": "anthropic",
        "gpt": "openai",
    }
    return aliases.get(normalized, normalized)


def load_or_create_config(paths: AppPaths) -> JobBotConfig:
    ensure_app_dirs(paths)
    if not paths.config_file.exists():
        config = default_config()
        save_config(config, paths.config_file)
        return config

    with paths.config_file.open("r", encoding="utf-8") as handle:
        raw = _load_serialized_config(handle.read())

    cheap_stage_provider = _normalize_stage_provider(
        raw.get("cheap_stage_provider", "openai"),
        fallback="openai",
        cheap_stage_provider="ollama_local",
        strong_stage_provider=str(raw.get("strong_stage_provider", "anthropic")),
    )
    strong_stage_provider = _normalize_stage_provider(
        raw.get("strong_stage_provider", "anthropic"),
        fallback="anthropic",
        cheap_stage_provider=cheap_stage_provider,
        strong_stage_provider="anthropic",
    )
    doc_stage_provider = _normalize_stage_provider(
        raw.get("doc_stage_provider", "openai"),
        fallback="openai",
        cheap_stage_provider=cheap_stage_provider,
        strong_stage_provider=strong_stage_provider,
    )

    config = JobBotConfig(
        source=_merge_dataclass(SourceConfig, raw.get("source")),
        gmail=_merge_dataclass(GmailConfig, raw.get("gmail")),
        schedule=_merge_dataclass(ScheduleConfig, raw.get("schedule")),
        automation_mode=str(raw.get("automation_mode", "semi_auto")),
        llm_provider=str(raw.get("llm_provider", "anthropic")),
        cheap_stage_provider=cheap_stage_provider,
        cheap_stage_model=str(raw.get("cheap_stage_model", "gpt-5-nano")),
        strong_stage_provider=strong_stage_provider,
        strong_stage_model=str(raw.get("strong_stage_model", "claude-sonnet-4-20250514")),
        doc_stage_provider=doc_stage_provider,
        doc_stage_model=str(raw.get("doc_stage_model", "gpt-5-mini")),
        ollama_base_url=str(raw.get("ollama_base_url", "http://localhost:11434")),
        proxy_list=list(raw.get("proxy_list", [])),
        scoring_threshold=int(raw.get("scoring_threshold", 70)),
        rate_limit_min_seconds=int(raw.get("rate_limit_min_seconds", 3)),
        rate_limit_max_seconds=int(raw.get("rate_limit_max_seconds", 5)),
        resume_source_path=str(raw.get("resume_source_path", "")),
        output_dir=str(raw.get("output_dir", "output")),
        target_titles=list(raw.get("target_titles", ["software engineer", "python developer"])),
        include_titles=list(raw.get("include_titles", ["software engineer", "python developer"])),
        exclude_titles=list(raw.get("exclude_titles", ["principal", "sales", "designer"])),
        force_escalate_keywords=list(raw.get("force_escalate_keywords", ["python", "automation", "llm", "agent"])),
        salary_floor=int(raw.get("salary_floor", 0)),
        cheap_reject_threshold=int(raw.get("cheap_reject_threshold", 55)),
        cheap_escalate_threshold=int(raw.get("cheap_escalate_threshold", 75)),
        final_apply_threshold=int(raw.get("final_apply_threshold", 80)),
        precheap_gate_enabled=bool(raw.get("precheap_gate_enabled", True)),
        precheap_gate_reject_threshold=int(raw.get("precheap_gate_reject_threshold", 30)),
        skip_ai_scoring_in_semi_auto=bool(raw.get("skip_ai_scoring_in_semi_auto", True)),
        fast_rank_min_score=int(raw.get("fast_rank_min_score", 20) if raw.get("fast_rank_min_score") not in (None, 35) else 20),
        cheap_ai_top_n=int(raw.get("cheap_ai_top_n", 8)),
        strong_ai_top_n=int(raw.get("strong_ai_top_n", 3)),
        progressive_queue_enabled=bool(raw.get("progressive_queue_enabled", True)),
        enable_cost_tracking=bool(raw.get("enable_cost_tracking", True)),
        scoring_max_workers=int(raw.get("scoring_max_workers", 4)),
        anthropic_api_key=str(raw.get("anthropic_api_key", "")),
        openai_api_key=str(raw.get("openai_api_key", "")),
    )
    validate_config(config)
    normalized_payload = asdict(config)
    if normalized_payload != raw:
        try:
            save_config(config, paths.config_file)
        except PermissionError:
            LOGGER.warning("Config normalization could not be saved because the config file was unavailable.")
    return config


def validate_config(config: JobBotConfig) -> None:
    if config.rate_limit_min_seconds < 0 or config.rate_limit_max_seconds < config.rate_limit_min_seconds:
        raise ValueError("Invalid rate limit range")
    if not 0 <= config.scoring_threshold <= 100:
        raise ValueError("scoring_threshold must be between 0 and 100")
    if config.automation_mode not in {"semi_auto", "auto"}:
        raise ValueError("automation_mode must be 'semi_auto' or 'auto'")
    if config.llm_provider not in {"anthropic", "openai"}:
        raise ValueError("llm_provider must be 'anthropic' or 'openai'")
    if config.source.provider not in {"usajobs", "jobspy", "adzuna"}:
        raise ValueError("source.provider must be 'usajobs', 'jobspy', or 'adzuna'")
    if not config.source.jobspy_sites:
        raise ValueError("source.jobspy_sites must contain at least one site")
    if config.source.days_back <= 0:
        raise ValueError("source.days_back must be greater than 0")
    if not 0 <= config.fast_rank_min_score <= 100:
        raise ValueError("fast_rank_min_score must be between 0 and 100")
    if config.cheap_ai_top_n < 0:
        raise ValueError("cheap_ai_top_n must be >= 0")
    if config.strong_ai_top_n < 0:
        raise ValueError("strong_ai_top_n must be >= 0")
    if config.strong_ai_top_n > config.cheap_ai_top_n and config.cheap_ai_top_n > 0:
        raise ValueError("strong_ai_top_n must be <= cheap_ai_top_n")
    if config.cheap_stage_provider not in {"ollama_local", "openai", "anthropic"}:
        raise ValueError("cheap_stage_provider must be 'ollama_local', 'openai', or 'anthropic'")
    if config.strong_stage_provider not in {"openai", "anthropic"}:
        raise ValueError("strong_stage_provider must be 'openai' or 'anthropic'")
    if config.doc_stage_provider not in {"openai", "anthropic", "ollama_local"}:
        raise ValueError("doc_stage_provider must be 'openai', 'anthropic', or 'ollama_local'")
    if not 0 <= config.cheap_reject_threshold <= 100:
        raise ValueError("cheap_reject_threshold must be between 0 and 100")
    if not 0 <= config.cheap_escalate_threshold <= 100:
        raise ValueError("cheap_escalate_threshold must be between 0 and 100")
    if not 0 <= config.final_apply_threshold <= 100:
        raise ValueError("final_apply_threshold must be between 0 and 100")
    if not 0 <= config.precheap_gate_reject_threshold <= 100:
        raise ValueError("precheap_gate_reject_threshold must be between 0 and 100")
    if config.source.results_per_page <= 0:
        raise ValueError("source.results_per_page must be greater than 0")
    if config.cheap_reject_threshold > config.cheap_escalate_threshold:
        raise ValueError("cheap_reject_threshold must be <= cheap_escalate_threshold")
    if config.cheap_escalate_threshold > config.final_apply_threshold:
        raise ValueError("cheap_escalate_threshold must be <= final_apply_threshold (otherwise the strong stage can never produce an apply_candidate)")
    if config.schedule.start_hour_est < 0 or config.schedule.end_hour_est > 23:
        raise ValueError("Schedule hours must be between 0 and 23")
    if config.schedule.end_hour_est < config.schedule.start_hour_est:
        raise ValueError("Schedule end hour must be >= start hour")


def validate_config_for_run(config: JobBotConfig, paths: "AppPaths") -> None:
    """Validate that the config is ready to run a pipeline. Raises ConfigurationError with actionable messages."""
    errors: list[str] = []

    # Resume file must exist
    if config.resume_source_path.strip():
        resume_path = Path(config.resume_source_path.strip()).expanduser()
        if not resume_path.is_absolute():
            resume_path = paths.root / resume_path
        if not resume_path.exists():
            errors.append(f"Resume file not found: {resume_path}. Update 'Resume source' in Setup tab.")
    else:
        errors.append("No resume configured. Set 'Resume source' in the Setup tab.")

    # API keys must be present for non-Ollama providers that will actually be called.
    # In semi_auto mode: docs are generated manually after the run, so skip doc stage check.
    # In semi_auto + skip_ai_scoring: no AI calls happen at all during the run.
    is_semi_auto = config.automation_mode == "semi_auto"
    skip_ai_stages = is_semi_auto and config.skip_ai_scoring_in_semi_auto
    stages_to_check = []
    if not skip_ai_stages:
        stages_to_check += [
            ("cheap", "cheap_stage_provider", None),
            ("strong", "strong_stage_provider", None),
        ]
    if not is_semi_auto:
        stages_to_check.append(("doc", "doc_stage_provider", None))
    for stage_name, provider_attr, key_attr in stages_to_check:
        provider = getattr(config, f"{stage_name}_stage_provider")
        if provider == "anthropic":
            key = config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                errors.append(f"{stage_name.title()} stage uses Anthropic but no API key is set. Add it in the Setup tab or set ANTHROPIC_API_KEY env var.")
        elif provider == "openai":
            key = config.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
            if not key:
                errors.append(f"{stage_name.title()} stage uses OpenAI but no API key is set. Add it in the Setup tab or set OPENAI_API_KEY env var.")

    if errors:
        raise ValueError("Cannot start run:\n" + "\n".join(f"  • {e}" for e in errors))


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
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    active_log_path = log_file
    try:
        handlers.insert(0, logging.FileHandler(log_file, encoding="utf-8"))
    except PermissionError:
        fallback_name = f"{log_file.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{log_file.suffix}"
        fallback_path = log_file.with_name(fallback_name)
        try:
            handlers.insert(0, logging.FileHandler(fallback_path, encoding="utf-8"))
            active_log_path = fallback_path
        except PermissionError:
            active_log_path = None

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
    )
    if active_log_path is None:
        LOGGER.warning("Logging configured without file output because the log file was unavailable.")
    else:
        LOGGER.info("Logging configured at %s", active_log_path)


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
