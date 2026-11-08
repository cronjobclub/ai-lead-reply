"""Send three demo leads to the running app: an emergency job, a question and spam.

Usage (with the app running):  python scripts/send_demo_leads.py
Optional: python scripts/send_demo_leads.py --to you+test@gmail.com --url http://127.0.0.1:8000
"""

import argparse
import time

import httpx

DEMO_LEADS = [
    {
        "name": "Priya Raman",
        "phone": "647-555-0188",
        "message": "Water is coming through our kitchen ceiling from the upstairs bathroom. "
                   "I've turned off the valve under the toilet but it's still dripping. "
                   "We're near Danforth and Pape. Can someone come today?",
    },
    {
        "name": "Marcus Lee",
        "phone": "",
        "message": "Hi, our basement floor drain backs up a little after heavy rain. "
                   "Is that something a backwater valve fixes, and roughly what does a drain cleaning cost?",
    },
    {
        "name": "SEO Growth Team",
        "phone": "",
        "message": "Dear business owner, we can get your website to #1 on Google in 30 days. "
                   "Reply YES for a free audit. Limited offer!!!",
    },
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--to", default="demo-lead@example.com",
                    help="Email address the replies go to (use your own for a real test)")
    args = ap.parse_args()

    user, _, domain = args.to.partition("@")
    for i, lead in enumerate(DEMO_LEADS, 1):
        payload = {**lead, "email": f"{user}+lead{i}@{domain}" if "gmail" in domain else args.to}
        r = httpx.post(f"{args.url}/lead", json=payload, timeout=10)
        print(f"{i}. {lead['name']:<18} -> HTTP {r.status_code}")
        time.sleep(1)
    print(f"\nWatch the replies arrive at {args.url}/leads")


if __name__ == "__main__":
    main()
