from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from config import JobBotConfig
from database import Job
from resume_parser import ResumeData


LOGGER = logging.getLogger(__name__)
MODEL_NAME = "claude-sonnet-4-20250514"


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


class MatchScorer:
    def __init__(self, config: JobBotConfig) -> None:
        self.config = config
        self.client = self._build_client(config.anthropic_api_key)

    def score_job(self, job: Job, resume_data: ResumeData) -> MatchScore:
        scored_at = datetime.now(timezone.utc).isoformat()
        if not self.client:
            return MatchScore(
                score=None,
                rationale="Anthropic API key is not configured.",
                strengths=[],
                gaps=[],
                is_match=False,
                status="error",
                error_message="Missing Anthropic API key",
                scored_at=scored_at,
            )

        prompt = {
            "resume": {
                "name": resume_data.name,
                "summary": resume_data.summary,
                "skills": resume_data.skills,
                "experience_lines": resume_data.experience_lines,
            },
            "job": {
                "title": job.title,
                "employer": job.employer,
                "location": job.location,
                "salary_range": job.salary_range,
                "description_full": job.description_full,
            },
            "instructions": {
                "return_json": True,
                "fields": ["score", "rationale", "strengths", "gaps"],
                "scoring_scale": "0-100",
                "be_conservative": True,
            },
        }

        try:
            response = self.client.messages.create(
                model=MODEL_NAME,
                max_tokens=1000,
                temperature=0,
                system=(
                    "You are a careful recruiting analyst. Compare the candidate resume to the job. "
                    "Do not invent qualifications. Return only valid JSON with keys "
                    "score, rationale, strengths, and gaps."
                ),
                messages=[{"role": "user", "content": json.dumps(prompt)}],
            )
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            ).strip()
            payload = json.loads(text)
            score = int(payload.get("score", 0))
            return MatchScore(
                score=score,
                rationale=str(payload.get("rationale", "")),
                strengths=[str(item) for item in payload.get("strengths", [])][:5],
                gaps=[str(item) for item in payload.get("gaps", [])][:5],
                is_match=score >= self.config.scoring_threshold,
                status="scored",
                error_message="",
                scored_at=scored_at,
            )
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Failed to score job %s", job.id)
            return MatchScore(
                score=None,
                rationale="Scoring failed.",
                strengths=[],
                gaps=[],
                is_match=False,
                status="error",
                error_message=str(exc),
                scored_at=scored_at,
            )

    @staticmethod
    def _build_client(api_key: str):
        if not api_key:
            return None
        try:
            from anthropic import Anthropic
        except ImportError:  # pragma: no cover
            return None
        return Anthropic(api_key=api_key)
