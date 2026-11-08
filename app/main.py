"""The web app: a demo contact form, the /lead webhook, and a /leads dashboard.

Run it with:  uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from html import escape

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import pages, store
from .ai import LeadAI
from .config import Settings, load_profile
from .mailer import Mailer
from .pipeline import Lead, process_lead

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lead-reply")



@lru_cache
def settings() -> Settings:
    s = Settings()
    for problem in s.validate():
        log.warning("Setup: %s", problem)
    return s


@lru_cache
def profile() -> dict:
    return load_profile(settings().profile_path)


@lru_cache
def ai() -> LeadAI:
    return LeadAI(settings().anthropic_api_key, settings().model, profile())


def mailer() -> Mailer:
    return Mailer(settings())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = settings()
    log.info("Business: %s | model: %s | send mode: %s | review mode: %s",
             profile()["business_name"], s.model, s.send_mode, "ON" if s.review_mode else "off")
    log.info("Contact form: http://127.0.0.1:8000/   Dashboard: http://127.0.0.1:8000/leads")
    yield


app = FastAPI(title="AI Lead Reply", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def form_page() -> str:
    return pages.contact_form(profile())


@app.post("/lead")
async def receive_lead(request: Request, background: BackgroundTasks):
    received = time.time()
    if request.headers.get("content-type", "").startswith("application/json"):
        data = await request.json()
        wants_html = False
    else:
        data = dict(await request.form())
        wants_html = True

    name = str(data.get("name", "")).strip()[:120]
    email = str(data.get("email", "")).strip()[:200]
    message = str(data.get("message", "")).strip()[:5000]
    if not (name and "@" in email and message):
        raise HTTPException(422, "name, a valid email and message are required")

    lead = Lead(name=name, email=email, phone=str(data.get("phone", "")).strip()[:40],
                message=message, honeypot=str(data.get("website", "")).strip())
    # Reply in the background so the visitor sees "thanks" instantly.
    background.add_task(process_lead, lead, ai(), mailer(), settings(), profile(), received)

    if wants_html:
        return HTMLResponse(pages.thank_you(profile(), name))
    return JSONResponse({"status": "received"}, status_code=202)


@app.get("/leads", response_class=HTMLResponse)
def dashboard(token: str = "") -> str:
    s = settings()
    if s.dashboard_token and token != s.dashboard_token:
        raise HTTPException(403, "Add ?token=YOUR_DASHBOARD_TOKEN to the address")
    rows = sorted(store.read_all(s.log_path), key=lambda r: r.get("received_at", ""), reverse=True)
    return pages.dashboard(profile(), rows, review_mode=s.review_mode)


@app.get("/health")
def health() -> dict:
    s = settings()
    return {"ok": not s.validate(), "problems": s.validate(), "model": s.model,
            "send_mode": s.send_mode, "review_mode": s.review_mode,
            "business": escape(profile()["business_name"])}
