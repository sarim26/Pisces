"""SMTP email delivery for customer replies and notifications."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from loguru import logger

from config import Config
from models import Ticket


class SmtpMailer:
    """Send email via configured SMTP (Zoho, Gmail, local relay, etc.)."""

    def __init__(self):
        self.smtp_server = Config.SMTP_SERVER
        self.smtp_port = Config.SMTP_PORT
        self.smtp_username = (Config.SMTP_USERNAME or "").strip()
        self.smtp_password = (Config.SMTP_PASSWORD or "").strip()
        self.support_email = Config.SUPPORT_EMAIL
        self.from_name = Config.SMTP_FROM_NAME

    def is_configured(self) -> bool:
        """True when SMTP host and credentials are set (not placeholders)."""
        if not self.smtp_server or self.smtp_server == "localhost":
            if not self.smtp_username:
                return False
        if not self.smtp_username or not self.smtp_password:
            return False
        placeholder_markers = (
            "your-app-password",
            "your-zoho",
            "placeholder",
            "changeme",
        )
        password_lower = self.smtp_password.lower()
        if any(marker in password_lower for marker in placeholder_markers):
            return False
        return True

    def _from_header(self) -> str:
        from_addr = self.smtp_username or self.support_email
        if self.from_name:
            return f"{self.from_name} <{from_addr}>"
        return from_addr

    def _connect(self):
        """Open an authenticated SMTP connection (SSL on 465, STARTTLS otherwise)."""
        if self.smtp_port == 465:
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
            if self.smtp_username and self.smtp_password:
                server.starttls()

        if self.smtp_username and self.smtp_password:
            server.login(self.smtp_username, self.smtp_password)

        return server

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        reply_to: Optional[str] = None,
    ) -> bool:
        """Send a plain-text email. Returns True on success."""
        if not to_email or not to_email.strip():
            logger.error("Cannot send email: recipient address is empty")
            return False

        if not self.is_configured():
            logger.error(
                "SMTP is not configured. Set SMTP_SERVER, SMTP_USERNAME, and "
                "SMTP_PASSWORD in .env (use your Zoho app-specific password)."
            )
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self._from_header()
            msg["To"] = to_email.strip()
            msg["Subject"] = subject
            reply_addr = reply_to or self.support_email
            if reply_addr:
                msg["Reply-To"] = reply_addr

            msg.attach(MIMEText(body, "plain", "utf-8"))

            server = self._connect()
            server.send_message(msg)
            server.quit()

            logger.info(f"Email sent via SMTP to {to_email}")
            return True

        except Exception as e:
            logger.error(f"SMTP send failed to {to_email}: {e}")
            return False

    def test_connection(self) -> bool:
        """Verify SMTP login without sending a message."""
        if not self.is_configured():
            logger.warning(
                "SMTP not configured — customer reply emails will not be sent. "
                "Update SMTP_* values in .env with your Zoho credentials."
            )
            return False

        try:
            server = self._connect()
            server.noop()
            server.quit()
            logger.info("SMTP connection test successful")
            return True
        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False


class CustomerMailer(SmtpMailer):
    """Send ticket reply emails directly to requesters."""

    def send_ticket_reply(
        self,
        ticket: Ticket,
        to_email: str,
        response_text: str,
    ) -> bool:
        subject = f"Re: [Request #{ticket.ticket_id}] {ticket.subject}"
        body = (
            f"{response_text}\n\n"
            f"---\n"
            f"{Config.BOT_NAME}\n"
            f"{Config.COMPANY_NAME}\n"
            f"Ticket ID: {ticket.ticket_id}\n"
            f"Reply to this email or contact {Config.SUPPORT_EMAIL} for further assistance."
        )
        return self.send_email(
            to_email=to_email,
            subject=subject,
            body=body,
            reply_to=self.support_email,
        )
