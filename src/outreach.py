"""
Outreach generator: drafts a personalized 4-line intro email for each
top-ranked investor, citing their thesis and portfolio.

Modes:
  - template (default): template-based drafts, offline.
  - llm: an LLM writes each draft grounded in the investor's actual thesis text.
    Providers: --provider gemini (free key, GEMINI_API_KEY) or
    --provider claude (ANTHROPIC_API_KEY). Responses are cached like scoring.

Every draft records draft_source = template | llm | template_fallback, and LLM
drafts are checked for grounding: a draft that names none of the investor's
listed portfolio companies is flagged (grounded = False) for human review.

Usage:
  python src/outreach.py --top 20
  python src/outreach.py --top 10 --mode llm                     # free Gemini
  python src/outreach.py --top 10 --mode llm --provider claude

Output: output/outreach_drafts.csv
"""

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

TEMPLATE = """Subject: EUR 1.5M seed - AI-assisted radiology platform ({geo} fit)

Hi {name},

Given {firm_ref} focus on {sector} and your work with companies like {portfolio}, I wanted to share an Austrian MedTech startup we believe fits your thesis: an AI-assisted radiology platform automating scan analysis and structured reporting, live in 3 hospital pilots with a CE/MDR pathway underway.

We are raising a EUR 1.5M seed round with tickets from EUR 250K, and your {stage} sweet spot matches where we are. Happy to share the deck and pilot data if useful.

Best regards,
{sender}"""

LLM_SYSTEM = """You write concise, factual cold outreach emails from a startup to an investor.
Rules: reference the investor's SPECIFIC thesis and exactly one portfolio company from the
data given; do not invent any facts about the investor or the startup; professional tone,
no hype words; 4 sentences; end with a soft ask for a call.
Return JSON: {"subject": "...", "body": "..."}"""


def template_draft(row: pd.Series, startup: dict, sender: str) -> dict:
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


def is_grounded(body: str, row: pd.Series) -> bool:
    """Cheap hallucination check: the draft must cite a portfolio company we actually gave it."""
    portfolio = [p.strip() for p in str(row["portfolio_examples"]).split(",") if p.strip()]
    return any(p.lower() in body.lower() for p in portfolio)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--mode", choices=["template", "demo", "llm"], default="template",
                        help="'demo' is kept as an alias of 'template'")
    parser.add_argument("--provider", choices=["gemini", "claude"], default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--rpm", type=float, default=6)
    parser.add_argument("--sender", default="Om Rana")
    args = parser.parse_args()

    scored = pd.read_csv(ROOT / "output" / "scored_investors.csv").head(args.top)
    with (ROOT / "data" / "startup_profile.json").open(encoding="utf-8") as f:
        startup = json.load(f)

    client = None
    if args.mode == "llm":
        from llm import FatalLLMError, LLMClient, QuotaExhausted
        try:
            client = LLMClient(args.provider, args.model,
                               cache_path=ROOT / "output" / "llm_cache.jsonl", rpm=args.rpm)
        except FatalLLMError as e:
            raise SystemExit(f"LLM run aborted: {e}")

    drafts, failures, quota_hit = [], 0, False
    for _, row in scored.iterrows():
        source = "template"
        d = template_draft(row, startup, args.sender)
        if client and not quota_hit:
            try:
                raw = client.complete_json(
                    LLM_SYSTEM, f"INVESTOR: {investor_blob(row)}\nSTARTUP: {json.dumps(startup)}")
                d = {"subject": str(raw["subject"]), "body": str(raw["body"])}
                source = "llm"
            except FatalLLMError as e:
                raise SystemExit(f"LLM run aborted: {e}")
            except QuotaExhausted:
                quota_hit = True
                source = "template_fallback"
            except Exception as e:
                failures += 1
                print(f"  ! {row['name']}: {e} - template fallback")
                source = "template_fallback"
        drafts.append({"rank": row["rank"], "name": row["name"],
                       "contact_email": row["contact_email"],
                       "total_score": row["total_score"], **d,
                       "draft_source": source, "grounded": is_grounded(d["body"], row)})

    out = ROOT / "output" / "outreach_drafts.csv"
    df = pd.DataFrame(drafts)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} outreach drafts to {out}")
    print(f"  sources: {df['draft_source'].value_counts().to_dict()}")
    print(f"  grounded (cites a real portfolio company): {int(df['grounded'].sum())}/{len(df)}")
    if quota_hit:
        print("  !! daily quota reached - remaining drafts are templates; re-run tomorrow.")
    print(f"\nSample draft for #{drafts[0]['rank']} {drafts[0]['name']}:\n")
    print(drafts[0]["subject"])
    print(drafts[0]["body"][:400])


if __name__ == "__main__":
    main()
