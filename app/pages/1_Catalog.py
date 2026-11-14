"""Module A - Investigation Catalog."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import catalog as cat  # noqa: E402

st.set_page_config(page_title="Investigation Catalog", layout="wide")


@st.cache_data
def catalog_data():
    return cat.load_catalog()


df, is_fixture = catalog_data()

st.title("Investigation Catalog")
st.caption("NASA PSI investigations whose research area is Combustion Science, built from NASA's own PSI "
           "records. O2 (mole fraction), pressure (kPa) and flow ranges are computed from an investigation's experimental table only "
           "when a column header states the quantity and unit; the column used is shown beside them. "
           "Pillar and fuel phase are the team's labels, each with its basis. "
           "A cell with no source is left blank and shown as \"not stated\".")
if is_fixture:
    st.error("**Placeholder data.** `data/catalog/investigations.csv` does not exist yet, so this page is "
             f"showing {len(df)} made-up placeholder rows from `tests/fixtures/`. They are not NASA "
             "investigations. The page switches to the real catalog as soon as that file is added.")

# ---------------------------------------------------------------- filters
with st.sidebar:
    st.header("Filters")
    opts = lambda c: sorted(v for v in df[c].unique() if v)  # noqa: E731
    pillars = st.multiselect("Fire-safety pillar", opts("fire_safety_pillar"))
    phases = st.multiselect("Fuel phase", opts("fuel_phase"))
    hardware = st.multiselect("Hardware", opts("hardware"))
    o2_vals = pd.concat([df["o2_min_frac"], df["o2_max_frac"]]).dropna()
    o2_range, keep_unstated = None, True
    if len(o2_vals) and o2_vals.min() < o2_vals.max():
        o2_range = st.slider("O2 range tested (mole fraction)", float(o2_vals.min()), float(o2_vals.max()),
                             (float(o2_vals.min()), float(o2_vals.max())))
        keep_unstated = st.checkbox("Keep investigations whose O2 range is not stated", value=True)

view = cat.filter_catalog(df, pillars, phases, hardware, o2_range, keep_unstated)
st.subheader(f"Investigations ({len(view)} of {len(df)})")
table = view[cat.COLUMNS].copy()
for c in cat.COLUMNS:
    if c != "source_url":
        table[c] = table[c].map(cat.show)
st.dataframe(table.rename(columns=cat.LABELS), hide_index=True, width="stretch",
             column_config={cat.LABELS["source_url"]: st.column_config.LinkColumn(display_text="Open PSI page")})

# ---------------------------------------------------------------- compare
st.subheader("Compare side by side")
picked = st.multiselect("Pick 2 or 3 investigations", list(view["psi_id"]), max_selections=3,
                        format_func=lambda i: f"{i} - {df.set_index('psi_id').loc[i, 'name']}")
if len(picked) >= 2:
    side, differs = cat.compare(df, picked)
    style = side.style.apply(
        lambda row: ["background-color: rgba(250,178,25,0.30)" if differs[side.index.get_loc(row.name)] else ""
                     for _ in row], axis=1)
    st.dataframe(style, width="stretch")
    st.caption(f"Highlighted rows are the {sum(differs)} fields on which these investigations differ.")
else:
    st.caption("Pick at least 2 investigations to compare them.")

# ---------------------------------------------------------------- ranking
st.subheader("Relevance ranking for a habitat")
left, right = st.columns([1, 2])
with left:
    habitat = st.selectbox("Habitat", list(cat.HABITATS))
    h = cat.HABITATS[habitat]
    st.caption(h["note"])
    o2_target = st.number_input("Habitat O2 (mole fraction)", 0.0, 1.0, h["o2_frac"], 0.01, key=f"o2_{habitat}")
    p_target = st.number_input("Habitat pressure (kPa)", 0.0, 400.0, h["pressure_kpa"], 0.1, key=f"p_{habitat}")
    pillar_opts = sorted(v for v in df["fire_safety_pillar"].unique() if v)
    pillar = st.selectbox("Fire-safety pillar of interest", pillar_opts,
                          index=pillar_opts.index("suppression") if "suppression" in pillar_opts else 0)
    st.markdown("**Weights**")
    weights = {k: st.slider(label, 0, 10, cat.DEFAULT_WEIGHTS[k], key=f"w_{k}")
               for k, label in cat.CRITERIA.items()}
with right:
    ranked = cat.rank(view, weights, pillar, o2_target, p_target, h["pressure_rule"])
    if sum(weights.values()) == 0:
        st.warning("All weights are 0, so every score is 0.")
    rule = ("its lowest pressure is at or below" if h["pressure_rule"] == "at_or_below"
            else "its pressure range contains")
    st.caption(f"Score = 100 x sum(weight x criterion) / sum(weights). An investigation meets the O2 criterion "
               f"when its highest O2 mole fraction is at least {o2_target:g}, and the pressure criterion when {rule} "
               f"{p_target:g} kPa. A blank cell scores zero. This is a transparent sum, not an AI score.")
    if len(ranked):
        score = ranked[["rank", "psi_id", "acronym", "name", "score"] + [f"points_{k}" for k in cat.CRITERIA]
                       + ["source_url"]].copy()
        st.dataframe(
            score.rename(columns={"rank": "Rank", "psi_id": "PSI id", "acronym": "Acronym", "name": "Name",
                                  "score": "Score", "source_url": "PSI page",
                                  **{f"points_{k}": f"Points: {k}" for k in cat.CRITERIA}}),
            hide_index=True, width="stretch",
            column_config={"PSI page": st.column_config.LinkColumn(display_text="Open PSI page"),
                           "Score": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
                           **{f"Points: {k}": st.column_config.NumberColumn(format="%.0f", help=cat.CRITERIA[k])
                              for k in cat.CRITERIA}})
        st.caption("\"=\" marks a tie; tied investigations are listed in alphabetical order of acronym.")
        st.markdown("**Catalog cells behind each criterion**")
        st.dataframe(ranked[["psi_id"] + [f"cell_{k}" for k in cat.CRITERIA]].rename(
            columns={"psi_id": "PSI id", "cell_pillar": "Pillar", "cell_phase": "Fuel phase",
                     "cell_o2": "Ambient O2 max (mole fraction)", "cell_pressure": "Pressure (kPa)",
                     "cell_data": "Data table in PSI"}),
            hide_index=True, width="stretch")
    else:
        st.caption("No investigation matches the filters.")

# ---------------------------------------------------------------- Q&A
st.subheader("Ask a question")
st.markdown("Questions are now answered on the **Ask NASA Records** page (sidebar): it searches the full text of "
            "NASA's records and cites the passage behind every claim.")
