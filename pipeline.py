from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import AppPaths, JobBotConfig, resolve_output_dir
from deterministic_filter import apply_deterministic_filter
from database import Database, Job
from doc_generator import DocumentGenerator, GeneratedDocs
from document_tailoring import DocumentTailoringPayload
from gmail_client import DeliveryResult, GmailClient
from match_scorer import MatchScore, MatchScorer, StageEvaluation
from resume_parser import ResumeData, load_cached_resume, parse_resume
from scrapers.scraper_router import ScraperRouter


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineResult:
    run_id: int
    status: str
    jobs_seen: int
    jobs_matched: int
    message: str
    estimated_cost_usd: float = 0.0


class JobBotPipeline:
    def __init__(self, config: JobBotConfig, paths: AppPaths, database: Database) -> None:
        self.config = config
        self.paths = paths
        self.database = database
        self.scraper = ScraperRouter(config)
        self.scorer = MatchScorer(config, database)
        self.doc_generator = DocumentGenerator()
        self.gmail_client = GmailClient(config.gmail, paths.token_file)

    @staticmethod
    def _emit_progress(progress_callback, stage: str, message: str, progress: int) -> None:
        if progress_callback:
            progress_callback(stage, message, progress)

    def run(self) -> PipelineResult:
        started_at = datetime.now(timezone.utc).isoformat()
        run_id = self.database.create_run(started_at, stage="starting")
        jobs_seen = 0
        jobs_matched = 0
        run_cost = 0.0
        resume: ResumeData | None = None
        try:
            self.database.update_run(run_id, stage="scraping", message="Fetching jobs")
            fetched = self.scraper.fetch_jobs()
            jobs_seen = len(fetched)

            self.database.update_run(run_id, stage="filtering", message="Applying deterministic filters", jobs_seen=jobs_seen)
            output_dir = resolve_output_dir(self.config, self.paths)
            output_dir.mkdir(parents=True, exist_ok=True)
            seen_job_ids: set[str] = set()
            recent_job_ids = self.database.recent_job_ids(hours=24)

            for idx, (job, _raw_payload) in enumerate(fetched, start=1):
                self.database.update_run(
                    run_id,
                    stage="filtering",
                    message=f"Checking job {idx}/{jobs_seen}: {job.title} at {job.employer}",
                    jobs_seen=jobs_seen,
                    jobs_matched=jobs_matched,
                )
                if job.id in recent_job_ids:
                    continue
                self.database.upsert_job(job, _raw_payload)
                filter_result = apply_deterministic_filter(job, self.config, seen_job_ids=seen_job_ids)
                if filter_result.outcome == "filtered_out":
                    self._record_skipped_match(job, filter_result.reason)
                    continue

                if self.config.automation_mode == "semi_auto" and self.config.skip_ai_scoring_in_semi_auto:
                    self.database.update_run(
                        run_id,
                        stage="review_queue",
                        message=f"Queued without AI scoring: {job.title} at {job.employer}",
                        jobs_seen=jobs_seen,
                        jobs_matched=jobs_matched + 1,
                    )
                    self._record_review_queue_match(job, "AI scoring skipped in semi_auto for faster review queueing.")
                    self.database.record_delivery(
                        job.id,
                        method="approval_queue",
                        status="pending_approval",
                        message_id="",
                        error_message="Waiting for manual approval in review queue.",
                        delivered_at="",
                    )
                    jobs_matched += 1
                    continue

                self.database.update_run(
                    run_id,
                    stage="cheap_scoring",
                    message=f"Cheap scoring {idx}/{jobs_seen}: {job.title} at {job.employer}",
                    jobs_seen=jobs_seen,
                    jobs_matched=jobs_matched,
                )
                resume = resume or self._load_resume()
                cheap_eval = self.scorer.cheap_evaluate(job, resume, force_escalate=filter_result.force_escalate)
                run_cost += cheap_eval.estimated_cost_usd
                if cheap_eval.status != "scored":
                    self._record_evaluation_result(job, cheap_eval)
                    continue

                if cheap_eval.decision == "reject":
                    self._record_evaluation_result(job, cheap_eval)
                    continue

                strong_eval: StageEvaluation
                if cheap_eval.decision == "pass_direct":
                    strong_eval = StageEvaluation(
                        stage_name="strong",
                        provider=cheap_eval.provider,
                        model=cheap_eval.model,
                        status=cheap_eval.status,
                        decision="apply_candidate" if (cheap_eval.score or 0) >= self.config.final_apply_threshold else "review",
                        score=cheap_eval.score,
                        confidence=cheap_eval.confidence,
                        rationale=cheap_eval.rationale,
                        strengths=cheap_eval.strengths,
                        gaps=cheap_eval.gaps,
                        input_tokens=cheap_eval.input_tokens,
                        output_tokens=cheap_eval.output_tokens,
                        estimated_cost_usd=0.0,
                        error_message=cheap_eval.error_message,
                        evaluated_at=cheap_eval.evaluated_at,
                        cached=True,
                    )
                else:
                    self.database.update_run(
                        run_id,
                        stage="strong_scoring",
                        message=f"Strong scoring {idx}/{jobs_seen}: {job.title} at {job.employer}",
                        jobs_seen=jobs_seen,
                        jobs_matched=jobs_matched,
                    )
                    resume = resume or self._load_resume()
                    strong_eval = self.scorer.strong_evaluate(job, resume)
                    run_cost += strong_eval.estimated_cost_usd
                self._record_evaluation_result(job, strong_eval)
                if strong_eval.status != "scored" or strong_eval.decision not in {"apply_candidate", "review"}:
                    continue

                if self.config.automation_mode == "semi_auto":
                    self.database.update_run(
                        run_id,
                        stage="review_queue",
                        message=f"Queued for manual review: {job.title} at {job.employer}",
                        jobs_seen=jobs_seen,
                        jobs_matched=jobs_matched + 1,
                    )
                    self.database.record_delivery(
                        job.id,
                        method="approval_queue",
                        status="pending_approval",
                        message_id="",
                        error_message="Waiting for manual approval in review queue.",
                        delivered_at="",
                    )
                    jobs_matched += 1
                    continue

                if strong_eval.decision != "apply_candidate":
                    continue

                self.database.update_run(
                    run_id,
                    stage="document_generation",
                    message=f"Generating documents for {job.title} at {job.employer}",
                    jobs_seen=jobs_seen,
                    jobs_matched=jobs_matched,
                )
                resume = resume or self._load_resume()
                docs = self._generate_documents(
                    job,
                    resume,
                    strong_eval.to_match_score(self.config.final_apply_threshold),
                    output_dir,
                    ai_notes=strong_eval.rationale,
                )
                jobs_matched += 1
                if self.config.automation_mode == "auto" and job.apply_method == "email":
                    self.database.update_run(
                        run_id,
                        stage="delivery",
                        message=f"Sending application for {job.title} at {job.employer}",
                        jobs_seen=jobs_seen,
                        jobs_matched=jobs_matched,
                    )
                    delivery = self._deliver(job, strong_eval.to_match_score(self.config.final_apply_threshold), docs)
                    self.database.record_delivery(
                        job.id,
                        method=delivery.method,
                        status=delivery.status,
                        message_id=delivery.message_id,
                        error_message=delivery.error_message,
                        delivered_at=datetime.now(timezone.utc).isoformat(),
                    )
                else:
                    self.database.update_run(
                        run_id,
                        stage="review_queue",
                        message=f"Queued for approval: {job.title} at {job.employer}",
                        jobs_seen=jobs_seen,
                        jobs_matched=jobs_matched,
                    )
                    self.database.record_delivery(
                        job.id,
                        method="approval_queue",
                        status="pending_approval",
                        message_id="",
                        error_message="Waiting for manual approval in review queue.",
                        delivered_at="",
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
            return PipelineResult(run_id, "completed", jobs_seen, jobs_matched, "Run completed", round(run_cost, 4))
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
            return PipelineResult(run_id, "failed", jobs_seen, jobs_matched, str(exc), round(run_cost, 4))

    def _load_resume(self) -> ResumeData:
        cached = load_cached_resume(self.paths.resume_json)
        source_path = self._resolve_resume_path(self.config.resume_source_path.strip())
        cache_has_docx_templates = True
        if cached and source_path.suffix.lower() == ".docx":
            cache_has_docx_templates = bool(
                cached.key_skills_templates
                and cached.work_experience_entries
                and all(
                    entry.role_template is not None and entry.bullet_templates
                    for entry in cached.work_experience_entries
                )
            )
        if (
            cached
            and cached.source_path == str(source_path)
            and cached.header_lines
            and cached.education_lines
            and cached.work_experience_entries
            and cache_has_docx_templates
        ):
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

    def _record_skipped_match(self, job: Job, reason: str) -> None:
        self.database.record_match_result(
            job.id,
            score=0,
            rationale=reason,
            strengths=[],
            gaps=[],
            is_match=False,
            status="skipped",
            error_message="",
            scored_at=datetime.now(timezone.utc).isoformat(),
        )

    def _record_evaluation_result(self, job: Job, evaluation: StageEvaluation) -> None:
        is_match = evaluation.status == "scored" and evaluation.decision == "apply_candidate"
        self.database.record_match_result(
            job.id,
            score=evaluation.score,
            rationale=evaluation.rationale,
            strengths=evaluation.strengths,
            gaps=evaluation.gaps,
            is_match=is_match,
            status=evaluation.decision if evaluation.status == "scored" else evaluation.status,
            error_message=evaluation.error_message,
            scored_at=evaluation.evaluated_at,
        )

    def _record_review_queue_match(self, job: Job, rationale: str) -> None:
        self.database.record_match_result(
            job.id,
            score=0,
            rationale=rationale,
            strengths=[],
            gaps=[],
            is_match=False,
            status="review",
            error_message="",
            scored_at=datetime.now(timezone.utc).isoformat(),
        )

    def _generate_documents(self, job: Job, resume: ResumeData, score: MatchScore, output_dir: Path, *, ai_notes: str, progress_callback=None) -> GeneratedDocs:
        tailoring_payload = self._prepare_document_tailoring(job, resume, score, ai_notes=ai_notes)
        docs = self.doc_generator.generate(
            output_dir,
            job,
            resume,
            score,
            ai_notes="",
            tailoring_payload=tailoring_payload,
            progress_callback=progress_callback,
        )
        self._emit_progress(progress_callback, "saving_database_state", "Saving document metadata...", 7)
        self.database.record_generated_documents(
            job.id,
            output_dir=str(docs.output_dir),
            resume_docx_path=str(docs.resume_docx_path) if docs.resume_docx_path != Path() else "",
            resume_pdf_path=str(docs.resume_pdf_path) if docs.resume_pdf_path != Path() else "",
            cover_letter_path=str(docs.cover_letter_path),
            status=docs.status,
            error_message=docs.error_message,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        return docs

    def _prepare_document_tailoring(self, job: Job, resume: ResumeData, score: MatchScore, *, ai_notes: str) -> DocumentTailoringPayload:
        local_payload = self.doc_generator.build_local_tailoring_payload(job, resume, score, ai_notes=ai_notes)
        if not self.doc_generator.should_escalate_tailoring(job, resume, local_payload):
            LOGGER.info("Using local tailoring for %s", job.id)
            return local_payload

        LOGGER.info("Escalating document tailoring to AI for %s", job.id)
        ai_payload = self.scorer.tailor_documents_with_ai(job, resume, local_payload, alignment_notes=ai_notes, retry_count=0)
        if ai_payload:
            valid, issues = self.doc_generator.validate_tailoring_payload(ai_payload)
            if valid:
                LOGGER.info("AI tailoring accepted for %s via %s/%s", job.id, ai_payload.provider, ai_payload.model)
                return ai_payload
            LOGGER.warning("AI tailoring quality check failed for %s: %s", job.id, ", ".join(issues))
            retry_payload = self.scorer.tailor_documents_with_ai(job, resume, local_payload, alignment_notes=ai_notes, retry_count=1)
            if retry_payload:
                valid, issues = self.doc_generator.validate_tailoring_payload(retry_payload)
                if valid:
                    LOGGER.info("AI tailoring retry accepted for %s via %s/%s", job.id, retry_payload.provider, retry_payload.model)
                    return retry_payload
                LOGGER.warning("AI tailoring retry failed for %s: %s", job.id, ", ".join(issues))

        LOGGER.info("Falling back to local tailoring for %s", job.id)
        local_payload.route = "fallback"
        local_payload.fallback_reason = "AI tailoring unavailable or failed quality checks."
        return local_payload

    def _deliver(self, job: Job, score: MatchScore, docs: GeneratedDocs) -> DeliveryResult:
        return self.gmail_client.deliver_match(job, score, docs)

    def generate_documents_for_job(self, job_id: str, *, progress_callback=None) -> GeneratedDocs:
        LOGGER.info("Manual document generation started for %s", job_id)
        self._emit_progress(progress_callback, "starting", "Starting document generation...", 0)
        row = self.database.get_review_row(job_id)
        if not row:
            raise ValueError("Selected job could not be found")
        self._emit_progress(progress_callback, "loading_job", f"Loading {row['title']} at {row['employer']}...", 1)
        self._emit_progress(progress_callback, "parsing_resume", "Loading and parsing resume...", 2)
        resume = self._load_resume()
        job = Job(
            id=row["id"],
            title=row["title"],
            employer=row["employer"],
            location=row["location"],
            salary_range="",
            description_full=row["description_full"],
            apply_method=row["apply_method"],
            apply_url=row["apply_url"],
            hiring_manager_email=row["hiring_manager_email"],
            source=row["source"],
            posted_at=row["posted_at"],
            scraped_at=row["scraped_at"],
        )
        score = MatchScore(
            score=row["score"],
            rationale=row["rationale"],
            strengths=[],
            gaps=[],
            is_match=row["match_status"] in {"apply_candidate", "review"},
            status=row["match_status"],
            error_message="",
            scored_at="",
        )
        output_dir = resolve_output_dir(self.config, self.paths)
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            docs = self._generate_documents(job, resume, score, output_dir, ai_notes=row["rationale"], progress_callback=progress_callback)
            if docs.status == "failed":
                raise ValueError(docs.error_message or "Document generation failed.")
            self._emit_progress(progress_callback, "completed", "Documents generated.", 8)
            LOGGER.info("Manual document generation completed for %s", job_id)
            return docs
        except Exception:
            LOGGER.exception("Manual document generation failed for %s", job_id)
            raise

    def approve_and_send(self, job_id: str) -> DeliveryResult:
        row = self.database.get_review_row(job_id)
        if not row:
            raise ValueError("Selected job could not be found")
        resume = self._load_resume()
        job = Job(
            id=row["id"],
            title=row["title"],
            employer=row["employer"],
            location=row["location"],
            salary_range="",
            description_full=row["description_full"],
            apply_method=row["apply_method"],
            apply_url=row["apply_url"],
            hiring_manager_email=row["hiring_manager_email"],
            source=row["source"],
            posted_at="",
            scraped_at="",
            )
        score = MatchScore(
            score=row["score"],
            rationale=row["rationale"],
            strengths=[],
            gaps=[],
            is_match=True,
            status=row["match_status"],
            error_message="",
            scored_at="",
        )
        docs = GeneratedDocs(
            output_dir=Path(row["output_dir"]) if row["output_dir"] else Path(),
            resume_pdf_path=Path(row["resume_pdf_path"]) if row["resume_pdf_path"] else Path(),
            cover_letter_path=Path(row["cover_letter_path"]) if row["cover_letter_path"] else Path(),
            resume_docx_path=Path(row["resume_docx_path"]) if row.get("resume_docx_path") else Path(),
            status=row.get("document_status", "pending"),
            error_message=row.get("document_error", ""),
        )
        resume_missing = (
            (not row.get("resume_docx_path") and not row["resume_pdf_path"])
            or (docs.resume_docx_path and not docs.resume_docx_path.exists() and docs.resume_pdf_path and not docs.resume_pdf_path.exists())
            or (docs.resume_docx_path == Path() and docs.resume_pdf_path and not docs.resume_pdf_path.exists())
        )
        docs_missing = (
            resume_missing
            or not row["cover_letter_path"]
            or not docs.cover_letter_path.exists()
        )
        if self.config.automation_mode == "semi_auto" and docs_missing:
            raise ValueError("Generate documents first before approving and sending in semi_auto.")
        if docs_missing:
            output_dir = resolve_output_dir(self.config, self.paths)
            output_dir.mkdir(parents=True, exist_ok=True)
            docs = self._generate_documents(job, resume, score, output_dir, ai_notes=row["rationale"])
        delivery = self._deliver(job, score, docs)
        self.database.record_delivery(
            job.id,
            method=delivery.method,
            status=delivery.status,
            message_id=delivery.message_id,
            error_message=delivery.error_message,
            delivered_at=datetime.now(timezone.utc).isoformat(),
        )
        return delivery
