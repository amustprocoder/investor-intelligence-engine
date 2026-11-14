"""
Rubric tuning with an honest held-out estimate.

The trap this script avoids: if you sweep rubric parameters on the shortlist and then
report precision on that same shortlist, the number is optimistic - the sweep has
partly fitted the analyst's noise. So:

  1. In-sample sweep (the old method, kept for contrast): best precision@40 on all 520.
  2. Held-out: 25 repeated stratified 50/50 splits. Tune on half A (precision@k,
     k = analyst picks in A), score the winner on the untouched half B.
     The gap between A and B is the overfitting the in-sample number hides.
  3. Noise ceiling: re-run the simulated analyst with fresh gut-feel noise.
     If the analyst only agrees with themselves X% of the time, no model can be
     expected to beat ~X% - chasing more would mean fitting noise.

Usage:  python src/tune_rubric.py
Writes: output/tuning_report.json
"""

import itertools
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from make_shortlist import analyst_base, build_shortlist
from scoring import V1, V2, RubricParams, load_inputs, rubric_features

ROOT = Path(__file__).resolve().parent.parent
N_SPLITS = 25
SPLIT_SEED = 2026
RERUN_SEEDS = range(100, 150)

WEIGHT_SETS = [(wt, ws, wk, wg)
               for wt, ws, wk, wg in itertools.product([0.40, 0.45, 0.50], [0.25, 0.20],
                                                       [0.20, 0.15], [0.15, 0.10])
               if abs(wt + ws + wk + wg - 1.0) < 1e-9]
GRID = [RubricParams(hw, pw, adj, g2, g3, *w)
        for hw, pw, adj, g2, g3, w in itertools.product(
            [18, 20, 22, 26],   # thesis: points per exact sector-keyword hit
            [0, 7, 9, 11],      # thesis: points per clinical-ops term (0 = v1 behaviour)
            [30, 40, 55],       # stage: credit for adjacent-stage investors
            [55, 60, 65],       # geo: 2nd priority (Europe)
            [25, 30, 35],       # geo: 3rd priority (Global)
            WEIGHT_SETS)]


def score_matrix(feats: pd.DataFrame, configs: list) -> np.ndarray:
    """Total score of every investor under every config: shape (configs, investors)."""
    hits, partial = feats["hits"].to_numpy(float), feats["partial"].to_numpy(float)
    exact, adj = feats["stage_exact"].to_numpy(bool), feats["stage_adjacent"].to_numpy(bool)
    ticket, geo_rank = feats["ticket"].to_numpy(float), feats["geo_rank"].to_numpy(int)
    out = np.empty((len(configs), len(feats)))
    for i, p in enumerate(configs):
        thesis = np.minimum(100, hits * p.hit_w + partial * p.partial_w)
        stage = np.where(exact, 100, np.where(adj, p.adjacent_stage, 10))
        geo = np.select([geo_rank == 0, geo_rank == 1, geo_rank == 2],
                        [100, p.geo_second, p.geo_third], 20)
        out[i] = np.round(thesis * p.w_thesis + stage * p.w_stage
                          + ticket * p.w_ticket + geo * p.w_geo, 1)
    return out


def hits_at_k(scores: np.ndarray, labels: np.ndarray, k: int) -> np.ndarray:
    """Analyst picks inside each config's top-k (stable order -> ties broken by investor order)."""
    order = np.argsort(-scores, axis=1, kind="stable")[:, :k]
    return labels[order].sum(axis=1)


def best_config(scores: np.ndarray, labels: np.ndarray, k: int) -> int:
    """Max precision@k; ties broken by picks in top-2k (prefers near-misses over far misses)."""
    key = hits_at_k(scores, labels, k) * 1000 + hits_at_k(scores, labels, 2 * k)
    return int(np.argmax(key))


def stratified_halves(labels: np.ndarray, rng: np.random.Generator) -> tuple:
    pos, neg = np.flatnonzero(labels), np.flatnonzero(~labels)
    pos, neg = rng.permutation(pos), rng.permutation(neg)
    a = np.concatenate([pos[: len(pos) // 2], neg[: len(neg) // 2]])
    b = np.concatenate([pos[len(pos) // 2:], neg[len(neg) // 2:]])
    return np.sort(a), np.sort(b)


def summary(values) -> dict:
    v = np.asarray(values, float)
    return {"mean": round(float(v.mean()), 3), "std": round(float(v.std()), 3),
            "min": round(float(v.min()), 3), "max": round(float(v.max()), 3)}


def main() -> None:
    investors, startup = load_inputs()
    shortlist = pd.read_csv(ROOT / "data" / "manual_shortlist.csv")
    picks = set(shortlist["investor_id"])
    labels = investors["investor_id"].isin(picks).to_numpy()
    feats = rubric_features(investors, startup)

    configs = GRID + [V1, V2]
    S = score_matrix(feats, configs)
    i_v1, i_v2 = len(GRID), len(GRID) + 1
    k_full = int(labels.sum())

    # 1. in-sample (old method)
    full_hits = hits_at_k(S, labels, k_full)
    i_best = best_config(S[:len(GRID)], labels, k_full)
    in_sample = {
        "v1_precision_at_40": round(full_hits[i_v1] / k_full, 3),
        "v2_precision_at_40": round(full_hits[i_v2] / k_full, 3),
        "best_grid_precision_at_40": round(full_hits[i_best] / k_full, 3),
        "best_grid_params": asdict(GRID[i_best]),
    }

    # 2. held-out
    rng = np.random.default_rng(SPLIT_SEED)
    tuned_train, tuned_test, v1_test, v2_test, chosen = [], [], [], [], []
    for _ in range(N_SPLITS):
        a, b = stratified_halves(labels, rng)
        ka, kb = int(labels[a].sum()), int(labels[b].sum())
        j = best_config(S[:len(GRID), a], labels[a], ka)
        tuned_train.append(hits_at_k(S[[j]][:, a], labels[a], ka)[0] / ka)
        test_hits = hits_at_k(S[[j, i_v1, i_v2]][:, b], labels[b], kb) / kb
        tuned_test.append(test_hits[0])
        v1_test.append(test_hits[1])
        v2_test.append(test_hits[2])
        chosen.append(GRID[j])
    weight_freq = pd.Series([f"{p.w_thesis:.2f}/{p.w_stage:.2f}/{p.w_ticket:.2f}/{p.w_geo:.2f}"
                             for p in chosen]).value_counts()
    held_out = {
        "n_splits": N_SPLITS,
        "k_per_half": k_full // 2,
        "tuned_on_A_scored_on_A": summary(tuned_train),
        "tuned_on_A_scored_on_B": summary(tuned_test),
        "v1_hand_set_on_B": summary(v1_test),
        "v2_fixed_on_B_optimistic": summary(v2_test),
        "optimism_gap": round(float(np.mean(tuned_train) - np.mean(tuned_test)), 3),
        "clinical_ops_terms_chosen_in": f"{sum(p.partial_w > 0 for p in chosen)}/{N_SPLITS} splits",
        "weights_chosen_thesis_stage_ticket_geo": weight_freq.to_dict(),
    }

    # 3. noise ceiling
    base = investors.apply(analyst_base, axis=1)
    noise_free_top = set(investors.loc[base.sort_values(ascending=False, kind="stable")
                                       .index[:k_full], "investor_id"])
    reruns = [len(set(build_shortlist(investors, seed=s)["investor_id"]) & picks) / k_full
              for s in RERUN_SEEDS]
    ceiling = {
        "analyst_noise_free_vs_shortlist": round(len(noise_free_top & picks) / k_full, 3),
        "analyst_rerun_vs_shortlist": summary(reruns),
    }

    report = {"in_sample": in_sample, "held_out": held_out, "noise_ceiling": ceiling,
              "grid_size": len(GRID)}
    out = ROOT / "output" / "tuning_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    ho = held_out
    print(f"Swept {len(GRID)} rubric configurations.\n")
    print("1) In-sample (tune and score on the same 40 picks - optimistic)")
    print(f"   v1 {in_sample['v1_precision_at_40']:.0%} | v2 {in_sample['v2_precision_at_40']:.0%}"
          f" | best of grid {in_sample['best_grid_precision_at_40']:.0%}")
    print(f"\n2) Held-out ({N_SPLITS} stratified 50/50 splits, precision@{k_full // 2} per half)")
    print(f"   tuned, scored on its own half A:  {ho['tuned_on_A_scored_on_A']['mean']:.0%}")
    print(f"   tuned, scored on unseen half B:   {ho['tuned_on_A_scored_on_B']['mean']:.0%}"
          f"  (+/- {ho['tuned_on_A_scored_on_B']['std']:.0%})   <- the honest number")
    print(f"   v1 hand-set weights on half B:    {ho['v1_hand_set_on_B']['mean']:.0%}")
    print(f"   optimism gap (A - B):             {ho['optimism_gap']:+.0%}")
    print(f"   clinical-ops terms chosen in {ho['clinical_ops_terms_chosen_in']}")
    print(f"\n3) Noise ceiling - same analyst, fresh gut-feel noise, vs the shortlist:")
    print(f"   {ceiling['analyst_rerun_vs_shortlist']['mean']:.0%} agreement on average "
          f"(range {ceiling['analyst_rerun_vs_shortlist']['min']:.0%}-"
          f"{ceiling['analyst_rerun_vs_shortlist']['max']:.0%}); "
          f"noise-free analyst: {ceiling['analyst_noise_free_vs_shortlist']:.0%}")
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()
