"""
Export the evaluation numbers the public site quotes into site/proof.js.

The site (site/index.html) is a static page: it reads site/investors.js (the verified
investor database) and site/proof.js (this file's output), so it loads instantly from
any static host and never "sleeps" like a free Streamlit Cloud app.

Deterministic (no timestamps) so CI can check the committed file is up to date.

Usage:  python src/export_site.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
SITE = ROOT / "site"


def main() -> None:
    ev = json.loads((OUTPUT / "evaluation_report.json").read_text(encoding="utf-8"))
    tu = json.loads((OUTPUT / "tuning_report.json").read_text(encoding="utf-8"))
    proof = {
        "n_test_profiles": ev["n_investors_scored"],
        "held_out": tu["held_out"]["tuned_on_A_scored_on_B"]["mean"],
        "held_out_std": tu["held_out"]["tuned_on_A_scored_on_B"]["std"],
        "n_splits": tu["held_out"]["n_splits"],
        "noise_ceiling": tu["noise_ceiling"]["analyst_rerun_vs_shortlist"]["mean"],
        "in_sample_best": tu["in_sample"]["best_grid_precision_at_40"],
        "optimism_gap": tu["held_out"]["optimism_gap"],
        "roc_auc": ev["roc_auc"],
    }
    SITE.mkdir(exist_ok=True)
    out = SITE / "proof.js"
    out.write_text("window.PROOF = " + json.dumps(proof) + ";\n", encoding="utf-8", newline="\n")
    print(f"Wrote evaluation summary to {out}")


if __name__ == "__main__":
    main()
