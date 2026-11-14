"""
Investor Intelligence Engine - Streamlit dashboard (local exploration).

The public live demo is the static site in site/ (never sleeps); this app reads the
same outputs. Run the pipeline first (or use the included output):
  python run_all.py

Then:  streamlit run app.py
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
DATA = ROOT / "data"

# ---------------------------------------------------------------- palette
# Validated categorical palette (colorblind-safe, fixed assignment per entity)
GEO_COLORS = {"DACH": "#2a78d6", "Europe": "#eb6834", "Global": "#1baf7a"}
BLUE = "#2a78d6"
BLUE_DARK = "#0d366b"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
GOOD = "#0ca30c"

PLOTLY_LAYOUT = dict(
    font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif',
              color=INK_2, size=13),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor="#c3c2b7",
               tickcolor="#c3c2b7", title_font_color=MUTED),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor="#c3c2b7",
               tickcolor="#c3c2b7", title_font_color=MUTED),
    hoverlabel=dict(bgcolor="#ffffff", font_color=INK, bordercolor=GRID),
)
PLOTLY_CONFIG = {"displayModeBar": False}

st.set_page_config(page_title="Investor Intelligence Engine", page_icon="📊",
                   layout="wide")

# ---------------------------------------------------------------- custom CSS
st.markdown("""
<style>
/* page + typography */
html, body, [class*="css"] {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}
#MainMenu, footer, header [data-testid="stToolbar"] {visibility: hidden;}
.block-container {padding-top: 1.2rem; max-width: 1250px;}

/* hero band */
.hero {
  background: linear-gradient(120deg, #0d366b 0%, #1c5cab 55%, #2a78d6 100%);
  border-radius: 18px;
  padding: 28px 34px 24px 34px;
  color: #ffffff;
  margin-bottom: 18px;
}
.hero h1 {color:#ffffff; font-size: 2rem; margin: 0 0 6px 0; font-weight: 750;}
.hero p  {color:#cde2fb; font-size: 0.95rem; margin: 0; line-height: 1.5;}
.hero .chips {margin-top: 14px;}
.hero .chip {
  display: inline-block; background: rgba(255,255,255,0.14);
  border: 1px solid rgba(255,255,255,0.25); border-radius: 999px;
  padding: 4px 14px; margin-right: 8px; font-size: 0.8rem; color: #ffffff;
}

/* KPI metric cards */
[data-testid="stMetric"] {
  background: #fcfcfb;
  border: 1px solid rgba(11,11,11,0.10);
  border-radius: 14px;
  padding: 14px 18px;
  box-shadow: 0 1px 3px rgba(11,11,11,0.04);
}
[data-testid="stMetricLabel"] {color: #52514e;}
[data-testid="stMetricValue"] {color: #0b0b0b; font-weight: 700;}

/* top-3 cards */
.topcard {
  background: #fcfcfb; border: 1px solid rgba(11,11,11,0.10);
  border-radius: 14px; padding: 16px 18px; height: 100%;
  box-shadow: 0 1px 3px rgba(11,11,11,0.04);
}
.topcard .medal {font-size: 1.4rem;}
.topcard .name {font-weight: 700; color: #0b0b0b; font-size: 1.02rem; margin: 2px 0;}
.topcard .meta {color: #898781; font-size: 0.8rem;}
.topcard .score {color: #1c5cab; font-weight: 750; font-size: 1.5rem; margin-top: 6px;}
.topcard .score small {color:#898781; font-weight: 400; font-size: 0.75rem;}

/* tabs */
button[data-baseweb="tab"] {font-size: 0.95rem; font-weight: 600;}
.stTabs [data-baseweb="tab-highlight"] {background-color: #2a78d6;}

/* sidebar */
section[data-testid="stSidebar"] {background: #fcfcfb; border-right: 1px solid #e1e0d9;}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load(data_version: float = 0.0):
    # data_version is the newest mtime of the output files - when the pipeline
    # is re-run, the cache key changes and fresh results load automatically.
    scored = pd.read_csv(OUTPUT / "scored_investors.csv")
    manual = pd.read_csv(DATA / "manual_shortlist.csv")
    startup = json.loads((DATA / "startup_profile.json").read_text(encoding="utf-8"))
    report = json.loads((OUTPUT / "evaluation_report.json").read_text(encoding="utf-8")) \
        if (OUTPUT / "evaluation_report.json").exists() else None
    drafts_path = OUTPUT / "outreach_drafts.csv"
    drafts = pd.read_csv(drafts_path) if drafts_path.exists() else None
    tuning = json.loads((OUTPUT / "tuning_report.json").read_text(encoding="utf-8")) \
        if (OUTPUT / "tuning_report.json").exists() else None
    llm_cmp = json.loads((OUTPUT / "llm_vs_rubric.json").read_text(encoding="utf-8")) \
        if (OUTPUT / "llm_vs_rubric.json").exists() else None
    return scored, manual, startup, report, drafts, tuning, llm_cmp


try:
    data_version = max((p.stat().st_mtime for p in OUTPUT.glob("*") if p.is_file()),
                       default=0.0)
    scored, manual, startup, report, drafts, tuning, llm_cmp = load(data_version)
except FileNotFoundError:
    st.error("Run the pipeline first - see README (python src/scoring.py etc.)")
    st.stop()

# -------------------------------------------------------------------- hero
st.markdown(f"""
<div class="hero">
  <h1>📊 Investor Intelligence Engine</h1>
  <p>AI-scored fundraising pipeline for an anonymized Austrian MedTech startup —
  {startup['one_liner'].rstrip('.')}.</p>
  <div class="chips">
    <span class="chip">💶 Round: EUR {startup['round_size_eur']:,} ({startup['stage']})</span>
    <span class="chip">🌍 DACH-first, Europe-wide</span>
    <span class="chip">🤖 LLM scoring · 4-dimension rubric</span>
    <span class="chip">✅ Held-out evaluation</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------- sidebar
st.sidebar.markdown("### 🎛️ Filters")
geo = st.sidebar.multiselect("Geography focus", sorted(scored["geography_focus"].unique()))
itype = st.sidebar.multiselect("Investor type", sorted(scored["type"].unique()))
country = st.sidebar.multiselect("HQ country", sorted(scored["hq_country"].unique()))
min_score = st.sidebar.slider("Min total score", 0, 100, 0, 5)
only_shortlist = st.sidebar.checkbox("Only analyst picks (simulated ground truth)")
st.sidebar.markdown("---")
st.sidebar.caption("**Scoring rubric (v2)** — thesis fit 45% · stage 25% · "
                   "ticket 20% · geography 10%")
st.sidebar.caption("Built by **Om Rana** · NIT Rourkela '25 · based on live "
                   "€1.5M MedTech fundraise screening work (client anonymized).")

df = scored.copy()
df["in_manual_shortlist"] = df["investor_id"].isin(set(manual["investor_id"]))
if geo:
    df = df[df["geography_focus"].isin(geo)]
if itype:
    df = df[df["type"].isin(itype)]
if country:
    df = df[df["hq_country"].isin(country)]
df = df[df["total_score"] >= min_score]
if only_shortlist:
    df = df[df["in_manual_shortlist"]]

# ---------------------------------------------------------------- KPI strip
c1, c2, c3, c4 = st.columns(4)
c1.metric("🗂️ Investors screened", f"{len(scored):,}")
c2.metric("🔎 Matching filters", f"{len(df):,}")
c3.metric("📈 Avg score (filtered)", f"{df['total_score'].mean():.1f}" if len(df) else "—")
if tuning:
    c4.metric("🎯 Held-out precision",
              f"{tuning['held_out']['tuned_on_A_scored_on_B']['mean']:.0%}",
              f"analyst noise ceiling ≈ "
              f"{tuning['noise_ceiling']['analyst_rerun_vs_shortlist']['mean']:.0%}",
              delta_color="off")

st.write("")

tab_pipe, tab_detail, tab_eval, tab_outreach, tab_how = st.tabs(
    ["🏆 Ranked pipeline", "🔍 Investor detail", "🎯 Model evaluation",
     "✉️ Outreach drafts", "⚙️ How it works"])

# ------------------------------------------------------------------ pipeline
with tab_pipe:
    st.markdown("#### Top picks")
    medals = ["🥇", "🥈", "🥉"]
    tcols = st.columns(3)
    for col, medal, (_, r) in zip(tcols, medals, df.head(3).iterrows()):
        col.markdown(f"""
        <div class="topcard">
          <span class="medal">{medal}</span>
          <div class="name">{r['name']}</div>
          <div class="meta">{r['type']} · {r['hq_country']} · {r['geography_focus']}
          {'· ✅ analyst pick' if r['in_manual_shortlist'] else ''}</div>
          <div class="score">{r['total_score']:.1f} <small>/ 100</small></div>
        </div>""", unsafe_allow_html=True)

    st.write("")
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### Ranked pipeline")
        show = df[["rank", "name", "type", "hq_country", "geography_focus",
                   "total_score", "thesis_fit", "stage_fit", "ticket_fit", "geo_fit",
                   "in_manual_shortlist"]]
        st.dataframe(show, hide_index=True, height=480,
                     column_config={
                         "rank": st.column_config.NumberColumn("Rank", width="small"),
                         "name": "Investor",
                         "type": "Type",
                         "hq_country": "HQ",
                         "geography_focus": "Focus",
                         "total_score": st.column_config.ProgressColumn(
                             "Total", min_value=0, max_value=100, format="%.1f"),
                         "thesis_fit": st.column_config.NumberColumn("Thesis", width="small"),
                         "stage_fit": st.column_config.NumberColumn("Stage", width="small"),
                         "ticket_fit": st.column_config.NumberColumn("Ticket", width="small"),
                         "geo_fit": st.column_config.NumberColumn("Geo", width="small"),
                         "in_manual_shortlist": st.column_config.CheckboxColumn("Analyst pick"),
                     })
        st.download_button("⬇️ Download filtered pipeline (CSV)",
                           show.to_csv(index=False), "investor_pipeline.csv")
    with right:
        st.markdown("#### Score distribution")
        fig = px.histogram(df, x="total_score", nbins=30, color="geography_focus",
                           color_discrete_map=GEO_COLORS,
                           category_orders={"geography_focus": ["DACH", "Europe", "Global"]},
                           labels={"total_score": "Total score", "count": "Investors"})
        fig.update_traces(marker_line_width=1, marker_line_color=SURFACE)
        fig.update_layout(**PLOTLY_LAYOUT, height=260,
                          margin=dict(t=10, b=10, l=10, r=10),
                          legend=dict(title="", orientation="h", y=1.15),
                          bargap=0.05)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

        st.markdown("#### Top-40 by geography")
        top40 = df.head(40)
        geo_counts = top40["geography_focus"].value_counts()
        fig2 = go.Figure(go.Pie(
            labels=geo_counts.index, values=geo_counts.values, hole=0.62,
            marker=dict(colors=[GEO_COLORS.get(g, MUTED) for g in geo_counts.index],
                        line=dict(color=SURFACE, width=2)),
            textinfo="label+percent", textfont=dict(size=12)))
        fig2.add_annotation(text=f"<b>{len(top40)}</b><br><span style='font-size:11px;color:{MUTED}'>targets</span>",
                            showarrow=False, font=dict(size=22, color=INK))
        fig2.update_layout(**{k: v for k, v in PLOTLY_LAYOUT.items()
                              if k not in ("xaxis", "yaxis")},
                           height=260, margin=dict(t=10, b=10, l=10, r=10),
                           showlegend=False)
        st.plotly_chart(fig2, use_container_width=True, config=PLOTLY_CONFIG)

# -------------------------------------------------------------------- detail
with tab_detail:
    pick = st.selectbox("Choose an investor",
                        df["name"] + "  (#" + df["rank"].astype(str) + ")")
    row = df[df["name"] == pick.split("  (#")[0]].iloc[0]
    a, b = st.columns([2, 3], gap="large")
    with a:
        st.markdown(f"### {row['name']}")
        st.markdown(f"**Type:** {row['type']} &nbsp;|&nbsp; **HQ:** {row['hq_country']} "
                    f"&nbsp;|&nbsp; **Focus:** {row['geography_focus']}")
        st.markdown(f"**Stages:** {row['stage_focus']}")
        st.markdown(f"**Ticket:** EUR {row['ticket_min_eur']:,.0f} – {row['ticket_max_eur']:,.0f}")
        st.markdown(f"**Sectors:** {row['sectors']}")
        st.markdown(f"**Thesis:** _{row['thesis']}_")
        st.markdown(f"**Portfolio:** {row['portfolio_examples']}")
        if row["in_manual_shortlist"]:
            st.success("✅ Also picked by the simulated analyst (ground truth)")
        if isinstance(row.get("rationale"), str) and row["rationale"]:
            st.info(f"Model rationale: {row['rationale']}")
    with b:
        dims = pd.DataFrame({
            "dimension": ["Geo fit (10%)", "Ticket fit (20%)",
                          "Stage fit (25%)", "Thesis fit (45%)"],
            "score": [row["geo_fit"], row["ticket_fit"],
                      row["stage_fit"], row["thesis_fit"]],
        })
        fig = go.Figure(go.Bar(
            x=dims["score"], y=dims["dimension"], orientation="h",
            marker=dict(color=BLUE, cornerradius=4),
            text=dims["score"], textposition="outside",
            textfont=dict(color=INK_2), width=0.55,
            hovertemplate="%{y}: %{x}<extra></extra>"))
        fig.update_layout(**PLOTLY_LAYOUT, height=280,
                          margin=dict(t=20, b=10, l=10, r=30),
                          xaxis_range=[0, 112], yaxis_title="",
                          xaxis_title="Score (0–100)")
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        st.metric("Total weighted score", f"{row['total_score']:.1f} / 100",
                  f"Rank #{int(row['rank'])} of {len(scored)}", delta_color="off")

# ---------------------------------------------------------------- evaluation
with tab_eval:
    st.markdown("#### Model ranking vs a simulated analyst shortlist")
    st.caption("Ground truth = a simulated analyst's 40-investor shortlist (heuristic screen "
               "+ gut-feel noise). The real fundraise pipeline is client-confidential and "
               "lives on a different universe, so it can't be the benchmark here.")
    if not report or not tuning:
        st.warning("Run `python run_all.py` to generate the evaluation reports.")
    else:
        ho, ins, ceil = tuning["held_out"], tuning["in_sample"], tuning["noise_ceiling"]
        lo, hi = report["precision_at_40_ci95"]
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Held-out precision", f"{ho['tuned_on_A_scored_on_B']['mean']:.0%}",
                  f"± {ho['tuned_on_A_scored_on_B']['std']:.0%} over {ho['n_splits']} splits",
                  delta_color="off")
        e2.metric("In-sample precision@40", f"{report['precision_at_40']:.0%}",
                  f"95% CI {lo:.0%}–{hi:.0%}", delta_color="off")
        e3.metric("Analyst noise ceiling",
                  f"{ceil['analyst_rerun_vs_shortlist']['mean']:.0%}",
                  "same analyst, re-run", delta_color="off")
        e4.metric("ROC-AUC (all 520)", f"{report['roc_auc']:.2f}",
                  f"recall@80 = {report['recall_at_80']:.0%}", delta_color="off")

        st.write("")
        st.markdown("**Why the in-sample number overstates the model**")
        bars = pd.DataFrame([
            ("v1 rubric · in-sample", ins["v1_precision_at_40"], "In-sample"),
            ("v2 rubric · in-sample", ins["v2_precision_at_40"], "In-sample"),
            ("Best of grid · in-sample", ins["best_grid_precision_at_40"], "In-sample"),
            ("v1 rubric · held-out", ho["v1_hand_set_on_B"]["mean"], "Held-out"),
            ("Tuned rubric · held-out", ho["tuned_on_A_scored_on_B"]["mean"], "Held-out"),
        ], columns=["label", "precision", "kind"])
        fig = go.Figure()
        for kind, color in [("In-sample", "#c3c2b7"), ("Held-out", BLUE)]:
            sub = bars[bars["kind"] == kind]
            fig.add_trace(go.Bar(
                x=sub["precision"], y=sub["label"], orientation="h", name=kind,
                marker=dict(color=color, cornerradius=4), width=0.6,
                text=[f"{v:.0%}" for v in sub["precision"]], textposition="outside",
                textfont=dict(color=INK_2),
                hovertemplate="%{y}: %{x:.0%}<extra></extra>"))
        ceiling_v = ceil["analyst_rerun_vs_shortlist"]["mean"]
        fig.add_vline(x=ceiling_v, line_dash="dash", line_color=MUTED,
                      annotation_text=f"noise ceiling {ceiling_v:.0%}",
                      annotation_font_color=MUTED, annotation_position="top")
        fig.update_layout(**PLOTLY_LAYOUT, height=270, margin=dict(t=30, b=10, l=10, r=40),
                          xaxis_range=[0.4, 0.88], xaxis_tickformat=".0%",
                          xaxis_title="Precision (share of model top-k the analyst also picked)",
                          legend=dict(title="", orientation="h", y=1.18), barmode="overlay")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        st.caption(
            f"Tuning on the same shortlist you score on looks like a "
            f"{ins['best_grid_precision_at_40'] - ins['v1_precision_at_40']:+.0%} gain. "
            f"On unseen halves the tuned rubric beats hand-set v1 by only "
            f"{ho['tuned_on_A_scored_on_B']['mean'] - ho['v1_hand_set_on_B']['mean']:+.0%}, "
            f"and the optimism gap is {ho['optimism_gap']:+.0%}. One change was robust: "
            f"counting clinical-operations language toward thesis fit "
            f"(chosen in {ho['clinical_ops_terms_chosen_in']}). The weight shifts were mostly "
            f"noise. Held-out precision already sits at the analyst's own re-run agreement.")

        st.write("")
        st.markdown("**Where does the model place each analyst pick?**")
        ranks = scored.set_index("investor_id")["rank"]
        mm = manual.copy()
        mm["model_rank"] = mm["investor_id"].map(ranks)
        fig = go.Figure(go.Scatter(
            x=mm["model_rank"], y=[0] * len(mm), mode="markers",
            marker=dict(color=BLUE, size=10, opacity=0.75,
                        line=dict(color=SURFACE, width=2)),
            text=mm["name"],
            hovertemplate="<b>%{text}</b><br>model rank: %{x}<extra></extra>"))
        fig.add_vline(x=40, line_dash="dash", line_color=MUTED,
                      annotation_text="top-40 cutoff",
                      annotation_font_color=MUTED)
        fig.update_layout(**PLOTLY_LAYOUT, height=190,
                          margin=dict(t=10, b=30, l=10, r=10),
                          xaxis_title="Model rank of analyst-picked investor")
        fig.update_yaxes(visible=False)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

        if report["human_picks_missed_by_model_top80"]:
            with st.expander(f"Analyst picks the model missed entirely "
                             f"({len(report['human_picks_missed_by_model_top80'])})"):
                for n in report["human_picks_missed_by_model_top80"]:
                    st.markdown(f"- {n}")
        st.info("**Key learning:** a number measured on the data you tuned on is a claim, "
                "not a result. Held-out splits cut the apparent gain from tuning to almost "
                "nothing, and re-running the analyst showed the label noise caps agreement "
                "near 70%. Past that point, more tuning just fits the analyst's gut feel.")

    st.write("")
    st.markdown("#### 🤖 LLM vs rubric (same investors)")
    if not llm_cmp:
        st.info("No LLM run yet. With a free Gemini key: `python src/scoring.py --mode llm "
                "--sample 60` then `python src/compare.py` (or double-click RUN-LLM.bat). "
                "The sample is 30 analyst picks + 30 others, so both scorers face the same "
                "test.")
    else:
        auc = llm_cmp["auc_vs_analyst"]
        l1, l2, l3 = st.columns(3)
        l1.metric("Investors compared", llm_cmp["n_compared"],
                  f"{llm_cmp['n_analyst_picks']} analyst picks", delta_color="off")
        l2.metric("Rank agreement (Spearman)", f"{llm_cmp['spearman_total']:.2f}")
        l3.metric("AUC vs analyst: LLM | rubric", f"{auc['llm']:.2f} | {auc['rubric']:.2f}")
        dim_tbl = pd.DataFrame({
            "Dimension": list(llm_cmp["spearman_by_dimension"]),
            "Spearman": list(llm_cmp["spearman_by_dimension"].values()),
            "Mean |diff| (pts)": list(llm_cmp["mean_abs_diff_by_dimension"].values())})
        st.dataframe(dim_tbl, hide_index=True)
        st.markdown("**Biggest disagreements**")
        st.dataframe(pd.DataFrame(llm_cmp["biggest_disagreements"]), hide_index=True,
                     column_config={"analyst_pick": st.column_config.CheckboxColumn("Analyst pick")})

# ------------------------------------------------------------------ outreach
with tab_outreach:
    st.markdown("#### Auto-drafted personalized outreach")
    st.caption("Each draft is built from the investor's actual thesis and portfolio "
               "in the dataset; LLM drafts are automatically checked for citing a real "
               "portfolio company. A human reviews every draft before anything is sent.")
    if drafts is None:
        st.warning("Run `python src/outreach.py --top 20` to generate drafts.")
    else:
        who = st.selectbox("Draft for", drafts["name"])
        d = drafts[drafts["name"] == who].iloc[0]
        st.markdown(f"**To:** {d['contact_email']} &nbsp;|&nbsp; "
                    f"**Fit score:** {d['total_score']} &nbsp;|&nbsp; "
                    f"**Source:** {d.get('draft_source', 'template')} &nbsp;|&nbsp; "
                    f"{'✅ cites a real portfolio company' if d.get('grounded', True) else '⚠️ not grounded — review'}")
        st.markdown(f"**Subject:** {d['subject']}")
        st.text_area("Body", d["body"], height=280, label_visibility="collapsed")
        st.download_button("⬇️ Download all drafts (CSV)",
                           drafts.to_csv(index=False), "outreach_drafts.csv")

# ----------------------------------------------------------------- how tab
with tab_how:
    st.markdown("#### Pipeline architecture")
    st.markdown("""
```
investors.csv (520 profiles)
        │
        ▼
┌─────────────────────┐      ┌───────────────────────┐
│  Scoring engine     │─────▶│  Ranked pipeline       │
│  LLM (Gemini/Claude)│      │  0–100 weighted score  │
│  or offline rubric  │      └──────────┬────────────┘
└─────────────────────┘                 │
   thesis 45% · stage 25%               ▼
   ticket 20% · geo 10%      ┌───────────────────────┐
                             │ Evaluation vs analyst │
                             │ held-out splits +     │
                             │ noise ceiling         │
                             └──────────┬────────────┘
                                        ▼
                             ┌───────────────────────┐
                             │ Outreach generator    │
                             │ + this dashboard      │
                             └───────────────────────┘
```
""")
    st.markdown("""
- **Scoring** — every investor is scored 0–100 on a 4-dimension weighted rubric via
  LLM structured-JSON calls (Gemini free tier or Claude; provider-agnostic), with a
  deterministic offline rubric as the no-API-key fallback.
- **Evaluation** — the model's ranking is benchmarked against a simulated analyst's
  40-investor shortlist. Rubric parameters are tuned on one half of the data and scored
  on the other (25 repeated splits): held-out precision **{h:.0%}**, against an analyst
  noise ceiling of **{c:.0%}**.
- **LLM vs rubric** — the same investors scored both ways and compared on rank
  agreement and AUC; LLM responses are cached so free-tier runs resume across days.
- **Outreach** — personalized intro drafts grounded in each investor's actual thesis
  text, with an automatic check that each draft cites a portfolio company it was given.
- **Human in the loop** — the pipeline screens 520 investors in seconds (rubric) or
  minutes (LLM), but the final shortlist call and every sent email stay human decisions.
""".format(h=tuning["held_out"]["tuned_on_A_scored_on_B"]["mean"] if tuning else 0,
           c=tuning["noise_ceiling"]["analyst_rerun_vs_shortlist"]["mean"] if tuning else 0))
    st.caption("Dataset note: synthetic universe with fictional firm names, shaped like "
               "a real DACH MedTech seed screen. The actual tracker is client-confidential.")
