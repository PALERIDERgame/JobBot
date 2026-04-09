from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib import error, request

from config import JobBotConfig
from database import Database, Job, StageEvaluationRecord
from document_tailoring import DocumentTailoringAttempt, DocumentTailoringPayload
from resume_parser import ResumeData, ResumeWorkEntry


LOGGER = logging.getLogger(__name__)
PROMPT_VERSION = "cost_funnel_v2"

OPENAI_PRICE_PER_MTOKEN = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-5-nano": {"input": 0.20, "output": 1.25},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
}
ANTHROPIC_PRICE_PER_MTOKEN = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
}


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


class MatchScorer:
    def __init__(self, config: JobBotConfig, database: Database | None = None) -> None:
        self.config = config
        self.database = database

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

    def score_job(self, job: Job, resume_data: ResumeData) -> MatchScore:
        evaluation = self.strong_evaluate(job, resume_data)
        return evaluation.to_match_score(self.config.final_apply_threshold)

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
                    "Keep cover letter concise and professional.",
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
            "Improve wording quality and relevance while keeping claims plausibly grounded in the source resume."
        )
        try:
            text = self._create_completion(provider, model, prompt, system_prompt=system_prompt)
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
            text, input_tokens, output_tokens = self._create_completion_with_usage(provider, model, prompt)
            payload = json.loads(text)
            score = int(payload.get("score", 0))
            confidence = self._parse_confidence(payload.get("confidence", 0.0))
            decision = self._decision_for(stage_name, score=score, confidence=confidence, force_escalate=bool(payload.get("force_escalate", False)))
            evaluation = StageEvaluation(
                stage_name=stage_name,
                provider=provider,
                model=model,
                status="scored",
                decision=decision,
                score=score,
                confidence=confidence,
                rationale=str(payload.get("rationale", "")),
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
            return ("anthropic", "claude-3-5-haiku-latest")
        return None

    def _build_cheap_prompt(self, job: Job, resume_data: ResumeData, *, force_escalate: bool) -> dict[str, object]:
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
            "instructions": {
                "return_json": True,
                "fields": ["score", "confidence", "rationale", "strengths", "gaps"],
                "goal": (
                    "Fast screening pass using the rubric above. Apply screening_constraints first — "
                    "if the job clearly fails location or salary constraints, score below 25. "
                    "Use the rubric to score resume fit. Be consistent; return a confident score when the match is obvious."
                ),
            },
        }

    def _build_strong_prompt(self, job: Job, resume_data: ResumeData) -> dict[str, object]:
        return {
            "resume_summary": self._resume_summary(resume_data),
            "job": self._job_summary(job),
            "instructions": {
                "return_json": True,
                "fields": ["score", "confidence", "rationale", "strengths", "gaps"],
                "goal": "Deeper fit review using the rubric above. Score the resume against core job requirements precisely.",
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
        if provider == "ollama_local":
            try:
                req = request.Request(f"{self.config.ollama_base_url.rstrip('/')}/api/tags", method="GET")
                with request.urlopen(req, timeout=2):
                    return {"base_url": self.config.ollama_base_url.rstrip("/")}
            except Exception:  # pragma: no cover
                return None
        if provider == "anthropic" and self.config.anthropic_api_key:
            try:
                from anthropic import Anthropic
            except ImportError:  # pragma: no cover
                return None
            return Anthropic(api_key=self.config.anthropic_api_key)
        if provider == "openai" and self.config.openai_api_key:
            try:
                from openai import OpenAI
            except ImportError:  # pragma: no cover
                return None
            return OpenAI(api_key=self.config.openai_api_key)
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
            text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()
            usage = getattr(response, "usage", None)
            return text, int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            max_tokens=1000,
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
            return "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            max_tokens=1000,
            temperature=0,
            response_format={"type": "json_object"},
        )
        return (response.choices[0].message.content or "").strip()

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
        if self.config.doc_stage_provider == "cheap_stage":
            return self.config.cheap_stage_provider, self.config.cheap_stage_model
        return self.config.doc_stage_provider, self.config.doc_stage_model
