from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from email.message import EmailMessage
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
        if not self.config.recipient_email or not self.config.sender_email:
            return DeliveryResult("gmail", "failed", "", "Sender or recipient email missing")
        if not self.config.client_secrets_file:
            return DeliveryResult("gmail", "failed", "", "Gmail client secrets file missing")

        try:
            service = self._build_service()
            message = EmailMessage()
            message["To"] = self.config.recipient_email
            message["From"] = self.config.sender_email
            message["Subject"] = f"JobBot match: {job.title} at {job.employer}"
            message.set_content(
                "\n".join(
                    [
                        f"Match score: {score.score if score.score is not None else 'N/A'}",
                        f"Employer: {job.employer}",
                        f"Role: {job.title}",
                        f"Location: {job.location}",
                        f"Apply URL: {job.apply_url}",
                        "",
                        score.rationale,
                    ]
                )
            )

            for attachment_path in (docs.resume_pdf_path, docs.cover_letter_path):
                data = attachment_path.read_bytes()
                message.add_attachment(
                    data,
                    maintype="application",
                    subtype="octet-stream",
                    filename=attachment_path.name,
                )

            encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            response = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": encoded})
                .execute()
            )
            return DeliveryResult("gmail", "sent", response.get("id", ""), "")
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Failed to send Gmail delivery for %s", job.id)
            return DeliveryResult("gmail", "failed", "", str(exc))

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
