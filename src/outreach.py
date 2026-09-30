"""
Outreach generator: drafts a personalized 4-line intro email for each
top-ranked investor, citing their thesis and portfolio.

Modes:
  - demo (default): template-based drafts, offline.
  - llm: an LLM writes each draft grounded in the investor's actual thesis text.
    Providers: --provider gemini (free key, GEMINI_API_KEY) or
    --provider claude (ANTHROPIC_API_KEY).

Usage:
  python src/outreach.py --top 20
  python src/outreach.py --top 20 --mode llm                     # free Gemini
  python src/outreach.py --top 20 --mode llm --provider claude

Output: output/outreach_drafts.csv
"""

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

TEMPLATE = """Subject: EUR 1.5M seed - AI-assisted radiology platform ({geo} fit)

Hi {name},

Given {firm_ref} focus on {sector} and your work with companies like {portfolio}, I wanted to share an Austrian MedTech startup we believe fits your thesis: an AI-assisted radiology platform automating scan analysis and structured reporting, live in 3 hospital pilots with a CE/MDR pathway underway.

We are raising a EUR 1.5M seed round with tickets from EUR 250K, and your {stage} sweet spot matches where we are. Happy to share the deck and pilot data if useful.

Best regards,
{sender}"""

LLM_PROMPT = """Write a 4-sentence cold outreach email to this investor for the startup below.
Rules: reference their SPECIFIC thesis and one portfolio company from the data given;
do not invent any facts; professional, no hype words; end with a soft ask for a call.
Return JSON: {"subject": "...", "body": "..."}

INVESTOR: %s
STARTUP: %s"""


def demo_draft(row: pd.Series, startup: dict, sender: str) -> dict:
    first_sector = str(row["sectors"]).split(";")[0].strip()
    first_stage = str(row["stage_focus"]).split(";")[0].strip()
    portfolio = str(row["portfolio_examples"]).split(",")[0].strip()
    is_person = row["type"] == "Angel"
    body = TEMPLATE.format(
        name=row["name"].split()[0] if is_person else f"{row['name']} team",
        firm_ref="your" if is_person else f"{row['name']}'s",
        sector=first_sector, portfolio=portfolio, stage=first_stage,
        geo=row["geography_focus"], sender=sender,
    )
    subject, _, rest = body.partition("\n\n")
    return {"subject": subject.replace("Subject: ", ""), "body": rest}


def investor_blob(row: pd.Series) -> str:
    return row[["name", "type", "sectors", "thesis", "portfolio_examples",
                "stage_focus", "geography_focus"]].to_json()


def claude_draft(client, model: str, row: pd.Series, startup: dict) -> dict:
    msg = client.messages.create(
        model=model, max_tokens=500,
        messages=[{"role": "user",
                   "content": LLM_PROMPT % (investor_blob(row), json.dumps(startup))}],
    )
    text = msg.content[0].text.strip()
    return json.loads(text[text.find("{"):text.rfind("}") + 1])


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def gemini_draft(model: str, row: pd.Series, startup: dict) -> dict:
    import requests
    body = {"contents": [{"parts": [{"text":
            LLM_PROMPT % (investor_blob(row), json.dumps(startup))}]}],
            "generationConfig": {"responseMimeType": "application/json"}}
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
               "Content-Type": "application/json"}
    for attempt in range(3):
        resp = requests.post(GEMINI_URL.format(model=model), json=body,
                             headers=headers, timeout=60)
        if resp.status_code == 429:
            time.sleep(25)
            continue
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text[text.find("{"):text.rfind("}") + 1])
    raise RuntimeError("Gemini rate limit: 3 attempts failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--mode", choices=["demo", "llm"], default="demo")
    parser.add_argument("--provider", choices=["gemini", "claude"], default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--sender", default="Om Rana")
    args = parser.parse_args()

    scored = pd.read_csv(ROOT / "output" / "scored_investors.csv").head(args.top)
    with (ROOT / "data" / "startup_profile.json").open(encoding="utf-8") as f:
        startup = json.load(f)

    client = None
    if args.mode == "llm":
        if args.provider == "claude":
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise SystemExit("Set ANTHROPIC_API_KEY for --provider claude, or use --provider gemini (free).")
            import anthropic
            client = anthropic.Anthropic()
            model = args.model or "claude-haiku-4-5-20251001"
        else:
            if not os.environ.get("GEMINI_API_KEY"):
                raise SystemExit("Set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey), or run demo mode.")
            model = args.model or "gemini-2.0-flash"

    drafts = []
    for _, row in scored.iterrows():
        if args.mode == "llm":
            try:
                if args.provider == "claude":
                    d = claude_draft(client, model, row, startup)
                else:
                    d = gemini_draft(model, row, startup)
                    time.sleep(4)  # Gemini free-tier rate limit
            except Exception as e:
                print(f"  ! {row['name']}: {e} - falling back to template")
                d = demo_draft(row, startup, args.sender)
        else:
            d = demo_draft(row, startup, args.sender)
        drafts.append({"rank": row["rank"], "name": row["name"],
                       "contact_email": row["contact_email"],
                       "total_score": row["total_score"], **d})

    out = ROOT / "output" / "outreach_drafts.csv"
    pd.DataFrame(drafts).to_csv(out, index=False)
    print(f"Wrote {len(drafts)} outreach drafts to {out} (mode={args.mode})")
    print(f"\nSample draft for #{drafts[0]['rank']} {drafts[0]['name']}:\n")
    print(drafts[0]["subject"])
    print(drafts[0]["body"][:400])


if __name__ == "__main__":
    main()
