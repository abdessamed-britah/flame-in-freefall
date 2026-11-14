"""Unified data - test conditions of every PSI experimental table, in the same units."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
UNIFIED = ROOT / "data" / "unified" / "tests_conditions.csv"
UNITS_MAP = ROOT / "data" / "unified" / "units_map.csv"

AXES = {"o2_mole_frac": "O2 mole fraction", "pressure_kpa": "Pressure (kPa)",
        "flow_speed_cm_s": "Flow speed (cm/s)", "diluent_mole_frac": "Diluent mole fraction",
        "sample_size_mm": "Sample size (mm)"}
MOON = {"o2_mole_frac": 0.30, "pressure_kpa": 70.3}  # challenge brief: 30% O2, 10.2 psi
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#8a8984"
SYMBOL = {"ambient": "circle", "oxidizer stream": "diamond-open", "": "circle"}

st.set_page_config(page_title="Unified data", layout="wide")


@st.cache_data
def load():
    df = pd.read_csv(UNIFIED, dtype=str, keep_default_na=False)
    for c in AXES:
        df[c] = pd.to_numeric(df[c].where(df[c] != ""))
    return df, pd.read_csv(UNITS_MAP, dtype=str, keep_default_na=False)


st.title("Unified data")
if not UNIFIED.exists():
    st.error("data/unified/tests_conditions.csv is missing. Run `python src/normalize.py`.")
    st.stop()
df, units = load()

st.caption(f"Test conditions from all {df['source_file'].nunique()} experimental tables of the NASA PSI Combustion "
           f"Science investigations ({len(df)} rows, {df['psi_id'].nunique()} investigations), in the same units: "
           "mole fraction, kPa, cm/s, mm. A value is converted only when the source column states its unit; "
           "otherwise the cell is blank. Measurements stay in NASA's original tables, linked by PSI id, file and row.")

# ---------------------------------------------------------------- filters
with st.sidebar:
    st.header("Filters")
    names = df.drop_duplicates("psi_id").set_index("psi_id")["investigation"]
    picked = st.multiselect("Investigation", list(names.index), format_func=lambda i: f"{i} - {names[i][:40]}")
    phases = st.multiselect("Fuel phase (team label)", sorted(v for v in df["fuel_phase"].unique() if v))
    bases = st.multiselect("O2 basis", sorted(v for v in df["o2_basis"].unique() if v))
    fuel_text = st.text_input("Fuel contains", "")
    only_tests = st.checkbox("Hide rows that are not single tests (test days, summaries)", value=False)

view = df
if picked:
    view = view[view["psi_id"].isin(picked)]
if phases:
    view = view[view["fuel_phase"].isin(phases)]
if bases:
    view = view[view["o2_basis"].isin(bases)]
if fuel_text.strip():
    view = view[view["fuel"].str.contains(fuel_text.strip(), case=False, regex=False)]
if only_tests:
    view = view[~view["quality_flag"].str.contains("row_is_")]

# ---------------------------------------------------------------- plot
st.subheader(f"Plot one condition against another ({len(view)} of {len(df)} rows)")
a, b = st.columns(2)
x = a.selectbox("Horizontal axis", list(AXES), index=0, format_func=AXES.get)
y = b.selectbox("Vertical axis", list(AXES), index=1, format_func=AXES.get)
pts = view.dropna(subset=[x, y])

fig = go.Figure()
order = pts["psi_id"].value_counts().index.tolist()  # most rows first
for k, pid in enumerate(order):
    g = pts[pts["psi_id"] == pid]
    colour = PALETTE[k] if k < len(PALETTE) else OTHER
    for basis, gg in g.groupby("o2_basis"):
        suffix = f", {basis}" if basis and "o2_mole_frac" in (x, y) else ""
        fig.add_trace(go.Scatter(
            x=gg[x], y=gg[y], mode="markers", name=f"{pid} {g['investigation'].iloc[0][:28]}{suffix} ({len(gg)})",
            marker=dict(color=colour, size=9, symbol=SYMBOL.get(basis, "circle"),
                        line=dict(color="rgba(255,255,255,0.85)", width=1)),
            customdata=gg[["psi_id", "investigation", "test_id", "fuel", "o2_basis", "source_row"]].to_numpy(),
            hovertemplate=("%{customdata[0]} %{customdata[1]}<br>Test %{customdata[2]} (row %{customdata[5]})<br>"
                           "Fuel: %{customdata[3]}<br>O2 basis: %{customdata[4]}<br>"
                           + AXES[x] + ": %{x:.4g}<br>" + AXES[y] + ": %{y:.4g}<extra></extra>")))
if x in MOON and y in MOON and x != y:
    fig.add_trace(go.Scatter(x=[MOON[x]], y=[MOON[y]], mode="markers+text", name="Moon Base (0.30 O2, 70.3 kPa)",
                             text=["Moon Base"], textposition="top center",
                             marker=dict(symbol="star", size=18, color="#d03b3b",
                                         line=dict(color="white", width=1)),
                             hovertemplate="Moon Base: O2 0.30, 70.3 kPa (challenge brief)<extra></extra>"))
else:
    if x in MOON:
        fig.add_vline(x=MOON[x], line=dict(color="#d03b3b", width=1.5, dash="dash"),
                      annotation_text=f"Moon Base {MOON[x]:g}", annotation_position="top right")
    if y in MOON:
        fig.add_hline(y=MOON[y], line=dict(color="#d03b3b", width=1.5, dash="dash"),
                      annotation_text=f"Moon Base {MOON[y]:g}", annotation_position="top right")
fig.update_layout(xaxis_title=AXES[x], yaxis_title=AXES[y], height=520, hovermode="closest",
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), margin=dict(l=10, r=10, t=80, b=10))
if pts.empty:
    st.info(f"No row in the current selection has both {AXES[x]} and {AXES[y]}.")
else:
    st.plotly_chart(fig, width="stretch")
    note = (f"{len(pts)} rows from {pts['psi_id'].nunique()} investigations have both values. "
            "The red marker is the Moon Base atmosphere from the challenge brief (O2 0.30 at 70.3 kPa). ")
    if "o2_mole_frac" in (x, y) and (pts["o2_basis"] == "oxidizer stream").any():
        note += ("Open diamonds are oxidizer-stream O2 (the gas fed through the burner), not the ambient "
                 "atmosphere, so they are not comparable with a habitat atmosphere.")
    st.caption(note)

# ---------------------------------------------------------------- table and download
st.subheader("Rows")
st.dataframe(view, hide_index=True, width="stretch")
st.download_button("Download the unified table (CSV, all rows)", UNIFIED.read_bytes(),
                   file_name="tests_conditions.csv", mime="text/csv")
st.download_button("Download the current selection (CSV)", view.to_csv(index=False).encode("utf-8"),
                   file_name="tests_conditions_selection.csv", mime="text/csv")

st.subheader("Where each value comes from")
st.caption("Every source column used, its original unit and the conversion applied. Columns whose header does "
           "not state a unit are listed as \"unit not stated\" and are not used.")
st.dataframe(units, hide_index=True, width="stretch")
