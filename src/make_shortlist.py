"""
Build the SIMULATED analyst shortlist (data/manual_shortlist.csv).

Honest framing: the real 40-investor pipeline from the live EUR 1.5M MedTech
fundraise is client-confidential and was built on a different (real) universe,
so it cannot be the ground truth for this synthetic dataset. Instead this
script simulates an analyst: a heuristic screen with its own emphasis
(healthcare sector names, DACH-first, Seed) plus random "judgment noise"
for gut feel and brand familiarity. Everything the repo reports as
"agreement with the analyst" is agreement with this simulated screen.

The noise term matters: re-running the same analyst with a different noise
seed gives a different shortlist, which caps how much agreement any model
can reach (see tune_rubric.py -> noise ceiling).

Run after generate_dataset.py:  python src/make_shortlist.py
"""

import random
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SHORTLIST_SEED = 7  # different seed than the dataset - independent "analyst" judgment
SHORTLIST_SIZE = 40
NOISE = 12          # +/- points of gut-feel noise per investor

HEALTH_TERMS = ["Medical Devices", "Digital Health", "HealthTech", "AI in Healthcare",
                "Diagnostics", "Radiology AI", "Clinical Software"]


def analyst_base(row: pd.Series) -> float:
    """The analyst's systematic preferences - similar rubric, different emphasis."""
    score = 0.0
    sectors = str(row["sectors"])
    thesis = str(row["thesis"]).lower()

    # Analysts overweight obvious sector matches...
    score += sum(12 for t in HEALTH_TERMS if t in sectors)
    if "hospital" in thesis or "clinical" in thesis or "regulatory" in thesis:
        score += 15

    # ...and geography, sometimes more than the model does
    score += {"DACH": 30, "Europe": 15, "Global": 0}.get(row["geography_focus"], 0)

    if "Seed" in str(row["stage_focus"]):
        score += 20

    # Ticket: humans eyeball it rather than compute overlap
    if row["ticket_min_eur"] <= 1_500_000 and row["ticket_max_eur"] >= 250_000:
        score += 10
    return score


def build_shortlist(investors: pd.DataFrame, seed: int = SHORTLIST_SEED,
                    size: int = SHORTLIST_SIZE) -> pd.DataFrame:
    """One analyst pass: systematic score + gut-feel noise, top `size` kept."""
    rng = random.Random(seed)
    scored = investors.copy()
    scored["analyst_score"] = [analyst_base(r) + rng.uniform(-NOISE, NOISE)
                               for _, r in investors.iterrows()]
    return scored.sort_values("analyst_score", ascending=False).head(size)


def main() -> None:
    investors = pd.read_csv(DATA / "investors.csv")
    shortlist = build_shortlist(investors)
    out = DATA / "manual_shortlist.csv"
    shortlist[["investor_id", "name", "type", "hq_country", "geography_focus",
               "stage_focus", "sectors"]].to_csv(out, index=False)
    print(f"Wrote {len(shortlist)}-investor simulated analyst shortlist to {out}")


if __name__ == "__main__":
    main()
