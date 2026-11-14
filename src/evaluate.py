"""
Evaluation: compare a model ranking against the simulated analyst's
40-investor shortlist (data/manual_shortlist.csv - see make_shortlist.py).

Metrics:
  - Precision@40 (+ 95% Wilson interval): how many of the model's top-40 the analyst also picked
  - Recall@80: how many analyst picks appear in the model's top-80 (near-misses)
  - ROC-AUC: chance a random analyst pick outscores a random non-pick (threshold-free)
  - Mean model rank of analyst picks (lower = model agrees with the analyst)

Caveat printed with the numbers: the v2 rubric's parameters were chosen on this same
shortlist, so these are IN-SAMPLE numbers. The honest generalisation estimate is the
held-out result from tune_rubric.py (output/tuning_report.json).

Usage:  python src/evaluate.py
        python src/evaluate.py --scores output/scored_investors_llm.csv --out output/evaluation_report_llm.json
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from metrics import precision_at_k, recall_at_k, roc_auc, wilson_interval

ROOT = Path(__file__).resolve().parent.parent


def evaluate(scored: pd.DataFrame, manual: pd.DataFrame) -> dict:
    scored = scored.sort_values("rank")
    manual_ids = set(manual["investor_id"])
    ranked = list(scored["investor_id"])
    overlap = len(set(ranked[:40]) & manual_ids)
    lo, hi = wilson_interval(overlap, 40)
    labels = scored["investor_id"].isin(manual_ids)
    ranks = scored.set_index("investor_id")["rank"]
    human_ranks = [int(ranks[i]) for i in manual_ids if i in ranks.index]
    missed = manual[~manual["investor_id"].isin(ranked[:80])]
    return {
        "n_investors_scored": len(scored),
        "model_top40_vs_human_top40_overlap": overlap,
        "precision_at_40": round(precision_at_k(ranked, manual_ids, 40), 3),
        "precision_at_40_ci95": [round(lo, 3), round(hi, 3)],
        "recall_at_80": round(recall_at_k(ranked, manual_ids, 80), 3),
        "roc_auc": round(roc_auc(scored["total_score"], labels), 3),
        "mean_model_rank_of_human_picks": round(sum(human_ranks) / len(human_ranks), 1),
        "human_picks_missed_by_model_top80": missed["name"].tolist(),
        "in_sample": True,
        "note": "v2 parameters were tuned on this shortlist; see tuning_report.json "
                "for held-out numbers.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", default=str(ROOT / "output" / "scored_investors.csv"))
    parser.add_argument("--out", default=str(ROOT / "output" / "evaluation_report.json"))
    args = parser.parse_args()

    scored = pd.read_csv(args.scores)
    manual = pd.read_csv(ROOT / "data" / "manual_shortlist.csv")
    if len(scored) < 520:
        raise SystemExit(f"{args.scores} has only {len(scored)} investors - precision@40 "
                         "needs the full universe. For a partial LLM run use src/compare.py.")
    report = evaluate(scored, manual)

    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lo, hi = report["precision_at_40_ci95"]
    print("=== Model vs. simulated analyst shortlist (IN-SAMPLE) ===")
    print(f"Top-40 overlap:            {report['model_top40_vs_human_top40_overlap']}/40  "
          f"(precision@40 = {report['precision_at_40']:.0%}, 95% CI {lo:.0%}-{hi:.0%})")
    print(f"Recall@80:                 {report['recall_at_80']:.0%} of analyst picks in model top-80")
    print(f"ROC-AUC:                   {report['roc_auc']:.3f}")
    print(f"Mean model rank of picks:  {report['mean_model_rank_of_human_picks']:.1f}")
    missed = report["human_picks_missed_by_model_top80"]
    if missed:
        print(f"\nAnalyst picks the model missed entirely (not in top-80): {len(missed)}")
        for n in missed:
            print(f"  - {n}")
    print("\nNote: in-sample. Held-out estimate -> python src/tune_rubric.py")
    print(f"Report written to {out}")


if __name__ == "__main__":
    main()
