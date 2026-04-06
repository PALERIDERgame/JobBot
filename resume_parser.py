from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ResumeData:
    source_path: str
    raw_text: str
    name: str
    email: str
    phone: str
    summary: str
    skills: list[str]
    experience_lines: list[str]

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "raw_text": self.raw_text,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "summary": self.summary,
            "skills": self.skills,
            "experience_lines": self.experience_lines,
        }


def _extract_text_from_path(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        if pdfplumber is None:
            raise RuntimeError("pdfplumber is required to parse PDF resumes")
        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return "\n".join(pages).strip()
    return path.read_text(encoding="utf-8").strip()


def _find_line(lines: list[str], token: str) -> str:
    token = token.lower()
    for line in lines:
        if token in line.lower():
            return line.strip()
    return ""


def _guess_name(lines: list[str]) -> str:
    for line in lines[:5]:
        line = line.strip()
        if not line:
            continue
        if "@" in line or any(ch.isdigit() for ch in line):
            continue
        return line
    return "Unknown Candidate"


def parse_resume(source_path: Path, cache_path: Path) -> ResumeData:
    text = _extract_text_from_path(source_path)
    if not text:
        raise ValueError("Resume file contained no extractable text")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    email = next((line for line in lines if "@" in line), "")
    phone = next((line for line in lines if sum(ch.isdigit() for ch in line) >= 7), "")
    skills_line = _find_line(lines, "skills")
    summary_line = _find_line(lines, "summary") or " ".join(lines[:3])
    experience_lines = [line for line in lines if any(keyword in line.lower() for keyword in ("engineer", "developer", "manager", "analyst", "designed", "built"))][:8]
    skills = [part.strip(" ,") for part in skills_line.split(":")[-1].split(",") if part.strip()] if skills_line else []
    resume = ResumeData(
        source_path=str(source_path),
        raw_text=text,
        name=_guess_name(lines),
        email=email,
        phone=phone,
        summary=summary_line,
        skills=skills,
        experience_lines=experience_lines,
    )
    cache_path.write_text(json.dumps(resume.to_dict(), indent=2), encoding="utf-8")
    LOGGER.info("Cached parsed resume at %s", cache_path)
    return resume


def load_cached_resume(cache_path: Path) -> ResumeData | None:
    if not cache_path.exists():
        return None
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    return ResumeData(**payload)
