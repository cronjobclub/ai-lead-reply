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

    # "outbox" writes emails as files in ./outbox (no setup). "smtp" really sends them.
    send_mode: str = field(default_factory=lambda: os.getenv("SEND_MODE", "outbox").lower())
    # When on, every reply goes to the owner for approval instead of to the lead.
    review_mode: bool = field(default_factory=lambda: _bool("REVIEW_MODE", False))

    owner_email: str = field(default_factory=lambda: os.getenv("OWNER_EMAIL", "owner@example.com"))
    from_email: str = field(default_factory=lambda: os.getenv("FROM_EMAIL", os.getenv("SMTP_USER", "owner@example.com")))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))

    # Optional: require ?token=... to open the /leads dashboard.
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
        if self.send_mode not in {"outbox", "smtp"}:
            problems.append("SEND_MODE must be 'outbox' or 'smtp'")
        if self.send_mode == "smtp" and not (self.smtp_user and self.smtp_password):
            problems.append("SEND_MODE=smtp needs SMTP_USER and SMTP_PASSWORD (a Gmail app password)")
        return problems


def load_profile(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        profile = yaml.safe_load(fh) or {}
    if not profile.get("business_name"):
        raise ValueError(f"{path} needs at least a business_name")
    return profile
