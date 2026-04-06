from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import sanitize_filename
from database import Job
from match_scorer import MatchScore
from resume_parser import ResumeData


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class GeneratedDocs:
    output_dir: Path
    resume_pdf_path: Path
    cover_letter_path: Path


class DocumentGenerator:
    def generate(self, base_output_dir: Path, job: Job, resume: ResumeData, score: MatchScore) -> GeneratedDocs:
        folder_name = f"{sanitize_filename(job.employer)}_{datetime.now().strftime('%Y-%m-%d')}"
        output_dir = base_output_dir / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        resume_pdf_path = output_dir / "resume.pdf"
        cover_letter_path = output_dir / "cover_letter.txt"

        self._build_resume_pdf(resume_pdf_path, job, resume, score)
        self._build_cover_letter(cover_letter_path, job, resume, score)
        LOGGER.info("Generated documents for %s at %s", job.id, output_dir)
        return GeneratedDocs(output_dir=output_dir, resume_pdf_path=resume_pdf_path, cover_letter_path=cover_letter_path)

    def _build_resume_pdf(self, path: Path, job: Job, resume: ResumeData, score: MatchScore) -> None:
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        except ImportError:
            self._write_fallback_pdf(path, job, resume, score)
            return

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(path), pagesize=letter)
        story = [
            Paragraph(resume.name, styles["Title"]),
            Paragraph(resume.email, styles["Normal"]),
            Paragraph(resume.phone, styles["Normal"]),
            Spacer(1, 12),
            Paragraph("Professional Summary", styles["Heading2"]),
            Paragraph(resume.summary, styles["BodyText"]),
            Spacer(1, 12),
            Paragraph("Target Role", styles["Heading2"]),
            Paragraph(f"{job.title} at {job.employer}", styles["BodyText"]),
            Spacer(1, 12),
            Paragraph("Relevant Skills", styles["Heading2"]),
            Paragraph(", ".join(resume.skills[:12]) or "Skills not detected from resume source.", styles["BodyText"]),
            Spacer(1, 12),
            Paragraph("Relevant Experience Highlights", styles["Heading2"]),
        ]
        for line in resume.experience_lines[:8]:
            story.append(Paragraph(f"- {line}", styles["BodyText"]))
        if not resume.experience_lines:
            story.append(Paragraph("No experience lines were confidently extracted from the source resume.", styles["BodyText"]))
        story.extend(
            [
                Spacer(1, 12),
                Paragraph("Match Notes", styles["Heading2"]),
                Paragraph(f"Match score: {score.score if score.score is not None else 'N/A'}", styles["BodyText"]),
                Paragraph(score.rationale or "No rationale available.", styles["BodyText"]),
            ]
        )
        doc.build(story)

    def _build_cover_letter(self, path: Path, job: Job, resume: ResumeData, score: MatchScore) -> None:
        letter_text = "\n".join(
            [
                f"Dear Hiring Team at {job.employer},",
                "",
                f"I am applying for the {job.title} role in {job.location}.",
                f"My background includes {resume.summary}.",
                "",
                "A few relevant strengths I would bring to this role:",
                *[f"- {item}" for item in (score.strengths or resume.experience_lines[:3])],
                "",
                "I would welcome the chance to discuss how my experience aligns with your needs.",
                "",
                f"Sincerely,\n{resume.name}",
            ]
        )
        path.write_text(letter_text, encoding="utf-8")

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
