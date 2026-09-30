"""
Build the "manual shortlist" ground-truth file (data/manual_shortlist.csv).

In the real project this file came from a human analyst's 40-investor pipeline
built during a live EUR 1.5M MedTech fundraise. For the public repo we recreate
an equivalent: an analyst-style heuristic pass (healthcare thesis + right stage
+ DACH-first) with a bit of human judgment noise, applied to the same universe.

Run after generate_dataset.py:  python src/make_shortlist.py
"""

import random
from pathlib import Path

import pandas as pd

random.seed(7)  # different seed than the dataset - independent "human" judgment

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

HEALTH_TERMS = ["Medical Devices", "Digital Health", "HealthTech", "AI in Healthcare",
                "Diagnostics", "Radiology AI", "Clinical Software"]


def analyst_pass(row: pd.Series) -> float:
    """How a human analyst 'feels' about a target - similar rubric, different emphasis."""
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

    # Human judgment noise: pattern-matching, brand familiarity, gut feel
    score += random.uniform(-12, 12)
    return score


def main() -> None:
    investors = pd.read_csv(DATA / "investors.csv")
    investors["analyst_score"] = investors.apply(analyst_pass, axis=1)
    shortlist = investors.sort_values("analyst_score", ascending=False).head(40)
    out = DATA / "manual_shortlist.csv"
    shortlist[["investor_id", "name", "type", "hq_country", "geography_focus",
               "stage_focus", "sectors"]].to_csv(out, index=False)
    print(f"Wrote 40-investor manual shortlist to {out}")


if __name__ == "__main__":
    main()
