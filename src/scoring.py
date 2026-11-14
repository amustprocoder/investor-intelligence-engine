"""
Scoring engine: ranks every investor against the startup profile.

Two modes:
  - rubric (default): deterministic rubric scoring, runs offline with no API key.
    Writes output/scored_investors.csv (the full 520-investor pipeline).
  - llm: sends each investor profile + the startup profile to an LLM and asks for
    structured JSON scores on the same 4-dimension rubric. Writes a SEPARATE file,
    output/scored_investors_llm.csv, so a partial LLM run never overwrites the
    full rubric pipeline. Every row records score_source = llm | rubric_fallback.
    Providers: --provider gemini (FREE key from https://aistudio.google.com, set
    GEMINI_API_KEY) or --provider claude (set ANTHROPIC_API_KEY).

Rubric (weighted 0-100 total), v2 weights:
  thesis_fit  45%  - sector/thesis overlap with the startup
  stage_fit   25%  - does the investor invest at the startup's stage?
  ticket_fit  20%  - does the investor's ticket range overlap the target range?
  geo_fit     10%  - geography priority match (DACH > Europe > Global)

Usage:
  python src/scoring.py                                  # rubric mode (offline)
  python src/scoring.py --mode llm --sample 60           # free Gemini: 30 analyst picks + 30 others
  python src/scoring.py --mode llm                       # all 520 (needs several free-tier days;
                                                         #   re-run the same command to resume)
  python src/scoring.py --mode llm --provider claude     # Claude (paid key)

Output: output/scored_investors.csv (rubric) or output/scored_investors_llm.csv (llm)
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

DIMENSIONS = ["thesis_fit", "stage_fit", "ticket_fit", "geo_fit"]
CLINICAL_OPS_TERMS = ["health", "medical", "clinical", "diagnos", "radiolog",
                      "hospital", "regulatory", "mdr", "reimburse"]


@dataclass(frozen=True)
class RubricParams:
    hit_w: float = 26           # thesis points per exact sector-keyword hit
    partial_w: float = 9        # thesis points per clinical-operations term
    adjacent_stage: float = 55  # stage credit when only an adjacent stage matches
    geo_second: float = 65      # 2nd geography priority (DACH = 100)
    geo_third: float = 35       # 3rd geography priority
    w_thesis: float = 0.45
    w_stage: float = 0.25
    w_ticket: float = 0.20
    w_geo: float = 0.10

    @property
    def weights(self) -> dict:
        return dict(zip(DIMENSIONS, [self.w_thesis, self.w_stage, self.w_ticket, self.w_geo]))


# v1: hand-set weights, sector-name matching only.
# v2: clinical-operations language counts toward thesis fit; thesis 40->45%, geo 15->10%.
V1 = RubricParams(partial_w=0, w_thesis=0.40, w_geo=0.15)
V2 = RubricParams()
WEIGHTS = V2.weights


def load_inputs():
    investors = pd.read_csv(DATA / "investors.csv")
    with (DATA / "startup_profile.json").open(encoding="utf-8") as f:
        startup = json.load(f)
    return investors, startup


# ------------------------------------------------------------- rubric scorer
def rubric_features(investors: pd.DataFrame, startup: dict) -> pd.DataFrame:
    """Raw per-investor signals. Extracted once; params only re-weight them."""
    keywords = [k.lower() for k in startup["sector_keywords"]]
    lo, hi = startup["ticket_sweet_spot_eur"]
    prio = startup["geography_priority"]
    rows = []
    for _, r in investors.iterrows():
        text = f"{r['sectors']} {r['thesis']}".lower()
        stages = [s.strip() for s in str(r["stage_focus"]).split(";")]
        t_lo, t_hi = float(r["ticket_min_eur"]), float(r["ticket_max_eur"])
        overlap = max(0.0, min(hi, t_hi) - max(lo, t_lo))
        rows.append({
            "hits": sum(1 for k in keywords if k in text),
            "partial": sum(1 for k in CLINICAL_OPS_TERMS if k in text),
            "stage_exact": startup["stage"] in stages,
            "stage_adjacent": any(s in stages for s in ["Pre-Seed", "Series A"]),
            # slightly-oversized tickets are still partly useful
            "ticket": round(min(1.0, overlap / (hi - lo)) * 100) if overlap > 0
                      else (30 if t_lo <= hi * 2 else 5),
            "geo_rank": prio.index(r["geography_focus"]) if r["geography_focus"] in prio else -1,
        })
    return pd.DataFrame(rows, index=investors.index)


def rubric_dimensions(features: pd.DataFrame, p: RubricParams = V2) -> pd.DataFrame:
    thesis = (features["hits"] * p.hit_w + features["partial"] * p.partial_w).clip(upper=100)
    stage = pd.Series(np.where(features["stage_exact"], 100.0,
                               np.where(features["stage_adjacent"], p.adjacent_stage, 10.0)),
                      index=features.index)
    geo = features["geo_rank"].map({0: 100.0, 1: p.geo_second, 2: p.geo_third}).fillna(20.0)
    return pd.DataFrame({"thesis_fit": thesis, "stage_fit": stage,
                         "ticket_fit": features["ticket"].astype(float), "geo_fit": geo})


def weighted_total(dims: pd.DataFrame, weights: dict = WEIGHTS) -> pd.Series:
    return sum(dims[k] * w for k, w in weights.items()).round(1)


def rank_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by total score; stable sort so ties keep investor order (reproducible ranks)."""
    df = df.sort_values("total_score", ascending=False, kind="mergesort")
    df["rank"] = range(1, len(df) + 1)
    return df


# ---------------------------------------------------------------- llm scorer
LLM_SYSTEM = """You are an investment analyst screening investors for a startup fundraise.
Score the investor against the startup on four dimensions, each an integer 0-100:
- thesis_fit: sector and thesis alignment with the startup
- stage_fit: does the investor invest at the startup's current stage?
- ticket_fit: does the investor's typical ticket range fit the target check size?
- geo_fit: geography match against the startup's priority list
Anchors: 100 = clear match, 50 = partial or adjacent match, 0 = clear mismatch.
Base your scores ONLY on the investor data provided - do not assume facts not present.
Respond with strict JSON: {"thesis_fit": int, "stage_fit": int, "ticket_fit": int,
"geo_fit": int, "rationale": "<one sentence citing the data>"}"""


def investor_blob(row: pd.Series) -> str:
    return row[["name", "type", "hq_country", "geography_focus", "stage_focus",
                "ticket_min_eur", "ticket_max_eur", "sectors", "thesis",
                "portfolio_examples"]].to_json()


def llm_user_prompt(row: pd.Series, startup: dict) -> str:
    return f"STARTUP:\n{json.dumps(startup)}\n\nINVESTOR:\n{investor_blob(row)}"


def parse_scores(raw: dict) -> dict:
    """Validate the model's JSON: all four dimensions present, clamped to 0-100."""
    from llm import LLMError
    out = {}
    for k in DIMENSIONS:
        try:
            out[k] = max(0, min(100, int(round(float(raw[k])))))
        except (KeyError, TypeError, ValueError) as e:
            raise LLMError(f"missing/invalid '{k}' in {raw}") from e
    out["rationale"] = str(raw.get("rationale", "")).strip()
    return out


def stratified_sample(investors: pd.DataFrame, n: int, seed: int = 11) -> pd.DataFrame:
    """Half simulated-analyst picks, half others - a fair, cheap LLM-vs-rubric test set.

    The labels only choose WHICH investors get scored; the LLM never sees them.
    """
    picks = set(pd.read_csv(DATA / "manual_shortlist.csv")["investor_id"])
    pos = investors[investors["investor_id"].isin(picks)]
    neg = investors[~investors["investor_id"].isin(picks)]
    n_pos = min(n // 2, len(pos))
    sample = pd.concat([pos.sample(n_pos, random_state=seed),
                        neg.sample(n - n_pos, random_state=seed)])
    return sample.sort_values("investor_id")


def run_llm(investors: pd.DataFrame, startup: dict, client) -> tuple:
    """Score each investor with the LLM. Returns (records, failures, quota_hit)."""
    from llm import FatalLLMError, QuotaExhausted
    fallback = rubric_dimensions(rubric_features(investors, startup))
    records, failures, quota_hit = [], [], False
    for i, (idx, row) in enumerate(investors.iterrows(), 1):
        try:
            scores = parse_scores(client.complete_json(LLM_SYSTEM, llm_user_prompt(row, startup)))
            source = "llm"
        except FatalLLMError:
            raise
        except QuotaExhausted:
            quota_hit = True
            break
        except Exception as e:  # one bad response must not kill the batch - but it is recorded
            failures.append((row["name"], str(e)))
            scores = {**fallback.loc[idx].to_dict(), "rationale": "LLM call failed - rubric fallback."}
            source = "rubric_fallback"
        records.append({**row.to_dict(), **{k: scores[k] for k in DIMENSIONS},
                        "rationale": scores["rationale"], "score_source": source})
        if i % 10 == 0:
            print(f"  scored {i}/{len(investors)}  (network calls {client.network_calls}, "
                  f"cache hits {client.cache_hits})")
    return records, failures, quota_hit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rubric", "demo", "llm"], default="rubric",
                        help="'demo' is kept as an alias of 'rubric'")
    parser.add_argument("--provider", choices=["gemini", "claude"], default="gemini",
                        help="LLM provider for --mode llm (gemini has a free tier)")
    parser.add_argument("--model", default=None, help="Override model id")
    parser.add_argument("--limit", type=int, default=None,
                        help="llm mode: score only the first N investors")
    parser.add_argument("--sample", type=int, default=None,
                        help="llm mode: stratified sample of N (half analyst picks)")
    parser.add_argument("--rpm", type=float, default=6,
                        help="llm mode: max requests per minute (free tier is low)")
    args = parser.parse_args()

    investors, startup = load_inputs()
    OUTPUT.mkdir(exist_ok=True)

    if args.mode != "llm":
        if args.limit or args.sample:
            raise SystemExit("--limit/--sample only apply to --mode llm "
                             "(the rubric scores all 520 in under a second).")
        dims = rubric_dimensions(rubric_features(investors, startup))
        df = pd.concat([investors, dims], axis=1)
        df["rationale"] = "Rubric score (offline mode)."
        df["score_source"] = "rubric"
        df["total_score"] = weighted_total(dims)
        df = rank_frame(df)
        out = OUTPUT / "scored_investors.csv"
        df.to_csv(out, index=False)
        print(f"Wrote {len(df)} scored investors to {out} (mode=rubric)")
    else:
        from llm import FatalLLMError, LLMClient
        if args.sample:
            investors = stratified_sample(investors, args.sample)
        elif args.limit:
            investors = investors.head(args.limit)
        try:
            client = LLMClient(args.provider, args.model,
                               cache_path=OUTPUT / "llm_cache.jsonl", rpm=args.rpm)
            print(f"LLM scoring {len(investors)} investors with {client.provider}/{client.model} ...")
            records, failures, quota_hit = run_llm(investors, startup, client)
        except FatalLLMError as e:
            raise SystemExit(f"\nLLM run aborted: {e}")

        llm_rows = sum(1 for r in records if r["score_source"] == "llm")
        if failures:
            print(f"\n!! {len(failures)} LLM calls failed and used the rubric fallback "
                  "(marked score_source=rubric_fallback). First errors:")
            for name, err in failures[:3]:
                print(f"   - {name}: {err[:160]}")
        if quota_hit:
            print(f"\n!! Daily free-tier quota reached after {len(records)}/{len(investors)}. "
                  "Responses so far are cached - run the SAME command tomorrow to resume.")
        if llm_rows == 0:
            raise SystemExit("\nNo investor was scored by the LLM - nothing written. "
                             "Fix the error above and re-run.")
        df = pd.DataFrame(records)
        df["total_score"] = weighted_total(df[DIMENSIONS])
        df = rank_frame(df)
        out = OUTPUT / "scored_investors_llm.csv"
        df.to_csv(out, index=False)
        print(f"\nWrote {len(df)} LLM-scored investors to {out} "
              f"({llm_rows} by LLM, {len(df) - llm_rows} fallback; "
              f"{client.network_calls} network calls, {client.cache_hits} cache hits)")
        print("Next: python src/compare.py   (LLM vs rubric on the same investors)")

    print("\nTop 10:")
    print(df.head(10)[["rank", "name", "type", "hq_country", "total_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
