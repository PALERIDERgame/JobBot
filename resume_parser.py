from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

try:
    from docx import Document as DocxDocument
except ImportError:  # pragma: no cover
    DocxDocument = None


LOGGER = logging.getLogger(__name__)
SECTION_HEADERS = {
    "summary",
    "professional summary",
    "profile",
    "objective",
    "skills",
    "key skills",
    "technical skills",
    "work experience",
    "experience",
    "professional experience",
    "education",
}
MONTH_PATTERN = re.compile(
    r"^(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)"
    r"(?:\s+\d{4})?(?:\s*-\s*(?:PRESENT|(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{4}))?$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ResumeWorkEntry:
    role_line: str
    date_line: str
    bullets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "role_line": self.role_line,
            "date_line": self.date_line,
            "bullets": self.bullets,
        }


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
    header_lines: list[str] = field(default_factory=list)
    education_lines: list[str] = field(default_factory=list)
    key_skills_lines: list[str] = field(default_factory=list)
    work_experience_entries: list[ResumeWorkEntry] = field(default_factory=list)

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
            "header_lines": self.header_lines,
            "education_lines": self.education_lines,
            "key_skills_lines": self.key_skills_lines,
            "work_experience_entries": [entry.to_dict() for entry in self.work_experience_entries],
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
    if path.suffix.lower() == ".docx":
        if DocxDocument is None:
            raise RuntimeError("python-docx is required to parse DOCX resumes")
        document = DocxDocument(str(path))
        paragraphs: list[str] = []
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
            if "bullet" in style_name and not text.startswith(("•", "-", "*")):
                text = f"• {text}"
            paragraphs.append(text)
        return "\n".join(paragraphs).strip()
    return path.read_text(encoding="utf-8").strip()


def _find_line(lines: list[str], token: str) -> str:
    token = token.lower()
    for line in lines:
        if token in line.lower():
            return line.strip()
    return ""


def _extract_email(text: str) -> str:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else ""


def _extract_phone(text: str) -> str:
    match = re.search(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}", text)
    return match.group(0) if match else ""


def _normalize_header(line: str) -> str:
    return re.sub(r"[:\s]+$", "", line.strip().lower())


def _is_section_header(line: str) -> bool:
    normalized = _normalize_header(line)
    return normalized in SECTION_HEADERS


def _is_contact_or_link_line(line: str) -> bool:
    lowered = line.lower()
    return bool(
        _extract_email(line)
        or _extract_phone(line)
        or "linkedin.com" in lowered
        or "http://" in lowered
        or "https://" in lowered
        or "|" in line
    )


def _is_noise_line(line: str) -> bool:
    lowered = line.lower()
    return _is_contact_or_link_line(line) or lowered in {"work experience", "experience", "key skills", "skills"}


def _summary_from_sections(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if _normalize_header(line) in {"summary", "professional summary", "profile", "objective"}:
            collected: list[str] = []
            for candidate in lines[idx + 1:]:
                if _is_section_header(candidate):
                    break
                if _is_noise_line(candidate):
                    continue
                collected.append(candidate)
                if len(" ".join(collected)) >= 240:
                    break
            if collected:
                return " ".join(collected)[:280]
    return ""


def _fallback_summary(lines: list[str]) -> str:
    candidates = [
        line for line in lines[:12]
        if not _is_noise_line(line) and not _is_section_header(line) and len(line.split()) >= 4
    ]
    return " ".join(candidates[:2])[:280] if candidates else ""


def _extract_skills(lines: list[str]) -> list[str]:
    skills: list[str] = []
    for idx, line in enumerate(lines):
        normalized = _normalize_header(line)
        if normalized in {"skills", "key skills", "technical skills"} or any(normalized.startswith(f"{header}:") for header in ("skills", "key skills", "technical skills")):
            block: list[str] = []
            for candidate in lines[idx + 1:]:
                if _is_section_header(candidate):
                    break
                if _is_contact_or_link_line(candidate):
                    continue
                block.append(candidate)
                if len(block) >= 5:
                    break
            source = [line.split(":", 1)[-1]] if ":" in line else []
            source.extend(block)
            for item in re.split(r"[,;\n]", " ".join(source)):
                cleaned = item.strip(" -*\t")
                if cleaned and len(cleaned) > 1:
                    skills.append(cleaned)
            break
    deduped: list[str] = []
    seen: set[str] = set()
    for skill in skills:
        lowered = skill.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(skill)
    return deduped[:12]


def _extract_experience_lines(lines: list[str]) -> list[str]:
    experience: list[str] = []
    in_experience_section = False
    for line in lines:
        normalized = _normalize_header(line)
        if normalized in {"work experience", "experience", "professional experience"}:
            in_experience_section = True
            continue
        if in_experience_section and _is_section_header(line):
            break
        if _is_noise_line(line):
            continue
        if in_experience_section:
            if any(keyword in line.lower() for keyword in ("manager", "director", "analyst", "coordinator", "specialist", "developer", "engineer", "campaign", "operations")):
                experience.append(line)
        elif any(keyword in line.lower() for keyword in ("engineer", "developer", "manager", "analyst", "director", "coordinator", "specialist", "built", "designed")):
            experience.append(line)
    deduped: list[str] = []
    seen: set[str] = set()
    for line in experience:
        lowered = line.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(line)
    return deduped[:8]


def _find_section_index(lines: list[str], names: tuple[str, ...]) -> int:
    for idx, line in enumerate(lines):
        if _normalize_header(line) in names:
            return idx
    return -1


def _is_role_line(line: str) -> bool:
    return "—" in line or " - " in line or " – " in line


def _is_date_line(line: str) -> bool:
    return bool(MONTH_PATTERN.match(line.strip()))


def _parse_work_entries(lines: list[str], *, header_lines: list[str]) -> list[ResumeWorkEntry]:
    entries: list[ResumeWorkEntry] = []
    current: ResumeWorkEntry | None = None
    header_values = {line.strip().lower() for line in header_lines}
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() in header_values:
            continue
        if _is_contact_or_link_line(line):
            continue
        if current and not current.date_line and _is_date_line(line):
            current.date_line = line
            continue
        if _is_role_line(line):
            if current and current.role_line:
                entries.append(current)
            current = ResumeWorkEntry(role_line=line, date_line="", bullets=[])
            continue
        bullet_text = line.lstrip("●•*- ").strip()
        if current is None:
            continue
        if line.startswith(("●", "•", "-", "*")) or not current.bullets:
            current.bullets.append(bullet_text)
        else:
            current.bullets[-1] = f"{current.bullets[-1]} {bullet_text}".strip()
    if current and current.role_line:
        entries.append(current)
    return entries


def _structured_sections(lines: list[str]) -> tuple[list[str], list[ResumeWorkEntry], list[str], list[str]]:
    work_idx = _find_section_index(lines, ("work experience", "experience", "professional experience"))
    education_idx = _find_section_index(lines, ("education",))
    skills_idx = _find_section_index(lines, ("key skills", "skills", "technical skills"))
    header_lines = lines[:work_idx] if work_idx > 0 else lines[:2]
    work_lines = lines[work_idx + 1:education_idx] if work_idx >= 0 and education_idx > work_idx else []
    education_lines = lines[education_idx + 1:skills_idx] if education_idx >= 0 and skills_idx > education_idx else []
    key_skills_lines = lines[skills_idx + 1:] if skills_idx >= 0 else []
    work_entries = _parse_work_entries(work_lines, header_lines=header_lines)
    return header_lines, work_entries, education_lines, key_skills_lines


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
    header_lines, work_entries, education_lines, key_skills_lines = _structured_sections(lines)
    email = _extract_email(text)
    phone = _extract_phone(text)
    summary_line = _summary_from_sections(lines) or _fallback_summary(lines) or "Experienced professional with relevant background."
    experience_lines = _extract_experience_lines(lines)
    skills = _extract_skills(lines)
    resume = ResumeData(
        source_path=str(source_path),
        raw_text=text,
        name=_guess_name(lines),
        email=email,
        phone=phone,
        summary=summary_line,
        skills=skills,
        experience_lines=experience_lines,
        header_lines=header_lines,
        education_lines=education_lines,
        key_skills_lines=key_skills_lines,
        work_experience_entries=work_entries,
    )
    cache_path.write_text(json.dumps(resume.to_dict(), indent=2), encoding="utf-8")
    LOGGER.info("Cached parsed resume at %s", cache_path)
    return resume


def load_cached_resume(cache_path: Path) -> ResumeData | None:
    if not cache_path.exists():
        return None
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["header_lines"] = payload.get("header_lines", [])
    payload["education_lines"] = payload.get("education_lines", [])
    payload["key_skills_lines"] = payload.get("key_skills_lines", [])
    payload["work_experience_entries"] = [
        ResumeWorkEntry(**entry) if isinstance(entry, dict) else entry
        for entry in payload.get("work_experience_entries", [])
    ]
    return ResumeData(**payload)
