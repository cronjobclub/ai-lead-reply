"""The lead log: one CSV row per lead, easy to open in Excel or Google Sheets."""

from __future__ import annotations

import csv
import threading
from pathlib import Path

COLUMNS = [
    "received_at", "replied_at", "seconds_to_reply", "name", "email", "phone",
    "kind", "urgency", "summary", "action", "reply_subject", "reply_body",
    "input_tokens", "output_tokens", "cost_usd", "error", "message",
]

_lock = threading.Lock()


def append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            if new:
                writer.writeheader()
            writer.writerow({k: row.get(k, "") for k in COLUMNS})


def read_all(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
