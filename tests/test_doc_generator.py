from __future__ import annotations

import unittest
from pathlib import Path

from database import Job
from doc_generator import DocumentGenerator
from match_scorer import MatchScore
from resume_parser import ResumeData, ResumeWorkEntry
from test_support import workspace_temp_dir


def _build_source_resume_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, height - 48, "ROBERT THOM")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, height - 64, "robert@example.com | linkedin.com/in/example | (530) 220-4847")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(72, height - 120, "WORK EXPERIENCE")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(72, height - 150, "Underdog Strategies, New York, NY — Digital Advertising and Field Manager")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(72, height - 164, "JULY 2024 - Present")
    pdf.drawString(82, height - 180, "- Led digital ad strategy and reporting")
    pdf.drawString(82, height - 194, "- Managed creative vendors and launches")
    pdf.showPage()

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, height - 48, "ROBERT THOM")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, height - 64, "robert@example.com | linkedin.com/in/example | (530) 220-4847")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(72, height - 110, "Behavioral Associates, New York, NY — Operations Manager")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(72, height - 124, "JUNE 2023 - JULY 2024")
    pdf.drawString(82, height - 140, "- Directed software implementation")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(72, height - 240, "EDUCATION")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, height - 256, "University of California, Davis")
    pdf.drawString(72, height - 270, "Bachelor of Arts in Political Science Class of 2015")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(72, height - 320, "KEY SKILLS")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, height - 336, "Operations, Project Management, Data Analysis, Canva, Adobe Photoshop")
    pdf.save()


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

    def test_generate_resume_preserves_source_sections_without_generic_placeholders(self) -> None:
        with workspace_temp_dir() as tmp:
            generator = DocumentGenerator()
            resume = ResumeData(
                "",
                "",
                "ROBERT THOM",
                "robert@example.com",
                "(530) 220-4847",
                "Marketing and operations leader",
                ["Operations", "Project Management", "Data Analysis"],
                ["Led field operations", "Managed paid media"],
                header_lines=["ROBERT THOM", "robert@example.com | linkedin.com/in/example | (530) 220-4847"],
                education_lines=["University of California, Davis", "Bachelor of Arts in Political Science Class of 2015"],
                key_skills_lines=["Operations, Project Management, Data Analysis"],
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
                Job("1", "Director of Ecommerce", "MILK BAR", "New York, NY", "", "Lead ecommerce growth, analytics, and digital strategy.", "board", "https://example.com", "", "jobspy", "", ""),
                resume,
                MatchScore(0, "AI scoring skipped in semi_auto for faster review queueing.", [], [], False, "review", "", "2026-01-01T00:00:00+00:00"),
                ai_notes="",
            )
            import pdfplumber
            with pdfplumber.open(docs.resume_pdf_path) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages)
            self.assertIn("WORK EXPERIENCE", text)
            self.assertIn("EDUCATION", text)
            self.assertIn("KEY SKILLS", text)
            self.assertIn("University of California, Davis", text)
            self.assertNotIn("Target Role", text)
            self.assertNotIn("Match Notes", text)

    def test_generate_resume_keeps_full_key_skills_list(self) -> None:
        with workspace_temp_dir() as tmp:
            generator = DocumentGenerator()
            resume = ResumeData(
                "",
                "",
                "ROBERT THOM",
                "robert@example.com",
                "(530) 220-4847",
                "Marketing and operations leader",
                ["Operations"],
                ["Led field operations"],
                header_lines=["ROBERT THOM", "robert@example.com | linkedin.com/in/example | (530) 220-4847"],
                education_lines=["University of California, Davis"],
                key_skills_lines=[
                    "Operations, Project Management, CRM, Data Analysis, MS Excel, MS Powerpoint, MS Project, Asana, "
                    "Meta Ads Manager, Programmatic Display, Google Adwords, Youtube, TikTok, Native Advertising, "
                    "WordPress, Mailchimp, Salesforce Marketing Cloud, SEO, Google Analytics, Canva, Adobe InDesign, Adobe Photoshop"
                ],
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
                Job("1", "Director of Ecommerce", "MILK BAR", "New York, NY", "", "Lead ecommerce growth, analytics, and digital strategy.", "board", "https://example.com", "", "jobspy", "", ""),
                resume,
                MatchScore(0, "", [], [], False, "review", "", "2026-01-01T00:00:00+00:00"),
                ai_notes="",
            )
            import pdfplumber
            with pdfplumber.open(docs.resume_pdf_path) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages)
            self.assertIn("Adobe Photoshop", text)
            self.assertIn("Mailchimp", text)

    def test_generate_resume_uses_source_pdf_as_overlay_base(self) -> None:
        with workspace_temp_dir() as tmp:
            source_pdf = Path(tmp) / "source_resume.pdf"
            _build_source_resume_pdf(source_pdf)
            generator = DocumentGenerator()
            resume = ResumeData(
                str(source_pdf),
                "",
                "ROBERT THOM",
                "robert@example.com",
                "(530) 220-4847",
                "Marketing and operations leader",
                ["Operations"],
                ["Led field operations"],
                header_lines=["ROBERT THOM", "robert@example.com | linkedin.com/in/example | (530) 220-4847"],
                education_lines=["University of California, Davis", "Bachelor of Arts in Political Science Class of 2015"],
                key_skills_lines=["Operations, Project Management, Data Analysis, Canva, Adobe Photoshop"],
                work_experience_entries=[
                    ResumeWorkEntry(
                        role_line="Underdog Strategies, New York, NY — Digital Advertising and Field Manager",
                        date_line="JULY 2024 - Present",
                        bullets=["Led digital ad strategy and reporting", "Managed creative vendors and launches"],
                    ),
                    ResumeWorkEntry(
                        role_line="Behavioral Associates, New York, NY — Operations Manager",
                        date_line="JUNE 2023 - JULY 2024",
                        bullets=["Directed software implementation"],
                    ),
                ],
            )
            docs = generator.generate(
                Path(tmp),
                Job("1", "Director of Ecommerce", "MILK BAR", "New York, NY", "", "Lead ecommerce growth, analytics, and digital strategy.", "board", "https://example.com", "", "jobspy", "", ""),
                resume,
                MatchScore(0, "", [], [], False, "review", "", "2026-01-01T00:00:00+00:00"),
                ai_notes="",
            )

            import pdfplumber
            with pdfplumber.open(docs.resume_pdf_path) as pdf:
                self.assertEqual(len(pdf.pages), 2)
                text = "\n".join((page.extract_text() or "") for page in pdf.pages)
            self.assertIn("Underdog Strategies, New York, NY", text)
            self.assertIn("Operations, Project Management, Data Analysis", text)
            self.assertNotIn("Target Role", text)
