from __future__ import annotations

import logging
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from application_routing import EmailApplyAssessment, assess_email_apply
from config import AppPaths, JobBotConfig, resolve_output_dir
from deterministic_filter import apply_deterministic_filter
from database import Database, Job
from doc_generator import DocumentGenerator, GeneratedDocs
from document_tailoring import DocumentTailoringPayload
from gmail_client import DeliveryResult, GmailClient
from match_scorer import MatchScore, MatchScorer, StageEvaluation
from portal_filler import PortalAutofillReadiness, PortalFiller
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


@dataclass(slots=True)
class ApprovalResult:
    delivery: DeliveryResult
    approval_log: str
    approval_route: str
    docs_action: str
    portal_platform: str


class JobBotPipeline:
    def __init__(self, config: JobBotConfig, paths: AppPaths, database: Database) -> None:
        self.config = config
        self.paths = paths
        self.database = database
        self.scraper = ScraperRouter(config)
        self.scorer = MatchScorer(config, database)
        self.doc_generator = DocumentGenerator()
        self.gmail_client = GmailClient(config.gmail, paths.token_file)
        self.portal_filler = PortalFiller(headless=True)
        self.portal_readiness = self.portal_filler.check_readiness()
        self._log_portal_readiness("startup", self.portal_readiness)
        gmail_ready, gmail_summary = self.gmail_client.readiness_status()
        LOGGER.info("Gmail readiness: %s (%s)", gmail_summary, "ready" if gmail_ready else "not_ready")

    @staticmethod
    def _log_portal_readiness(context: str, readiness: PortalAutofillReadiness) -> None:
        LOGGER.info(
            "Portal autofill readiness [%s]: %s (%s) detail=%s",
            context,
            readiness.summary,
            readiness.reason_code,
            readiness.technical_detail or "none",
        )

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
                    delivery = self._deliver(job, resume, strong_eval.to_match_score(self.config.final_apply_threshold), docs)
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
        tailoring_payload = self._prepare_document_tailoring(job, resume, score, ai_notes=ai_notes, progress_callback=progress_callback)
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
            cover_letter_path=str(docs.cover_letter_txt_path) if docs.cover_letter_txt_path != Path() else "",
            cover_letter_docx_path=str(docs.cover_letter_docx_path) if docs.cover_letter_docx_path != Path() else "",
            cover_letter_pdf_path=str(docs.cover_letter_pdf_path) if docs.cover_letter_pdf_path != Path() else "",
            status=docs.status,
            error_message=docs.error_message,
            generated_at=datetime.now(timezone.utc).isoformat(),
            tailoring_route=tailoring_payload.route,
            tailoring_provider=tailoring_payload.provider,
            tailoring_model=tailoring_payload.model,
            tailoring_fallback_reason=tailoring_payload.fallback_reason,
            tailoring_retry_count=tailoring_payload.retry_count,
            resume_ai_status=tailoring_payload.resume_ai_status,
            cover_letter_ai_status=tailoring_payload.cover_letter_ai_status,
            rejected_bullets_repaired=tailoring_payload.rejected_bullets_repaired,
            cover_letter_fallback=tailoring_payload.cover_letter_fallback,
            ai_validation_attempts=tailoring_payload.ai_validation_attempts,
            resume_retry_performed=tailoring_payload.resume_retry_performed,
            cover_letter_retry_performed=tailoring_payload.cover_letter_retry_performed,
            ai_repair_applied=tailoring_payload.ai_repair_applied,
            pdf_exporter_used=docs.pdf_exporter_used,
            page_fit_attempts=docs.page_fit_attempts,
        )
        return docs

    def _prepare_document_tailoring(self, job: Job, resume: ResumeData, score: MatchScore, *, ai_notes: str, progress_callback=None) -> DocumentTailoringPayload:
        local_payload = self.doc_generator.build_local_tailoring_payload(job, resume, score, ai_notes=ai_notes)
        local_payload.ai_validation_attempts = 0
        if not self.doc_generator.should_escalate_tailoring(job, resume, local_payload):
            LOGGER.info("Using local tailoring for %s", job.id)
            return local_payload

        LOGGER.info("Escalating document tailoring to AI for %s", job.id)
        self._emit_progress(progress_callback, "validating_ai", "Validating AI content...", 3)
        first_attempt = self.scorer.tailor_documents_with_ai(job, resume, local_payload, alignment_notes=ai_notes, retry_count=0)
        ai_payload = first_attempt.payload
        best_partial_payload: DocumentTailoringPayload | None = None
        if ai_payload:
            repaired_payload, issues, failed_sections = self.doc_generator.repair_ai_tailoring_payload(ai_payload, local_payload)
            repaired_payload.ai_validation_attempts = 1
            repaired_payload.retry_count = first_attempt.retry_count
            if repaired_payload.ai_repair_applied:
                self._emit_progress(progress_callback, "repairing_ai", "Repairing invalid AI content...", 3)
            valid, validation_issues = self.doc_generator.validate_tailoring_payload(repaired_payload)
            issues = issues + validation_issues
            if valid and not failed_sections:
                LOGGER.info("AI tailoring accepted for %s via %s/%s", job.id, repaired_payload.provider, repaired_payload.model)
                return repaired_payload
            if valid and repaired_payload.route == "openai":
                best_partial_payload = repaired_payload
            LOGGER.warning("AI tailoring quality check failed for %s: %s", job.id, ", ".join(issues))
            retry_sections = self._retry_sections_for_failed_parts(failed_sections)
            retry_preview = best_partial_payload or local_payload
            if "resume" in retry_sections:
                retry_preview.resume_retry_performed = True
                self._emit_progress(progress_callback, "retrying_resume", "Retrying resume bullet generation...", 3)
            if "cover_letter" in retry_sections:
                retry_preview.cover_letter_retry_performed = True
                self._emit_progress(progress_callback, "retrying_cover_letter", "Retrying cover letter generation...", 3)
            retry_attempt = self.scorer.tailor_documents_with_ai(
                job,
                resume,
                retry_preview,
                alignment_notes=ai_notes,
                retry_count=1,
                requested_sections=retry_sections,
            )
            retry_payload = retry_attempt.payload
            if retry_payload:
                retry_payload = self._preserve_unrequested_sections(retry_payload, retry_preview, retry_sections)
                repaired_retry_payload, retry_issues, retry_failed_sections = self.doc_generator.repair_ai_tailoring_payload(retry_payload, retry_preview)
                repaired_retry_payload = self._restore_unrequested_section_statuses(repaired_retry_payload, retry_preview, retry_sections)
                repaired_retry_payload.ai_validation_attempts = 2
                repaired_retry_payload.retry_count = retry_attempt.retry_count
                repaired_retry_payload.resume_retry_performed = "resume" in retry_sections
                repaired_retry_payload.cover_letter_retry_performed = "cover_letter" in retry_sections
                repaired_retry_payload.ai_repair_applied = repaired_retry_payload.ai_repair_applied or bool(best_partial_payload and best_partial_payload.ai_repair_applied)
                valid, retry_validation_issues = self.doc_generator.validate_tailoring_payload(repaired_retry_payload)
                retry_issues = retry_issues + retry_validation_issues
                if valid and not retry_failed_sections:
                    LOGGER.info("AI tailoring retry accepted for %s via %s/%s", job.id, repaired_retry_payload.provider, repaired_retry_payload.model)
                    return repaired_retry_payload
                if valid and repaired_retry_payload.route == "openai":
                    repaired_retry_payload.fallback_reason = "; ".join(retry_issues) if retry_issues else ""
                    LOGGER.info("AI tailoring partially accepted for %s via %s/%s", job.id, repaired_retry_payload.provider, repaired_retry_payload.model)
                    return repaired_retry_payload
                LOGGER.warning("AI tailoring retry failed for %s: %s", job.id, ", ".join(retry_issues))
                if best_partial_payload:
                    best_partial_payload.ai_validation_attempts = 2
                    best_partial_payload.resume_retry_performed = "resume" in retry_sections
                    best_partial_payload.cover_letter_retry_performed = "cover_letter" in retry_sections
                    LOGGER.info("Using best partial AI tailoring for %s after retry failure", job.id)
                    return best_partial_payload
                first_attempt = retry_attempt
            else:
                if best_partial_payload:
                    best_partial_payload.ai_validation_attempts = 2
                    best_partial_payload.resume_retry_performed = "resume" in retry_sections
                    best_partial_payload.cover_letter_retry_performed = "cover_letter" in retry_sections
                    LOGGER.info("Using best partial AI tailoring for %s after retry returned no payload", job.id)
                    return best_partial_payload
                first_attempt = retry_attempt
        elif first_attempt.attempted and self._should_retry_ai_attempt(first_attempt.failure_reason):
            LOGGER.warning("AI tailoring parse failed for %s; retrying once", job.id)
            self._emit_progress(progress_callback, "retrying_ai", "Retrying AI content generation...", 3)
            retry_attempt = self.scorer.tailor_documents_with_ai(job, resume, local_payload, alignment_notes=ai_notes, retry_count=1)
            retry_payload = retry_attempt.payload
            if retry_payload:
                repaired_retry_payload, retry_issues, retry_failed_sections = self.doc_generator.repair_ai_tailoring_payload(retry_payload, local_payload)
                repaired_retry_payload.ai_validation_attempts = 2
                repaired_retry_payload.retry_count = retry_attempt.retry_count
                valid, retry_validation_issues = self.doc_generator.validate_tailoring_payload(repaired_retry_payload)
                retry_issues = retry_issues + retry_validation_issues
                if valid and not retry_failed_sections:
                    LOGGER.info("AI tailoring retry accepted for %s via %s/%s", job.id, repaired_retry_payload.provider, repaired_retry_payload.model)
                    return repaired_retry_payload
                if valid and repaired_retry_payload.route == "openai":
                    repaired_retry_payload.fallback_reason = "; ".join(retry_issues) if retry_issues else ""
                    LOGGER.info("AI tailoring partially accepted for %s via %s/%s", job.id, repaired_retry_payload.provider, repaired_retry_payload.model)
                    return repaired_retry_payload
                LOGGER.warning("AI tailoring retry failed for %s: %s", job.id, ", ".join(retry_issues))
            first_attempt = retry_attempt
        elif first_attempt.attempted:
            LOGGER.warning("AI tailoring failed for %s: %s", job.id, first_attempt.failure_reason)
        LOGGER.info("Falling back to local tailoring for %s", job.id)
        local_payload.route = "fallback"
        local_payload.ai_attempted = first_attempt.attempted
        local_payload.provider = first_attempt.provider
        local_payload.model = first_attempt.model
        if ai_payload and 'issues' in locals() and issues:
            local_payload.fallback_reason = "OpenAI payload failed tailoring quality checks: " + ", ".join(issues)
        else:
            local_payload.fallback_reason = first_attempt.failure_reason or "AI tailoring unavailable."
        local_payload.retry_count = first_attempt.retry_count
        local_payload.resume_ai_status = "local"
        local_payload.cover_letter_ai_status = "local"
        local_payload.cover_letter_fallback = "local" if first_attempt.attempted else ""
        local_payload.ai_validation_attempts = 2 if first_attempt.retry_count else 1 if first_attempt.attempted else 0
        local_payload.resume_retry_performed = False
        local_payload.cover_letter_retry_performed = False
        local_payload.ai_repair_applied = False
        return local_payload

    @staticmethod
    def _retry_sections_for_failed_parts(failed_sections: set[str]) -> set[str]:
        if not failed_sections:
            return {"resume", "cover_letter"}
        return set(failed_sections)

    @staticmethod
    def _preserve_unrequested_sections(
        payload: DocumentTailoringPayload,
        baseline: DocumentTailoringPayload,
        requested_sections: set[str],
    ) -> DocumentTailoringPayload:
        if "resume" not in requested_sections:
            payload.work_entries = baseline.work_entries
            payload.key_skills = baseline.key_skills
        if "cover_letter" not in requested_sections:
            payload.cover_letter_text = baseline.cover_letter_text
        return payload

    @staticmethod
    def _restore_unrequested_section_statuses(
        payload: DocumentTailoringPayload,
        baseline: DocumentTailoringPayload,
        requested_sections: set[str],
    ) -> DocumentTailoringPayload:
        if "resume" not in requested_sections:
            payload.resume_ai_status = baseline.resume_ai_status
            payload.rejected_bullets_repaired = baseline.rejected_bullets_repaired
        if "cover_letter" not in requested_sections:
            payload.cover_letter_ai_status = baseline.cover_letter_ai_status
            payload.cover_letter_fallback = baseline.cover_letter_fallback
        if payload.resume_ai_status in {"accepted", "partial"} or payload.cover_letter_ai_status == "accepted":
            payload.route = "openai"
        return payload

    @staticmethod
    def _should_retry_ai_attempt(failure_reason: str) -> bool:
        lowered = failure_reason.lower()
        return "parsed as json" in lowered or "payload structure" in lowered

    def _deliver(self, job: Job, resume: ResumeData, score: MatchScore, docs: GeneratedDocs) -> DeliveryResult:
        assessment = self._assess_email_delivery(job)
        if not assessment.is_explicit:
            return DeliveryResult("manual", "blocked_hr_email", "", f"Blocked send: {assessment.reason}")
        return self.gmail_client.deliver_match(
            job,
            score,
            docs,
            sender_name=self.doc_generator._signoff_name(resume),
            allow_fallback=False,
        )

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

    def approve_and_send(self, job_id: str, *, progress_callback=None) -> DeliveryResult:
        row = self.database.get_review_row(job_id)
        if not row:
            raise ValueError("Selected job could not be found")
        self._emit_progress(progress_callback, "loading_job", f"Loading {row['title']} at {row['employer']}...", 1)
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
        self._emit_progress(progress_callback, "checking_documents", "Checking generated application documents...", 2)
        approval_notes = [
            f"Route selected: {'email' if row['apply_method'] == 'email' else 'portal/manual'}",
        ]
        docs = GeneratedDocs(
            output_dir=Path(row["output_dir"]) if row["output_dir"] else Path(),
            resume_pdf_path=Path(row["resume_pdf_path"]) if row["resume_pdf_path"] else Path(),
            cover_letter_pdf_path=Path(row["cover_letter_pdf_path"]) if row.get("cover_letter_pdf_path") else Path(),
            resume_docx_path=Path(row["resume_docx_path"]) if row.get("resume_docx_path") else Path(),
            cover_letter_docx_path=Path(row["cover_letter_docx_path"]) if row.get("cover_letter_docx_path") else Path(),
            cover_letter_txt_path=Path(row["cover_letter_path"]) if row["cover_letter_path"] else Path(),
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
            or not row.get("cover_letter_pdf_path")
            or not docs.cover_letter_pdf_path.exists()
        )
        if self.config.automation_mode == "semi_auto" and docs_missing:
            raise ValueError("Generate documents first before approving and sending in semi_auto.")
        docs_action = "reused"
        if docs_missing:
            output_dir = resolve_output_dir(self.config, self.paths)
            output_dir.mkdir(parents=True, exist_ok=True)
            self._emit_progress(progress_callback, "generating_documents", "Generating missing application documents...", 3)
            docs = self._generate_documents(job, resume, score, output_dir, ai_notes=row["rationale"], progress_callback=progress_callback)
            docs_action = "generated_missing"
            approval_notes.append("Documents generated during approval flow.")
        else:
            approval_notes.append("Existing generated documents reused.")
        approval = self._deliver_for_approval(job, resume, score, docs, docs_action=docs_action, progress_callback=progress_callback)
        self.database.record_delivery(
            job.id,
            method=approval.delivery.method,
            status=approval.delivery.status,
            message_id=approval.delivery.message_id,
            error_message=approval.delivery.error_message,
            delivered_at=datetime.now(timezone.utc).isoformat(),
            approval_log=approval.approval_log,
            approval_route=approval.approval_route,
            approval_docs_action=approval.docs_action,
            approval_portal_platform=approval.portal_platform,
        )
        return approval.delivery

    def verify_portal_autofill_runtime(self, *, progress_callback=None) -> PortalAutofillReadiness:
        self._emit_progress(progress_callback, "starting", "Testing portal autofill runtime...", 0)
        self._emit_progress(progress_callback, "checking_runtime", "Importing Playwright and launching headless Chromium...", 4)
        readiness = self.portal_filler.check_readiness()
        self.portal_readiness = readiness
        self._log_portal_readiness("runtime_test", readiness)
        final_message = readiness.summary if readiness.ready else f"{readiness.summary} - {readiness.technical_detail or readiness.reason_code}"
        self._emit_progress(progress_callback, "runtime_checked", final_message, 7)
        return readiness

    def _deliver_for_approval(
        self,
        job: Job,
        resume: ResumeData,
        score: MatchScore,
        docs: GeneratedDocs,
        *,
        docs_action: str,
        progress_callback=None,
    ) -> ApprovalResult:
        if job.apply_method == "email":
            assessment = self._assess_email_delivery(job)
            if not assessment.is_explicit:
                self._emit_progress(progress_callback, "blocked_email", "Blocking send because no validated HR email is present...", 6)
                result = DeliveryResult("manual", "blocked_hr_email", "", f"Blocked send: {assessment.reason}")
            else:
                self._emit_progress(progress_callback, "sending_email", "Sending employer email application...", 6)
                result = self.gmail_client.deliver_match(
                    job,
                    score,
                    docs,
                    sender_name=self.doc_generator._signoff_name(resume),
                    allow_fallback=False,
                )
            log = "\n".join(
                [
                    "Route: email",
                    f"Documents: {docs_action}",
                    f"HR email: {assessment.confidence}",
                    f"HR email review: {assessment.reason}",
                    f"Validated HR recipient: {assessment.email or 'Not present'}",
                    f"Final status: {result.status} via {result.method}",
                    f"Message: {result.error_message or 'Application email sent.'}",
                ]
            )
            route = "email" if assessment.is_explicit else "manual"
            return ApprovalResult(result, log, route, docs_action, "")
        if not job.apply_url:
            result = DeliveryResult("manual", "failed", "", "No application URL available for manual or portal apply.")
            log = "\n".join(
                [
                    "Route: manual",
                    f"Documents: {docs_action}",
                    "Final status: failed via manual",
                    f"Message: {result.error_message}",
                ]
            )
            return ApprovalResult(result, log, "manual", docs_action, "")
        if not self.portal_readiness.ready:
            self._emit_progress(progress_callback, "opening_manual_apply", "Portal autofill unavailable; opening apply page...", 6)
            opened = self._open_apply_url(job.apply_url)
            result = DeliveryResult(
                "portal",
                "opened_manual" if opened else "failed",
                "",
                "Portal autofill unavailable; opened apply page for manual completion." if opened else self.portal_readiness.summary,
            )
            log = "\n".join(
                [
                    "Route: manual_open",
                    f"Documents: {docs_action}",
                    f"Portal readiness: {self.portal_readiness.reason_code}",
                    f"Portal readiness detail: {self.portal_readiness.technical_detail or 'None'}",
                    f"Final status: {result.status} via {result.method}",
                    f"Message: {result.error_message}",
                ]
            )
            return ApprovalResult(result, log, "manual_open", docs_action, "")

        self._emit_progress(progress_callback, "attempting_portal", "Attempting portal autofill...", 6)
        portal_result = self.portal_filler.fill(job, resume, docs, progress_callback=progress_callback)
        method = portal_result.platform if portal_result.platform != "unknown" else "portal"
        if portal_result.status == "submitted":
            self._emit_progress(progress_callback, "completed", "Application submitted.", 8)
            result = DeliveryResult(method, "submitted", "", portal_result.message)
            log = "\n".join(
                [
                    "Route: portal",
                    f"Documents: {docs_action}",
                    f"Portal platform: {method}",
                    f"Final status: {result.status} via {result.method}",
                    f"Message: {portal_result.message}",
                ]
            )
            return ApprovalResult(result, log, "portal", docs_action, method)
        self._emit_progress(progress_callback, "opening_manual_apply", "Opening application page...", 7)
        opened = self._open_apply_url(job.apply_url)
        if portal_result.status == "login_required":
            result = DeliveryResult(
                method,
                "blocked_login",
                "",
                "Login wall blocked autofill; opened apply page for manual completion." if opened else "Login wall blocked autofill.",
            )
            log = "\n".join(
                [
                    "Route: portal",
                    f"Documents: {docs_action}",
                    f"Portal platform: {method}",
                    "Fallback: login wall",
                    f"Final status: {result.status} via {result.method}",
                    f"Message: {result.error_message}",
                ]
            )
            return ApprovalResult(result, log, "portal", docs_action, method)
        if portal_result.status == "captcha":
            result = DeliveryResult(
                method,
                "blocked_captcha",
                "",
                "CAPTCHA blocked autofill; opened apply page for manual completion." if opened else "CAPTCHA blocked autofill.",
            )
            log = "\n".join(
                [
                    "Route: portal",
                    f"Documents: {docs_action}",
                    f"Portal platform: {method}",
                    "Fallback: captcha",
                    f"Final status: {result.status} via {result.method}",
                    f"Message: {result.error_message}",
                ]
            )
            return ApprovalResult(result, log, "portal", docs_action, method)
        if portal_result.status == "unsupported":
            if method == "indeed" and "posting page" in portal_result.message.lower():
                detail = (
                    "Indeed posting page is not an automatable apply form; opened apply page for manual completion."
                    if opened
                    else "Indeed posting page is not an automatable apply form."
                )
                fallback_label = "indeed posting page"
            else:
                detail = (
                    "Portal not supported for autofill; opened apply page for manual completion."
                    if opened
                    else "Portal not supported for autofill."
                )
                fallback_label = "unsupported portal"
            result = DeliveryResult(
                method,
                "unsupported_portal",
                "",
                detail,
            )
            log = "\n".join(
                [
                    "Route: portal",
                    f"Documents: {docs_action}",
                    f"Portal platform: {method}",
                    f"Fallback: {fallback_label}",
                    f"Final status: {result.status} via {result.method}",
                    f"Message: {result.error_message}",
                ]
            )
            return ApprovalResult(result, log, "portal", docs_action, method)
        if portal_result.status == "screening_questions":
            result = DeliveryResult(
                method,
                "opened_manual" if opened else "failed",
                "",
                "Screening questions require manual completion; opened apply page for review." if opened else "Screening questions require manual completion.",
            )
            log = "\n".join(
                [
                    "Route: portal",
                    f"Documents: {docs_action}",
                    f"Portal platform: {method}",
                    "Fallback: screening questions",
                    f"Final status: {result.status} via {result.method}",
                    f"Message: {result.error_message}",
                ]
            )
            return ApprovalResult(result, log, "portal", docs_action, method)
        result = DeliveryResult(
            method,
            "opened_manual" if opened else "failed",
            "",
            "Portal autofill could not complete; opened apply page for manual completion." if opened else portal_result.message,
        )
        log = "\n".join(
            [
                "Route: portal",
                f"Documents: {docs_action}",
                f"Portal platform: {method}",
                "Fallback: generic portal failure",
                f"Final status: {result.status} via {result.method}",
                f"Message: {result.error_message}",
            ]
        )
        return ApprovalResult(result, log, "portal", docs_action, method)

    def portal_autofill_readiness(self) -> PortalAutofillReadiness:
        self.portal_readiness = self.portal_filler.check_readiness()
        self._log_portal_readiness("refresh", self.portal_readiness)
        return self.portal_readiness

    @staticmethod
    def _assess_email_delivery(job: Job) -> EmailApplyAssessment:
        return assess_email_apply(job.description_full or "", job.apply_url, existing_email=job.hiring_manager_email or "")

    @staticmethod
    def _open_apply_url(apply_url: str) -> bool:
        try:
            return bool(webbrowser.open(apply_url))
        except Exception:
            LOGGER.exception("Failed to open apply URL: %s", apply_url)
            return False
