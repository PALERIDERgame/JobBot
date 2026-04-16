from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Job:
    id: str
    title: str
    employer: str
    location: str
    salary_range: str
    description_full: str
    apply_method: str
    apply_url: str
    hiring_manager_email: str
    source: str
    posted_at: str
    scraped_at: str

    @staticmethod
    def build_id(employer: str, title: str, location: str) -> str:
        digest = hashlib.sha256(f"{employer}|{title}|{location}".lower().encode("utf-8"))
        return digest.hexdigest()


@dataclass(slots=True)
class StageEvaluationRecord:
    job_id: str
    stage_name: str
    resume_hash: str
    provider: str
    model: str
    prompt_version: str
    status: str
    decision: str
    score: int | None
    confidence: float | None
    rationale: str
    strengths: list[str]
    gaps: list[str]
    required_match_breakdown: dict[str, Any]
    missing_required_items: list[str]
    adjacent_transferable_strengths: list[str]
    red_flags: list[str]
    recommended_action: str
    resume_tailoring_focus: list[str]
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    cached: bool
    evaluated_at: str


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            try:
                self._connection.execute("PRAGMA journal_mode=WAL;")
            except sqlite3.OperationalError:
                self._connection.execute("PRAGMA journal_mode=DELETE;")
            self._connection.execute("PRAGMA synchronous=NORMAL;")
            self._connection.execute("PRAGMA temp_store=MEMORY;")
        return self._connection

    def initialize(self) -> None:
        connection = self.connect()
        cursor = connection.cursor()
        cursor.executescript(
            """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    employer TEXT NOT NULL,
                    location TEXT NOT NULL,
                    salary_range TEXT NOT NULL,
                    description_full TEXT NOT NULL,
                    apply_method TEXT NOT NULL,
                    apply_url TEXT NOT NULL,
                    hiring_manager_email TEXT NOT NULL,
                    source TEXT NOT NULL,
                    posted_at TEXT NOT NULL,
                    scraped_at TEXT NOT NULL,
                    raw_payload TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS run_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    jobs_seen INTEGER NOT NULL DEFAULT 0,
                    jobs_matched INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    jobs_seen INTEGER NOT NULL DEFAULT 0,
                    jobs_matched INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0,
                    fast_rank_candidates INTEGER NOT NULL DEFAULT 0,
                    fast_rank_survivors INTEGER NOT NULL DEFAULT 0,
                    cheap_shortlist_size INTEGER NOT NULL DEFAULT 0,
                    cheap_stage_duration_ms INTEGER NOT NULL DEFAULT 0,
                    cheap_stage_provider TEXT NOT NULL DEFAULT '',
                    cheap_stage_model TEXT NOT NULL DEFAULT '',
                    cheap_parse_failures INTEGER NOT NULL DEFAULT 0,
                    strong_shortlist_size INTEGER NOT NULL DEFAULT 0,
                    strong_stage_duration_ms INTEGER NOT NULL DEFAULT 0,
                    strong_stage_provider TEXT NOT NULL DEFAULT '',
                    strong_stage_model TEXT NOT NULL DEFAULT '',
                    strong_parse_failures INTEGER NOT NULL DEFAULT 0,
                    error_summary TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS match_results (
                    job_id TEXT PRIMARY KEY,
                    score INTEGER,
                    rationale TEXT NOT NULL DEFAULT '',
                    strengths TEXT NOT NULL DEFAULT '[]',
                    gaps TEXT NOT NULL DEFAULT '[]',
                    confidence REAL,
                    required_match_breakdown TEXT NOT NULL DEFAULT '{}',
                    missing_required_items TEXT NOT NULL DEFAULT '[]',
                    adjacent_transferable_strengths TEXT NOT NULL DEFAULT '[]',
                    red_flags TEXT NOT NULL DEFAULT '[]',
                    recommended_action TEXT NOT NULL DEFAULT '',
                    resume_tailoring_focus TEXT NOT NULL DEFAULT '[]',
                    gating_reason TEXT NOT NULL DEFAULT '',
                    policy_blocked INTEGER NOT NULL DEFAULT 0,
                    is_match INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    score_source TEXT NOT NULL DEFAULT '',
                    verification_stage TEXT NOT NULL DEFAULT '',
                    provisional_rank INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NOT NULL DEFAULT '',
                    scored_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS generated_documents (
                    job_id TEXT PRIMARY KEY,
                    output_dir TEXT NOT NULL,
                    resume_docx_path TEXT NOT NULL DEFAULT '',
                    resume_pdf_path TEXT NOT NULL DEFAULT '',
                    cover_letter_path TEXT NOT NULL DEFAULT '',
                    cover_letter_docx_path TEXT NOT NULL DEFAULT '',
                    cover_letter_pdf_path TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT NOT NULL DEFAULT '',
                    generated_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS deliveries (
                    job_id TEXT PRIMARY KEY,
                    method TEXT NOT NULL DEFAULT 'local',
                    status TEXT NOT NULL DEFAULT 'pending',
                    message_id TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    delivered_at TEXT NOT NULL DEFAULT '',
                    approval_log TEXT NOT NULL DEFAULT '',
                    approval_route TEXT NOT NULL DEFAULT '',
                    approval_docs_action TEXT NOT NULL DEFAULT '',
                    approval_portal_platform TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS ai_evaluations (
                    job_id TEXT NOT NULL,
                    stage_name TEXT NOT NULL,
                    resume_hash TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    decision TEXT NOT NULL DEFAULT '',
                    score INTEGER,
                    confidence REAL,
                    rationale TEXT NOT NULL DEFAULT '',
                    strengths TEXT NOT NULL DEFAULT '[]',
                    gaps TEXT NOT NULL DEFAULT '[]',
                    required_match_breakdown TEXT NOT NULL DEFAULT '{}',
                    missing_required_items TEXT NOT NULL DEFAULT '[]',
                    adjacent_transferable_strengths TEXT NOT NULL DEFAULT '[]',
                    red_flags TEXT NOT NULL DEFAULT '[]',
                    recommended_action TEXT NOT NULL DEFAULT '',
                    resume_tailoring_focus TEXT NOT NULL DEFAULT '[]',
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0,
                    cached INTEGER NOT NULL DEFAULT 0,
                    evaluated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(job_id, stage_name, resume_hash, provider, model, prompt_version),
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    noted_at TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at DESC);
                CREATE INDEX IF NOT EXISTS idx_match_results_status ON match_results(status);
                CREATE INDEX IF NOT EXISTS idx_ai_evaluations_job_stage ON ai_evaluations(job_id, stage_name);
                CREATE INDEX IF NOT EXISTS idx_outcomes_job_id ON outcomes(job_id);
                CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);
            """
        )
        self._ensure_column("generated_documents", "resume_docx_path", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "cover_letter_docx_path", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "cover_letter_pdf_path", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "tailoring_route", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "tailoring_provider", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "tailoring_model", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "tailoring_fallback_reason", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "tailoring_retry_count", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("generated_documents", "resume_ai_status", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "cover_letter_ai_status", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "rejected_bullets_repaired", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("generated_documents", "cover_letter_fallback", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "ai_validation_attempts", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("generated_documents", "resume_retry_performed", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("generated_documents", "cover_letter_retry_performed", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("generated_documents", "ai_repair_applied", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("generated_documents", "pdf_exporter_used", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("generated_documents", "page_fit_attempts", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("deliveries", "approval_log", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("deliveries", "approval_route", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("deliveries", "approval_docs_action", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("deliveries", "approval_portal_platform", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("match_results", "score_source", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("match_results", "verification_stage", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("match_results", "provisional_rank", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("match_results", "confidence", "REAL")
        self._ensure_column("match_results", "required_match_breakdown", "TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column("match_results", "missing_required_items", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("match_results", "adjacent_transferable_strengths", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("match_results", "red_flags", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("match_results", "recommended_action", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("match_results", "resume_tailoring_focus", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("match_results", "gating_reason", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("match_results", "policy_blocked", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("ai_evaluations", "required_match_breakdown", "TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column("ai_evaluations", "missing_required_items", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("ai_evaluations", "adjacent_transferable_strengths", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("ai_evaluations", "red_flags", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("ai_evaluations", "recommended_action", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("ai_evaluations", "resume_tailoring_focus", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("runs", "estimated_cost_usd", "REAL NOT NULL DEFAULT 0")
        self._ensure_column("runs", "fast_rank_candidates", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "fast_rank_survivors", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "cheap_shortlist_size", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "cheap_stage_duration_ms", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "cheap_stage_provider", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("runs", "cheap_stage_model", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("runs", "cheap_parse_failures", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "strong_shortlist_size", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "strong_stage_duration_ms", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "strong_stage_provider", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("runs", "strong_stage_model", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("runs", "strong_parse_failures", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "error_summary", "TEXT NOT NULL DEFAULT ''")
        connection.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        connection = self.connect()
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column in columns:
            return
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_run(self, started_at: str, stage: str, status: str = "running", message: str = "") -> int:
        connection = self.connect()
        with self._lock:
            cursor = connection.cursor()
            cursor.execute(
                """
                    INSERT INTO run_history (started_at, stage, status, message)
                    VALUES (?, ?, ?, ?)
                """,
                (started_at, stage, status, message),
            )
            run_id = int(cursor.lastrowid)
            connection.execute(
                """
                    INSERT INTO runs (id, started_at, stage, status, message)
                    VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, started_at, stage, status, message),
            )
            connection.commit()
            return run_id

    def update_run(
        self,
        run_id: int,
        *,
        ended_at: str | None = None,
        status: str | None = None,
        stage: str | None = None,
        message: str | None = None,
        jobs_seen: int | None = None,
        jobs_matched: int | None = None,
        estimated_cost_usd: float | None = None,
        fast_rank_candidates: int | None = None,
        fast_rank_survivors: int | None = None,
        cheap_shortlist_size: int | None = None,
        cheap_stage_duration_ms: int | None = None,
        cheap_stage_provider: str | None = None,
        cheap_stage_model: str | None = None,
        cheap_parse_failures: int | None = None,
        strong_shortlist_size: int | None = None,
        strong_stage_duration_ms: int | None = None,
        strong_stage_provider: str | None = None,
        strong_stage_model: str | None = None,
        strong_parse_failures: int | None = None,
        error_summary: str | None = None,
    ) -> None:
        history_assignments: list[str] = []
        history_params: list[Any] = []
        runs_assignments: list[str] = []
        runs_params: list[Any] = []
        for column, value in (
            ("ended_at", ended_at),
            ("status", status),
            ("stage", stage),
            ("message", message),
            ("jobs_seen", jobs_seen),
            ("jobs_matched", jobs_matched),
        ):
            if value is not None:
                runs_assignments.append(f"{column} = ?")
                runs_params.append(value)
                history_assignments.append(f"{column} = ?")
                history_params.append(value)
        for column, value in (
            ("estimated_cost_usd", estimated_cost_usd),
            ("fast_rank_candidates", fast_rank_candidates),
            ("fast_rank_survivors", fast_rank_survivors),
            ("cheap_shortlist_size", cheap_shortlist_size),
            ("cheap_stage_duration_ms", cheap_stage_duration_ms),
            ("cheap_stage_provider", cheap_stage_provider),
            ("cheap_stage_model", cheap_stage_model),
            ("cheap_parse_failures", cheap_parse_failures),
            ("strong_shortlist_size", strong_shortlist_size),
            ("strong_stage_duration_ms", strong_stage_duration_ms),
            ("strong_stage_provider", strong_stage_provider),
            ("strong_stage_model", strong_stage_model),
            ("strong_parse_failures", strong_parse_failures),
            ("error_summary", error_summary),
        ):
            if value is not None:
                runs_assignments.append(f"{column} = ?")
                runs_params.append(value)
        if not history_assignments and not runs_assignments:
            return
        connection = self.connect()
        with self._lock:
            if history_assignments:
                history_params.append(run_id)
                connection.execute(
                    f"UPDATE run_history SET {', '.join(history_assignments)} WHERE id = ?",
                    history_params,
                )
            if runs_assignments:
                runs_params.append(run_id)
                connection.execute(
                    f"UPDATE runs SET {', '.join(runs_assignments)} WHERE id = ?",
                    runs_params,
                )
            connection.commit()

    def upsert_job(self, job: Job, raw_payload: dict[str, Any] | None = None) -> None:
        payload = json.dumps(raw_payload or {}, ensure_ascii=True, default=str)
        connection = self.connect()
        with self._lock:
            connection.execute(
                """
                    INSERT INTO jobs (
                        id, title, employer, location, salary_range, description_full,
                        apply_method, apply_url, hiring_manager_email, source, posted_at,
                        scraped_at, raw_payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        employer=excluded.employer,
                        location=excluded.location,
                        salary_range=excluded.salary_range,
                        description_full=excluded.description_full,
                        apply_method=excluded.apply_method,
                        apply_url=excluded.apply_url,
                        hiring_manager_email=excluded.hiring_manager_email,
                        source=excluded.source,
                        posted_at=excluded.posted_at,
                        scraped_at=excluded.scraped_at,
                        raw_payload=excluded.raw_payload
                """,
                (
                    job.id,
                    job.title,
                    job.employer,
                    job.location,
                    job.salary_range,
                    job.description_full,
                    job.apply_method,
                    job.apply_url,
                    job.hiring_manager_email,
                    job.source,
                    job.posted_at,
                    job.scraped_at,
                    payload,
                ),
            )
            connection.commit()

    def record_match_result(
        self,
        job_id: str,
        *,
        score: int | None,
        rationale: str,
        strengths: list[str],
        gaps: list[str],
        confidence: float | None = None,
        required_match_breakdown: dict[str, Any] | None = None,
        missing_required_items: list[str] | None = None,
        adjacent_transferable_strengths: list[str] | None = None,
        red_flags: list[str] | None = None,
        recommended_action: str = "",
        resume_tailoring_focus: list[str] | None = None,
        gating_reason: str = "",
        policy_blocked: bool = False,
        is_match: bool,
        status: str,
        score_source: str = "",
        verification_stage: str = "",
        provisional_rank: int = 0,
        error_message: str,
        scored_at: str,
    ) -> None:
        connection = self.connect()
        with self._lock:
            connection.execute(
                """
                    INSERT INTO match_results (
                        job_id, score, rationale, strengths, gaps, confidence, required_match_breakdown,
                        missing_required_items, adjacent_transferable_strengths, red_flags, recommended_action,
                        resume_tailoring_focus, gating_reason, policy_blocked, is_match, status, score_source,
                        verification_stage, provisional_rank, error_message, scored_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        score=excluded.score,
                        rationale=excluded.rationale,
                        strengths=excluded.strengths,
                        gaps=excluded.gaps,
                        confidence=excluded.confidence,
                        required_match_breakdown=excluded.required_match_breakdown,
                        missing_required_items=excluded.missing_required_items,
                        adjacent_transferable_strengths=excluded.adjacent_transferable_strengths,
                        red_flags=excluded.red_flags,
                        recommended_action=excluded.recommended_action,
                        resume_tailoring_focus=excluded.resume_tailoring_focus,
                        gating_reason=excluded.gating_reason,
                        policy_blocked=excluded.policy_blocked,
                        is_match=excluded.is_match,
                        status=excluded.status,
                        score_source=excluded.score_source,
                        verification_stage=excluded.verification_stage,
                        provisional_rank=excluded.provisional_rank,
                        error_message=excluded.error_message,
                        scored_at=excluded.scored_at
                """,
                (
                    job_id,
                    score,
                    rationale,
                    json.dumps(strengths, ensure_ascii=True),
                    json.dumps(gaps, ensure_ascii=True),
                    confidence,
                    json.dumps(required_match_breakdown or {}, ensure_ascii=True),
                    json.dumps(missing_required_items or [], ensure_ascii=True),
                    json.dumps(adjacent_transferable_strengths or [], ensure_ascii=True),
                    json.dumps(red_flags or [], ensure_ascii=True),
                    recommended_action,
                    json.dumps(resume_tailoring_focus or [], ensure_ascii=True),
                    gating_reason,
                    int(policy_blocked),
                    int(is_match),
                    status,
                    score_source,
                    verification_stage,
                    provisional_rank,
                    error_message,
                    scored_at,
                ),
            )
            connection.commit()

    def record_generated_documents(
        self,
        job_id: str,
        *,
        output_dir: str,
        resume_docx_path: str,
        resume_pdf_path: str,
        cover_letter_path: str,
        cover_letter_docx_path: str = "",
        cover_letter_pdf_path: str = "",
        status: str,
        error_message: str,
        generated_at: str,
        tailoring_route: str = "",
        tailoring_provider: str = "",
        tailoring_model: str = "",
        tailoring_fallback_reason: str = "",
        tailoring_retry_count: int = 0,
        resume_ai_status: str = "",
        cover_letter_ai_status: str = "",
        rejected_bullets_repaired: int = 0,
        cover_letter_fallback: str = "",
        ai_validation_attempts: int = 0,
        resume_retry_performed: bool = False,
        cover_letter_retry_performed: bool = False,
        ai_repair_applied: bool = False,
        pdf_exporter_used: str = "",
        page_fit_attempts: int = 0,
    ) -> None:
        connection = self.connect()
        with self._lock:
            connection.execute(
                """
                    INSERT INTO generated_documents (
                        job_id, output_dir, resume_docx_path, resume_pdf_path, cover_letter_path, cover_letter_docx_path, cover_letter_pdf_path,
                        status, error_message, generated_at,
                        tailoring_route, tailoring_provider, tailoring_model,
                        tailoring_fallback_reason, tailoring_retry_count,
                        resume_ai_status, cover_letter_ai_status, rejected_bullets_repaired, cover_letter_fallback,
                        ai_validation_attempts, resume_retry_performed, cover_letter_retry_performed, ai_repair_applied,
                        pdf_exporter_used, page_fit_attempts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        output_dir=excluded.output_dir,
                        resume_docx_path=excluded.resume_docx_path,
                        resume_pdf_path=excluded.resume_pdf_path,
                        cover_letter_path=excluded.cover_letter_path,
                        cover_letter_docx_path=excluded.cover_letter_docx_path,
                        cover_letter_pdf_path=excluded.cover_letter_pdf_path,
                        status=excluded.status,
                        error_message=excluded.error_message,
                        generated_at=excluded.generated_at,
                        tailoring_route=excluded.tailoring_route,
                        tailoring_provider=excluded.tailoring_provider,
                        tailoring_model=excluded.tailoring_model,
                        tailoring_fallback_reason=excluded.tailoring_fallback_reason,
                        tailoring_retry_count=excluded.tailoring_retry_count,
                        resume_ai_status=excluded.resume_ai_status,
                        cover_letter_ai_status=excluded.cover_letter_ai_status,
                        rejected_bullets_repaired=excluded.rejected_bullets_repaired,
                        cover_letter_fallback=excluded.cover_letter_fallback,
                        ai_validation_attempts=excluded.ai_validation_attempts,
                        resume_retry_performed=excluded.resume_retry_performed,
                        cover_letter_retry_performed=excluded.cover_letter_retry_performed,
                        ai_repair_applied=excluded.ai_repair_applied,
                        pdf_exporter_used=excluded.pdf_exporter_used,
                        page_fit_attempts=excluded.page_fit_attempts
                """,
                (
                    job_id, output_dir, resume_docx_path, resume_pdf_path, cover_letter_path, cover_letter_docx_path, cover_letter_pdf_path,
                    status, error_message, generated_at,
                    tailoring_route, tailoring_provider, tailoring_model,
                    tailoring_fallback_reason, tailoring_retry_count,
                    resume_ai_status, cover_letter_ai_status, rejected_bullets_repaired, cover_letter_fallback,
                    ai_validation_attempts, int(resume_retry_performed), int(cover_letter_retry_performed), int(ai_repair_applied),
                    pdf_exporter_used, page_fit_attempts,
                ),
            )
            connection.commit()

    def record_delivery(
        self,
        job_id: str,
        *,
        method: str,
        status: str,
        message_id: str,
        error_message: str,
        delivered_at: str,
        approval_log: str = "",
        approval_route: str = "",
        approval_docs_action: str = "",
        approval_portal_platform: str = "",
    ) -> None:
        connection = self.connect()
        with self._lock:
            connection.execute(
                """
                    INSERT INTO deliveries (
                        job_id, method, status, message_id, error_message, delivered_at,
                        approval_log, approval_route, approval_docs_action, approval_portal_platform
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        method=excluded.method,
                        status=excluded.status,
                        message_id=excluded.message_id,
                        error_message=excluded.error_message,
                        delivered_at=excluded.delivered_at,
                        approval_log=excluded.approval_log,
                        approval_route=excluded.approval_route,
                        approval_docs_action=excluded.approval_docs_action,
                        approval_portal_platform=excluded.approval_portal_platform
                """,
                (
                    job_id,
                    method,
                    status,
                    message_id,
                    error_message,
                    delivered_at,
                    approval_log,
                    approval_route,
                    approval_docs_action,
                    approval_portal_platform,
                ),
            )
            connection.commit()

    def upsert_ai_evaluation(self, record: StageEvaluationRecord) -> None:
        connection = self.connect()
        with self._lock:
            connection.execute(
                """
                    INSERT INTO ai_evaluations (
                        job_id, stage_name, resume_hash, provider, model, prompt_version,
                        status, decision, score, confidence, rationale, strengths, gaps, required_match_breakdown,
                        missing_required_items, adjacent_transferable_strengths, red_flags, recommended_action,
                        resume_tailoring_focus, input_tokens, output_tokens, estimated_cost_usd, cached, evaluated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id, stage_name, resume_hash, provider, model, prompt_version) DO UPDATE SET
                        status=excluded.status,
                        decision=excluded.decision,
                        score=excluded.score,
                        confidence=excluded.confidence,
                        rationale=excluded.rationale,
                        strengths=excluded.strengths,
                        gaps=excluded.gaps,
                        required_match_breakdown=excluded.required_match_breakdown,
                        missing_required_items=excluded.missing_required_items,
                        adjacent_transferable_strengths=excluded.adjacent_transferable_strengths,
                        red_flags=excluded.red_flags,
                        recommended_action=excluded.recommended_action,
                        resume_tailoring_focus=excluded.resume_tailoring_focus,
                        input_tokens=excluded.input_tokens,
                        output_tokens=excluded.output_tokens,
                        estimated_cost_usd=excluded.estimated_cost_usd,
                        cached=excluded.cached,
                        evaluated_at=excluded.evaluated_at
                """,
                (
                    record.job_id,
                    record.stage_name,
                    record.resume_hash,
                    record.provider,
                    record.model,
                    record.prompt_version,
                    record.status,
                    record.decision,
                    record.score,
                    record.confidence,
                    record.rationale,
                    json.dumps(record.strengths, ensure_ascii=True),
                    json.dumps(record.gaps, ensure_ascii=True),
                    json.dumps(record.required_match_breakdown, ensure_ascii=True),
                    json.dumps(record.missing_required_items, ensure_ascii=True),
                    json.dumps(record.adjacent_transferable_strengths, ensure_ascii=True),
                    json.dumps(record.red_flags, ensure_ascii=True),
                    record.recommended_action,
                    json.dumps(record.resume_tailoring_focus, ensure_ascii=True),
                    record.input_tokens,
                    record.output_tokens,
                    record.estimated_cost_usd,
                    int(record.cached),
                    record.evaluated_at,
                ),
            )
            connection.commit()

    def get_ai_evaluation(
        self,
        job_id: str,
        *,
        stage_name: str,
        resume_hash: str,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> StageEvaluationRecord | None:
        connection = self.connect()
        row = connection.execute(
            """
            SELECT * FROM ai_evaluations
            WHERE job_id = ? AND stage_name = ? AND resume_hash = ? AND provider = ? AND model = ? AND prompt_version = ?
            """,
            (job_id, stage_name, resume_hash, provider, model, prompt_version),
        ).fetchone()
        if not row:
            return None
        payload = dict(row)
        return StageEvaluationRecord(
            job_id=payload["job_id"],
            stage_name=payload["stage_name"],
            resume_hash=payload["resume_hash"],
            provider=payload["provider"],
            model=payload["model"],
            prompt_version=payload["prompt_version"],
            status=payload["status"],
            decision=payload["decision"],
            score=payload["score"],
            confidence=payload["confidence"],
            rationale=payload["rationale"],
            strengths=json.loads(payload["strengths"]),
            gaps=json.loads(payload["gaps"]),
            required_match_breakdown=json.loads(payload.get("required_match_breakdown") or "{}"),
            missing_required_items=json.loads(payload.get("missing_required_items") or "[]"),
            adjacent_transferable_strengths=json.loads(payload.get("adjacent_transferable_strengths") or "[]"),
            red_flags=json.loads(payload.get("red_flags") or "[]"),
            recommended_action=payload.get("recommended_action", ""),
            resume_tailoring_focus=json.loads(payload.get("resume_tailoring_focus") or "[]"),
            input_tokens=payload["input_tokens"],
            output_tokens=payload["output_tokens"],
            estimated_cost_usd=float(payload["estimated_cost_usd"]),
            cached=bool(payload["cached"]),
            evaluated_at=payload["evaluated_at"],
        )

    def summarize_costs(self) -> list[dict[str, Any]]:
        connection = self.connect()
        rows = connection.execute(
            """
            SELECT stage_name, COUNT(*) AS evaluations, ROUND(SUM(estimated_cost_usd), 4) AS total_cost
            FROM ai_evaluations
            GROUP BY stage_name
            ORDER BY stage_name
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_review_rows(self, *, min_scraped_at: str | None = None) -> list[dict[str, Any]]:
        query = """
        SELECT
            jobs.id,
            jobs.title,
            jobs.employer,
            jobs.location,
            jobs.posted_at,
            jobs.scraped_at,
            jobs.description_full,
            jobs.source,
            jobs.apply_method,
            jobs.apply_url,
            jobs.hiring_manager_email,
            COALESCE(match_results.score, 0) AS score,
            COALESCE(match_results.rationale, '') AS rationale,
            COALESCE(match_results.status, 'pending') AS match_status,
            COALESCE(match_results.score_source, '') AS score_source,
            COALESCE(match_results.verification_stage, '') AS verification_stage,
            COALESCE(match_results.provisional_rank, 0) AS provisional_rank,
            COALESCE(match_results.confidence, 0) AS confidence,
            COALESCE(match_results.required_match_breakdown, '{}') AS required_match_breakdown,
            COALESCE(match_results.missing_required_items, '[]') AS missing_required_items,
            COALESCE(match_results.adjacent_transferable_strengths, '[]') AS adjacent_transferable_strengths,
            COALESCE(match_results.red_flags, '[]') AS red_flags,
            COALESCE(match_results.recommended_action, '') AS recommended_action,
            COALESCE(match_results.resume_tailoring_focus, '[]') AS resume_tailoring_focus,
            COALESCE(match_results.gating_reason, '') AS gating_reason,
            COALESCE(match_results.policy_blocked, 0) AS policy_blocked,
            COALESCE(generated_documents.resume_docx_path, '') AS resume_docx_path,
            COALESCE(generated_documents.resume_pdf_path, '') AS resume_pdf_path,
            COALESCE(generated_documents.cover_letter_path, '') AS cover_letter_path,
            COALESCE(generated_documents.cover_letter_docx_path, '') AS cover_letter_docx_path,
            COALESCE(generated_documents.cover_letter_pdf_path, '') AS cover_letter_pdf_path,
            COALESCE(generated_documents.status, 'pending') AS document_status,
            COALESCE(generated_documents.error_message, '') AS document_error,
            COALESCE(generated_documents.generated_at, '') AS generated_at,
            COALESCE(deliveries.status, 'pending') AS delivery_status
            ,COALESCE(deliveries.approval_log, '') AS approval_log
        FROM jobs
        LEFT JOIN match_results ON match_results.job_id = jobs.id
        LEFT JOIN generated_documents ON generated_documents.job_id = jobs.id
        LEFT JOIN deliveries ON deliveries.job_id = jobs.id
        """
        connection = self.connect()
        params: tuple[Any, ...] = ()
        if min_scraped_at:
            query += " WHERE jobs.scraped_at >= ?"
            params = (min_scraped_at,)
            query += " AND COALESCE(deliveries.status, 'pending') != 'skipped' AND COALESCE(match_results.status, 'pending') NOT IN ('skipped', 'reject', 'error')"
        else:
            query += " WHERE COALESCE(deliveries.status, 'pending') != 'skipped' AND COALESCE(match_results.status, 'pending') NOT IN ('skipped', 'reject', 'error')"
        query += """
        ORDER BY
            CASE COALESCE(match_results.verification_stage, '')
                WHEN 'strong_verified' THEN 3
                WHEN 'cheap_verified' THEN 2
                WHEN 'fast_ranked' THEN 1
                ELSE 0
            END DESC,
            COALESCE(match_results.score, 0) DESC,
            jobs.scraped_at DESC
        """
        rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_review_row(self, job_id: str) -> dict[str, Any] | None:
        connection = self.connect()
        row = connection.execute(
            """
            SELECT
                jobs.id,
                jobs.title,
                jobs.employer,
                jobs.location,
                jobs.posted_at,
                jobs.scraped_at,
                jobs.description_full,
                jobs.source,
                jobs.apply_method,
                jobs.apply_url,
                jobs.hiring_manager_email,
                COALESCE(match_results.score, 0) AS score,
                COALESCE(match_results.rationale, '') AS rationale,
                COALESCE(match_results.status, 'pending') AS match_status,
                COALESCE(match_results.score_source, '') AS score_source,
                COALESCE(match_results.verification_stage, '') AS verification_stage,
                COALESCE(match_results.provisional_rank, 0) AS provisional_rank,
                COALESCE(match_results.confidence, 0) AS confidence,
                COALESCE(match_results.required_match_breakdown, '{}') AS required_match_breakdown,
                COALESCE(match_results.missing_required_items, '[]') AS missing_required_items,
                COALESCE(match_results.adjacent_transferable_strengths, '[]') AS adjacent_transferable_strengths,
                COALESCE(match_results.red_flags, '[]') AS red_flags,
                COALESCE(match_results.recommended_action, '') AS recommended_action,
                COALESCE(match_results.resume_tailoring_focus, '[]') AS resume_tailoring_focus,
                COALESCE(match_results.gating_reason, '') AS gating_reason,
                COALESCE(match_results.policy_blocked, 0) AS policy_blocked,
                COALESCE(generated_documents.output_dir, '') AS output_dir,
                COALESCE(generated_documents.resume_docx_path, '') AS resume_docx_path,
                COALESCE(generated_documents.resume_pdf_path, '') AS resume_pdf_path,
                COALESCE(generated_documents.cover_letter_path, '') AS cover_letter_path,
                COALESCE(generated_documents.cover_letter_docx_path, '') AS cover_letter_docx_path,
                COALESCE(generated_documents.cover_letter_pdf_path, '') AS cover_letter_pdf_path,
                COALESCE(generated_documents.status, 'pending') AS document_status,
                COALESCE(generated_documents.error_message, '') AS document_error,
                COALESCE(generated_documents.generated_at, '') AS generated_at,
                COALESCE(generated_documents.tailoring_route, '') AS tailoring_route,
                COALESCE(generated_documents.tailoring_provider, '') AS tailoring_provider,
                COALESCE(generated_documents.tailoring_model, '') AS tailoring_model,
                COALESCE(generated_documents.tailoring_fallback_reason, '') AS tailoring_fallback_reason,
                COALESCE(generated_documents.tailoring_retry_count, 0) AS tailoring_retry_count,
                COALESCE(generated_documents.resume_ai_status, '') AS resume_ai_status,
                COALESCE(generated_documents.cover_letter_ai_status, '') AS cover_letter_ai_status,
                COALESCE(generated_documents.rejected_bullets_repaired, 0) AS rejected_bullets_repaired,
                COALESCE(generated_documents.cover_letter_fallback, '') AS cover_letter_fallback,
                COALESCE(generated_documents.ai_validation_attempts, 0) AS ai_validation_attempts,
                COALESCE(generated_documents.resume_retry_performed, 0) AS resume_retry_performed,
                COALESCE(generated_documents.cover_letter_retry_performed, 0) AS cover_letter_retry_performed,
                COALESCE(generated_documents.ai_repair_applied, 0) AS ai_repair_applied,
                COALESCE(generated_documents.pdf_exporter_used, '') AS pdf_exporter_used,
                COALESCE(generated_documents.page_fit_attempts, 0) AS page_fit_attempts,
                COALESCE(deliveries.method, 'local') AS delivery_method,
                COALESCE(deliveries.status, 'pending') AS delivery_status,
                COALESCE(deliveries.message_id, '') AS message_id,
                COALESCE(deliveries.error_message, '') AS delivery_error,
                COALESCE(deliveries.approval_log, '') AS approval_log,
                COALESCE(deliveries.approval_route, '') AS approval_route,
                COALESCE(deliveries.approval_docs_action, '') AS approval_docs_action,
                COALESCE(deliveries.approval_portal_platform, '') AS approval_portal_platform
            FROM jobs
            LEFT JOIN match_results ON match_results.job_id = jobs.id
            LEFT JOIN generated_documents ON generated_documents.job_id = jobs.id
            LEFT JOIN deliveries ON deliveries.job_id = jobs.id
            WHERE jobs.id = ?
            """,
            (job_id,),
        ).fetchone()
        return dict(row) if row else None

    def recent_job_ids(self, *, hours: int = 24, before_scraped_at: str | None = None) -> set[str]:
        cutoff = (datetime.now(timezone.utc)).timestamp() - (hours * 3600)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        query = "SELECT id FROM jobs WHERE scraped_at >= ?"
        params: list[Any] = [cutoff_iso]
        if before_scraped_at:
            query += " AND scraped_at <= ?"
            params.append(before_scraped_at)
        connection = self.connect()
        rows = connection.execute(query, tuple(params)).fetchall()
        return {str(row["id"]) for row in rows}

    def latest_run(self) -> dict[str, Any] | None:
        connection = self.connect()
        row = connection.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return dict(row)
        row = connection.execute(
            "SELECT * FROM run_history ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def recent_runs(self, *, limit: int = 10) -> list[dict[str, Any]]:
        connection = self.connect()
        rows = connection.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_outcome(self, job_id: str, outcome: str, notes: str = "") -> None:
        noted_at = datetime.now(timezone.utc).isoformat()
        connection = self.connect()
        with self._lock:
            connection.execute(
                "INSERT INTO outcomes (job_id, outcome, noted_at, notes) VALUES (?, ?, ?, ?)",
                (job_id, outcome, noted_at, notes),
            )
            connection.commit()

    def get_outcomes_summary(self) -> dict[str, Any]:
        connection = self.connect()
        rows = connection.execute(
            "SELECT outcome, COUNT(*) AS count FROM outcomes GROUP BY outcome"
        ).fetchall()
        outcome_counts = {str(row["outcome"]): int(row["count"]) for row in rows}
        total_applied = connection.execute(
            "SELECT COUNT(*) AS n FROM deliveries WHERE status IN ('sent', 'pending_approval')"
        ).fetchone()
        total_with_outcome = connection.execute(
            "SELECT COUNT(DISTINCT job_id) AS n FROM outcomes"
        ).fetchone()
        positive = sum(outcome_counts.get(k, 0) for k in ("phone_screen", "interview", "offer"))
        total_tracked = int(total_with_outcome["n"]) if total_with_outcome else 0
        response_rate = round(positive / total_tracked * 100, 1) if total_tracked > 0 else 0.0
        return {
            "total_applied": int(total_applied["n"]) if total_applied else 0,
            "total_with_outcome": total_tracked,
            "response_rate_pct": response_rate,
            "by_outcome": outcome_counts,
        }

    def get_latest_outcome(self, job_id: str) -> str | None:
        connection = self.connect()
        row = connection.execute(
            "SELECT outcome FROM outcomes WHERE job_id = ? ORDER BY noted_at DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        return str(row["outcome"]) if row else None

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __del__(self) -> None:  # pragma: no cover
        self.close()
