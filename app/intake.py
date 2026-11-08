"""Getting a lead in safely: read any website builder's form, and limit abuse.

Website builders all send forms differently:
  plain HTML form   name=...&email=...&message=...
  Contact Form 7    {"your-name": ..., "your-email": ..., "your-message": ...}
  Wix Automations   {"data": {"field:first_name": ..., "field:email": ...}}
  Webflow webhook   {"triggerType": "form_submission", "payload": {"data": {"Name": ..., "Email": ...}}}
extract_fields() finds name, email, phone and message in any of these shapes.
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from datetime import date

_KEYS = {
    "name": ["name", "fullname", "yourname", "contactname", "customername"],
    "first": ["firstname", "fname", "givenname"],
    "last": ["lastname", "lname", "surname", "familyname"],
    "email": ["email", "emailaddress", "youremail", "mail", "replyto"],
    "phone": ["phone", "phonenumber", "yourphone", "tel", "telephone", "mobile", "cell"],
    "message": ["message", "yourmessage", "howcanwehelp", "comments", "comment", "details",
                "description", "enquiry", "inquiry", "question", "body", "text", "notes"],
    "website": ["website"],  # the hidden honeypot field on our own form (only bots fill it in)
}


def _norm(key: str) -> str:
    key = key.split(":")[-1]  # Wix: "field:email" -> "email"
    return re.sub(r"[^a-z0-9]", "", key.lower())


# Containers that hold the visitor's answers (Wix "data", Webflow "payload.data", ...). Their
# values win over same-named keys higher up, such as Webflow's form "name".
_ANSWER_KEYS = {"data", "fields", "formdata", "submission", "values", "answers", "entry"}


def _flatten(data, out: dict[str, str], depth: int = 0) -> None:
    """Collect every leaf value under its own (normalised) key; answer containers first."""
    if depth > 4 or not isinstance(data, dict):
        return
    first, later, leaves = [], [], []
    for key, value in data.items():
        if isinstance(value, dict):
            (first if _norm(str(key)) in _ANSWER_KEYS else later).append(value)
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            later.extend(value)
        else:
            leaves.append((key, value))
    for child in first:
        _flatten(child, out, depth + 1)
    for key, value in leaves:
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        if value is not None:
            out.setdefault(_norm(str(key)), str(value))
    for child in later:
        _flatten(child, out, depth + 1)


def extract_fields(data: dict) -> dict[str, str]:
    flat: dict[str, str] = {}
    _flatten(data, flat)

    def pick(kind: str) -> str:
        for k in _KEYS[kind]:
            if flat.get(k, "").strip():
                return flat[k].strip()
        return ""

    name = pick("name") or " ".join(p for p in (pick("first"), pick("last")) if p)
    email = pick("email")
    if not email:  # any field that holds an email address
        email = next((v.strip() for k, v in flat.items() if "email" in k and "@" in v), "")
    message = pick("message")
    if not message:  # the longest free-text field that isn't one of the others
        used = {name, email, pick("phone")}
        texts = [v for v in flat.values() if v not in used and len(v) > 15 and "@" not in v]
        message = max(texts, key=len, default="")
    return {"name": name[:120], "email": email[:200], "phone": pick("phone")[:40],
            "message": message[:5000], "website": pick("website")[:200]}


class RateLimiter:
    """At most `limit` leads per visitor IP in any rolling hour (kept in memory)."""

    def __init__(self, limit: int, window_s: float = 3600):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, ip: str, now: float | None = None) -> bool:
        if self.limit <= 0:
            return True
        now = time.time() if now is None else now
        with self.lock:
            q = self.hits[ip]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


class DailyBudget:
    """Counts Claude calls per calendar day so a spam flood can't run up the bill."""

    def __init__(self, limit: int):
        self.limit = limit
        self.day = date.today()
        self.used = 0
        self.lock = threading.Lock()

    def take(self, today: date | None = None) -> bool:
        if self.limit <= 0:
            return True
        today = today or date.today()
        with self.lock:
            if today != self.day:
                self.day, self.used = today, 0
            if self.used >= self.limit:
                return False
            self.used += 1
            return True


def client_ip(headers, fallback: str) -> str:
    """The visitor's IP. Hosts like Railway put it first in X-Forwarded-For."""
    fwd = headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or fallback
