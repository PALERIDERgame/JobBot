from __future__ import annotations

from dataclasses import dataclass, field

from resume_parser import ResumeWorkEntry


@dataclass(slots=True)
class DocumentTailoringPayload:
    work_entries: list[ResumeWorkEntry] = field(default_factory=list)
    key_skills: list[str] = field(default_factory=list)
    cover_letter_text: str = ""
    route: str = "local"
    provider: str = ""
    model: str = ""
    fallback_reason: str = ""
    retry_count: int = 0

