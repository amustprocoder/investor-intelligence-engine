"""
Ranking metrics shared by evaluate.py, tune_rubric.py and compare.py.

Kept dependency-free (pandas only) so the repo installs light on Streamlit Cloud.
"""

import math

import pandas as pd


def precision_at_k(ranked_ids, relevant: set, k: int) -> float:
    """Share of the top-k ranked ids that are in the relevant set."""
    return len(set(list(ranked_ids)[:k]) & relevant) / k


def recall_at_k(ranked_ids, relevant: set, k: int) -> float:
    """Share of the relevant set that appears in the top-k ranked ids."""
    return len(set(list(ranked_ids)[:k]) & relevant) / len(relevant)


def roc_auc(scores, labels) -> float:
    """Probability that a random positive outscores a random negative (ties = 0.5).

    Mann-Whitney U formulation with average ranks, so tied scores are handled
    correctly - the rubric produces many ties.
    """
    s = pd.Series(list(scores), dtype=float)
    y = pd.Series(list(labels), dtype=bool)
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = s.rank(method="average")
    return float((ranks[y].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple:
    """95% Wilson score interval for a proportion - honest error bars on small n."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def spearman(a, b) -> float:
    """Spearman rank correlation (Pearson on average ranks; no scipy needed)."""
    ra = pd.Series(list(a), dtype=float).rank()
    rb = pd.Series(list(b), dtype=float).rank()
    return float(ra.corr(rb))
