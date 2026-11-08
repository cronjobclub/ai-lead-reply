"""What happens to one lead: sort it, reply (or not), alert the owner, log it."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from . import store
from .ai import LeadAI, Triage
from .config import Settings
from .mailer import Mailer

log = logging.getLogger("lead-reply")


@dataclass
class Lead:
    name: str
    email: str
    phone: str
    message: str
    honeypot: str = ""  # hidden form field: only bots fill it in


def _owner_block(lead: Lead, t: Triage | None) -> str:
    lines = [
        f"Name:    {lead.name}",
        f"Email:   {lead.email}",
        f"Phone:   {lead.phone or 'not given'}",
    ]
    if t:
        lines += [f"Kind:    {t.kind}  (urgency: {t.urgency})", f"Summary: {t.summary}"]
    lines += ["", "Their message:", lead.message]
    return "\n".join(lines)


def process_lead(lead: Lead, ai: LeadAI, mailer: Mailer, settings: Settings, profile: dict,
                 received: float | None = None, ai_allowed: bool = True) -> dict:
    received = received or time.time()
    row = {
        "received_at": datetime.fromtimestamp(received).isoformat(timespec="seconds"),
        "name": lead.name, "email": lead.email, "phone": lead.phone, "message": lead.message,
    }
    biz = profile["business_name"]

    try:
        if lead.honeypot:
            t = Triage("spam", "none", "Bot filled the hidden form field", "", "")
        elif not ai_allowed:
            raise RuntimeError("Daily limit of Claude calls reached (MAX_AI_CALLS_PER_DAY)")
        else:
            t = ai.triage(lead.name, lead.email, lead.phone, lead.message)

        cost = (t.input_tokens * settings.price_input_per_mtok
                + t.output_tokens * settings.price_output_per_mtok) / 1_000_000
        row.update(kind=t.kind, urgency=t.urgency, summary=t.summary,
                   reply_subject=t.reply_subject, reply_body=t.reply_body,
                   input_tokens=t.input_tokens, output_tokens=t.output_tokens,
                   cost_usd=f"{cost:.6f}")

        if t.kind == "spam":
            row["action"] = "no reply (spam)"
        else:
            body = t.reply_body
            if profile.get("ai_disclosure"):
                body += f"\n\n--\n{profile['ai_disclosure']}"

            if settings.review_mode:
                mailer.send(
                    settings.owner_email,
                    f"[Approve?] {t.reply_subject}",
                    "REVIEW_MODE is on, so this reply was NOT sent to the customer.\n"
                    f"Forward or copy it to {lead.email} if it looks right.\n\n"
                    f"--- Draft reply ---\nSubject: {t.reply_subject}\n\n{body}\n\n"
                    f"--- The lead ---\n{_owner_block(lead, t)}",
                )
                row["action"] = "draft sent to owner for approval"
            else:
                mailer.send(lead.email, t.reply_subject, body, reply_to=settings.owner_email)
                row["action"] = "replied"
                if t.kind == "hot_lead":
                    mailer.send(
                        settings.owner_email,
                        f"[HOT LEAD{' - EMERGENCY' if t.urgency == 'emergency' else ''}] {t.summary}",
                        f"A reply was already sent. Follow up personally.\n\n{_owner_block(lead, t)}"
                        f"\n\n--- Reply we sent ---\n{body}",
                    )
                    row["action"] = "replied + owner alerted"

    except Exception as exc:  # never lose a lead: hand it to a human
        log.exception("Lead processing failed")
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        row["action"] = "needs manual reply"
        try:
            mailer.send(settings.owner_email, f"[NEEDS MANUAL REPLY] New lead from {lead.name}",
                        f"The assistant could not answer this lead automatically ({row['error']}).\n\n"
                        f"{_owner_block(lead, None)}")
        except Exception:
            log.exception("Could not alert the owner either")

    done = time.time()
    row["replied_at"] = datetime.fromtimestamp(done).isoformat(timespec="seconds")
    row["seconds_to_reply"] = f"{done - received:.1f}"
    store.append(settings.log_path, row)
    log.info("%s | %s | %s | %ss | $%s", biz, row.get("kind", "?"), row["action"],
             row["seconds_to_reply"], row.get("cost_usd", "0"))
    return row
