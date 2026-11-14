"""Guards on the committed data: the pipeline must stay reproducible."""

import pandas as pd

from conftest import ROOT
from make_shortlist import build_shortlist


def test_shortlist_is_reproducible():
    investors = pd.read_csv(ROOT / "data" / "investors.csv")
    committed = pd.read_csv(ROOT / "data" / "manual_shortlist.csv")
    assert list(build_shortlist(investors)["investor_id"]) == list(committed["investor_id"])


def test_dataset_shape():
    investors = pd.read_csv(ROOT / "data" / "investors.csv")
    assert len(investors) == 520
    assert investors["investor_id"].is_unique
    assert (investors["ticket_min_eur"] <= investors["ticket_max_eur"]).all()
