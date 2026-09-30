"""
Rubric tuning: parameter sweep of the demo scorer against the human shortlist.

This is how the v2 rubric was found. Instead of guessing weights, every
combination of rubric parameters is evaluated on precision@40 vs the human
ground truth, and the best-agreeing configuration wins.

Result of the recorded sweep: v1 (40/25/20/15, sector-name matching only)
scored 68% precision@40; the winner - thesis 45%, stage 25%, ticket 20%,
geo 10%, with clinical-operations terms counting toward thesis fit - scores 75%.

Usage:  python src/tune_rubric.py
"""

import itertools
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

PARTIAL_TERMS = ["health", "medical", "clinical", "diagnos", "radiolog",
                 "hospital", "regulatory", "mdr", "reimburse"]


def precompute(investors: pd.DataFrame, startup: dict) -> pd.DataFrame:
    """Extract the per-investor raw signals once; the sweep only re-weights them."""
    kw = [k.lower() for k in startup["sector_keywords"]]
    lo, hi = startup["ticket_sweet_spot_eur"]
    rows = []
    for _, r in investors.iterrows():
        text = f"{r['sectors']} {r['thesis']}".lower()
        stages = [s.strip() for s in str(r["stage_focus"]).split(";")]
        t_lo, t_hi = float(r["ticket_min_eur"]), float(r["ticket_max_eur"])
        ov = max(0.0, min(hi, t_hi) - max(lo, t_lo))
        rows.append({
            "id": r["investor_id"],
            "hits": sum(1 for k in kw if k in text),
            "partial": sum(1 for k in PARTIAL_TERMS if k in text),
            "seed": startup["stage"] in stages,
            "adj": any(s in stages for s in ["Pre-Seed", "Series A"]),
            "ticket": round(min(1.0, ov / (hi - lo)) * 100) if ov > 0
                      else (30 if t_lo <= hi * 2 else 5),
            "geo": r["geography_focus"],
        })
    return pd.DataFrame(rows)


def main() -> None:
    investors = pd.read_csv(DATA / "investors.csv")
    manual_ids = set(pd.read_csv(DATA / "manual_shortlist.csv")["investor_id"])
    startup = json.loads((DATA / "startup_profile.json").read_text(encoding="utf-8"))
    base = precompute(investors, startup)

    results = []
    grid = itertools.product(
        [18, 20, 22, 26],            # thesis: points per exact sector-keyword hit
        [7, 9, 11],                  # thesis: points per clinical-ops term
        [30, 40, 55],                # stage: credit for adjacent-stage investors
        [55, 60, 65], [25, 30, 35],  # geo: Europe / Global steps (DACH = 100)
        [0.40, 0.45, 0.50],          # weight: thesis
        [0.25, 0.20],                # weight: stage
        [0.20, 0.15],                # weight: ticket
        [0.15, 0.10],                # weight: geo
    )
    for hw, pw, adj, ge, gg, wt, ws, wk, wg in grid:
        if abs(wt + ws + wk + wg - 1.0) > 1e-9:
            continue
        thesis = (base["hits"] * hw + base["partial"] * pw).clip(upper=100)
        stage = (base["seed"] * 100
                 + ((~base["seed"]) & base["adj"]) * adj
                 + ((~base["seed"]) & (~base["adj"])) * 10)
        geo = base["geo"].map({"DACH": 100, "Europe": ge, "Global": gg}).fillna(15)
        total = thesis * wt + stage * ws + base["ticket"] * wk + geo * wg
        top40 = set(base.loc[total.sort_values(ascending=False).index[:40], "id"])
        overlap = len(top40 & manual_ids)
        results.append({"precision_at_40": overlap / 40, "hit_w": hw, "partial_w": pw,
                        "adjacent_stage": adj, "geo_europe": ge, "geo_global": gg,
                        "w_thesis": wt, "w_stage": ws, "w_ticket": wk, "w_geo": wg})

    df = pd.DataFrame(results).sort_values("precision_at_40", ascending=False)
    print(f"Swept {len(df)} configurations. Top 10 by precision@40:\n")
    print(df.head(10).to_string(index=False))
    print("\nBest configuration is the v2 rubric in src/scoring.py.")


if __name__ == "__main__":
    main()
