"""Settings from .env and the business profile from business_profile.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("MODEL", "claude-haiku-5-5"))
    # USD per million tokens, used only for the cost column in the log.
    # Check https://platform.claude.com/docs/en/about-claude/pricing for current prices.
    price_input_per_mtok: float = field(default_factory=lambda: float(os.getenv("PRICE_INPUT_PER_MTOK", "0.10")))
    price_output_per_mtok: float = field(default_factory=lambda: float(os.getenv("PRICE_OUTPUT_PER_MTOK", "0.50")))

    # "outbox" writes emails as files in ./outbox (no setup). "smtp" sends through Gmail or any
    # SMTP server. "resend" sends through Resend's HTTPS API (for hosts that block SMTP).
    send_mode: str = field(default_factory=lambda: os.getenv("SEND_MODE", "outbox").lower())
    # When on, every reply goes to the owner for approval instead of to the lead.
    review_mode: bool = field(default_factory=lambda: _bool("REVIEW_MODE", False))

    owner_email: str = field(default_factory=lambda: os.getenv("OWNER_EMAIL", "owner@example.com"))
    from_email: str = field(default_factory=lambda: os.getenv("FROM_EMAIL", os.getenv("SMTP_USER", "owner@example.com")))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    resend_api_key: str = field(default_factory=lambda: os.getenv("RESEND_API_KEY", ""))

    # Production = the app is on the public internet. Turned on automatically on Railway.
    production: bool = field(default_factory=lambda: _bool("PRODUCTION", bool(os.getenv("RAILWAY_ENVIRONMENT"))))
    # Website builders (WordPress, Wix, Webflow) post JSON; they must send this secret as an
    # X-Webhook-Secret header or ?secret=... on the URL. Empty = not required.
    webhook_secret: str = field(default_factory=lambda: os.getenv("WEBHOOK_SECRET", ""))
    # Abuse limits: leads accepted per visitor IP per hour, and Claude calls per day.
    max_leads_per_ip_per_hour: int = field(default_factory=lambda: int(os.getenv("MAX_LEADS_PER_IP_PER_HOUR", "5")))
    max_ai_calls_per_day: int = field(default_factory=lambda: int(os.getenv("MAX_AI_CALLS_PER_DAY", "200")))

    # Required in production: open the dashboard at /leads?token=...
    dashboard_token: str = field(default_factory=lambda: os.getenv("DASHBOARD_TOKEN", ""))

    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", str(ROOT / "data"))))
    outbox_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTBOX_DIR", str(ROOT / "outbox"))))
    profile_path: Path = field(default_factory=lambda: Path(os.getenv("PROFILE_PATH", str(ROOT / "business_profile.yaml"))))

    @property
    def log_path(self) -> Path:
        return self.data_dir / "leads.csv"

    def validate(self) -> list[str]:
        problems = []
        if not self.anthropic_api_key:
            problems.append("ANTHROPIC_API_KEY is missing from .env")
        if self.send_mode not in {"outbox", "smtp", "resend"}:
            problems.append("SEND_MODE must be 'outbox', 'smtp' or 'resend'")
        if self.send_mode == "smtp" and not (self.smtp_user and self.smtp_password):
            problems.append("SEND_MODE=smtp needs SMTP_USER and SMTP_PASSWORD (a Gmail app password)")
        if self.send_mode == "resend" and not (self.resend_api_key and "@" in self.from_email):
            problems.append("SEND_MODE=resend needs RESEND_API_KEY and FROM_EMAIL on your verified domain")
        if self.production:
            if len(self.dashboard_token) < 16:
                problems.append("PRODUCTION: set DASHBOARD_TOKEN to a random string of 16+ characters "
                                "(the dashboard stays locked until you do)")
            if self.send_mode == "outbox":
                problems.append("PRODUCTION: SEND_MODE=outbox only saves files, no customer gets a reply")
        return problems


def load_profile(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        profile = yaml.safe_load(fh) or {}
    if not profile.get("business_name"):
        raise ValueError(f"{path} needs at least a business_name")
    return profile
