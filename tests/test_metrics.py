import math

import pandas as pd

from evaluate import evaluate
from metrics import precision_at_k, recall_at_k, roc_auc, spearman, wilson_interval


def test_precision_and_recall():
    ranked = ["a", "b", "c", "d"]
    assert precision_at_k(ranked, {"a", "d"}, 2) == 0.5
    assert recall_at_k(ranked, {"a", "d"}, 2) == 0.5
    assert recall_at_k(ranked, {"a", "d"}, 4) == 1.0


def test_auc_perfect_reversed_and_ties():
    labels = [True, True, False, False]
    assert roc_auc([4, 3, 2, 1], labels) == 1.0
    assert roc_auc([1, 2, 3, 4], labels) == 0.0
    assert roc_auc([1, 1, 1, 1], labels) == 0.5
    assert math.isnan(roc_auc([1, 2], [True, True]))


def test_wilson_interval_contains_estimate():
    lo, hi = wilson_interval(29, 40)
    assert lo < 29 / 40 < hi
    assert 0.55 < lo < 0.60 and 0.83 < hi < 0.86


def test_spearman():
    assert spearman([1, 2, 3], [10, 20, 30]) == 1.0
    assert spearman([1, 2, 3], [30, 20, 10]) == -1.0


def test_evaluate_counts_overlap():
    scored = pd.DataFrame({"investor_id": [f"I{i}" for i in range(100)],
                           "total_score": list(range(100, 0, -1)),
                           "rank": range(1, 101)})
    manual = pd.DataFrame({"investor_id": [f"I{i}" for i in range(20, 60)],
                           "name": [f"N{i}" for i in range(20, 60)]})
    r = evaluate(scored, manual)
    assert r["model_top40_vs_human_top40_overlap"] == 20
    assert r["recall_at_80"] == 1.0
    assert r["human_picks_missed_by_model_top80"] == []
