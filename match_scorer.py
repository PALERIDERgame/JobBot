from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib import error, request

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:  # pragma: no cover
    TfidfVectorizer = None
    cosine_similarity = None

from config import JobBotConfig
from database import Database, Job, StageEvaluationRecord
from document_tailoring import DocumentTailoringAttempt, DocumentTailoringPayload
from resume_parser import ResumeData, ResumeWorkEntry


LOGGER = logging.getLogger(__name__)
PROMPT_VERSION = "cost_funnel_v2"

_PRECHEAP_STOPWORDS = {
    "and", "the", "for", "with", "from", "that", "this", "your", "will", "role", "team", "work", "into",
    "their", "about", "across", "have", "has", "our", "you", "job", "position", "new", "york", "experience",
    "using", "within", "required", "preferred", "strong",
}
OPENAI_PRICE_PER_MTOKEN = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-5-nano": {"input": 0.20, "output": 1.25},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
}
ANTHROPIC_PRICE_PER_MTOKEN = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}


_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}
_VALID_CHEAP_DECISIONS = {"reject", "escalate", "pass_direct", "error"}
_VALID_STRONG_DECISIONS = {"reject", "review", "apply_candidate", "skip", "error"}


def _call_with_retry(fn, *, max_attempts: int = 3, base_delay: float = 2.0):
    """Call fn(), retrying on transient API errors with exponential backoff."""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            exc_text = str(exc)
            status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            # Fail fast on auth/client errors
            if status_code in {400, 401, 403}:
                raise
            # Check for retryable status codes or transient error messages
            is_retryable = (
                status_code in _RETRYABLE_STATUS_CODES
                or isinstance(exc, (TimeoutError, ConnectionError, error.URLError))
                or "timeout" in exc_text.lower()
                or "rate limit" in exc_text.lower()
                or "overloaded" in exc_text.lower()
            )
            if not is_retryable or attempt == max_attempts - 1:
                raise
            delay = base_delay * (2 ** attempt)
            LOGGER.warning("AI API transient error (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, max_attempts, delay, exc_text)
            last_exc = exc
            time.sleep(delay)
    raise last_exc  # pragma: no cover


@dataclass(slots=True)
class MatchScore:
    score: int | None
    rationale: str
    strengths: list[str]
    gaps: list[str]
    is_match: bool
    status: str
    error_message: str
    scored_at: str


@dataclass(slots=True)
class StageEvaluation:
    stage_name: str
    provider: str
    model: str
    status: str
    decision: str
    score: int | None
    confidence: float | None
    rationale: str
    strengths: list[str]
    gaps: list[str]
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    error_message: str
    evaluated_at: str
    cached: bool = False

    def to_match_score(self, threshold: int) -> MatchScore:
        return MatchScore(
            score=self.score,
            rationale=self.rationale,
            strengths=self.strengths,
            gaps=self.gaps,
            is_match=(self.score or 0) >= threshold and self.status == "scored",
            status=self.status,
            error_message=self.error_message,
            scored_at=self.evaluated_at,
        )


@dataclass(slots=True)
class PrecheapGateResult:
    gate_score: int
    tfidf_score: int
    keyword_overlap_count: int
    keyword_overlap_terms: list[str]
    decision: str
    reason: str


@dataclass(slots=True)
class FastRankResult:
    score: int
    rationale: str
    title_match_score: int
    target_title_overlap: int
    keyword_overlap_count: int
    keyword_overlap_terms: list[str]
    tfidf_score: int
    force_escalate_hit: bool
    query_overlap_score: int
    location_penalty: int
    salary_penalty: int


class MatchScorer:
    def __init__(self, config: JobBotConfig, database: Database | None = None) -> None:
        self.config = config
        self.database = database
        self._client_cache: dict[str, object | None] = {}

    @staticmethod
    def build_resume_hash(resume_data: ResumeData) -> str:
        payload = json.dumps(
            {
                "summary": resume_data.summary,
                "skills": resume_data.skills,
                "experience_lines": resume_data.experience_lines,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def cheap_evaluate(self, job: Job, resume_data: ResumeData, *, force_escalate: bool = False) -> StageEvaluation:
        provider = self.config.cheap_stage_provider
        model = self.config.cheap_stage_model
        if provider == "ollama_local" and self._build_client(provider) is None:
            fallback = self._cheap_fallback_provider()
            if fallback is not None:
                provider, model = fallback
        return self._evaluate(
            stage_name="cheap",
            provider=provider,
            model=model,
            job=job,
            resume_data=resume_data,
            prompt=self._build_cheap_prompt(job, resume_data, force_escalate=force_escalate),
        )

    def strong_evaluate(self, job: Job, resume_data: ResumeData) -> StageEvaluation:
        return self._evaluate(
            stage_name="strong",
            provider=self.config.strong_stage_provider,
            model=self.config.strong_stage_model,
            job=job,
            resume_data=resume_data,
            prompt=self._build_strong_prompt(job, resume_data),
        )

    def precheap_gate(self, job: Job, resume_data: ResumeData) -> PrecheapGateResult:
        if not self.config.precheap_gate_enabled:
            return PrecheapGateResult(
                gate_score=0,
                tfidf_score=0,
                keyword_overlap_count=0,
                keyword_overlap_terms=[],
                decision="pass",
                reason="Pre-cheap gate disabled.",
            )
        if TfidfVectorizer is None or cosine_similarity is None:
            return PrecheapGateResult(
                gate_score=0,
                tfidf_score=0,
                keyword_overlap_count=0,
                keyword_overlap_terms=[],
                decision="pass",
                reason="Pre-cheap gate skipped (scikit-learn unavailable).",
            )

        resume_text = self._build_resume_gate_text(resume_data)
        job_text = self._build_job_gate_text(job)
        if not resume_text or not job_text:
            return PrecheapGateResult(
                gate_score=0,
                tfidf_score=0,
                keyword_overlap_count=0,
                keyword_overlap_terms=[],
                decision="pass",
                reason="Pre-cheap gate skipped (insufficient text).",
            )

        overlap_terms = self._keyword_overlap_terms(job_text, resume_text)
        overlap_count = len(overlap_terms)
        keyword_overlap_score = min(overlap_count * 5, 100)
        tfidf_score = self._tfidf_similarity_score(resume_text, job_text)
        gate_score = int(round((0.7 * tfidf_score) + (0.3 * keyword_overlap_score)))
        threshold = self.config.precheap_gate_reject_threshold
        decision = "reject" if gate_score < threshold else "pass"
        top_terms = overlap_terms[:10]
        reason = (
            f"Pre-cheap gate {decision}: tfidf={tfidf_score}, "
            f"overlap={overlap_count} ({', '.join(top_terms)})"
        )

        LOGGER.info(
            "precheap_gate job_id=%s gate_score=%s tfidf_score=%s overlap=%s terms=%s decision=%s threshold=%s",
            job.id,
            gate_score,
            tfidf_score,
            overlap_count,
            ",".join(top_terms),
            decision,
            threshold,
        )
        return PrecheapGateResult(
            gate_score=gate_score,
            tfidf_score=tfidf_score,
            keyword_overlap_count=overlap_count,
            keyword_overlap_terms=top_terms,
            decision=decision,
            reason=reason,
        )

    def score_job(self, job: Job, resume_data: ResumeData) -> MatchScore:
        evaluation = self.strong_evaluate(job, resume_data)
        return evaluation.to_match_score(self.config.final_apply_threshold)

    def fast_rank_job(self, job: Job, resume_data: ResumeData, *, force_escalate: bool = False) -> FastRankResult:
        resume_text = self._build_resume_gate_text(resume_data)
        job_text = self._build_job_gate_text(job)
        overlap_terms = self._keyword_overlap_terms(job_text, resume_text)
        overlap_count = len(overlap_terms)
        tfidf_score = self._tfidf_similarity_score(resume_text, job_text)
        title_match_score = self._title_match_score(job.title)
        target_title_overlap = self._target_title_overlap(job.title)
        query_overlap_score = self._query_overlap_score(job_text)
        force_hit = force_escalate or self._contains_any(job_text, self.config.force_escalate_keywords)
        location_penalty = self._location_penalty(job)
        salary_penalty = self._salary_penalty(job)

        raw_score = (
            12
            + (tfidf_score * 0.25)
            + (min(overlap_count * 8, 100) * 0.20)
            + (title_match_score * 0.25)
            + (target_title_overlap * 0.15)
            + (query_overlap_score * 0.15)
        )
        if force_hit:
            raw_score += 12
        raw_score -= location_penalty + salary_penalty
        score = max(0, min(100, int(round(raw_score))))
        rationale_bits = [
            f"title={title_match_score}",
            f"tfidf={tfidf_score}",
            f"overlap={overlap_count}",
        ]
        if target_title_overlap:
            rationale_bits.append(f"target_titles={target_title_overlap}")
        if query_overlap_score:
            rationale_bits.append(f"query={query_overlap_score}")
        if force_hit:
            rationale_bits.append("force_escalate")
        if location_penalty:
            rationale_bits.append(f"location_penalty={location_penalty}")
        if salary_penalty:
            rationale_bits.append(f"salary_penalty={salary_penalty}")
        return FastRankResult(
            score=score,
            rationale="Fast rank: " + ", ".join(rationale_bits),
            title_match_score=title_match_score,
            target_title_overlap=target_title_overlap,
            keyword_overlap_count=overlap_count,
            keyword_overlap_terms=overlap_terms[:12],
            tfidf_score=tfidf_score,
            force_escalate_hit=force_hit,
            query_overlap_score=query_overlap_score,
            location_penalty=location_penalty,
            salary_penalty=salary_penalty,
        )

    def suggest_job_keywords(self, resume_data: ResumeData) -> str:
        provider = self.config.cheap_stage_provider
        model = self.config.cheap_stage_model
        if provider == "ollama_local" and self._build_client(provider) is None:
            fallback = self._cheap_fallback_provider()
            if fallback is not None:
                provider, model = fallback
        if self._build_client(provider) is None:
            raise RuntimeError(f"{provider} is not configured or available.")

        prompt = {
            "resume_summary": self._resume_summary(resume_data),
            "instructions": {
                "return_json": True,
                "fields": ["keywords"],
                "goal": (
                    "Generate concise job-search keywords based on the candidate's resume. "
                    "Favor titles, domains, skills, and adjacent search terms that will improve job-board recall."
                ),
                "constraints": [
                    "Return 8 to 16 keywords or short keyword phrases.",
                    "Keep each keyword or phrase to 1 to 3 words.",
                    "Do not include personal names, emails, or phone numbers.",
                ],
            },
        }
        system_prompt = (
            "You generate job search keywords from resumes. "
            "Return only valid JSON with a single key named keywords whose value is an array of strings."
        )
        text = self._create_completion(provider, model, prompt, system_prompt=system_prompt)
        keywords = self._parse_keyword_response(text)
        if not keywords:
            raise RuntimeError("Keyword suggestion returned no usable terms.")
        return " ".join(keywords)

    def document_generation_notes(self, job: Job, resume_data: ResumeData, strong_eval: StageEvaluation) -> str:
        provider, model = self._resolve_doc_provider_model()
        if self._build_client(provider) is None:
            return ""
        prompt = {
            "resume_summary": self._resume_summary(resume_data),
            "job": self._job_summary(job),
            "alignment_notes": strong_eval.rationale,
            "instructions": {
                "return_plain_text": True,
                "output": "Return a concise cover-letter-style summary plus 3 resume emphasis bullets.",
            },
        }
        try:
            return self._create_completion(provider, model, prompt, system_prompt="Write concise, accurate application materials without inventing experience.")
        except Exception:  # pragma: no cover
            LOGGER.exception("Failed to generate document notes for %s", job.id)
            return ""

    def tailor_documents_with_ai(
        self,
        job: Job,
        resume_data: ResumeData,
        local_preview: DocumentTailoringPayload,
        *,
        alignment_notes: str = "",
        retry_count: int = 0,
        requested_sections: set[str] | None = None,
    ) -> DocumentTailoringAttempt:
        provider, model = self._resolve_doc_provider_model()
        LOGGER.info("Resolved doc tailoring provider/model for %s: %s/%s", job.id, provider, model)
        if provider != "openai":
            return DocumentTailoringAttempt(attempted=False, provider=provider, model=model, retry_count=retry_count)
        compatibility_error = self._validate_doc_provider_model(provider, model)
        if compatibility_error:
            LOGGER.warning("Skipping AI document tailoring for %s: %s", job.id, compatibility_error)
            return DocumentTailoringAttempt(
                attempted=False,
                provider=provider,
                model=model,
                failure_reason=compatibility_error,
                retry_count=retry_count,
            )
        if self._build_client(provider) is None:
            return DocumentTailoringAttempt(
                attempted=False,
                provider=provider,
                model=model,
                failure_reason=f"{provider} client unavailable",
                retry_count=retry_count,
            )

        prompt = {
            "candidate": self._resume_summary(resume_data),
            "job": self._job_summary(job),
            "alignment_notes": alignment_notes,
            "work_entries": [
                {
                    "role_line": entry.role_line,
                    "date_line": entry.date_line,
                    "bullets": entry.bullets,
                }
                for entry in resume_data.work_experience_entries
            ],
            "current_preview": {
                "work_entries": [
                    {
                        "role_line": entry.role_line,
                        "date_line": entry.date_line,
                        "bullets": entry.bullets,
                    }
                    for entry in local_preview.work_entries
                ],
                "key_skills": local_preview.key_skills,
                "cover_letter_text": local_preview.cover_letter_text,
            },
            "instructions": {
                "return_json": True,
                "fields": ["work_entries", "key_skills", "cover_letter_text"],
                "retry_sections": sorted(requested_sections) if requested_sections else ["resume", "cover_letter"],
                "constraints": [
                    "Preserve employers, role titles, dates, and chronology exactly.",
                    "Return one work entry for each source work entry in the same order.",
                    "Preserve at least one bullet per role and do not invent jobs or dates.",
                    "Keep rewritten bullets plausible and grounded in the source resume.",
                    "Cover letter must use the problem-solution format: open by naming the specific role and company, then identify ONE challenge or goal the company/role is facing (inferred from the job description), present the candidate as the solution with 1-2 quantified achievements from their actual experience, and close with a specific call to action.",
                    "Cover letter must: mention the company by name at least once, include at least one metric or number from the candidate's experience, stay under 300 words, and NOT open with 'I am writing to apply'.",
                ],
            },
        }
        if retry_count > 0:
            prompt["instructions"]["constraints"].extend(
                [
                    "Avoid repeated openings or repeated closing clauses across bullets.",
                    "Reject any broken grammar such as duplicated verbs or dropped conjunctions.",
                    "Prefer preserving the original sentence when uncertain.",
                    "If retry_sections excludes a section, preserve that section from current_preview.",
                ]
            )

        system_prompt = (
            "You tailor resume and cover-letter content for job applications. "
            "Return only valid JSON with keys work_entries, key_skills, and cover_letter_text. "
            "Do not invent employers, titles, or dates. Preserve chronology. "
            "Improve wording quality and relevance while keeping claims plausibly grounded in the source resume. "
            "For cover_letter_text, always use the problem-solution format: name the role/company, identify a challenge from the job description, "
            "present the candidate as the solution with a quantified achievement, and close with a call to action. "
            "The cover letter must mention the company by name, include at least one metric, stay under 300 words, and never open with 'I am writing to apply'."
        )
        try:
            text, _meta = self._create_doc_tailoring_completion(provider, model, prompt, system_prompt=system_prompt)
            if not text:
                return DocumentTailoringAttempt(
                    attempted=True,
                    provider=provider,
                    model=model,
                    failure_reason="OpenAI response did not contain extractable text.",
                    retry_count=retry_count,
                )
            cleaned_text = self._extract_json_text(text)
            try:
                payload = json.loads(cleaned_text)
            except json.JSONDecodeError:
                payload = json.loads(cleaned_text.replace("\r\n", "\\n").replace("\n", "\\n"))
        except json.JSONDecodeError:
            LOGGER.exception("Failed to parse AI document tailoring response for %s", job.id)
            LOGGER.warning("AI document tailoring parse preview for %s: %s", job.id, self._safe_preview(cleaned_text if 'cleaned_text' in locals() else text if 'text' in locals() else ""))
            return DocumentTailoringAttempt(
                attempted=True,
                provider=provider,
                model=model,
                failure_reason="OpenAI response could not be parsed as JSON.",
                retry_count=retry_count,
            )
        except Exception as exc:
            LOGGER.exception("Failed AI document tailoring for %s", job.id)
            return DocumentTailoringAttempt(
                attempted=True,
                provider=provider,
                model=model,
                failure_reason=f"OpenAI request failed: {exc}",
                retry_count=retry_count,
            )

        try:
            tailored_entries = self._parse_tailored_entries(payload.get("work_entries"), resume_data)
            key_skills = self._parse_tailored_key_skills(payload.get("key_skills"), local_preview.key_skills)
            cover_letter_text = self._parse_tailored_cover_letter(payload.get("cover_letter_text"))
        except Exception:
            LOGGER.exception("Failed to parse AI document tailoring payload for %s", job.id)
            return DocumentTailoringAttempt(
                attempted=True,
                provider=provider,
                model=model,
                failure_reason="OpenAI payload structure could not be parsed.",
                retry_count=retry_count,
            )

        return DocumentTailoringAttempt(
            attempted=True,
            provider=provider,
            model=model,
            retry_count=retry_count,
            payload=DocumentTailoringPayload(
                work_entries=tailored_entries,
                key_skills=key_skills,
                cover_letter_text=cover_letter_text,
                route="openai",
                ai_attempted=True,
                provider=provider,
                model=model,
                retry_count=retry_count,
            ),
        )

    def _evaluate(
        self,
        *,
        stage_name: str,
        provider: str,
        model: str,
        job: Job,
        resume_data: ResumeData,
        prompt: dict[str, object],
    ) -> StageEvaluation:
        evaluated_at = datetime.now(timezone.utc).isoformat()
        resume_hash = self.build_resume_hash(resume_data)
        if self.database:
            cached = self.database.get_ai_evaluation(
                job.id,
                stage_name=stage_name,
                resume_hash=resume_hash,
                provider=provider,
                model=model,
                prompt_version=PROMPT_VERSION,
            )
            if cached:
                return self._record_to_eval(cached, cached=True)

        if self._build_client(provider) is None:
            return self._store_result(
                job.id,
                StageEvaluation(
                    stage_name=stage_name,
                    provider=provider,
                    model=model,
                    status="error",
                    decision="error",
                    score=None,
                    confidence=None,
                    rationale=f"{provider} is not configured or available.",
                    strengths=[],
                    gaps=[],
                    input_tokens=0,
                    output_tokens=0,
                    estimated_cost_usd=0.0,
                    error_message=f"{provider} client unavailable",
                    evaluated_at=evaluated_at,
                ),
                resume_hash,
            )

        try:
            text, input_tokens, output_tokens = _call_with_retry(
                lambda: self._create_completion_with_usage(provider, model, prompt)
            )
            payload = json.loads(text)
            # Validate and clamp score to [0, 100]
            raw_score = payload.get("score", 0)
            score = max(0, min(100, int(raw_score))) if raw_score is not None else 0
            if raw_score != score:
                LOGGER.warning("AI returned out-of-range score %s for %s; clamped to %s", raw_score, job.id, score)
            confidence = self._parse_confidence(payload.get("confidence", 0.0))
            decision = self._decision_for(stage_name, score=score, confidence=confidence, force_escalate=bool(payload.get("force_escalate", False)))
            # Validate decision enum
            valid_decisions = _VALID_CHEAP_DECISIONS if stage_name == "cheap" else _VALID_STRONG_DECISIONS
            if decision not in valid_decisions:
                LOGGER.warning("Unexpected decision %r for stage %s on %s; treating as escalate/review", decision, stage_name, job.id)
                decision = "escalate" if stage_name == "cheap" else "review"
            evaluation = StageEvaluation(
                stage_name=stage_name,
                provider=provider,
                model=model,
                status="scored",
                decision=decision,
                score=score,
                confidence=confidence,
                rationale=str(payload.get("rationale", "")) or "No rationale provided.",
                strengths=[str(item) for item in payload.get("strengths", [])][:5],
                gaps=[str(item) for item in payload.get("gaps", [])][:5],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=self._estimate_cost(provider, model, input_tokens, output_tokens),
                error_message="",
                evaluated_at=evaluated_at,
            )
            return self._store_result(job.id, evaluation, resume_hash)
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Failed %s evaluation for %s", stage_name, job.id)
            return self._store_result(
                job.id,
                StageEvaluation(
                    stage_name=stage_name,
                    provider=provider,
                    model=model,
                    status="error",
                    decision="error",
                    score=None,
                    confidence=None,
                    rationale="Evaluation failed.",
                    strengths=[],
                    gaps=[],
                    input_tokens=0,
                    output_tokens=0,
                    estimated_cost_usd=0.0,
                    error_message=str(exc),
                    evaluated_at=evaluated_at,
                ),
                resume_hash,
            )

    @staticmethod
    def _parse_confidence(value: object) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip().lower()
        if not text:
            return 0.0
        label_map = {
            "very low": 0.1,
            "low": 0.25,
            "moderate": 0.6,
            "medium": 0.6,
            "high": 0.85,
            "very high": 0.95,
        }
        if text in label_map:
            return label_map[text]
        try:
            return float(text)
        except ValueError:
            return 0.0

    def _store_result(self, job_id: str, evaluation: StageEvaluation, resume_hash: str) -> StageEvaluation:
        if self.database:
            self.database.upsert_ai_evaluation(
                StageEvaluationRecord(
                    job_id=job_id,
                    stage_name=evaluation.stage_name,
                    resume_hash=resume_hash,
                    provider=evaluation.provider,
                    model=evaluation.model,
                    prompt_version=PROMPT_VERSION,
                    status=evaluation.status,
                    decision=evaluation.decision,
                    score=evaluation.score,
                    confidence=evaluation.confidence,
                    rationale=evaluation.rationale,
                    strengths=evaluation.strengths,
                    gaps=evaluation.gaps,
                    input_tokens=evaluation.input_tokens,
                    output_tokens=evaluation.output_tokens,
                    estimated_cost_usd=evaluation.estimated_cost_usd,
                    cached=evaluation.cached,
                    evaluated_at=evaluation.evaluated_at,
                )
            )
        return evaluation

    def _record_to_eval(self, record: StageEvaluationRecord, *, cached: bool) -> StageEvaluation:
        return StageEvaluation(
            stage_name=record.stage_name,
            provider=record.provider,
            model=record.model,
            status=record.status,
            decision=record.decision,
            score=record.score,
            confidence=record.confidence,
            rationale=record.rationale,
            strengths=record.strengths,
            gaps=record.gaps,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            estimated_cost_usd=record.estimated_cost_usd,
            error_message="",
            evaluated_at=record.evaluated_at,
            cached=cached,
        )

    def _cheap_fallback_provider(self) -> tuple[str, str] | None:
        if self.config.openai_api_key:
            return ("openai", "gpt-5-nano")
        if self.config.anthropic_api_key:
            return ("anthropic", "claude-haiku-4-5-20251001")
        return None

    def _build_cheap_prompt(self, job: Job, resume_data: ResumeData, *, force_escalate: bool) -> dict[str, object]:
        overlap_terms = self._keyword_overlap_terms(
            self._build_job_gate_text(job),
            self._build_resume_gate_text(resume_data),
        )
        overlap_count = len(overlap_terms)
        screening: dict[str, object] = {}
        if self.config.source.location and self.config.source.location.strip():
            screening["target_location"] = self.config.source.location.strip()
            screening["location_note"] = (
                "Accept remote jobs regardless of location. "
                "Accept jobs whose location is in the same metro area as target_location. "
                "Reject jobs clearly in a different city or state."
            )
        if self.config.salary_floor > 0:
            screening["salary_floor_usd"] = self.config.salary_floor
            screening["salary_note"] = (
                "If the job lists a salary or range, reject if the lower bound annualised "
                "is clearly below salary_floor_usd. If salary is unlisted or ambiguous, do not reject."
            )
        return {
            "resume_summary": self._resume_summary(resume_data),
            "job": self._job_summary(job),
            "force_escalate": force_escalate,
            "screening_constraints": screening,
            "keyword_overlap_terms": overlap_terms[:12],
            "keyword_overlap_count": overlap_count,
            "instructions": {
                "return_json": True,
                "fields": ["score", "confidence", "rationale", "strengths", "gaps"],
                "goal": (
                    "Fast screening pass using the rubric above. Apply screening_constraints first — "
                    "if the job clearly fails location or salary constraints, score below 25. "
                    "Use the rubric to score resume fit. Be consistent; return a confident score when the match is obvious. "
                    "If keyword_overlap_count is high, avoid scoring below 50 unless core requirements are clearly missing."
                ),
            },
        }

    def _build_strong_prompt(self, job: Job, resume_data: ResumeData) -> dict[str, object]:
        overlap_terms = self._keyword_overlap_terms(
            self._build_job_gate_text(job),
            self._build_resume_gate_text(resume_data),
        )
        overlap_count = len(overlap_terms)
        return {
            "resume_summary": self._resume_summary(resume_data),
            "job": self._job_summary(job),
            "keyword_overlap_terms": overlap_terms[:12],
            "keyword_overlap_count": overlap_count,
            "instructions": {
                "return_json": True,
                "fields": ["score", "confidence", "rationale", "strengths", "gaps"],
                "goal": (
                    "Deeper fit review using the rubric above. Score the resume against core job requirements precisely. "
                    "If keyword_overlap_count is high, avoid scoring below 50 unless core requirements are clearly missing."
                ),
            },
        }

    def _resume_summary(self, resume_data: ResumeData) -> dict[str, object]:
        return {
            "name": resume_data.name,
            "summary": resume_data.summary,
            "skills": resume_data.skills[:15],
            "experience_highlights": resume_data.experience_lines[:8],
        }

    def _job_summary(self, job: Job) -> dict[str, object]:
        return {
            "title": job.title,
            "employer": job.employer,
            "location": job.location,
            "salary_range": job.salary_range,
            "description_excerpt": job.description_full[:2500],
            "apply_url": job.apply_url,
        }

    @staticmethod
    def _tokenize_terms(text: str) -> set[str]:
        if not text:
            return set()
        tokens = {
            token
            for token in re.findall(r"[a-z][a-z0-9+#&-]{2,}", text.lower())
            if token not in _PRECHEAP_STOPWORDS
        }
        return tokens

    def _keyword_overlap_terms(self, job_text: str, resume_text: str) -> list[str]:
        job_terms = self._tokenize_terms(job_text)
        resume_terms = self._tokenize_terms(resume_text)
        overlap = sorted(job_terms & resume_terms)
        return overlap

    @staticmethod
    def _build_resume_gate_text(resume_data: ResumeData) -> str:
        parts = [
            resume_data.summary or "",
            " ".join(resume_data.skills or []),
            " ".join(resume_data.experience_lines or []),
        ]
        return " ".join(part for part in parts if part).strip()

    @staticmethod
    def _build_job_gate_text(job: Job) -> str:
        return f"{job.title} {job.description_full}".strip()

    @staticmethod
    def _tfidf_similarity_score(resume_text: str, job_text: str) -> int:
        if TfidfVectorizer is None or cosine_similarity is None:
            return 0
        try:
            vectorizer = TfidfVectorizer(stop_words="english", max_features=1500)
            vectors = vectorizer.fit_transform([resume_text, job_text])
            similarity = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]
            return int(round(float(similarity) * 100))
        except ValueError:
            return 0

    def _title_match_score(self, title: str) -> int:
        title_lower = (title or "").lower()
        include_hits = sum(1 for item in self.config.include_titles if item.strip() and item.strip().lower() in title_lower)
        exclude_hits = sum(1 for item in self.config.exclude_titles if item.strip() and item.strip().lower() in title_lower)
        target_hits = sum(1 for item in self.config.target_titles if item.strip() and item.strip().lower() in title_lower)
        title_tokens = self._tokenize_terms(title_lower)
        keyword_tokens = self._tokenize_terms(" ".join(self.config.include_titles + self.config.target_titles + [self.config.source.keyword]))
        token_overlap = len(title_tokens & keyword_tokens)
        score = 35 + (include_hits * 22) + (target_hits * 15) + (token_overlap * 8) - (exclude_hits * 35)
        return max(0, min(100, score))

    def _target_title_overlap(self, title: str) -> int:
        title_tokens = self._tokenize_terms(title)
        target_tokens = self._tokenize_terms(" ".join(self.config.target_titles))
        if not title_tokens or not target_tokens:
            return 0
        overlap = len(title_tokens & target_tokens)
        return min(overlap * 20, 100)

    def _location_penalty(self, job: Job) -> int:
        target = (self.config.source.location or "").strip().lower()
        job_location = (job.location or "").strip().lower()
        if not target or not job_location:
            return 0
        if "remote" in job_location:
            return 0
        target_terms = self._tokenize_terms(target)
        job_terms = self._tokenize_terms(job_location)
        return 0 if (target_terms & job_terms) else 10

    def _salary_penalty(self, job: Job) -> int:
        floor = int(self.config.salary_floor or 0)
        if floor <= 0:
            return 0
        salary_text = (job.salary_range or "").replace(",", "")
        values = [int(match) for match in re.findall(r"\d{2,6}", salary_text)]
        if not values:
            return 0
        lower_bound = min(values)
        if lower_bound >= floor:
            return 0
        gap_ratio = max(0.0, min(1.0, (floor - lower_bound) / max(floor, 1)))
        return int(round(6 + (gap_ratio * 14)))

    def _query_overlap_score(self, job_text: str) -> int:
        query = (self.config.source.keyword or "").strip()
        if not query:
            return 0
        query_tokens = self._tokenize_terms(query)
        if not query_tokens:
            return 0
        job_tokens = self._tokenize_terms(job_text)
        overlap = len(query_tokens & job_tokens)
        return min(overlap * 25, 100)

    @staticmethod
    def _contains_any(text: str, phrases: list[str]) -> bool:
        lowered = (text or "").lower()
        return any(phrase.strip().lower() in lowered for phrase in phrases if phrase.strip())

    def _decision_for(self, stage_name: str, *, score: int, confidence: float, force_escalate: bool) -> str:
        if stage_name == "cheap":
            if force_escalate:
                return "escalate"
            if score < self.config.cheap_reject_threshold and confidence >= 0.75:
                return "reject"
            if score >= self.config.cheap_escalate_threshold and confidence >= 0.85:
                return "pass_direct"
            return "escalate"
        if score >= self.config.final_apply_threshold:
            return "apply_candidate"
        if score >= self.config.scoring_threshold:
            return "review"
        return "skip"

    def _build_client(self, provider: str):
        if provider in self._client_cache:
            return self._client_cache[provider]
        if provider == "ollama_local":
            try:
                req = request.Request(f"{self.config.ollama_base_url.rstrip('/')}/api/tags", method="GET")
                with request.urlopen(req, timeout=2):
                    client = {"base_url": self.config.ollama_base_url.rstrip("/")}
                    self._client_cache[provider] = client
                    return client
            except Exception:  # pragma: no cover
                self._client_cache[provider] = None
                return None
        if provider == "anthropic":
            api_key = self.config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                try:
                    from anthropic import Anthropic
                except ImportError:  # pragma: no cover
                    self._client_cache[provider] = None
                    return None
                client = Anthropic(api_key=api_key)
                self._client_cache[provider] = client
                return client
        if provider == "openai":
            api_key = self.config.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
            if api_key:
                try:
                    from openai import OpenAI
                except ImportError:  # pragma: no cover
                    self._client_cache[provider] = None
                    return None
                client = OpenAI(api_key=api_key)
                self._client_cache[provider] = client
                return client
        self._client_cache[provider] = None
        return None

    def _create_completion_with_usage(self, provider: str, model: str, prompt: dict[str, object]) -> tuple[str, int, int]:
        system_prompt = (
            "You are a recruiting evaluator. Do not invent qualifications. "
            "Return only valid JSON with keys score (int 0-100), confidence (float 0.0-1.0), "
            "rationale (string), strengths (list), and gaps (list).\n\n"
            "Scoring rubric:\n"
            "  0-24:  Clear mismatch — wrong field, wrong seniority, or clearly unqualified\n"
            "  25-39: Marginal — some relevance but missing most key requirements\n"
            "  40-59: Partial fit — meets some requirements, notable gaps in core skills\n"
            "  60-79: Good fit — meets most requirements with minor gaps\n"
            "  80-100: Strong fit — meets all or nearly all core requirements"
        )
        return self._create_completion_with_usage_for_system(provider, model, prompt, system_prompt=system_prompt)

    def _create_completion_with_usage_for_system(
        self,
        provider: str,
        model: str,
        prompt: dict[str, object],
        *,
        system_prompt: str,
    ) -> tuple[str, int, int]:
        if provider == "ollama_local":
            return self._create_ollama_completion(model, prompt, system_prompt=system_prompt)

        client = self._build_client(provider)
        if provider == "anthropic":
            response = client.messages.create(
                model=model,
                max_tokens=1000,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": json.dumps(prompt)}],
            )
            text = ""
            for block in response.content:
                block_text = getattr(block, "text", None)
                if block_text:
                    text = block_text.strip()
                    break
            if not text:
                LOGGER.warning("Anthropic returned empty text. stop_reason=%s content=%r", getattr(response, "stop_reason", None), response.content)
            usage = getattr(response, "usage", None)
            return text, int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            max_completion_tokens=1000,
            temperature=0,
            response_format={"type": "json_object"},
        )
        text = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        return text, int(getattr(usage, "prompt_tokens", 0) or 0), int(getattr(usage, "completion_tokens", 0) or 0)

    def _create_completion(self, provider: str, model: str, prompt: dict[str, object], *, system_prompt: str) -> str:
        if provider == "ollama_local":
            text, _, _ = self._create_ollama_completion(model, prompt, system_prompt=system_prompt)
            return text
        client = self._build_client(provider)
        if provider == "anthropic":
            response = client.messages.create(
                model=model,
                max_tokens=1000,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": json.dumps(prompt)}],
            )
            for block in response.content:
                block_text = getattr(block, "text", None)
                if block_text:
                    return block_text.strip()
            return ""
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            max_completion_tokens=1000,
            temperature=0,
            response_format={"type": "json_object"},
        )
        return (response.choices[0].message.content or "").strip()

    def _create_doc_tailoring_completion(
        self, provider: str, model: str, prompt: dict[str, object], *, system_prompt: str
    ) -> tuple[str, dict[str, object]]:
        """Use OpenAI Responses API with structured JSON schema output for document tailoring.

        Returns (text, meta) where text is a JSON string and meta describes how it was extracted.
        """
        client = self._build_client(provider)
        schema = {
            "type": "object",
            "properties": {
                "work_entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role_line": {"type": "string"},
                            "date_line": {"type": "string"},
                            "bullets": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["role_line", "date_line", "bullets"],
                        "additionalProperties": False,
                    },
                },
                "key_skills": {"type": "array", "items": {"type": "string"}},
                "cover_letter_text": {"type": "string"},
            },
            "required": ["work_entries", "key_skills", "cover_letter_text"],
            "additionalProperties": False,
        }
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            text={"format": {"type": "json_schema", "name": "document_tailoring", "schema": schema, "strict": True}},
            max_output_tokens=4000,
        )
        # Try structured output from model_dump (json_schema mode)
        try:
            dumped = response.model_dump(mode="python")
            structured = dumped.get("response")
            if isinstance(structured, dict) and "work_entries" in structured:
                text = json.dumps(structured)
                return text, {"mode": "json_schema", "shape_summary": "message(response)", "text_length": len(text)}
        except Exception:
            pass
        # Fall back to text extraction from output items
        text = ""
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) == "output_text":
                    text = getattr(content, "text", "") or ""
                    if text:
                        break
            if text:
                break
        return text, {"mode": "text_fallback", "shape_summary": "message(output_text)", "text_length": len(text)}

    def _create_ollama_completion(self, model: str, prompt: dict[str, object], *, system_prompt: str) -> tuple[str, int, int]:
        body = json.dumps(
            {
                "model": model,
                "stream": False,
                "format": "json",
                "prompt": f"{system_prompt}\n\n{json.dumps(prompt)}",
            }
        ).encode("utf-8")
        req = request.Request(
            url=f"{self.config.ollama_base_url.rstrip('/')}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError) as exc:  # pragma: no cover
            raise RuntimeError("Ollama is unavailable") from exc
        return str(payload.get("response", "")).strip(), int(payload.get("prompt_eval_count", 0)), int(payload.get("eval_count", 0))

    @staticmethod
    def _extract_openai_response_text(response: object) -> str:
        output_text = getattr(response, "output_text", "")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        parts: list[str] = []
        for output_item in getattr(response, "output", []) or []:
            for content_item in getattr(output_item, "content", []) or []:
                text_value = getattr(content_item, "text", None)
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(text_value.strip())
                    continue
                for attr in ("value", "output_text"):
                    candidate = getattr(content_item, attr, None)
                    if isinstance(candidate, str) and candidate.strip():
                        parts.append(candidate.strip())
                        break
                annotations = getattr(content_item, "annotations", None)
                if isinstance(annotations, list):
                    for annotation in annotations:
                        candidate = getattr(annotation, "text", None)
                        if isinstance(candidate, str) and candidate.strip():
                            parts.append(candidate.strip())
        return "\n".join(parts).strip()

    @staticmethod
    def _parse_keyword_response(text: str) -> list[str]:
        cleaned: list[str] = []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"keywords": re.split(r"[\s,]+", text.strip())}
        for item in payload.get("keywords", []):
            keyword = str(item).strip()
            keyword = re.sub(r"\s+", " ", keyword)
            keyword = keyword.strip(",.;:")
            if keyword:
                cleaned.append(keyword)
        return cleaned[:16]

    @staticmethod
    def _validate_doc_provider_model(provider: str, model: str) -> str:
        if provider == "openai":
            lowered = model.strip().lower()
            if not lowered:
                return "OpenAI model is blank."
            if ":" in lowered or lowered.startswith("qwen") or lowered.startswith("llama") or lowered.startswith("mistral"):
                return f"OpenAI model mismatch: {model} is not valid for provider openai."
        return ""

    @staticmethod
    def _safe_preview(text: str, limit: int = 200) -> str:
        cleaned = re.sub(r"\s+", " ", text or "").strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit].rstrip() + "..."

    @staticmethod
    def _parse_tailored_key_skills(value: object, fallback: list[str]) -> list[str]:
        if not isinstance(value, list):
            return fallback
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            skill = re.sub(r"\s+", " ", str(item or "").strip()).strip(",.;:")
            normalized = skill.lower()
            if not skill or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(skill)
        return cleaned or fallback

    @staticmethod
    def _parse_tailored_cover_letter(value: object) -> str:
        text = re.sub(r"\s+\n", "\n", str(value or "").strip())
        return text

    @staticmethod
    def _parse_tailored_entries(value: object, resume_data: ResumeData) -> list[ResumeWorkEntry]:
        if not isinstance(value, list) or len(value) != len(resume_data.work_experience_entries):
            return resume_data.work_experience_entries
        parsed: list[ResumeWorkEntry] = []
        for source_entry, item in zip(resume_data.work_experience_entries, value):
            if not isinstance(item, dict):
                return resume_data.work_experience_entries
            bullets_raw = item.get("bullets")
            if not isinstance(bullets_raw, list):
                return resume_data.work_experience_entries
            bullets = [
                re.sub(r"\s+", " ", str(bullet or "").strip()).strip()
                for bullet in bullets_raw
                if str(bullet or "").strip()
            ]
            if not bullets:
                bullets = source_entry.bullets[:1] or [source_entry.role_line]
            parsed.append(
                ResumeWorkEntry(
                    role_line=source_entry.role_line,
                    date_line=source_entry.date_line,
                    bullets=bullets,
                    role_template=source_entry.role_template,
                    date_template=source_entry.date_template,
                    bullet_templates=source_entry.bullet_templates,
                )
            )
        return parsed

    @staticmethod
    def _extract_json_text(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end >= start:
            return cleaned[start:end + 1].strip()
        return cleaned

    def _estimate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        if not self.config.enable_cost_tracking:
            return 0.0
        if provider == "openai":
            pricing = OPENAI_PRICE_PER_MTOKEN.get(model, {"input": 0.0, "output": 0.0})
            return round((input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"], 6)
        if provider == "anthropic":
            pricing = ANTHROPIC_PRICE_PER_MTOKEN.get(model, {"input": 0.0, "output": 0.0})
            return round((input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"], 6)
        return 0.0

    def _resolve_doc_provider_model(self) -> tuple[str, str]:
        if self.config.doc_stage_provider == "ollama_local":
            return "ollama_local", self.config.cheap_stage_model
        return self.config.doc_stage_provider, self.config.doc_stage_model
