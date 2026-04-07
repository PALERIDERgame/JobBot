from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from email.message import EmailMessage
import mimetypes
from pathlib import Path

from config import GmailConfig
from database import Job
from doc_generator import GeneratedDocs
from match_scorer import MatchScore


LOGGER = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


@dataclass(slots=True)
class DeliveryResult:
    method: str
    status: str
    message_id: str
    error_message: str


class GmailClient:
    def __init__(self, config: GmailConfig, token_path: Path) -> None:
        self.config = config
        self.token_path = token_path

    def deliver_match(self, job: Job, score: MatchScore, docs: GeneratedDocs) -> DeliveryResult:
        if not self.config.enabled:
            return DeliveryResult("local", "skipped", "", "Gmail delivery disabled")
        if not self.config.sender_email:
            return DeliveryResult("gmail", "failed", "", "Sender email missing")
        if not self.config.client_secrets_file:
            return DeliveryResult("gmail", "failed", "", "Gmail client secrets file missing")

        recipient, method = self._resolve_recipient(job)
        if not recipient:
            return DeliveryResult(method, "failed", "", "No delivery recipient available")

        try:
            service = self._build_service()
            message = EmailMessage()
            message["To"] = recipient
            message["From"] = self.config.sender_email
            message["Subject"] = self._build_subject(job)
            message.set_content(self._build_body(job, score))

            attachments = [path for path in (docs.resume_pdf_path, docs.resume_docx_path, docs.cover_letter_path) if path and path.exists()]
            for attachment_path in attachments:
                data = attachment_path.read_bytes()
                mime_type, _ = mimetypes.guess_type(str(attachment_path))
                maintype, subtype = (mime_type.split("/", 1) if mime_type else ("application", "octet-stream"))
                message.add_attachment(
                    data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=attachment_path.name,
                )

            encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            response = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": encoded})
                .execute()
            )
            return DeliveryResult(method, "sent", response.get("id", ""), "")
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Failed to send Gmail delivery for %s", job.id)
            return DeliveryResult(method, "failed", "", str(exc))

    def _resolve_recipient(self, job: Job) -> tuple[str, str]:
        if job.apply_method == "email" and job.hiring_manager_email:
            return job.hiring_manager_email, "gmail_employer"
        if self.config.recipient_email:
            return self.config.recipient_email, "gmail"
        return "", "gmail"

    @staticmethod
    def _build_subject(job: Job) -> str:
        return f"Application: {job.title} at {job.employer}"

    def _build_body(self, job: Job, score: MatchScore) -> str:
        greeting = f"Hello {job.employer} Hiring Team,"
        if job.apply_method == "email":
            return "\n".join(
                [
                    greeting,
                    "",
                    f"I am applying for the {job.title} role.",
                    "I have attached my tailored resume and cover letter for review.",
                    score.rationale or "My background is closely aligned with the role requirements.",
                    "",
                    "Thank you for your time and consideration.",
                    "",
                    self.config.sender_email,
                ]
            )
        return "\n".join(
            [
                greeting,
                "",
                f"JobBot flagged {job.title} at {job.employer} as a strong match.",
                f"Match score: {score.score if score.score is not None else 'N/A'}",
                f"Apply URL: {job.apply_url or 'Not provided'}",
                score.rationale or "No rationale available.",
                "",
                "The tailored resume and cover letter are attached.",
            ]
        )

    def _build_service(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Gmail dependencies are not installed") from exc

        credentials = None
        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.config.client_secrets_file, SCOPES)
                credentials = flow.run_local_server(port=0)
            self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return build("gmail", "v1", credentials=credentials)
