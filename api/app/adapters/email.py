"""EmailSender (D5). Dev/demo: SMTP to Mailpit (http://localhost:8025 shows the inbox).
Prod: swap for a transactional provider (e.g. Resend) behind the same interface."""

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.config import get_settings

log = logging.getLogger("forte.email")


class EmailSender(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


class SmtpEmailSender:
    def send(self, to: str, subject: str, text: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.email_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=5) as smtp:
            smtp.send_message(msg)


class ConsoleEmailSender:
    """Prints emails to the API log. Used in tests and when Mailpit isn't running."""

    def __init__(self) -> None:
        self.outbox: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, text: str) -> None:
        self.outbox.append((to, subject, text))
        log.info("EMAIL to=%s subject=%s\n%s", to, subject, text)
