"""
Evaluation: compare the model's top-40 ranking against the human-built
40-investor manual shortlist (ground truth from the live fundraise).

Metrics:
  - Precision@40 / overlap: how many of the model's top-40 are in the human top-40
  - Recall@80: how many human picks appear in the model's top-80 (near-misses)
  - Mean model rank of human picks (lower = model agrees with the human)

Usage:  python src/evaluate.py
Reads:  output/scored_investors.csv, data/manual_shortlist.csv
Writes: output/evaluation_report.json
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    scored = pd.read_csv(ROOT / "output" / "scored_investors.csv")
    manual = pd.read_csv(ROOT / "data" / "manual_shortlist.csv")

    manual_ids = set(manual["investor_id"])
    top40_ids = set(scored.head(40)["investor_id"])
    top80_ids = set(scored.head(80)["investor_id"])

    overlap40 = manual_ids & top40_ids
    precision_at_40 = len(overlap40) / 40
    recall_at_80 = len(manual_ids & top80_ids) / len(manual_ids)

    ranks = scored.set_index("investor_id")["rank"]
    human_ranks = [int(ranks[i]) for i in manual_ids if i in ranks.index]
    mean_rank = sum(human_ranks) / len(human_ranks)

    missed = manual[~manual["investor_id"].isin(top80_ids)]

    report = {
        "model_top40_vs_human_top40_overlap": len(overlap40),
        "precision_at_40": round(precision_at_40, 3),
        "recall_at_80": round(recall_at_80, 3),
        "mean_model_rank_of_human_picks": round(mean_rank, 1),
        "human_picks_missed_by_model_top80": missed["name"].tolist(),
    }

    out = ROOT / "output" / "evaluation_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== Model vs. human shortlist ===")
    print(f"Top-40 overlap:            {len(overlap40)}/40  (precision@40 = {precision_at_40:.0%})")
    print(f"Recall@80:                 {recall_at_80:.0%} of human picks in model top-80")
    print(f"Mean model rank of picks:  {mean_rank:.1f}")
    if len(missed):
        print(f"\nHuman picks the model missed entirely (not in top-80): {len(missed)}")
        for n in missed["name"]:
            print(f"  - {n}")
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()
