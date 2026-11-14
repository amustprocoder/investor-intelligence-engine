import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

STARTUP = {
    "sector_keywords": ["Medical Devices", "Radiology AI"],
    "stage": "Seed",
    "ticket_sweet_spot_eur": [250000, 1500000],
    "geography_priority": ["DACH", "Europe", "Global"],
}


def investor(**kw) -> dict:
    base = {"investor_id": "INV0001", "name": "Test Ventures", "type": "VC",
            "hq_country": "Austria", "geography_focus": "DACH", "stage_focus": "Seed",
            "ticket_min_eur": 250000, "ticket_max_eur": 1500000,
            "sectors": "Radiology AI; Medical Devices", "thesis": "Backs hospital software.",
            "portfolio_examples": "ScanIQ, MedFlow", "contact_email": "a@b.example.com"}
    return {**base, **kw}


@pytest.fixture
def startup() -> dict:
    return dict(STARTUP)


@pytest.fixture
def frame():
    def make(*rows) -> pd.DataFrame:
        return pd.DataFrame([investor(**r) for r in rows])
    return make
