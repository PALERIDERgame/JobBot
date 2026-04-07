from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import sanitize_filename
from database import Job
from match_scorer import MatchScore
from resume_parser import ResumeData


LOGGER = logging.getLogger(__name__)
_STOPWORDS = {
    "and", "the", "for", "with", "from", "that", "this", "your", "will", "role", "team", "work", "into",
    "their", "about", "across", "have", "has", "our", "you", "job", "position", "new", "york", "experience",
    "using", "within", "required", "preferred", "strong",
}
_INFERENCE_RULES = (
    {
        "skill": "Process Improvement",
        "triggers": ("process improvement", "continuous improvement", "workflow optimization"),
        "evidence": ("streamlined", "optimized", "implemented", "improved", "efficiency"),
    },
    {
        "skill": "Stakeholder Management",
        "triggers": ("stakeholder management", "stakeholder engagement"),
        "evidence": ("community leaders", "clients", "coalition partners", "donors", "executive leadership", "referral network"),
    },
    {
        "skill": "Cross-Functional Collaboration",
        "triggers": ("cross-functional", "cross functional"),
        "evidence": ("collaborated", "coordinated", "worked with", "team of", "freelance"),
    },
    {
        "skill": "Dashboard Reporting",
        "triggers": ("dashboard", "reporting", "kpi"),
        "evidence": ("dashboard", "reporting", "metrics", "analysis", "data"),
    },
    {
        "skill": "Vendor Management",
        "triggers": ("vendor management", "agency management"),
        "evidence": ("vendors", "graphic designers", "photographers", "videographers", "freelance"),
    },
    {
        "skill": "Email Marketing",
        "triggers": ("email marketing", "lifecycle marketing"),
        "evidence": ("mailchimp", "salesforce marketing cloud", "email messaging"),
    },
    {
        "skill": "CRM Management",
        "triggers": ("crm", "crm management"),
        "evidence": ("crm", "salesforce"),
    },
    {
        "skill": "SEO",
        "triggers": ("seo", "search engine optimization"),
        "evidence": ("seo", "google analytics", "wordpress"),
    },
    {
        "skill": "Audience Segmentation",
        "triggers": ("audience segmentation", "segmentation", "audience targeting"),
        "evidence": ("demographics", "voter outreach", "lead generation", "supporters"),
    },
    {
        "skill": "Program Management",
        "triggers": ("program management",),
        "evidence": ("programming", "planned and ran", "oversaw", "managed a staff"),
    },
)
_INFERENCE_BLOCKLIST = (
    "certification", "certificate", "licensed", "license", "licensure", "pmp", "cpa", "rn",
)


@dataclass(slots=True)
class GeneratedDocs:
    output_dir: Path
    resume_pdf_path: Path
    cover_letter_path: Path
    resume_docx_path: Path = Path()
    status: str = "generated"
    error_message: str = ""


@dataclass(slots=True)
class SkillCandidate:
    name: str
    confidence: float
    direct: bool


class DocumentGenerator:
    def generate(
        self,
        base_output_dir: Path,
        job: Job,
        resume: ResumeData,
        score: MatchScore,
        *,
        ai_notes: str = "",
    ) -> GeneratedDocs:
        folder_name = f"{sanitize_filename(job.employer)}_{datetime.now().strftime('%Y-%m-%d')}_{job.id[:8]}"
        output_dir = base_output_dir / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        resume_pdf_path = output_dir / "resume.pdf"
        resume_docx_path = output_dir / "resume.docx"
        cover_letter_path = output_dir / "cover_letter.txt"
        source_path = Path(resume.source_path) if resume.source_path else None

        status = "generated"
        error_message = ""
        if source_path and source_path.suffix.lower() == ".docx" and source_path.exists():
            self._build_docx_resume(resume_docx_path, job, resume, source_path)
            try:
                self._export_docx_to_pdf(resume_docx_path, resume_pdf_path)
            except Exception as exc:
                status = "generated_docx_only"
                error_message = str(exc)
                resume_pdf_path = Path()
        else:
            self._build_resume_pdf(resume_pdf_path, job, resume, score, ai_notes=ai_notes)
            resume_docx_path = Path()

        self._build_cover_letter(cover_letter_path, job, resume, score, ai_notes=ai_notes)
        LOGGER.info("Generated documents for %s at %s", job.id, output_dir)
        return GeneratedDocs(
            output_dir=output_dir,
            resume_pdf_path=resume_pdf_path,
            cover_letter_path=cover_letter_path,
            resume_docx_path=resume_docx_path,
            status=status,
            error_message=error_message,
        )

    def _build_docx_resume(self, path: Path, job: Job, resume: ResumeData, source_docx_path: Path) -> None:
        try:
            from docx import Document as DocxDocument
            from docx.oxml import OxmlElement
            from docx.text.paragraph import Paragraph
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("python-docx is required to generate DOCX resumes") from exc

        document = DocxDocument(str(source_docx_path))
        paragraphs = list(document.paragraphs)
        work_heading_idx = self._find_heading_index(paragraphs, "WORK EXPERIENCE")
        education_heading_idx = self._find_heading_index(paragraphs, "EDUCATION")
        key_skills_heading_idx = self._find_heading_index(paragraphs, "KEY SKILLS")
        if work_heading_idx < 0 or education_heading_idx < 0 or key_skills_heading_idx < 0:
            raise ValueError("DOCX resume is missing WORK EXPERIENCE, EDUCATION, or KEY SKILLS headings")

        education_heading = paragraphs[education_heading_idx]
        key_skills_heading = paragraphs[key_skills_heading_idx]
        work_body = paragraphs[work_heading_idx + 1:education_heading_idx]
        key_skills_body = paragraphs[key_skills_heading_idx + 1:]

        role_template = self._find_work_template(work_body, kind="role")
        date_template = self._find_work_template(work_body, kind="date")
        bullet_template = self._find_work_template(work_body, kind="bullet")
        key_skill_template = self._first_nonempty_paragraph(key_skills_body) or key_skills_heading

        for paragraph in work_body:
            self._remove_paragraph(paragraph)
        for paragraph in key_skills_body:
            self._remove_paragraph(paragraph)

        for entry in self._tailor_work_entries(resume, job):
            self._insert_paragraph_before(education_heading, text=str(entry["role_line"]), template=role_template or education_heading)
            if entry["date_line"]:
                self._insert_paragraph_before(education_heading, text=str(entry["date_line"]), template=date_template or role_template or education_heading)
            for bullet in entry["bullets"]:
                self._insert_paragraph_before(education_heading, text=str(bullet), template=bullet_template or date_template or role_template or education_heading)

        key_skill_anchor = key_skills_heading
        for skill_line in self._chunk_key_skills(self._tailor_key_skills(resume, job), target_chars=105):
            new_p = OxmlElement("w:p")
            key_skill_anchor._p.addnext(new_p)
            inserted = Paragraph(new_p, key_skill_anchor._parent)
            self._apply_paragraph_template(inserted, key_skill_template, skill_line)
            key_skill_anchor = inserted

        document.save(str(path))

    def _build_resume_pdf(self, path: Path, job: Job, resume: ResumeData, score: MatchScore, *, ai_notes: str) -> None:
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        except ImportError:
            self._write_fallback_pdf(path, job, resume, score)
            return

        styles = getSampleStyleSheet()
        contact_line = " | ".join(part for part in [resume.email, resume.phone] if part)
        clean_employer = self._display_employer(job.employer)
        clean_summary = self._clean_summary(resume.summary)
        skills_text = ", ".join(self._tailor_key_skills(resume, job)[:12]) or "Relevant skills were not confidently extracted from the resume source."
        experience_lines = resume.experience_lines[:6] or ["Relevant experience highlights were not confidently extracted from the resume source."]
        doc = SimpleDocTemplate(str(path), pagesize=letter)
        story = [
            Paragraph(resume.name, styles["Title"]),
            Paragraph(contact_line or "Contact details unavailable", styles["Normal"]),
            Spacer(1, 12),
            Paragraph("Professional Summary", styles["Heading2"]),
            Paragraph(clean_summary, styles["BodyText"]),
            Spacer(1, 12),
            Paragraph("Target Role", styles["Heading2"]),
            Paragraph(f"{job.title} at {clean_employer}", styles["BodyText"]),
            Spacer(1, 12),
            Paragraph("Relevant Skills", styles["Heading2"]),
            Paragraph(skills_text, styles["BodyText"]),
            Spacer(1, 12),
            Paragraph("Relevant Experience Highlights", styles["Heading2"]),
        ]
        for line in experience_lines:
            story.append(Paragraph(f"- {line}", styles["BodyText"]))
        story.extend(
            [
                Spacer(1, 12),
                Paragraph("Match Notes", styles["Heading2"]),
                Paragraph(f"Match score: {score.score if score.score is not None else 'N/A'}", styles["BodyText"]),
                Paragraph(self._clean_rationale(score.rationale), styles["BodyText"]),
            ]
        )
        if ai_notes:
            story.extend(
                [
                    Spacer(1, 12),
                    Paragraph("AI Tailoring Notes", styles["Heading2"]),
                    Paragraph(ai_notes.replace("\n", "<br/>"), styles["BodyText"]),
                ]
            )
        doc.build(story)

    def _build_cover_letter(self, path: Path, job: Job, resume: ResumeData, score: MatchScore, *, ai_notes: str) -> None:
        clean_employer = self._display_employer(job.employer)
        clean_summary = self._clean_summary(resume.summary)
        strengths = score.strengths or resume.skills[:3] or ["campaign management", "operations", "stakeholder coordination"]
        if ai_notes:
            letter_text = "\n".join(
                [
                    f"Dear Hiring Team at {clean_employer},",
                    "",
                    ai_notes,
                    "",
                    f"Sincerely,\n{resume.name}",
                ]
            )
        else:
            letter_text = "\n".join(
                [
                    f"Dear Hiring Team at {clean_employer},",
                    "",
                    f"I am applying for the {job.title} role{f' in {job.location}' if job.location else ''}.",
                    f"My background includes {clean_summary}",
                    "",
                    f"My recent work is most relevant in {', '.join(strengths[:3])}.",
                    "",
                    "Selected experience highlights:",
                    *[f"- {item}" for item in (resume.experience_lines[:3] or strengths[:3])],
                    "",
                    self._clean_rationale(score.rationale),
                    "",
                    "I would welcome the opportunity to discuss how my experience can support your team.",
                    "",
                    f"Sincerely,\n{resume.name}",
                ]
            )
        path.write_text(letter_text, encoding="utf-8")

    def _export_docx_to_pdf(self, docx_path: Path, pdf_path: Path) -> None:
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError:
            win32com = None
        else:
            win32com = win32com.client

        if win32com is not None:
            word = None
            document = None
            try:
                word = win32com.DispatchEx("Word.Application")
                word.Visible = False
                document = word.Documents.Open(str(docx_path.resolve()))
                document.SaveAs(str(pdf_path.resolve()), FileFormat=17)
                return
            except Exception as exc:
                LOGGER.warning("Word PDF export failed for %s: %s", docx_path, exc)
            finally:
                if document is not None:
                    document.Close(False)
                if word is not None:
                    word.Quit()

        soffice = shutil.which("soffice")
        if soffice:
            completed = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_path.parent), str(docx_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0 and pdf_path.exists():
                return
            raise RuntimeError((completed.stderr or completed.stdout or "LibreOffice PDF export failed").strip())

        raise RuntimeError("Could not export resume.pdf: Microsoft Word automation and LibreOffice are unavailable.")

    @staticmethod
    def _find_heading_index(paragraphs: list[object], heading_text: str) -> int:
        target = heading_text.strip().lower()
        for idx, paragraph in enumerate(paragraphs):
            if getattr(paragraph, "text", "").strip().lower() == target:
                return idx
        return -1

    @staticmethod
    def _is_date_text(text: str) -> bool:
        return bool(re.match(r"^(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)", text.strip(), re.IGNORECASE))

    def _find_work_template(self, paragraphs: list[object], *, kind: str):
        for paragraph in paragraphs:
            text = getattr(paragraph, "text", "").strip()
            if not text:
                continue
            style_name = (getattr(getattr(paragraph, "style", None), "name", "") or "").lower()
            if kind == "role" and not self._is_date_text(text) and "bullet" not in style_name:
                return paragraph
            if kind == "date" and self._is_date_text(text):
                return paragraph
            if kind == "bullet" and ("bullet" in style_name or text.startswith(("•", "-", "*"))):
                return paragraph
        return paragraphs[0] if paragraphs else None

    @staticmethod
    def _first_nonempty_paragraph(paragraphs: list[object]):
        for paragraph in paragraphs:
            if getattr(paragraph, "text", "").strip():
                return paragraph
        return None

    def _insert_paragraph_before(self, anchor, *, text: str, template):
        paragraph = anchor.insert_paragraph_before("")
        self._apply_paragraph_template(paragraph, template, text)
        return paragraph

    def _apply_paragraph_template(self, paragraph, template, text: str) -> None:
        if template is not None and getattr(template, "style", None) is not None:
            paragraph.style = template.style
            self._copy_paragraph_format(paragraph, template)
        for run in list(paragraph.runs):
            run._element.getparent().remove(run._element)
        run = paragraph.add_run(text)
        template_run = template.runs[0] if template is not None and getattr(template, "runs", None) else None
        if template_run is not None:
            font = run.font
            source_font = template_run.font
            font.bold = source_font.bold
            font.italic = source_font.italic
            font.name = source_font.name
            font.size = source_font.size
            font.underline = source_font.underline

    @staticmethod
    def _copy_paragraph_format(target, template) -> None:
        src = template.paragraph_format
        dest = target.paragraph_format
        for attr in (
            "left_indent",
            "right_indent",
            "first_line_indent",
            "keep_together",
            "keep_with_next",
            "page_break_before",
            "widow_control",
            "space_before",
            "space_after",
            "line_spacing",
            "line_spacing_rule",
        ):
            setattr(dest, attr, getattr(src, attr))
        dest.alignment = src.alignment

    @staticmethod
    def _remove_paragraph(paragraph) -> None:
        element = paragraph._element
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)

    @staticmethod
    def _chunk_key_skills(skills: list[str], *, target_chars: int) -> list[str]:
        lines: list[str] = []
        current = ""
        for skill in skills:
            candidate = f"{current}, {skill}" if current else skill
            if current and len(candidate) > target_chars:
                lines.append(current)
                current = skill
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines or ["Skills could not be extracted from the source resume."]

    def _tailor_work_entries(self, resume: ResumeData, job: Job) -> list[dict[str, object]]:
        job_terms = self._job_terms(job)
        entries: list[dict[str, object]] = []
        for entry in resume.work_experience_entries:
            scored_bullets = [
                (
                    self._bullet_relevance_score(bullet, job_terms),
                    idx,
                    self._refine_bullet(bullet.strip(), job_terms),
                )
                for idx, bullet in enumerate(entry.bullets)
            ]
            if any(score > 0 for score, _idx, _bullet in scored_bullets):
                scored_bullets.sort(key=lambda item: (item[0], -item[1]), reverse=True)
                reordered = [bullet for _score, _idx, bullet in scored_bullets]
            else:
                reordered = [self._refine_bullet(bullet.strip(), job_terms) for bullet in entry.bullets]
            entries.append(
                {
                    "role_line": entry.role_line,
                    "date_line": entry.date_line,
                    "bullets": reordered,
                }
            )
        return entries

    def _tailor_key_skills(self, resume: ResumeData, job: Job) -> list[str]:
        direct_skills = self._skills_from_lines(resume.key_skills_lines) or resume.skills
        if not direct_skills:
            direct_skills = ["Skills could not be extracted from the source resume."]
        combined: list[SkillCandidate] = [SkillCandidate(skill, 1.0, True) for skill in direct_skills]
        combined.extend(self._infer_skills(resume, job))
        seen: set[str] = set()
        deduped: list[SkillCandidate] = []
        for candidate in combined:
            normalized = candidate.name.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(candidate)
        deduped.sort(
            key=lambda candidate: (
                self._skill_relevance_score(candidate.name, self._job_terms(job)),
                candidate.confidence,
                1 if candidate.direct else 0,
            ),
            reverse=True,
        )
        return [candidate.name for candidate in deduped]

    def _infer_skills(self, resume: ResumeData, job: Job) -> list[SkillCandidate]:
        resume_text = f"{resume.raw_text} {' '.join(resume.experience_lines)} {' '.join(resume.key_skills_lines)}".lower()
        job_text = f"{job.title} {job.description_full}".lower()
        results: list[SkillCandidate] = []
        for rule in _INFERENCE_RULES:
            if not any(trigger in job_text for trigger in rule["triggers"]):
                continue
            if any(blocked in rule["skill"].lower() for blocked in _INFERENCE_BLOCKLIST):
                continue
            evidence_hits = sum(1 for evidence in rule["evidence"] if evidence in resume_text)
            if evidence_hits == 0:
                continue
            confidence = min(0.55 + (0.12 * evidence_hits), 0.92)
            if confidence > 0.50:
                results.append(SkillCandidate(rule["skill"], confidence, False))
        return results

    def _refine_bullet(self, bullet: str, job_terms: set[str]) -> str:
        cleaned = " ".join(bullet.split())
        if not cleaned:
            return cleaned
        if cleaned.endswith("."):
            return cleaned
        if len(set(re.findall(r"[a-z][a-z0-9+#&-]{2,}", cleaned.lower())) & job_terms) >= 2:
            return f"{cleaned}."
        return cleaned

    @staticmethod
    def _skills_from_lines(lines: list[str]) -> list[str]:
        skills: list[str] = []
        for item in re.split(r"[,;\n]", " ".join(lines)):
            cleaned = item.strip(" ,")
            if cleaned:
                skills.append(cleaned)
        return skills

    @staticmethod
    def _job_terms(job: Job) -> set[str]:
        text = f"{job.title} {job.description_full}".lower()
        return {token for token in re.findall(r"[a-z][a-z0-9+#&-]{2,}", text) if token not in _STOPWORDS}

    @staticmethod
    def _bullet_relevance_score(bullet: str, job_terms: set[str]) -> int:
        words = set(re.findall(r"[a-z][a-z0-9+#&-]{2,}", bullet.lower()))
        return len(words & job_terms)

    @staticmethod
    def _skill_relevance_score(skill: str, job_terms: set[str]) -> int:
        words = set(re.findall(r"[a-z][a-z0-9+#&-]{2,}", skill.lower()))
        return len(words & job_terms)

    @staticmethod
    def _display_employer(employer: str) -> str:
        cleaned = (employer or "").strip()
        if not cleaned or cleaned.lower() in {"nan", "none", "null"}:
            return "the hiring team"
        return cleaned

    @staticmethod
    def _clean_summary(summary: str) -> str:
        cleaned = " ".join((summary or "").split())
        if not cleaned:
            return "an adaptable background with relevant professional experience."
        return cleaned.rstrip(".") + "."

    @staticmethod
    def _clean_rationale(rationale: str) -> str:
        cleaned = " ".join((rationale or "").split())
        if not cleaned or "ai scoring skipped in semi_auto" in cleaned.lower():
            return "I believe my background is relevant to the role and would welcome the opportunity to discuss it further."
        return cleaned

    def _write_fallback_pdf(self, path: Path, job: Job, resume: ResumeData, score: MatchScore) -> None:
        lines = [
            "%PDF-1.1",
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj",
        ]
        text_lines = [
            resume.name,
            resume.email,
            resume.phone,
            f"Target: {job.title} at {job.employer}",
            resume.summary,
            f"Match score: {score.score if score.score is not None else 'N/A'}",
            score.rationale or "No rationale available.",
        ] + resume.experience_lines[:5]
        content_stream = ["BT /F1 12 Tf 50 750 Td"]
        for idx, text in enumerate(text_lines):
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content_stream.append(f"0 -{16 if idx else 0} Td ({escaped}) Tj")
        content_stream.append("ET")
        stream = "\n".join(content_stream)
        lines.append(f"4 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj")
        lines.append("5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")
        offsets = []
        output = []
        for item in lines:
            offsets.append(sum(len(part.encode('utf-8')) for part in output))
            output.append(f"{item}\n")
        xref_start = sum(len(part.encode("utf-8")) for part in output)
        xref = ["xref", "0 6", "0000000000 65535 f "]
        for offset in offsets:
            xref.append(f"{offset:010d} 00000 n ")
        trailer = ["trailer << /Root 1 0 R /Size 6 >>", f"startxref\n{xref_start}", "%%EOF"]
        path.write_text("".join(output + [line + "\n" for line in xref + trailer]), encoding="latin-1")
