import numpy as np
import pandas as pd

from scoring import (V1, V2, rank_frame, rubric_dimensions, rubric_features,
                     weighted_total)
from tune_rubric import score_matrix


def dims(frame, startup, params=V2, **row):
    return rubric_dimensions(rubric_features(frame(row), startup), params).iloc[0]


def test_weights_sum_to_one():
    for p in (V1, V2):
        assert abs(sum(p.weights.values()) - 1.0) < 1e-9


def test_perfect_match_scores_100(frame, startup):
    d = dims(frame, startup, thesis="clinical radiology hospital diagnostics, regulatory")
    assert d.to_dict() == {"thesis_fit": 100, "stage_fit": 100, "ticket_fit": 100, "geo_fit": 100}


def test_stage_exact_adjacent_and_miss(frame, startup):
    assert dims(frame, startup, stage_focus="Seed; Series A")["stage_fit"] == 100
    assert dims(frame, startup, stage_focus="Series A")["stage_fit"] == V2.adjacent_stage
    assert dims(frame, startup, stage_focus="Growth")["stage_fit"] == 10


def test_ticket_overlap_and_out_of_range(frame, startup):
    # half of the 250K-1.5M sweet spot overlaps
    assert dims(frame, startup, ticket_min_eur=875000, ticket_max_eur=5000000)["ticket_fit"] == 50
    # tiny angel cheques: no overlap, but below 2x the top of range -> partly useful
    assert dims(frame, startup, ticket_min_eur=10000, ticket_max_eur=40000)["ticket_fit"] == 30
    # far too big
    assert dims(frame, startup, ticket_min_eur=5000000, ticket_max_eur=20000000)["ticket_fit"] == 5


def test_geo_follows_priority_list(frame, startup):
    assert dims(frame, startup, geography_focus="Europe")["geo_fit"] == V2.geo_second
    assert dims(frame, startup, geography_focus="Global")["geo_fit"] == V2.geo_third
    assert dims(frame, startup, geography_focus="Mars")["geo_fit"] == 20


def test_v1_ignores_clinical_ops_language(frame, startup):
    row = dict(sectors="B2B SaaS", thesis="hospital clinical regulatory")
    assert dims(frame, startup, V1, **row)["thesis_fit"] == 0
    assert dims(frame, startup, V2, **row)["thesis_fit"] > 0


def test_tuning_matrix_matches_scoring_engine(frame, startup):
    df = frame({}, {"investor_id": "INV0002", "geography_focus": "Global",
                    "stage_focus": "Series B", "sectors": "FinTech", "thesis": "payments"})
    feats = rubric_features(df, startup)
    for p in (V1, V2):
        expected = weighted_total(rubric_dimensions(feats, p), p.weights).to_numpy()
        assert np.allclose(score_matrix(feats, [p])[0], expected)


def test_rank_is_stable_on_ties():
    df = pd.DataFrame({"investor_id": ["A", "B", "C"], "total_score": [50.0, 70.0, 50.0]})
    assert list(rank_frame(df)["investor_id"]) == ["B", "A", "C"]
