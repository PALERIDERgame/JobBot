from __future__ import annotations

import hashlib
import json
import sqlite3
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


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=MEMORY;")
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

                CREATE TABLE IF NOT EXISTS match_results (
                    job_id TEXT PRIMARY KEY,
                    score INTEGER,
                    rationale TEXT NOT NULL DEFAULT '',
                    strengths TEXT NOT NULL DEFAULT '[]',
                    gaps TEXT NOT NULL DEFAULT '[]',
                    is_match INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT NOT NULL DEFAULT '',
                    scored_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS generated_documents (
                    job_id TEXT PRIMARY KEY,
                    output_dir TEXT NOT NULL,
                    resume_pdf_path TEXT NOT NULL DEFAULT '',
                    cover_letter_path TEXT NOT NULL DEFAULT '',
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
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
            """
        )
        connection.commit()

    def create_run(self, started_at: str, stage: str, status: str = "running", message: str = "") -> int:
        connection = self.connect()
        cursor = connection.cursor()
        cursor.execute(
            """
                INSERT INTO run_history (started_at, stage, status, message)
                VALUES (?, ?, ?, ?)
            """,
            (started_at, stage, status, message),
        )
        connection.commit()
        return int(cursor.lastrowid)

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
    ) -> None:
        assignments: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("ended_at", ended_at),
            ("status", status),
            ("stage", stage),
            ("message", message),
            ("jobs_seen", jobs_seen),
            ("jobs_matched", jobs_matched),
        ):
            if value is not None:
                assignments.append(f"{column} = ?")
                params.append(value)
        if not assignments:
            return
        params.append(run_id)
        connection = self.connect()
        connection.execute(
            f"UPDATE run_history SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        connection.commit()

    def upsert_job(self, job: Job, raw_payload: dict[str, Any] | None = None) -> None:
        payload = json.dumps(raw_payload or {}, ensure_ascii=True)
        connection = self.connect()
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
        is_match: bool,
        status: str,
        error_message: str,
        scored_at: str,
    ) -> None:
        connection = self.connect()
        connection.execute(
            """
                INSERT INTO match_results (
                    job_id, score, rationale, strengths, gaps, is_match, status, error_message, scored_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    score=excluded.score,
                    rationale=excluded.rationale,
                    strengths=excluded.strengths,
                    gaps=excluded.gaps,
                    is_match=excluded.is_match,
                    status=excluded.status,
                    error_message=excluded.error_message,
                    scored_at=excluded.scored_at
            """,
            (
                job_id,
                score,
                rationale,
                json.dumps(strengths, ensure_ascii=True),
                json.dumps(gaps, ensure_ascii=True),
                int(is_match),
                status,
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
        resume_pdf_path: str,
        cover_letter_path: str,
        status: str,
        error_message: str,
        generated_at: str,
    ) -> None:
        connection = self.connect()
        connection.execute(
            """
                INSERT INTO generated_documents (
                    job_id, output_dir, resume_pdf_path, cover_letter_path, status, error_message, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    output_dir=excluded.output_dir,
                    resume_pdf_path=excluded.resume_pdf_path,
                    cover_letter_path=excluded.cover_letter_path,
                    status=excluded.status,
                    error_message=excluded.error_message,
                    generated_at=excluded.generated_at
            """,
            (job_id, output_dir, resume_pdf_path, cover_letter_path, status, error_message, generated_at),
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
    ) -> None:
        connection = self.connect()
        connection.execute(
            """
                INSERT INTO deliveries (job_id, method, status, message_id, error_message, delivered_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    method=excluded.method,
                    status=excluded.status,
                    message_id=excluded.message_id,
                    error_message=excluded.error_message,
                    delivered_at=excluded.delivered_at
            """,
            (job_id, method, status, message_id, error_message, delivered_at),
        )
        connection.commit()

    def list_review_rows(self) -> list[dict[str, Any]]:
        query = """
        SELECT
            jobs.id,
            jobs.title,
            jobs.employer,
            jobs.location,
            jobs.source,
            jobs.apply_url,
            COALESCE(match_results.score, 0) AS score,
            COALESCE(match_results.rationale, '') AS rationale,
            COALESCE(match_results.status, 'pending') AS match_status,
            COALESCE(generated_documents.resume_pdf_path, '') AS resume_pdf_path,
            COALESCE(generated_documents.cover_letter_path, '') AS cover_letter_path,
            COALESCE(generated_documents.status, 'pending') AS document_status,
            COALESCE(deliveries.status, 'pending') AS delivery_status
        FROM jobs
        LEFT JOIN match_results ON match_results.job_id = jobs.id
        LEFT JOIN generated_documents ON generated_documents.job_id = jobs.id
        LEFT JOIN deliveries ON deliveries.job_id = jobs.id
        ORDER BY COALESCE(match_results.score, 0) DESC, jobs.scraped_at DESC
        """
        connection = self.connect()
        rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    def latest_run(self) -> dict[str, Any] | None:
        connection = self.connect()
        row = connection.execute(
            "SELECT * FROM run_history ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __del__(self) -> None:  # pragma: no cover
        self.close()
