"""Flame in Freefall - home page."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import lab  # noqa: E402

st.set_page_config(page_title="Flame in Freefall", layout="wide")


@st.cache_data
def clean_data():
    return lab.load_clean()


df = clean_data()
fuels = df["fuel"].value_counts()
bands = df["pressure_band"].value_counts()
diluents = df["diluent"].value_counts()

st.title("Flame in Freefall")
st.caption("NASA Space Apps 2026")

st.markdown(
    "Fire behaves differently without gravity, and a Moon Base is expected to run on more oxygen at lower "
    "pressure than Earth. This dashboard helps researchers, engineers and students see what NASA's "
    "microgravity combustion investigations say about fire safety in crewed habitats: which investigations "
    "are most relevant, and how much suppressant gas it takes to push a burning fuel droplet towards "
    "extinction in a habitat-like atmosphere.")

st.subheader("Two modules")
a, b = st.columns(2)
with a:
    st.markdown("**Investigation Catalog**")
    st.markdown("Filter, compare and rank NASA PSI combustion investigations by relevance to a chosen habitat, "
                "with a transparent score.")
    st.markdown("Open **Catalog** in the sidebar.")
with b:
    st.markdown("**Moon Base Suppression Lab**")
    st.markdown("Pick a base atmosphere, a fuel and a suppressant (CO2 or He), and see how close the flame "
                "is to its extinction limit, with uncertainty and the nearest real NASA tests.")
    st.markdown("Open **Suppression Lab** in the sidebar.")

st.markdown("**Unified data** brings the test conditions of every PSI experimental table into one file with "
            "the same units, to filter, plot and download. Open **Unified Data** in the sidebar.")

st.subheader("Data sources")
st.markdown(
    f"- **NASA PSI-69, Flame Extinguishment Experiment (FLEX)**, experimental table, CC0: "
    f"[doi.org/10.60555/mbq8-0451]({lab.PSI69_DOI_URL}). "
    f"{len(df)} droplet-combustion tests from {df['test_date'].min()} to {df['test_date'].max()}: "
    + ", ".join(f"{n} {f.lower()}" for f, n in fuels.items()) + "; "
    f"{bands.get('near_760', 0)} near 760 mmHg, {bands.get('near_535', 0)} near 535 mmHg, "
    f"{bands.get('above_900', 0)} above 900 mmHg; "
    f"{diluents.get('CO2', 0)} with CO2, {diluents.get('He', 0)} with He, {diluents.get('none', 0)} with "
    "neither.\n"
    f"- Column meanings and units are documented in [NASA/TP-2015-216046]({lab.FLEX_REPORT_URL}) "
    "(Table IX and Appendix A.1); "
    "the team has not yet confirmed them against that report.")

st.subheader("Limits")
st.warning("\n".join(f"- {t}" for t in lab.LIMITS))
st.caption("Every number in this app is computed from the cleaned NASA table or from the model trained on it; "
           "see reports/audit.md and reports/validation.md in the repository.")
