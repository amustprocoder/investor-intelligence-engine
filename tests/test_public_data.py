"""Guards on the public investor database shipped with the site."""

import re

import pandas as pd

from conftest import ROOT

GENERIC = re.compile(r"^(info|office|hello|contact|dealflow|deals|post|mail|invest|investments|"
                     r"pitch|team|businessplans|board|kontakt|welcome|ventures|startups|apply|"
                     r"submissions|bp)@", re.I)


def load():
    return pd.read_csv(ROOT / "data" / "european_health_investors.csv").fillna("")


def test_only_generic_firm_inboxes():
    emails = [e for e in load()["email"] if e]
    assert emails and all(GENERIC.match(e) for e in emails)


def test_every_firm_has_a_website_and_known_type():
    df = load()
    assert df["website"].str.startswith("http").all()
    assert set(df["type"]) <= {"VC", "Angel network", "Family office", "Corporate VC", "Public fund"}


def test_stages_and_tickets_are_sane():
    df = load()
    stages = {"Pre-seed", "Seed", "Series A", "Series B", "Growth"}
    assert all(set(s.split("; ")) <= stages for s in df["stages"])
    both = df[(df["ticket_min_eur"] != "") & (df["ticket_max_eur"] != "")]
    assert (both["ticket_min_eur"].astype(float) <= both["ticket_max_eur"].astype(float)).all()
