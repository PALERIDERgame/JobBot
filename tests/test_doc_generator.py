from __future__ import annotations

import unittest
from pathlib import Path

from database import Job
from doc_generator import DocumentGenerator
from match_scorer import MatchScore
from resume_parser import ResumeData, ResumeWorkEntry
from test_support import workspace_temp_dir


def _build_source_resume_docx(path: Path) -> None:
    from docx import Document

    doc = Document()
    doc.add_paragraph("ROBERT THOM")
    doc.add_paragraph("robert@example.com | linkedin.com/in/example | (530) 220-4847")
    doc.add_paragraph("WORK EXPERIENCE")
    doc.add_paragraph("Underdog Strategies, New York, NY — Digital Advertising and Field Manager")
    doc.add_paragraph("JULY 2024 - Present")
    bullet = doc.add_paragraph(style="List Bullet")
    bullet.add_run("Led digital ad strategy and reporting")
    bullet = doc.add_paragraph(style="List Bullet")
    bullet.add_run("Managed creative vendors and launches")
    doc.add_paragraph("Behavioral Associates, New York, NY — Operations Manager")
    doc.add_paragraph("JUNE 2023 - JULY 2024")
    bullet = doc.add_paragraph(style="List Bullet")
    bullet.add_run("Directed software implementation and internal systems")
    doc.add_paragraph("EDUCATION")
    doc.add_paragraph("University of California, Davis")
    doc.add_paragraph("Bachelor of Arts in Political Science Class of 2015")
    doc.add_paragraph("KEY SKILLS")
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
            resume = ResumeData(
                str(source_docx),
                "",
                "ROBERT THOM",
                "robert@example.com",
                "(530) 220-4847",
                "Marketing and operations leader",
                ["Operations", "Project Management", "Data Analysis"],
                ["Led field operations", "Managed paid media"],
                header_lines=["ROBERT THOM", "robert@example.com | linkedin.com/in/example | (530) 220-4847"],
                education_lines=["University of California, Davis", "Bachelor of Arts in Political Science Class of 2015"],
                key_skills_lines=["Operations, Project Management, CRM, Data Analysis, Mailchimp, Google Analytics"],
                work_experience_entries=[
                    ResumeWorkEntry(
                        role_line="Underdog Strategies, New York, NY — Digital Advertising and Field Manager",
                        date_line="JULY 2024 - Present",
                        bullets=["Led digital ad strategy and reporting", "Managed creative vendors and launches"],
                    )
                ],
            )
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
            resume = ResumeData(
                str(source_docx),
                "",
                "ROBERT THOM",
                "robert@example.com",
                "(530) 220-4847",
                "Marketing and operations leader",
                ["Operations"],
                ["Led field operations"],
                header_lines=["ROBERT THOM"],
                education_lines=["University of California, Davis"],
                key_skills_lines=["Operations, Project Management"],
                work_experience_entries=[
                    ResumeWorkEntry(
                        role_line="Underdog Strategies, New York, NY — Digital Advertising and Field Manager",
                        date_line="JULY 2024 - Present",
                        bullets=["Led digital ad strategy and reporting"],
                    )
                ],
            )
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
