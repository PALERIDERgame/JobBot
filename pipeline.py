from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import AppPaths, JobBotConfig, resolve_output_dir
from database import Database, Job
from doc_generator import DocumentGenerator, GeneratedDocs
from gmail_client import DeliveryResult, GmailClient
from match_scorer import MatchScore, MatchScorer
from resume_parser import ResumeData, load_cached_resume, parse_resume
from scrapers.scraper_router import ScraperRouter
from title_classifier import is_target_title


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineResult:
    run_id: int
    status: str
    jobs_seen: int
    jobs_matched: int
    message: str


class JobBotPipeline:
    def __init__(self, config: JobBotConfig, paths: AppPaths, database: Database) -> None:
        self.config = config
        self.paths = paths
        self.database = database
        self.scraper = ScraperRouter(config)
        self.scorer = MatchScorer(config)
        self.doc_generator = DocumentGenerator()
        self.gmail_client = GmailClient(config.gmail, paths.token_file)

    def run(self) -> PipelineResult:
        started_at = datetime.now(timezone.utc).isoformat()
        run_id = self.database.create_run(started_at, stage="starting")
        jobs_seen = 0
        jobs_matched = 0
        try:
            resume = self._load_resume()
            self.database.update_run(run_id, stage="scraping", message="Fetching jobs")
            fetched = self.scraper.fetch_jobs()
            jobs_seen = len(fetched)
            for job, raw_payload in fetched:
                self.database.upsert_job(job, raw_payload)

            self.database.update_run(run_id, stage="scoring", message="Scoring candidate matches", jobs_seen=jobs_seen)
            output_dir = resolve_output_dir(self.config, self.paths)
            output_dir.mkdir(parents=True, exist_ok=True)

            for job, _raw_payload in fetched:
                if not is_target_title(job, self.config.target_titles):
                    self._record_skipped_match(job)
                    continue

                score = self.scorer.score_job(job, resume)
                self.database.record_match_result(
                    job.id,
                    score=score.score,
                    rationale=score.rationale,
                    strengths=score.strengths,
                    gaps=score.gaps,
                    is_match=score.is_match,
                    status=score.status,
                    error_message=score.error_message,
                    scored_at=score.scored_at,
                )
                if score.status != "scored" or not score.is_match:
                    continue

                docs = self._generate_documents(job, resume, score, output_dir)
                jobs_matched += 1
                delivery = self._deliver(job, score, docs)
                self.database.record_delivery(
                    job.id,
                    method=delivery.method,
                    status=delivery.status,
                    message_id=delivery.message_id,
                    error_message=delivery.error_message,
                    delivered_at=datetime.now(timezone.utc).isoformat(),
                )

            finished_at = datetime.now(timezone.utc).isoformat()
            self.database.update_run(
                run_id,
                ended_at=finished_at,
                status="completed",
                stage="completed",
                message="Run completed",
                jobs_seen=jobs_seen,
                jobs_matched=jobs_matched,
            )
            return PipelineResult(run_id, "completed", jobs_seen, jobs_matched, "Run completed")
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Pipeline run failed")
            self.database.update_run(
                run_id,
                ended_at=datetime.now(timezone.utc).isoformat(),
                status="failed",
                stage="failed",
                message=str(exc),
                jobs_seen=jobs_seen,
                jobs_matched=jobs_matched,
            )
            return PipelineResult(run_id, "failed", jobs_seen, jobs_matched, str(exc))

    def _load_resume(self) -> ResumeData:
        cached = load_cached_resume(self.paths.resume_json)
        source_path = self._resolve_resume_path(self.config.resume_source_path.strip())
        if cached and cached.source_path == str(source_path):
            return cached
        if not source_path:
            raise ValueError("resume_source_path is not configured")
        return parse_resume(source_path, self.paths.resume_json)

    def _resolve_resume_path(self, configured_path: str) -> Path:
        if not configured_path:
            raise ValueError("resume_source_path is not configured")
        path = Path(configured_path).expanduser()
        if path.is_absolute():
            return path
        return (self.paths.root / path).resolve()

    def _record_skipped_match(self, job: Job) -> None:
        self.database.record_match_result(
            job.id,
            score=0,
            rationale="Skipped because title did not match target filters.",
            strengths=[],
            gaps=[],
            is_match=False,
            status="skipped",
            error_message="",
            scored_at=datetime.now(timezone.utc).isoformat(),
        )

    def _generate_documents(self, job: Job, resume: ResumeData, score: MatchScore, output_dir: Path) -> GeneratedDocs:
        docs = self.doc_generator.generate(output_dir, job, resume, score)
        self.database.record_generated_documents(
            job.id,
            output_dir=str(docs.output_dir),
            resume_pdf_path=str(docs.resume_pdf_path),
            cover_letter_path=str(docs.cover_letter_path),
            status="generated",
            error_message="",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        return docs

    def _deliver(self, job: Job, score: MatchScore, docs: GeneratedDocs) -> DeliveryResult:
        return self.gmail_client.deliver_match(job, score, docs)
