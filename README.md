# AI Lead Reply

Answer every new contact-form lead in under a minute: Claude sorts the message (hot lead, question or spam), writes a personal reply in your business's voice, emails it, alerts you about hot leads and logs everything to a spreadsheet.

Built for the Cron Job Club video *"I Built an AI That Replies to Every New Lead in 60 Seconds."* ▶ **[Watch it on YouTube](https://youtu.be/ZHWXAyR6Lpw)**

![A lead fills in the form and the reply lands on the dashboard about 6 seconds later](docs/demo.gif)

*Real run, typing sped up. The reply was sent 6.1 seconds after the lead hit Send.*

<table>
<tr>
<td width="50%"><img src="docs/dashboard.png" alt="Dashboard: three leads sorted as spam, question and hot lead, with reply time and AI cost per lead"></td>
<td width="50%"><img src="docs/reply.png" alt="The hot lead's message and the reply Claude wrote in the business's voice"></td>
</tr>
<tr>
<td>The dashboard: every lead sorted, timed and costed</td>
<td>The reply Claude wrote for the hot lead</td>
</tr>
</table>

```
Contact form ──▶ /lead webhook ──▶ Claude (sort + draft) ──┬─ hot lead ─▶ reply + alert the owner
                                                            ├─ question ─▶ reply
                                                            └─ spam ─────▶ no reply
                                     every lead ──▶ data/leads.csv + /leads dashboard
```

## What it costs

One Claude call per lead. With `claude-haiku-5-5` that is a fraction of a cent per lead (about 1,300 tokens in and 250 out). The exact cost of every lead is in the log and on the dashboard. Prices: <https://platform.claude.com/docs/en/about-claude/pricing>

## Setup (about 10 minutes)

You need **Python 3.10 or newer** and a **Claude API key** from <https://platform.claude.com> (add a few dollars of credit).

```bash
git clone https://github.com/cronjobclub/ai-lead-reply.git
cd ai-lead-reply

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # Windows: copy .env.example .env
```

Open `.env` and set at least:

```
ANTHROPIC_API_KEY=sk-ant-...
OWNER_EMAIL=you@yourbusiness.com
```

Start it:

```bash
uvicorn app.main:app --reload
```

- Contact form: <http://127.0.0.1:8000>
- Lead dashboard: <http://127.0.0.1:8000/leads>

Fill in the form, or send three test leads (an emergency, a question and spam):

```bash
python scripts/send_demo_leads.py
```

## Make it yours

Edit **`business_profile.yaml`**: name, services, service area, hours, what you may say about prices, how to book, your tone and things it must never promise. No code changes needed. Restart the app after editing.

## Sending real email

By default `SEND_MODE=outbox`, so emails are saved as `.eml` files in `./outbox` (double-click to open them in your mail app). When the replies look right:

1. Turn on 2-Step Verification for your Google account.
2. Create an app password: Google Account → Security → 2-Step Verification → App passwords.
3. In `.env`:
   ```
   SEND_MODE=smtp
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=your16charapppassword
   FROM_EMAIL=you@gmail.com
   ```

On a server, use `SEND_MODE=resend` instead (see below): many hosts block Gmail's SMTP ports.

## Safety switches

| Setting | What it does |
| --- | --- |
| `REVIEW_MODE=true` | Replies go to **you** for approval instead of to the customer. Start here if you're nervous. |
| `business_profile.yaml → never` | Rules Claude must always follow (no exact arrival times, no invented prices). |
| `ai_disclosure` | A line under every reply saying an assistant drafted it. Keep it: it's honest and builds trust. |
| Hidden honeypot field | Bots that fill it in are marked as spam without calling Claude. |
| Failure fallback | If Claude or email fails, you get a "NEEDS MANUAL REPLY" email. A lead is never lost. |
| `DASHBOARD_TOKEN` | Required on a server: the dashboard opens only at `/leads?token=...`. |
| `WEBHOOK_SECRET` | Website builders posting JSON must send it (`X-Webhook-Secret` header or `?secret=`). |
| `MAX_LEADS_PER_IP_PER_HOUR` | Default 5, on a server only. Stops one visitor flooding the form. |
| `MAX_AI_CALLS_PER_DAY` | Default 200. After that, leads still reach you as "NEEDS MANUAL REPLY", so a spam flood can't run up your Claude bill. |

## Run it 24/7 on Railway (about 15 minutes, $5/month)

On your laptop the app only answers while the laptop is on. Railway runs it all the time. Prices checked November 2026: Railway Hobby is $5/month including $5 of usage, which should cover a small app like this. Resend's free plan sends 3,000 emails a month (100 a day).

**1. Email that works on a server.** Railway's Hobby plan blocks SMTP (Gmail), so send through Resend's HTTPS API:
   1. Sign up at [resend.com](https://resend.com) and create an API key.
   2. Domains → Add domain → add the DNS records it shows at your domain registrar. Until the domain is verified, Resend only delivers to your own address.

**2. Deploy.**
   1. Fork this repo (or use your copy) and sign in at [railway.com](https://railway.com) with GitHub.
   2. New Project → Deploy from GitHub repo → pick it. `railway.json` already tells Railway how to start the app and check `/health`.
   3. Right-click the service → Attach volume → mount path `/data` (this keeps `leads.csv` across deploys).
   4. Settings → Networking → Generate domain. That's your public address.

**3. Variables** (service → Variables; never put keys in the code):

| Variable | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | your Claude API key |
| `SEND_MODE` | `resend` |
| `RESEND_API_KEY` | your Resend key |
| `FROM_EMAIL` | `Your Business <hello@yourdomain.com>` (on the verified domain) |
| `OWNER_EMAIL` | where hot-lead alerts go |
| `DASHBOARD_TOKEN` | 16+ random characters, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(24))"` |
| `WEBHOOK_SECRET` | another random string, for website builders |
| `DATA_DIR` | `/data` |

Railway sets `RAILWAY_ENVIRONMENT`, which switches on production checks: the dashboard stays locked until `DASHBOARD_TOKEN` is set, and `/health` lists anything missing.

**4. Test it** from your phone: open `https://<your-domain>/`, send a message, then open `https://<your-domain>/leads?token=<DASHBOARD_TOKEN>`.

Prefer another host? It runs anywhere that runs Python (a `Procfile` is included). Render's free tier sleeps after 15 minutes idle and blocks SMTP; Fly.io is cheaper but uses a command-line tool.

## Connect your website form

`POST /lead` accepts a normal form post or JSON, and finds name, email, phone and message in whatever shape your site builder sends.

| Your site | How |
| --- | --- |
| Plain HTML | `<form method="post" action="https://<your-domain>/lead">` with fields `name`, `email`, `phone`, `message` |
| WordPress + Contact Form 7 | Plugin "CF7 to Webhook" → URL `https://<your-domain>/lead?secret=<WEBHOOK_SECRET>` |
| Wix | Automations → trigger: form submitted → action: Send HTTP request (POST, all data) to the same URL |
| Webflow | Site settings → Apps & integrations → Webhooks → Form submission → the same URL |
| Squarespace, others | Zapier, Make or n8n → POST the fields as JSON to the same URL |

## Project layout

```
app/
  main.py        web app: form page, /lead webhook, /leads dashboard
  pipeline.py    what happens to one lead
  ai.py          the Claude call (prompt + JSON schema)
  mailer.py      SMTP, Resend or outbox
  intake.py      reads any site builder's form; rate limit and daily AI cap
  store.py       leads.csv
  pages.py       HTML for the form and dashboard
  config.py      .env and business_profile.yaml
business_profile.yaml
scripts/send_demo_leads.py
railway.json     how Railway starts and health-checks the app
tests/           offline tests (no API key needed): python -m pytest
```

## Legal note

Replying to someone who contacted you is generally fine under anti-spam laws like Canada's CASL, but adding them to a marketing list is not. This is not legal advice; check the rules where you operate.

MIT licence.
