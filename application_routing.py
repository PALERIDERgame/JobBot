from __future__ import annotations

import re
from dataclasses import dataclass


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
EXCLUDED_CONTEXT_TERMS = (
    "privacy",
    "compliance",
    "accommodation",
    "not monitored",
    "agency",
    "data subject",
    "contact us",
    "applicant pre-collection notice",
    "reasonable accommodation",
    "recruiting partner",
    "unsolicited resumes",
)
HR_LOCAL_PART_TERMS = (
    "hr",
    "humanresources",
    "human-resources",
    "recruit",
    "recruiting",
    "recruiter",
    "talent",
    "career",
    "careers",
    "jobs",
    "hiring",
    "people",
    "staffing",
    "employment",
    "hiringteam",
)
DIRECT_APPLICATION_PHRASES = (
    "email your resume",
    "send your resume",
    "send resume",
    "send cv",
    "send your cv",
    "send your cover letter",
    "submit your resume",
    "submit your cover letter",
    "email your application",
    "submit your application",
    "apply by email",
    "email application to",
    "send application to",
)
REQUIRED_ACTION_TERMS = ("send", "email", "submit", "apply by email")
REQUIRED_MATERIAL_TERMS = ("resume", "cv", "cover letter", "application", "application materials")


@dataclass(slots=True)
class ApplicationRouting:
    apply_method: str
    apply_url: str
    hiring_manager_email: str


@dataclass(slots=True)
class EmailApplyAssessment:
    is_explicit: bool
    email: str
    confidence: str
    reason: str


def assess_email_apply(description: str, apply_url: str, existing_email: str = "") -> EmailApplyAssessment:
    candidate_email = ""
    for raw_line in description.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        email_match = EMAIL_PATTERN.search(line)
        if not email_match:
            continue
        normalized = line.lower()
        email_value = email_match.group(0)
        if not _looks_like_hr_email(email_value):
            continue
        if any(term in normalized for term in EXCLUDED_CONTEXT_TERMS):
            continue
        has_direct_instruction = any(phrase in normalized for phrase in DIRECT_APPLICATION_PHRASES)
        has_required_action = any(term in normalized for term in REQUIRED_ACTION_TERMS)
        has_required_material = any(term in normalized for term in REQUIRED_MATERIAL_TERMS)
        if has_direct_instruction or (has_required_action and has_required_material):
            return EmailApplyAssessment(True, email_value, "present", "Posting explicitly instructs candidates to send application materials to a validated HR email.")
        if not candidate_email:
            candidate_email = email_value

    if existing_email and _looks_like_hr_email(existing_email):
        candidate_email = existing_email

    if candidate_email:
        return EmailApplyAssessment(
            False,
            candidate_email,
            "not present",
            "Posting includes an HR-style email address but does not explicitly instruct candidates to send application materials there.",
        )

    return EmailApplyAssessment(False, "", "not present", "No validated HR/application email was found in the posting.")


def _looks_like_hr_email(email_value: str) -> bool:
    local_part = email_value.split("@", 1)[0].lower()
    normalized = re.sub(r"[^a-z]", "", local_part)
    return any(term in local_part or term in normalized for term in HR_LOCAL_PART_TERMS)


def infer_application_routing(description: str, apply_url: str) -> ApplicationRouting:
    assessment = assess_email_apply(description, apply_url)
    if assessment.is_explicit and assessment.email:
        return ApplicationRouting(
            apply_method="email",
            apply_url=apply_url,
            hiring_manager_email=assessment.email,
        )
    return ApplicationRouting(apply_method="board", apply_url=apply_url, hiring_manager_email="")
