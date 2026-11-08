"""Tests for running on the public internet: form adapters, limits, Resend, the locked dashboard."""

from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.intake import DailyBudget, RateLimiter, client_ip, extract_fields
from app.mailer import Mailer, MailError

from .test_pipeline import HOT, PROFILE, FakeMessages, make_ai


# ---------------------------------------------------------------- form adapters

def test_plain_form():
    f = extract_fields({"name": "Priya", "email": "p@example.com", "phone": "", "message": "Leak!", "website": ""})
    assert f == {"name": "Priya", "email": "p@example.com", "phone": "", "message": "Leak!", "website": ""}


def test_contact_form_7():
    f = extract_fields({"your-name": "Marcus Lee", "your-email": "m@example.com",
                        "your-subject": "Drain", "your-message": "My basement drain backs up."})
    assert (f["name"], f["email"], f["message"]) == ("Marcus Lee", "m@example.com", "My basement drain backs up.")


def test_wix_nested_with_first_last():
    f = extract_fields({"data": {"field:first_name": "Ana", "field:last_name": "Silva",
                                 "field:email": "ana@example.com", "field:phone": "416-555-0100",
                                 "field:long_answer": "Water heater is making a banging noise."}})
    assert f["name"] == "Ana Silva" and f["email"] == "ana@example.com" and f["phone"] == "416-555-0100"
    assert f["message"] == "Water heater is making a banging noise."


def test_webflow_webhook():
    f = extract_fields({"triggerType": "form_submission",
                        "payload": {"name": "Contact", "siteId": "abc",
                                    "data": {"Name": "Tom", "Email": "tom@example.com",
                                             "Message": "Need a quote for a new toilet."}}})
    # The form's own name ("Contact") sits higher up than the visitor's name; the visitor's wins.
    assert (f["name"], f["email"]) == ("Tom", "tom@example.com")
    assert f["message"] == "Need a quote for a new toilet."


def test_any_email_field_and_longest_text_fallback():
    f = extract_fields({"Full Name": "Lee", "Work Email": "lee@example.com",
                        "Tell us about the job": "Kitchen sink is draining very slowly since Monday."})
    assert f["email"] == "lee@example.com"
    assert f["message"].startswith("Kitchen sink")


# ---------------------------------------------------------------- limits

def test_rate_limiter_per_ip():
    rl = RateLimiter(2, window_s=3600)
    assert rl.allow("1.1.1.1", 0) and rl.allow("1.1.1.1", 1)
    assert not rl.allow("1.1.1.1", 2)
    assert rl.allow("2.2.2.2", 2)          # another visitor is unaffected
    assert rl.allow("1.1.1.1", 3700)       # an hour later it's allowed again


def test_daily_budget_resets():
    b = DailyBudget(1)
    assert b.take(date(2026, 11, 8)) and not b.take(date(2026, 11, 8))
    assert b.take(date(2026, 11, 9))


def test_client_ip_from_proxy():
    assert client_ip({"x-forwarded-for": "203.0.113.5, 10.0.0.1"}, "10.0.0.1") == "203.0.113.5"
    assert client_ip({}, "127.0.0.1") == "127.0.0.1"


# ---------------------------------------------------------------- Resend

def test_resend_sends_over_https(monkeypatch, tmp_path):
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, json=json, headers=headers)
        return httpx.Response(200, json={"id": "abc123"}, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.mailer.httpx.post", fake_post)
    s = Settings()
    s.send_mode, s.resend_api_key, s.from_email = "resend", "re_test", "Sam <sam@example.com>"
    result = Mailer(s).send("p@example.com", "Hi", "Body", reply_to="owner@example.com")
    assert sent["url"] == "https://api.resend.com/emails"
    assert sent["json"] == {"from": "Sam <sam@example.com>", "to": ["p@example.com"], "subject": "Hi",
                            "text": "Body", "reply_to": "owner@example.com"}
    assert sent["headers"]["Authorization"] == "Bearer re_test" and "abc123" in result


def test_resend_error_is_raised(monkeypatch):
    monkeypatch.setattr("app.mailer.httpx.post", lambda url, **k: httpx.Response(
        403, text="You can only send testing emails to your own email address",
        request=httpx.Request("POST", url)))
    s = Settings()
    s.send_mode, s.resend_api_key, s.from_email = "resend", "re_test", "sam@example.com"
    with pytest.raises(MailError, match="403"):
        Mailer(s).send("p@example.com", "Hi", "Body")


# ---------------------------------------------------------------- the web app in production

@pytest.fixture
def prod(tmp_path, monkeypatch):
    s = Settings()
    s.data_dir, s.outbox_dir = tmp_path / "data", tmp_path / "outbox"
    s.send_mode, s.production, s.owner_email = "outbox", True, "owner@example.com"
    s.dashboard_token, s.webhook_secret = "", "hook-secret"
    s.max_leads_per_ip_per_hour, s.max_ai_calls_per_day = 3, 1
    for fn in (main.limiter, main.budget):
        fn.cache_clear()
    monkeypatch.setattr(main, "settings", lambda: s)
    monkeypatch.setattr(main, "ai", lambda: make_ai(FakeMessages(HOT)))
    yield s, TestClient(main.app)
    for fn in (main.limiter, main.budget):
        fn.cache_clear()


def test_dashboard_locked_until_token_set(prod):
    s, client = prod
    assert client.get("/leads").status_code == 503
    s.dashboard_token = "a-long-random-token-123"
    assert client.get("/leads").status_code == 403
    assert client.get("/leads?token=a-long-random-token-123").status_code == 200


def test_webhook_secret_required_for_json(prod):
    _, client = prod
    lead = {"your-name": "Marcus", "your-email": "m@example.com", "your-message": "Question about drains"}
    assert client.post("/lead", json=lead).status_code == 401
    assert client.post("/lead?secret=hook-secret", json=lead).status_code == 202
    assert client.post("/lead", json=lead, headers={"X-Webhook-Secret": "hook-secret"}).status_code == 202


def test_rate_limit_and_daily_cap(prod):
    s, client = prod
    form = {"name": "Priya", "email": "p@example.com", "message": "Leak!", "website": ""}
    codes = [client.post("/lead", data=form, headers={"X-Forwarded-For": "203.0.113.9"}).status_code
             for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    from app import store
    rows = store.read_all(s.log_path)
    # Daily cap is 1: the first lead got an AI reply, the next two went to the owner by hand.
    assert [r["action"] for r in rows] == ["replied + owner alerted", "needs manual reply", "needs manual reply"]


def test_health_reports_production_problems(prod):
    _, client = prod
    problems = client.get("/health").json()["problems"]
    assert any("DASHBOARD_TOKEN" in p for p in problems) and any("outbox" in p for p in problems)
