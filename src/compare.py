"""
LLM vs rubric: how do the two scorers compare on the SAME investors?

Run after an LLM scoring run (e.g. `python src/scoring.py --mode llm --sample 60`).
Only rows the LLM actually scored (score_source == "llm") are compared - fallback
rows would make the two scorers look more alike than they are.

Reports:
  - Spearman rank agreement, overall and per dimension
  - ROC-AUC of each scorer at separating simulated-analyst picks from non-picks
    (same investors, same labels -> a fair head-to-head)
  - the biggest disagreements, with the LLM's one-line rationale

Usage:  python src/compare.py
Writes: output/llm_vs_rubric.json
"""

import json
from pathlib import Path

import pandas as pd

from metrics import roc_auc, spearman
from scoring import DIMENSIONS

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"


def compare(rubric: pd.DataFrame, llm: pd.DataFrame, picks: set) -> dict:
    llm = llm[llm["score_source"] == "llm"]
    cols = ["investor_id", "name", "total_score"] + DIMENSIONS
    m = llm[cols + ["rationale"]].merge(rubric[cols], on=["investor_id", "name"],
                                        suffixes=("_llm", "_rubric"))
    if len(m) < 5:
        raise SystemExit(f"Only {len(m)} LLM-scored investors - run more before comparing.")
    labels = m["investor_id"].isin(picks)
    m["rank_llm"] = m["total_score_llm"].rank(ascending=False, method="min")
    m["rank_rubric"] = m["total_score_rubric"].rank(ascending=False, method="min")
    m["rank_gap"] = m["rank_llm"] - m["rank_rubric"]
    gaps = m.reindex(m["rank_gap"].abs().sort_values(ascending=False).index).head(8)
    return {
        "n_compared": len(m),
        "n_analyst_picks": int(labels.sum()),
        "spearman_total": round(spearman(m["total_score_llm"], m["total_score_rubric"]), 3),
        "spearman_by_dimension": {d: round(spearman(m[f"{d}_llm"], m[f"{d}_rubric"]), 3)
                                  for d in DIMENSIONS},
        "mean_abs_diff_by_dimension": {d: round(float((m[f"{d}_llm"] - m[f"{d}_rubric"])
                                                      .abs().mean()), 1) for d in DIMENSIONS},
        "auc_vs_analyst": {"llm": round(roc_auc(m["total_score_llm"], labels), 3),
                           "rubric": round(roc_auc(m["total_score_rubric"], labels), 3)},
        "biggest_disagreements": [
            {"name": r["name"], "analyst_pick": r["investor_id"] in picks,
             "llm_score": float(r["total_score_llm"]),
             "rubric_score": float(r["total_score_rubric"]),
             "llm_rationale": r["rationale"]}
            for _, r in gaps.iterrows()],
    }


def main() -> None:
    llm_path = OUTPUT / "scored_investors_llm.csv"
    if not llm_path.exists():
        print("No LLM run yet - run `python src/scoring.py --mode llm --sample 60` first.")
        return
    rubric = pd.read_csv(OUTPUT / "scored_investors.csv")
    llm = pd.read_csv(llm_path)
    picks = set(pd.read_csv(ROOT / "data" / "manual_shortlist.csv")["investor_id"])
    report = compare(rubric, llm, picks)
    out = OUTPUT / "llm_vs_rubric.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"=== LLM vs rubric on {report['n_compared']} investors "
          f"({report['n_analyst_picks']} analyst picks) ===")
    print(f"Rank agreement (Spearman):  {report['spearman_total']:.2f}")
    for d, v in report["spearman_by_dimension"].items():
        print(f"   {d:<11} {v:>5.2f}   mean |diff| {report['mean_abs_diff_by_dimension'][d]:.0f} pts")
    auc = report["auc_vs_analyst"]
    print(f"AUC vs analyst picks:       LLM {auc['llm']:.3f} | rubric {auc['rubric']:.3f}")
    print("\nBiggest disagreements:")
    for g in report["biggest_disagreements"][:5]:
        tag = "pick" if g["analyst_pick"] else "    "
        print(f"  [{tag}] {g['name']:<28} LLM {g['llm_score']:5.1f} | rubric "
              f"{g['rubric_score']:5.1f}  - {g['llm_rationale'][:90]}")
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()
