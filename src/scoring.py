"""
Scoring engine: ranks every investor against the startup profile.

Two modes:
  - demo (default): deterministic rubric-based scoring, runs offline with no API key.
  - llm: sends each investor profile + the startup profile to an LLM and asks for
    structured JSON scores on the same 4-dimension rubric.
    Providers: --provider gemini (FREE key from https://aistudio.google.com, set
    GEMINI_API_KEY) or --provider claude (set ANTHROPIC_API_KEY).

Rubric (weighted 0-100 total):
  thesis_fit  40%  - sector/thesis overlap with the startup
  stage_fit   25%  - does the investor invest at the startup's stage?
  ticket_fit  20%  - does the investor's ticket range overlap the target range?
  geo_fit     15%  - geography priority match (DACH > Europe > Global)

Usage:
  python src/scoring.py                                  # demo mode (offline)
  python src/scoring.py --mode llm --limit 25            # free Gemini test run
  python src/scoring.py --mode llm                       # full Gemini run (free tier)
  python src/scoring.py --mode llm --provider claude     # Claude (paid key)

Output: output/scored_investors.csv
"""

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

# v2 weights (v1 was 40/25/20/15): disagreement analysis against the human
# shortlist showed thesis alignment predicts a human "yes" more strongly, and
# geography less strongly, than first assumed - thesis 40->45%, geo 15->10%.
WEIGHTS = {"thesis_fit": 0.45, "stage_fit": 0.25, "ticket_fit": 0.20, "geo_fit": 0.10}


def load_inputs():
    investors = pd.read_csv(DATA / "investors.csv")
    with (DATA / "startup_profile.json").open(encoding="utf-8") as f:
        startup = json.load(f)
    return investors, startup


# --------------------------------------------------------------- demo scorer
def demo_score_row(row: pd.Series, startup: dict) -> dict:
    """Deterministic rubric scoring - mirrors how an analyst would screen manually."""
    # 1. Thesis fit: overlap between investor sectors/thesis text and startup keywords.
    # v2 rubric: disagreement analysis vs the human shortlist showed the analyst also
    # rewards clinical-operations language (hospital pilots, regulatory readiness),
    # not just sector-name matches - so those signals now count toward thesis fit.
    inv_text = f"{row['sectors']} {row['thesis']}".lower()
    keywords = [k.lower() for k in startup["sector_keywords"]]
    hits = sum(1 for k in keywords if k in inv_text)
    partial = sum(1 for k in ["health", "medical", "clinical", "diagnos", "radiolog",
                              "hospital", "regulatory", "mdr", "reimburse"]
                  if k in inv_text)
    thesis = min(100, hits * 26 + partial * 9)

    # 2. Stage fit
    stages = [s.strip() for s in str(row["stage_focus"]).split(";")]
    if startup["stage"] in stages:
        stage = 100
    elif any(s in stages for s in ["Pre-Seed", "Series A"]):  # adjacent stages
        stage = 55
    else:
        stage = 10

    # 3. Ticket fit: overlap of investor ticket range with target sweet spot
    lo, hi = startup["ticket_sweet_spot_eur"]
    t_lo, t_hi = float(row["ticket_min_eur"]), float(row["ticket_max_eur"])
    overlap = max(0.0, min(hi, t_hi) - max(lo, t_lo))
    span = hi - lo
    ticket = round(min(1.0, overlap / span) * 100) if overlap > 0 else (
        30 if t_lo <= hi * 2 else 5)  # slightly-oversized tickets still partly useful

    # 4. Geography fit
    prio = startup["geography_priority"]
    geo_map = {prio[0]: 100, prio[1]: 65, prio[2]: 35}
    geo = geo_map.get(row["geography_focus"], 20)

    return {"thesis_fit": thesis, "stage_fit": stage, "ticket_fit": ticket, "geo_fit": geo,
            "rationale": "Rubric-based demo scoring (offline mode)."}


# ---------------------------------------------------------------- llm scorer
LLM_SYSTEM = """You are an investment analyst screening investors for a startup fundraise.
Score the investor against the startup on four dimensions, each 0-100:
- thesis_fit: sector and thesis alignment with the startup
- stage_fit: does the investor invest at the startup's current stage?
- ticket_fit: does the investor's typical ticket range fit the target check size?
- geo_fit: geography match against the startup's priority list
Base your scores ONLY on the investor data provided - do not assume facts not present.
Respond with strict JSON: {"thesis_fit": int, "stage_fit": int, "ticket_fit": int,
"geo_fit": int, "rationale": "<one sentence>"}"""


def investor_blob(row: pd.Series) -> str:
    return row[["name", "type", "hq_country", "geography_focus", "stage_focus",
                "ticket_min_eur", "ticket_max_eur", "sectors", "thesis",
                "portfolio_examples"]].to_json()


def claude_score_row(client, model: str, row: pd.Series, startup: dict) -> dict:
    msg = client.messages.create(
        model=model,
        max_tokens=300,
        system=LLM_SYSTEM,
        messages=[{"role": "user", "content":
                   f"STARTUP:\n{json.dumps(startup)}\n\nINVESTOR:\n{investor_blob(row)}"}],
    )
    text = msg.content[0].text.strip()
    start, end = text.find("{"), text.rfind("}") + 1
    return json.loads(text[start:end])


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def gemini_score_row(model: str, row: pd.Series, startup: dict) -> dict:
    """Free-tier Gemini call. Forces JSON output; retries once on rate limit (429)."""
    import requests
    prompt = (f"{LLM_SYSTEM}\n\nSTARTUP:\n{json.dumps(startup)}\n\n"
              f"INVESTOR:\n{investor_blob(row)}")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}}
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
               "Content-Type": "application/json"}
    for attempt in range(3):
        resp = requests.post(GEMINI_URL.format(model=model), json=body,
                             headers=headers, timeout=60)
        if resp.status_code == 429:  # free-tier rate limit: wait and retry
            time.sleep(25)
            continue
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text[text.find("{"):text.rfind("}") + 1])
    raise RuntimeError("Gemini rate limit: 3 attempts failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["demo", "llm"], default="demo")
    parser.add_argument("--provider", choices=["gemini", "claude"], default="gemini",
                        help="LLM provider for --mode llm (gemini has a free tier)")
    parser.add_argument("--model", default=None,
                        help="Override model id (defaults: gemini-2.0-flash / claude-haiku-4-5-20251001)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Score only the first N investors (useful to test llm mode)")
    args = parser.parse_args()

    investors, startup = load_inputs()
    if args.limit:
        investors = investors.head(args.limit)

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

    records = []
    for i, (_, row) in enumerate(investors.iterrows(), 1):
        if args.mode == "llm":
            try:
                if args.provider == "claude":
                    scores = claude_score_row(client, model, row, startup)
                else:
                    scores = gemini_score_row(model, row, startup)
                    time.sleep(4)  # stay under Gemini free-tier rate limit (15 req/min)
            except Exception as e:  # keep the batch alive on one bad response
                print(f"  ! {row['name']}: {e} - falling back to rubric")
                scores = demo_score_row(row, startup)
        else:
            scores = demo_score_row(row, startup)

        total = round(sum(scores[k] * w for k, w in WEIGHTS.items()), 1)
        records.append({**row.to_dict(),
                        **{k: scores[k] for k in WEIGHTS},
                        "rationale": scores.get("rationale", ""),
                        "total_score": total})
        step = 25 if args.mode == "llm" else 100
        if i % step == 0:
            print(f"  scored {i}/{len(investors)}")

    df = pd.DataFrame(records).sort_values("total_score", ascending=False)
    df["rank"] = range(1, len(df) + 1)
    OUTPUT.mkdir(exist_ok=True)
    out = OUTPUT / "scored_investors.csv"
    df.to_csv(out, index=False)
    print(f"\nWrote {len(df)} scored investors to {out} (mode={args.mode})")
    print("\nTop 10:")
    print(df.head(10)[["rank", "name", "type", "hq_country", "total_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
