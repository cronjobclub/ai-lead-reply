"""Offline tests: Claude is replaced by a fake, emails go to a temp outbox."""

import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app import store
from app.ai import LeadAI
from app.config import Settings, load_profile
from app.mailer import Mailer
from app.pipeline import Lead, process_lead

ROOT = Path(__file__).resolve().parent.parent
PROFILE = load_profile(ROOT / "business_profile.yaml")


def fake_response(payload: dict):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
    )


class FakeMessages:
    def __init__(self, payload=None, fail_first_with_output_config=False, error=None):
        self.payload = payload
        self.calls = []
        self.fail_first = fail_first_with_output_config
        self.error = error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if self.fail_first and "extra_body" in kwargs:
            req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.BadRequestError(
                "output_config.format is not supported for this model",
                response=httpx.Response(400, request=req), body=None)
        return fake_response(self.payload)


def make_ai(messages: FakeMessages) -> LeadAI:
    ai = LeadAI("test-key", "claude-haiku-5-5", PROFILE)
    ai.client = SimpleNamespace(messages=messages)
    return ai


HOT = {"kind": "hot_lead", "urgency": "emergency", "summary": "Leak through kitchen ceiling",
       "reply_subject": "We can help with the leak today",
       "reply_body": "Hi Priya,\n\nPlease call (416) 555-0142 now.\n\nSam, Maple Street Plumbing"}
SPAM = {"kind": "spam", "urgency": "none", "summary": "SEO pitch", "reply_subject": "", "reply_body": ""}


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.data_dir, s.outbox_dir = tmp_path / "data", tmp_path / "outbox"
    s.send_mode, s.review_mode, s.owner_email = "outbox", False, "owner@example.com"
    return s


def outbox(settings):
    return sorted(p.read_text() for p in settings.outbox_dir.glob("*.eml")) if settings.outbox_dir.exists() else []


LEAD = Lead("Priya Raman", "priya@example.com", "647-555-0188", "Water coming through the ceiling!")


def test_hot_lead_gets_reply_and_owner_alert(settings):
    row = process_lead(LEAD, make_ai(FakeMessages(HOT)), Mailer(settings), settings, PROFILE)
    mails = outbox(settings)
    assert row["action"] == "replied + owner alerted"
    assert len(mails) == 2
    assert any("To: priya@example.com" in m and "drafted by our assistant" in m for m in mails)
    assert any("To: owner@example.com" in m and "HOT LEAD - EMERGENCY" in m for m in mails)
    logged = store.read_all(settings.log_path)
    assert logged[0]["kind"] == "hot_lead" and float(logged[0]["cost_usd"]) == pytest.approx(0.00027)


def test_spam_gets_no_email(settings):
    row = process_lead(LEAD, make_ai(FakeMessages(SPAM)), Mailer(settings), settings, PROFILE)
    assert row["action"] == "no reply (spam)"
    assert outbox(settings) == []


def test_review_mode_sends_draft_to_owner_only(settings):
    settings.review_mode = True
    row = process_lead(LEAD, make_ai(FakeMessages(HOT)), Mailer(settings), settings, PROFILE)
    mails = outbox(settings)
    assert row["action"] == "draft sent to owner for approval"
    assert len(mails) == 1 and "To: owner@example.com" in mails[0] and "[Approve?]" in mails[0]


def test_honeypot_skips_claude(settings):
    messages = FakeMessages(HOT)
    bot = Lead("Bot", "bot@example.com", "", "buy now", honeypot="http://spam.example")
    row = process_lead(bot, make_ai(messages), Mailer(settings), settings, PROFILE)
    assert row["kind"] == "spam" and messages.calls == []


def test_ai_failure_hands_lead_to_owner(settings):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.APIConnectionError(request=req)
    row = process_lead(LEAD, make_ai(FakeMessages(error=err)), Mailer(settings), settings, PROFILE)
    mails = outbox(settings)
    assert row["action"] == "needs manual reply" and row["error"]
    assert len(mails) == 1 and "NEEDS MANUAL REPLY" in mails[0]
    assert store.read_all(settings.log_path)[0]["action"] == "needs manual reply"


def test_falls_back_when_structured_output_unsupported(settings):
    messages = FakeMessages(HOT, fail_first_with_output_config=True)
    t = make_ai(messages).triage("Priya", "priya@example.com", "", "Leak!")
    assert t.kind == "hot_lead" and len(messages.calls) == 2
    assert "extra_body" not in messages.calls[1] and "ONLY a JSON object" in messages.calls[1]["system"]


def test_structured_output_schema_is_sent(settings):
    messages = FakeMessages(HOT)
    make_ai(messages).triage("Priya", "priya@example.com", "", "Leak!")
    fmt = messages.calls[0]["extra_body"]["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False


def test_web_endpoints(settings, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main

    main.settings.cache_clear()
    monkeypatch.setattr(main, "settings", lambda: settings)
    monkeypatch.setattr(main, "ai", lambda: make_ai(FakeMessages(HOT)))
    client = TestClient(main.app)

    assert "Maple Street Plumbing" in client.get("/").text
    r = client.post("/lead", data={"name": "Priya Raman", "email": "priya@example.com",
                                   "phone": "", "message": "Leak!", "website": ""})
    assert r.status_code == 200 and "Thanks, Priya" in r.text
    r = client.post("/lead", json={"name": "Marcus", "email": "m@example.com", "message": "Question"})
    assert r.status_code == 202
    assert client.post("/lead", json={"name": "x", "email": "bad", "message": "y"}).status_code == 422
    dash = client.get("/leads").text
    assert "Hot lead" in dash and "Priya Raman" in dash and "median time to reply" in dash
