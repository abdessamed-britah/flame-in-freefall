"""Unified data - test conditions of every PSI experimental table, in the same units."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import theme  # noqa: E402

UNIFIED = ROOT / "data" / "unified" / "tests_conditions.csv"
UNITS_MAP = ROOT / "data" / "unified" / "units_map.csv"

AXES = {"o2_mole_frac": "O2 (mole fraction)", "pressure_kpa": "Pressure (kPa)",
        "flow_speed_cm_s": "Flow speed (cm/s)", "diluent_mole_frac": "Diluent (mole fraction)",
        "sample_size_mm": "Sample size (mm)"}
MOON = {"o2_mole_frac": 0.30, "pressure_kpa": 70.3}  # challenge brief: 30% O2, 10.2 psi
PSI_PAGE = "https://psi.nasa.gov/physci/repo/data/investigations/"
MOON_INK = "#eef1fa"


@st.cache_data
def load():
    df = pd.read_csv(UNIFIED, dtype=str, keep_default_na=False)
    for c in AXES:
        df[c] = pd.to_numeric(df[c].where(df[c] != ""))
    return df, pd.read_csv(UNITS_MAP, dtype=str, keep_default_na=False)


theme.header("Unified data",
             "The test conditions of every NASA combustion investigation in one table, in the same units.")
if not UNIFIED.exists():
    st.error("data/unified/tests_conditions.csv is missing. Run `python src/normalize.py`.")
    st.stop()
df, units = load()

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
a, b = st.columns(2)
x = a.selectbox("Horizontal axis", list(AXES), index=0, format_func=AXES.get)
y = b.selectbox("Vertical axis", list(AXES), index=1, format_func=AXES.get)
pts = view.dropna(subset=[x, y])

# Shape = investigation (fixed whatever the filters are: most rows first in the whole table).
# Colour = what the O2 value means: ambient (comparable with a habitat), oxidizer stream, or no O2 value.
all_ids = df["psi_id"].value_counts().index.tolist()
shape_of = {pid: theme.SERIES_SHAPES[k % len(theme.SERIES_SHAPES)] for k, pid in enumerate(all_ids)}
COLOUR = {"ambient": theme.FLAME, "oxidizer stream": theme.BLUE, "": theme.GREY}
BASIS = {"ambient": "ambient O2", "oxidizer stream": "oxidizer-stream O2", "": "no O2 value"}

fig = go.Figure()
for pid in pts["psi_id"].value_counts().index.tolist():  # most rows first
    g = pts[pts["psi_id"] == pid]
    for basis, gg in g.groupby("o2_basis"):
        stream, colour = basis == "oxidizer stream", COLOUR[basis]
        fig.add_trace(go.Scatter(
            x=gg[x], y=gg[y], mode="markers",
            name=f"{pid} {g['investigation'].iloc[0][:28]}, {BASIS[basis]} ({len(gg)})",
            marker=dict(color=colour, size=9, symbol=shape_of[pid] + ("-open" if stream else ""),
                        line=dict(color=colour if stream else "#0b1020", width=1.5 if stream else 1)),
            customdata=gg[["psi_id", "investigation", "test_id", "fuel", "o2_basis", "source_row"]].to_numpy(),
            hovertemplate=("%{customdata[0]} %{customdata[1]}<br>Test %{customdata[2]} (row %{customdata[5]})<br>"
                           "Fuel: %{customdata[3]}<br>O2 basis: %{customdata[4]}<br>"
                           + AXES[x] + ": %{x:.4g}<br>" + AXES[y] + ": %{y:.4g}<extra></extra>")))
if x in MOON and y in MOON and x != y:
    fig.add_trace(go.Scatter(x=[MOON[x]], y=[MOON[y]], mode="markers+text", name="Moon Base (0.30 O2, 70.3 kPa)",
                             text=["Moon Base"], textposition="top center", textfont=dict(color=MOON_INK),
                             marker=dict(symbol="star", size=20, color=MOON_INK, line=dict(color="#0b1020", width=1)),
                             hovertemplate="Moon Base: O2 0.30, 70.3 kPa (challenge brief)<extra></extra>"))
else:
    if x in MOON:
        fig.add_vline(x=MOON[x], line=dict(color=MOON_INK, width=1.5, dash="dot"),
                      annotation_text=f"Moon Base {MOON[x]:g}", annotation_position="top right")
    if y in MOON:
        fig.add_hline(y=MOON[y], line=dict(color=MOON_INK, width=1.5, dash="dot"),
                      annotation_text=f"Moon Base {MOON[y]:g}", annotation_position="top right")
fig.update_layout(xaxis_title=AXES[x], yaxis_title=AXES[y], height=520)
if pts.empty:
    theme.note(f"No row in the current selection has both {AXES[x]} and {AXES[y]}.")
else:
    theme.chart(fig)
    st.caption(f"{len(pts)} of {len(view)} selected rows, from {pts['psi_id'].nunique()} investigations, have both "
               "values. The white star or dotted line is the Moon Base atmosphere of the challenge brief "
               "(O2 0.30 at 70.3 kPa). Shape = investigation; orange = ambient O2, blue open = oxidizer-stream O2, "
               "grey = no O2 value.")
    if "o2_mole_frac" in (x, y) and (pts["o2_basis"] == "oxidizer stream").any():
        theme.caveat("Blue open markers are oxidizer-stream O2 (the gas fed through the burner), not the ambient "
                     "atmosphere, so they are not comparable with a habitat atmosphere.")

# ---------------------------------------------------------------- table and download
st.subheader(f"Rows ({len(view)} of {len(df)})")
table = view.assign(psi_page=PSI_PAGE + view["psi_id"])
st.dataframe(table, hide_index=True, width="stretch", column_config={
    "psi_id": "PSI id", "investigation": "Investigation", "test_id": "Test id", "source_file": "Source file",
    "source_row": "Source row", "fuel": "Fuel", "fuel_phase": "Fuel phase (team label)", "gravity": "Gravity",
    "o2_mole_frac": st.column_config.NumberColumn("O2 (mole fraction)", format="%.3f"),
    "o2_basis": "O2 basis",
    "pressure_kpa": st.column_config.NumberColumn("Pressure (kPa)", format="%.1f"),
    "flow_speed_cm_s": st.column_config.NumberColumn("Flow speed (cm/s)", format="%.1f"),
    "diluent": "Diluent",
    "diluent_mole_frac": st.column_config.NumberColumn("Diluent (mole fraction)", format="%.2f"),
    "sample_size_mm": st.column_config.NumberColumn("Sample size (mm)", format="%.2f"),
    "quality_flag": "Quality flag",
    "psi_page": st.column_config.LinkColumn("PSI page", display_text="Open PSI page")})
d1, d2 = st.columns(2)
d1.download_button("Download the unified table (CSV, all rows)", UNIFIED.read_bytes(),
                   file_name="tests_conditions.csv", mime="text/csv", type="primary", width="stretch")
d2.download_button("Download the current selection (CSV)", view.to_csv(index=False).encode("utf-8"),
                   file_name="tests_conditions_selection.csv", mime="text/csv", width="stretch")
st.caption("Downloads keep NASA's full precision; the table above rounds for display.")

with st.expander("Where each value comes from (units map)"):
    st.markdown(f"Test conditions from all {df['source_file'].nunique()} experimental tables "
                f"({len(df)} rows, {df['psi_id'].nunique()} investigations), in mole fraction, kPa, cm/s and mm. A "
                "value is converted only when the source column states its unit; otherwise the cell is blank and "
                "the column is listed below as \"unit not stated\". Measurements stay in NASA's original tables, "
                "linked by PSI id, file and row.")
    st.dataframe(units, hide_index=True, width="stretch", column_config={
        "psi_id": "PSI id", "source_file": "Source file", "source_column": "Source column",
        "original_unit": "Original unit", "conversion": "Conversion", "factor": "Factor",
        "target_column": "Target column", "status": "Status", "note": "Note"})
