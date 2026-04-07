from __future__ import annotations

import unittest
from pathlib import Path

from database import Job
from doc_generator import DocumentGenerator
from match_scorer import MatchScore
from resume_parser import ResumeData, ResumeWorkEntry, parse_resume
from test_support import workspace_temp_dir


def _build_source_resume_docx(path: Path) -> None:
    from docx import Document

    doc = Document()
    doc.add_paragraph("ROBERT THOM")
    doc.add_paragraph("robert@example.com | linkedin.com/in/example | (530) 220-4847")
    doc.add_paragraph("WORK EXPERIENCE", style="Heading 1")
    doc.add_paragraph("Underdog Strategies, New York, NY — Digital Advertising and Field Manager", style="Heading 2")
    doc.add_paragraph("JULY 2024 - Present")
    bullet = doc.add_paragraph(style="List Bullet")
    bullet.add_run("Led digital ad strategy and reporting")
    bullet = doc.add_paragraph(style="List Bullet")
    bullet.add_run("Managed creative vendors and launches")
    doc.add_paragraph("Behavioral Associates, New York, NY — Operations Manager", style="Heading 2")
    doc.add_paragraph("JUNE 2023 - JULY 2024", style="Heading 3")
    bullet = doc.add_paragraph(style="List Bullet")
    bullet.add_run("Directed software implementation and internal systems")
    doc.add_paragraph("EDUCATION", style="Heading 1")
    doc.add_paragraph("University of California, Davis", style="Heading 2")
    doc.add_paragraph("KEY SKILLS", style="Heading 1")
    doc.add_paragraph("Operations, Project Management, CRM, Data Analysis, Mailchimp, Google Analytics")
    doc.save(str(path))


class DocumentGeneratorTests(unittest.TestCase):
    def test_generate_creates_files(self) -> None:
        with workspace_temp_dir() as tmp:
            generator = DocumentGenerator()
            docs = generator.generate(
                Path(tmp),
                Job("1", "Engineer", "Acme", "Remote", "", "Role", "board", "https://example.com", "", "usajobs", "", ""),
                ResumeData("", "", "Jane", "jane@example.com", "555", "Summary", ["Python"], ["Built APIs"]),
                MatchScore(90, "Great fit", ["Python"], ["AWS"], True, "scored", "", "2026-01-01T00:00:00+00:00"),
                ai_notes="Strong API background and automation experience.",
            )
            self.assertTrue(docs.resume_pdf_path.exists())
            self.assertTrue(docs.cover_letter_path.exists())

    def test_generate_cover_letter_avoids_nan_employer_and_placeholder_rationale(self) -> None:
        with workspace_temp_dir() as tmp:
            generator = DocumentGenerator()
            docs = generator.generate(
                Path(tmp),
                Job("1", "Marketing Director", "nan", "New York, NY", "", "Role", "board", "https://example.com", "", "jobspy", "", ""),
                ResumeData("", "", "Jane", "jane@example.com", "555", "Marketing leader with operations experience", ["Campaign Management", "Operations"], ["Led field operations", "Managed paid media"]),
                MatchScore(0, "AI scoring skipped in semi_auto for faster review queueing.", [], [], False, "review", "", "2026-01-01T00:00:00+00:00"),
                ai_notes="",
            )
            text = docs.cover_letter_path.read_text(encoding="utf-8")
            self.assertNotIn("nan", text.lower())
            self.assertNotIn("AI scoring skipped", text)

    def test_generate_docx_resume_preserves_sections_and_writes_docx_and_pdf(self) -> None:
        with workspace_temp_dir() as tmp:
            source_docx = Path(tmp) / "source_resume.docx"
            _build_source_resume_docx(source_docx)
            generator = DocumentGenerator()
            generator._export_docx_to_pdf = lambda docx_path, pdf_path: pdf_path.write_bytes(b"pdf")
            resume = parse_resume(source_docx, Path(tmp) / "resume_cache.json")
            docs = generator.generate(
                Path(tmp),
                Job("1", "Director of Ecommerce", "MILK BAR", "New York, NY", "", "Lead ecommerce growth, analytics, and dashboard reporting.", "board", "https://example.com", "", "jobspy", "", ""),
                resume,
                MatchScore(0, "", [], [], False, "review", "", "2026-01-01T00:00:00+00:00"),
                ai_notes="",
            )
            self.assertTrue(docs.resume_docx_path.exists())
            self.assertTrue(docs.resume_pdf_path.exists())
            self.assertEqual(docs.status, "generated")

            from docx import Document
            document = Document(str(docs.resume_docx_path))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            self.assertIn("WORK EXPERIENCE", text)
            self.assertIn("EDUCATION", text)
            self.assertIn("KEY SKILLS", text)
            self.assertIn("University of California, Davis", text)
            self.assertNotIn("Target Role", text)
            self.assertNotIn("Match Notes", text)
            work_paragraphs = [paragraph for paragraph in document.paragraphs if paragraph.text.strip()]
            numbered = [paragraph for paragraph in work_paragraphs if paragraph.text.startswith("Led") or paragraph.text.startswith("Managed") or paragraph.text.startswith("Directed")]
            self.assertTrue(numbered)
            self.assertTrue(all(paragraph.style.name != "Heading 2" for paragraph in numbered))
            self.assertTrue(
                all(
                    getattr(paragraph._p.pPr, "numPr", None) is not None or "bullet" in paragraph.style.name.lower()
                    for paragraph in numbered
                )
            )
            key_skills_heading_idx = next(idx for idx, paragraph in enumerate(work_paragraphs) if paragraph.text.strip() == "KEY SKILLS")
            self.assertEqual(len([paragraph for paragraph in work_paragraphs[key_skills_heading_idx + 1:] if paragraph.text.strip()]), 1)

    def test_generate_docx_resume_tailors_work_bullets_for_relevant_job(self) -> None:
        with workspace_temp_dir() as tmp:
            source_docx = Path(tmp) / "source_resume.docx"
            _build_source_resume_docx(source_docx)
            generator = DocumentGenerator()
            generator._export_docx_to_pdf = lambda docx_path, pdf_path: pdf_path.write_bytes(b"pdf")
            resume = parse_resume(source_docx, Path(tmp) / "resume_cache.json")
            docs = generator.generate(
                Path(tmp),
                Job("1", "Ecommerce Growth Manager", "MILK BAR", "New York, NY", "", "Lead ecommerce growth, marketing analytics, dashboard reporting, and cross-functional execution.", "board", "https://example.com", "", "jobspy", "", ""),
                resume,
                MatchScore(0, "", [], [], False, "review", "", "2026-01-01T00:00:00+00:00"),
                ai_notes="",
            )
            from docx import Document
            document = Document(str(docs.resume_docx_path))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
            self.assertIn("focus on analytics and reporting", text.lower())
            self.assertNotIn("Target Role", text)

    def test_inferred_skills_are_added_when_supported(self) -> None:
        generator = DocumentGenerator()
        resume = ResumeData(
            "resume.docx",
            "Mailchimp Salesforce Marketing Cloud streamlined campaign reporting dashboards",
            "ROBERT THOM",
            "robert@example.com",
            "(530) 220-4847",
            "Marketing leader",
            ["Operations"],
            ["Streamlined campaign reporting dashboards for executive leadership"],
            key_skills_lines=["Operations, Project Management, CRM, Data Analysis, Mailchimp, Salesforce Marketing Cloud"],
            work_experience_entries=[],
        )
        job = Job("1", "Lifecycle Marketing Manager", "Acme", "Remote", "", "Own email marketing, dashboard reporting, and process improvement.", "board", "", "", "jobspy", "", "")
        skills = generator._tailor_key_skills(resume, job)
        self.assertIn("Email Marketing", skills)
        self.assertIn("Dashboard Reporting", skills)
        self.assertIn("Process Improvement", skills)

    def test_unsupported_credentials_are_not_inferred(self) -> None:
        generator = DocumentGenerator()
        resume = ResumeData(
            "resume.docx",
            "Planned and ran programming and managed campaigns and analytics dashboards",
            "ROBERT THOM",
            "robert@example.com",
            "(530) 220-4847",
            "Marketing leader",
            ["Operations"],
            ["Planned and ran programming and managed campaigns and analytics dashboards"],
            key_skills_lines=["Operations, Project Management"],
            work_experience_entries=[],
        )
        job = Job("1", "Program Manager", "Acme", "Remote", "", "PMP certification required and program management preferred.", "board", "", "", "jobspy", "", "")
        skills = generator._tailor_key_skills(resume, job)
        self.assertIn("Program Management", skills)
        self.assertNotIn("PMP certification", " ".join(skills))

    def test_docx_generation_can_succeed_without_pdf_export(self) -> None:
        with workspace_temp_dir() as tmp:
            source_docx = Path(tmp) / "source_resume.docx"
            _build_source_resume_docx(source_docx)
            generator = DocumentGenerator()
            generator._export_docx_to_pdf = lambda docx_path, pdf_path: (_ for _ in ()).throw(RuntimeError("Word automation unavailable"))
            resume = parse_resume(source_docx, Path(tmp) / "resume_cache.json")
            docs = generator.generate(
                Path(tmp),
                Job("1", "Director", "Acme", "Remote", "", "Role", "board", "", "", "jobspy", "", ""),
                resume,
                MatchScore(0, "", [], [], False, "review", "", ""),
                ai_notes="",
            )
            self.assertTrue(docs.resume_docx_path.exists())
            self.assertEqual(docs.resume_pdf_path, Path())
            self.assertEqual(docs.status, "generated_docx_only")
            self.assertIn("Word automation unavailable", docs.error_message)

    def test_docx_generation_fails_when_template_sections_are_missing(self) -> None:
        with workspace_temp_dir() as tmp:
            from docx import Document

            bad_source = Path(tmp) / "bad_resume.docx"
            doc = Document()
            doc.add_paragraph("ROBERT THOM")
            doc.add_paragraph("KEY SKILLS", style="Heading 1")
            doc.add_paragraph("Operations, Project Management")
            doc.save(str(bad_source))

            generator = DocumentGenerator()
            resume = parse_resume(bad_source, Path(tmp) / "bad_resume_cache.json")
            with self.assertRaises(ValueError):
                generator.generate(
                    Path(tmp),
                    Job("1", "Director", "Acme", "Remote", "", "Role", "board", "", "", "jobspy", "", ""),
                    resume,
                    MatchScore(0, "", [], [], False, "review", "", ""),
                    ai_notes="",
                )
