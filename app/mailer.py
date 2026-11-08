"""Sending email: really (SMTP) or as files in ./outbox for testing."""

from __future__ import annotations

import re
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .config import Settings


class Mailer:
    def __init__(self, settings: Settings):
        self.s = settings

    def send(self, to: str, subject: str, body: str, reply_to: str | None = None) -> str:
        msg = EmailMessage()
        msg["From"] = self.s.from_email
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)

        if self.s.send_mode == "smtp":
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(self.s.smtp_user, self.s.smtp_password)
                smtp.send_message(msg)
            return f"sent to {to}"

        self.s.outbox_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", f"{to}-{subject}".lower()).strip("-")[:60]
        path = Path(self.s.outbox_dir) / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{slug}.eml"
        path.write_bytes(bytes(msg))
        return f"saved {path.name}"
