from __future__ import annotations

import re
from dataclasses import dataclass


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
ACTION_TERMS = ("apply", "application", "email", "send", "submit")
MATERIAL_TERMS = ("resume", "cv", "cover letter", "materials", "application")


@dataclass(slots=True)
class ApplicationRouting:
    apply_method: str
    apply_url: str
    hiring_manager_email: str


def infer_application_routing(description: str, apply_url: str) -> ApplicationRouting:
    for raw_line in description.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        email_match = EMAIL_PATTERN.search(line)
        if not email_match:
            continue
        normalized = line.lower()
        has_action = any(term in normalized for term in ACTION_TERMS)
        has_material = any(term in normalized for term in MATERIAL_TERMS)
        if has_action and has_material:
            return ApplicationRouting(
                apply_method="email",
                apply_url=apply_url,
                hiring_manager_email=email_match.group(0),
            )
    return ApplicationRouting(apply_method="board", apply_url=apply_url, hiring_manager_email="")
