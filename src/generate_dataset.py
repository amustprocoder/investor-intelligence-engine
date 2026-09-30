"""
Generate a realistic (synthetic) investor dataset for the Investor Intelligence Engine.

The dataset mirrors the shape of a real fundraise screening universe:
~500 VCs, angels, family offices and CVCs, weighted towards DACH/Europe,
with a healthcare/medtech-heavy subset — similar to a real MedTech raise universe.

All firm names are fictional. Run once:  python src/generate_dataset.py
Outputs: data/investors.csv
"""

import csv
import random
from pathlib import Path

random.seed(42)  # reproducible dataset

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------- name parts
PREFIXES = [
    "Alpen", "Nord", "Rhein", "Donau", "Tyrol", "Baltic", "Vienna", "Zurich",
    "Berlin", "Hansa", "Isar", "Elbe", "Mont", "Nova", "Astra", "Helix",
    "Vertex", "Quantum", "Signal", "Beacon", "Summit", "Granite", "Cobalt",
    "Aurora", "Polar", "Atlas", "Orion", "Lumen", "Vega", "Delta", "Femto",
    "Juno", "Kepler", "Linden", "Marble", "Oak", "Pinnacle", "Riverside",
    "Sterling", "Tessel", "Union", "Willow", "Zenith", "Argo", "Basil",
    "Cedar", "Drift", "Ember", "Falcon", "Garnet",
]
SUFFIXES_VC = ["Ventures", "Capital", "Partners", "Venture Partners", "VC", "Invest", "Growth"]
SUFFIXES_FO = ["Family Office", "Holding", "Beteiligungen", "Group", "Vermögensverwaltung"]
SUFFIXES_CVC = ["Corporate Ventures", "Strategic Ventures", "Innovation Fund"]

FIRST_NAMES = [
    "Lukas", "Anna", "Felix", "Sophie", "Maximilian", "Clara", "Jonas", "Lena",
    "Tobias", "Marie", "Sebastian", "Laura", "David", "Julia", "Florian",
    "Katharina", "Simon", "Nina", "Patrick", "Elena", "Marco", "Isabelle",
    "Andreas", "Petra", "Stefan", "Monika", "Erik", "Astrid", "Pieter", "Ingrid",
]
LAST_NAMES = [
    "Müller", "Schmidt", "Weber", "Wagner", "Becker", "Hoffmann", "Koch",
    "Bauer", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Braun",
    "Zimmermann", "Krüger", "Hartmann", "Lange", "Schmitt", "Werner",
    "Krause", "Meier", "Lehmann", "Huber", "Mayer", "Fuchs", "Weiss",
    "Jansen", "Visser", "Lindqvist", "Andersen", "Rossi", "Moreau", "Novak",
]

COUNTRIES = {
    "DACH": [("Germany", 0.55), ("Austria", 0.25), ("Switzerland", 0.20)],
    "Europe": [
        ("United Kingdom", 0.22), ("France", 0.16), ("Netherlands", 0.14),
        ("Sweden", 0.10), ("Denmark", 0.08), ("Spain", 0.08), ("Italy", 0.07),
        ("Finland", 0.06), ("Belgium", 0.05), ("Norway", 0.04),
    ],
    "Global": [("United States", 0.60), ("Israel", 0.15), ("Singapore", 0.10),
               ("Canada", 0.10), ("UAE", 0.05)],
}

SECTOR_POOLS = {
    "medtech": ["Medical Devices", "Digital Health", "HealthTech", "AI in Healthcare",
                "Diagnostics", "Radiology AI", "Clinical Software", "BioTech"],
    "generalist": ["B2B SaaS", "Enterprise Software", "AI/ML", "FinTech", "Deep Tech",
                   "Industrial Tech", "Consumer", "Climate Tech", "Cybersecurity",
                   "Logistics", "PropTech", "EdTech"],
}

STAGES = ["Pre-Seed", "Seed", "Series A", "Series B", "Growth"]

THESIS_TEMPLATES_HEALTH = [
    "Backs {stage_lo}-to-{stage_hi} companies transforming healthcare delivery in {region}, with a focus on {s1} and {s2}. Looks for clinical validation and regulatory awareness (MDR/CE).",
    "Invests in {s1} and {s2} startups at {stage_lo} stage across {region}. Thesis: software and AI will absorb routine clinical workflows; strong preference for founder-led commercial traction in hospitals.",
    "{region}-focused fund investing in {s1}, {s2} and adjacent life-science tooling from {stage_lo} to {stage_hi}. Values reimbursement strategy and health-system pilots over pure research.",
    "Specialist healthcare investor backing {s1} companies in {region}. Sweet spot {stage_lo}; frequently co-invests with strategic medtech corporates and follows on through {stage_hi}.",
]
THESIS_TEMPLATES_GEN = [
    "Generalist {stage_lo}-to-{stage_hi} investor in {region} with positions in {s1} and {s2}. Occasionally opportunistic in digital health when the model is software-first.",
    "Backs technical founders in {s1} and {s2} across {region}, {stage_lo} to {stage_hi}. Sector-agnostic within B2B; avoids capital-intensive hardware.",
    "{region} fund focused on {s1}, {s2} and data infrastructure at {stage_lo} stage. Thesis-driven around applied AI; healthcare exposure limited to a few portfolio bets.",
    "Invests {stage_lo}-{stage_hi} in {region} across {s1} and {s2}. Prefers rounds with a clear 18-month path to the next milestone.",
]

PORTFOLIO_HEALTH = [
    "ScanIQ", "MedFlow", "Radiant Dx", "CarePilot", "OrthoSense", "VitalGraph",
    "Klinix", "PathLens", "NeuroBeam", "PulseWare", "DermaCheck", "OncoView",
    "SurgIQ", "RehabLoop", "LabBridge", "TriageOS", "CardioLink", "MediNotes",
]
PORTFOLIO_GEN = [
    "Stackline", "PayNordic", "Fleetbase", "DataForge", "CloudMesh", "Quotable",
    "ShipRadar", "LedgerOne", "BuildOS", "TalentGrid", "SecureLoop", "AgriSense",
    "RetailPulse", "DocuSpeed", "EnergyKit", "MetricHub",
]


def pick_country(region: str) -> str:
    pool = COUNTRIES[region]
    r = random.random()
    acc = 0.0
    for country, w in pool:
        acc += w
        if r <= acc:
            return country
    return pool[-1][0]


def make_investor(idx: int, used_names: set) -> dict:
    inv_type = random.choices(
        ["VC", "Angel", "Family Office", "CVC"], weights=[0.55, 0.22, 0.15, 0.08]
    )[0]
    region = random.choices(["DACH", "Europe", "Global"], weights=[0.45, 0.40, 0.15])[0]
    is_health = random.random() < (0.45 if region == "DACH" else 0.35)

    # name
    while True:
        if inv_type == "Angel":
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        elif inv_type == "Family Office":
            name = f"{random.choice(PREFIXES)} {random.choice(SUFFIXES_FO)}"
        elif inv_type == "CVC":
            name = f"{random.choice(PREFIXES)}{random.choice(['Med', 'Tech', 'Health', 'Care', ''])} {random.choice(SUFFIXES_CVC)}"
        else:
            name = f"{random.choice(PREFIXES)} {random.choice(SUFFIXES_VC)}"
        if name not in used_names:
            used_names.add(name)
            break

    # stages: contiguous window
    lo = random.choices([0, 1, 2, 3], weights=[0.25, 0.40, 0.25, 0.10])[0]
    hi = min(lo + random.choice([0, 1, 1, 2]), len(STAGES) - 1)
    stage_focus = STAGES[lo:hi + 1]

    # ticket size (EUR)
    if inv_type == "Angel":
        tmin = random.choice([10, 25, 50]) * 1000
        tmax = tmin * random.choice([4, 6, 10])
    elif inv_type == "Family Office":
        tmin = random.choice([100, 250, 500]) * 1000
        tmax = tmin * random.choice([4, 6, 8])
    else:
        tmin = random.choice([250, 500, 1000, 2000]) * 1000
        tmax = tmin * random.choice([3, 5, 8])

    pool = SECTOR_POOLS["medtech"] if is_health else SECTOR_POOLS["generalist"]
    sectors = random.sample(pool, k=random.choice([2, 3]))
    if not is_health and random.random() < 0.15:
        sectors.append(random.choice(SECTOR_POOLS["medtech"]))

    templates = THESIS_TEMPLATES_HEALTH if is_health else THESIS_TEMPLATES_GEN
    thesis = random.choice(templates).format(
        stage_lo=stage_focus[0], stage_hi=stage_focus[-1], region=region,
        s1=sectors[0], s2=sectors[1] if len(sectors) > 1 else sectors[0],
    )

    port_pool = PORTFOLIO_HEALTH if is_health else PORTFOLIO_GEN
    portfolio = ", ".join(random.sample(port_pool, k=random.choice([2, 3])))

    country = pick_country(region)
    slug = name.lower().replace(" ", "").replace("ö", "oe").replace("ü", "ue").replace("ä", "ae").replace("ß", "ss")

    return {
        "investor_id": f"INV{idx:04d}",
        "name": name,
        "type": inv_type,
        "hq_country": country,
        "geography_focus": region,
        "stage_focus": "; ".join(stage_focus),
        "ticket_min_eur": tmin,
        "ticket_max_eur": tmax,
        "sectors": "; ".join(sectors),
        "thesis": thesis,
        "portfolio_examples": portfolio,
        "website": f"https://www.{slug[:24]}.example.com",
        "contact_email": f"contact@{slug[:24]}.example.com",
    }


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    used: set = set()
    rows = [make_investor(i + 1, used) for i in range(520)]
    out = DATA_DIR / "investors.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    health = sum(1 for r in rows if "Health" in r["sectors"] or "Medical" in r["sectors"]
                 or "Diagnostics" in r["sectors"] or "Radiology" in r["sectors"])
    print(f"Wrote {len(rows)} investors to {out}")
    print(f"Healthcare-relevant: {health} | DACH-focused: {sum(1 for r in rows if r['geography_focus'] == 'DACH')}")


if __name__ == "__main__":
    main()
