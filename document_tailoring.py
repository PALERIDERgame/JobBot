from __future__ import annotations

from dataclasses import dataclass, field

from resume_parser import ResumeWorkEntry


@dataclass(slots=True)
class DocumentTailoringPayload:
    work_entries: list[ResumeWorkEntry] = field(default_factory=list)
    key_skills: list[str] = field(default_factory=list)
    cover_letter_text: str = ""
    route: str = "local"
    ai_attempted: bool = False
    provider: str = ""
    model: str = ""
    fallback_reason: str = ""
    retry_count: int = 0
    resume_ai_status: str = "local"
    cover_letter_ai_status: str = "local"
    rejected_bullets_repaired: int = 0
    cover_letter_fallback: str = ""


@dataclass(slots=True)
class DocumentTailoringAttempt:
    payload: DocumentTailoringPayload | None = None
    attempted: bool = False
    provider: str = ""
    model: str = ""
    failure_reason: str = ""
    retry_count: int = 0
