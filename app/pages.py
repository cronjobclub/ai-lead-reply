"""HTML for the demo contact form, the thank-you page and the lead dashboard."""

from __future__ import annotations

from html import escape
from statistics import median

FONT = "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"


def contact_form(profile: dict) -> str:
    name = escape(profile["business_name"])
    services = "".join(f"<li>{escape(s)}</li>" for s in profile.get("services", [])[:5])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} | Contact us</title>
<style>
  *{{box-sizing:border-box}} body{{margin:0;font-family:{FONT};background:#F4F1EA;color:#1F2A2E}}
  header{{background:#1E4D5C;color:#fff;padding:22px 32px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}}
  header b{{font-size:22px;letter-spacing:-.3px}} header span{{opacity:.85}}
  main{{max-width:1040px;margin:40px auto;padding:0 20px;display:grid;grid-template-columns:1fr 1.2fr;gap:40px}}
  @media(max-width:800px){{main{{grid-template-columns:1fr}}}}
  h1{{font-size:38px;line-height:1.1;margin:0 0 14px;letter-spacing:-1px}}
  .lead{{font-size:18px;line-height:1.5;color:#4A5A60}} ul{{padding-left:20px;line-height:1.9}}
  form{{background:#fff;border-radius:16px;padding:30px;box-shadow:0 12px 40px rgba(30,77,92,.12);display:grid;gap:16px}}
  label{{font-weight:600;font-size:14px;display:grid;gap:6px}}
  input,textarea{{font:inherit;padding:12px 14px;border:1.5px solid #D5D9D4;border-radius:10px;background:#FBFBF9}}
  input:focus,textarea:focus{{outline:none;border-color:#1E4D5C}}
  textarea{{min-height:130px;resize:vertical}}
  button{{font:inherit;font-weight:700;font-size:17px;padding:14px;border:0;border-radius:10px;background:#E07A2E;color:#fff;cursor:pointer}}
  button:hover{{background:#C9671F}} .hp{{position:absolute;left:-9999px}}
  .note{{font-size:13px;color:#6B7A7F}}
</style></head><body>
<header><b>{name}</b><span>{escape(profile.get('phone', ''))} &middot; {escape(profile.get('hours', ''))}</span></header>
<main>
  <section>
    <h1>Plumbing problem? Tell us what's going on.</h1>
    <p class="lead">Serving {escape(profile.get('service_area', profile.get('city', '')))}. Send us a message and you'll hear back within minutes.</p>
    <ul>{services}</ul>
  </section>
  <form method="post" action="/lead">
    <label>Your name <input name="name" required autocomplete="name"></label>
    <label>Email <input name="email" type="email" required autocomplete="email"></label>
    <label>Phone (optional) <input name="phone" type="tel" autocomplete="tel"></label>
    <label>How can we help? <textarea name="message" required></textarea></label>
    <label class="hp" aria-hidden="true">Website <input name="website" tabindex="-1" autocomplete="off"></label>
    <button type="submit">Send message</button>
    <p class="note">By sending this form you agree that we reply to you by email.</p>
  </form>
</main></body></html>"""


def thank_you(profile: dict, name: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Thanks!</title>
<style>body{{margin:0;font-family:{FONT};background:#F4F1EA;color:#1F2A2E;display:grid;place-items:center;min-height:100vh}}
div{{background:#fff;padding:44px;border-radius:16px;max-width:520px;text-align:center;box-shadow:0 12px 40px rgba(30,77,92,.12)}}
h1{{margin:0 0 10px}} a{{color:#1E4D5C}}</style></head><body><div>
<h1>Thanks, {escape(name.split()[0] if name else 'there')}.</h1>
<p>{escape(profile['business_name'])} got your message. Check your inbox: a reply is on its way.</p>
<p><a href="/">Back</a></p></div></body></html>"""


KIND_STYLE = {
    "hot_lead": ("#00F0FF", "Hot lead"),
    "question": ("#10B981", "Question"),
    "spam": ("#6E7681", "Spam"),
}


def dashboard(profile: dict, rows: list[dict], review_mode: bool) -> str:
    secs = [float(r["seconds_to_reply"]) for r in rows if r.get("seconds_to_reply") and r.get("kind") != "spam"]
    cost = sum(float(r.get("cost_usd") or 0) for r in rows)
    stats = [
        (str(len(rows)), "leads"),
        (f"{median(secs):.0f}s" if secs else "-", "median time to reply"),
        (f"${cost:.4f}", "total AI cost"),
    ]
    stat_html = "".join(f"<div class=stat><b>{v}</b><span>{label}</span></div>" for v, label in stats)

    body = []
    for r in rows:
        color, label = KIND_STYLE.get(r.get("kind", ""), ("#F59E0B", "Needs you"))
        reply = escape(r.get("reply_body", "")).replace("\n", "<br>") or "<i>No reply sent</i>"
        error = f"<div class=err>{escape(r['error'])}</div>" if r.get("error") else ""
        body.append(f"""<tr>
<td class=mono>{escape(r.get('received_at', '')[11:])}</td>
<td><span class=pill style="color:{color};border-color:{color}">{label}</span>
    <div class=urg>{escape(r.get('urgency', ''))}</div></td>
<td><b>{escape(r.get('name', ''))}</b><div class=muted>{escape(r.get('email', ''))}</div></td>
<td>{escape(r.get('summary', ''))}<details><summary>Message and reply</summary>
    <p class=msg>{escape(r.get('message', ''))}</p><p class=reply>{reply}</p></details>{error}</td>
<td class=mono>{escape(r.get('action', ''))}</td>
<td class="mono big">{'-' if r.get('kind') == 'spam' or r.get('error') else escape(r.get('seconds_to_reply', '')) + 's'}</td>
<td class=mono>${float(r.get('cost_usd') or 0):.5f}</td></tr>""")
    rows_html = "".join(body) or "<tr><td colspan=7 class=empty>No leads yet. Submit the form at <a href='/'>/</a>.</td></tr>"
    banner = "<div class=review>REVIEW_MODE is on: drafts go to you, not to customers.</div>" if review_mode else ""

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Leads | {escape(profile['business_name'])}</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;font-family:{FONT};background:#0D1117;color:#E6EDF3;padding:36px}}
h1{{margin:0;font-size:30px;letter-spacing:-.6px}} .sub{{color:#8B949E;margin:6px 0 24px}}
.stats{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}}
.stat{{background:#161B22;border:1px solid #30363D;border-radius:14px;padding:16px 22px;min-width:180px}}
.stat b{{display:block;font-size:34px;color:#00F0FF}} .stat span{{color:#8B949E;font-size:14px}}
.wrap{{overflow-x:auto;border:1px solid #30363D;border-radius:14px}}
table{{width:100%;border-collapse:collapse;font-size:15px;min-width:900px}}
th{{text-align:left;color:#8B949E;font-weight:500;font-size:13px;padding:12px 14px;background:#161B22;border-bottom:1px solid #30363D}}
td{{padding:14px;border-bottom:1px solid #21262D;vertical-align:top}}
.mono{{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:13px;color:#8B949E}} .big{{font-size:18px;color:#10B981}}
.pill{{border:1.5px solid;border-radius:999px;padding:3px 10px;font-size:13px;font-weight:600;white-space:nowrap}}
.urg{{color:#8B949E;font-size:12px;margin-top:6px}} .muted{{color:#8B949E;font-size:13px}}
details{{margin-top:8px;color:#8B949E}} summary{{cursor:pointer;font-size:13px}}
.msg{{color:#C9D1D9;border-left:3px solid #30363D;padding-left:10px}} .reply{{color:#E6EDF3;border-left:3px solid #00F0FF;padding-left:10px}}
.err{{color:#F59E0B;font-size:13px;margin-top:6px}} .empty{{text-align:center;color:#8B949E;padding:40px}}
.review{{background:rgba(245,158,11,.12);border:1px solid #F59E0B;color:#F59E0B;padding:10px 14px;border-radius:10px;margin-bottom:18px}}
a{{color:#00F0FF}}
</style></head><body>
<h1>{escape(profile['business_name'])}: incoming leads</h1>
<div class=sub>Updates every 3 seconds (paused while a lead is open) &middot; newest first</div>
<script>
// Reload for new leads, but never while someone is reading an expanded lead.
setInterval(function () {
  if (!document.querySelector("details[open]")) location.reload();
}, 3000);
</script>
{banner}<div class=stats>{stat_html}</div>
<div class=wrap><table><thead><tr><th>Received</th><th>Kind</th><th>From</th><th>Summary</th><th>Action</th><th>Reply time</th><th>AI cost</th></tr></thead>
<tbody>{rows_html}</tbody></table></div>
</body></html>"""
