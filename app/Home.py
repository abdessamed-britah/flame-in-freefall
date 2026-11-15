"""Flame in Freefall - entry point: navigation, shared look, and the landing page."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import catalog as cat  # noqa: E402
import lab  # noqa: E402
import retrieve  # noqa: E402
import theme  # noqa: E402

UNIFIED = ROOT / "data" / "unified" / "tests_conditions.csv"
LIVE_URL = "https://flame-in-freefall-1.streamlit.app/"
KEY = {"preset": "Moon Base (30% O2, ~535 mmHg)", "fuel": "Methanol", "suppressant": "CO2"}  # the key-finding case

st.set_page_config(page_title="Flame in Freefall", page_icon=":material/local_fire_department:", layout="wide")


@st.cache_data
def counts() -> dict:
    """The four landing-page numbers, each counted from its data file."""
    return {"investigations": len(cat.load_catalog()[0]),
            "unified": len(pd.read_csv(UNIFIED, usecols=["psi_id"])),
            "passages": len(retrieve.load_passages()),
            "flex": len(lab.load_clean())}


@st.cache_data
def key_finding() -> dict:
    """The Suppression Lab result for its default case, computed with the same functions as that page."""
    df = lab.load_clean()
    s = lab.slice_tests(df, KEY["preset"], KEY["fuel"], KEY["suppressant"])
    d0 = float(round(s["d0_mm"].median(), 2))
    pressure = lab.preset_pressure_mmhg(df, KEY["preset"])
    c = lab.curve(KEY["preset"], pressure, KEY["fuel"], KEY["suppressant"], d0, "d_ext_over_d0",
                  *lab.fraction_range(s))
    return {"sentence": lab.crossing_sentence(c, lab.DEFAULT_THRESHOLD, KEY["fuel"], KEY["suppressant"], d0),
            "pressure": pressure, "o2_base": lab.PRESETS[KEY["preset"]]["o2_base"], "tests": len(s)}


def landing() -> None:
    df = lab.load_clean()
    n = counts()
    st.title("Flame in Freefall")
    st.markdown("<p class='purpose'>A Moon Base will run on more oxygen at lower pressure than Earth: this is what "
                "NASA's microgravity combustion tests say about putting a fire out there.</p>",
                unsafe_allow_html=True)

    tiles = st.columns(4)
    tiles[0].metric("NASA investigations", f"{n['investigations']:,}", border=True,
                    help="Rows of data/catalog/investigations.csv (PSI, Combustion Science).")
    tiles[1].metric("Unified test rows", f"{n['unified']:,}", border=True,
                    help="Rows of data/unified/tests_conditions.csv, from 22 NASA tables.")
    tiles[2].metric("Passages of NASA text", f"{n['passages']:,}", border=True,
                    help="Rows of data/corpus/passages.jsonl, copied from the PSI records.")
    tiles[3].metric("FLEX droplet tests", f"{n['flex']:,}", border=True,
                    help="Rows of data/clean/flex_clean.csv (NASA PSI-69).")

    k = key_finding()
    theme.finding(f"**Key finding, Moon Base atmosphere ({k['o2_base']:.0%} O2 at about {k['pressure']:.0f} mmHg).** "
                  f"{k['sentence']}")
    theme.caveat(f"**Caveat.** This comes from {k['tests']} NASA tests on single fuel droplets, not cabin materials. "
                 f"Adding CO2 at a fixed O2/N2 balance also lowers O2 (40% CO2 brings {k['o2_base']:.0%} O2 down to "
                 f"{k['o2_base'] * 0.6:.0%}), so the data cannot separate the suppressant's effect from the lower "
                 "oxygen.")

    st.subheader("Explore")
    cards = [
        ("catalog", "Catalog", "Rank NASA's combustion investigations by relevance to a habitat, with weights you set."),
        ("unified", "Unified Data", "Plot and download the test conditions of every investigation, in the same units."),
        ("lab", "Suppression Lab", "See how much CO2 or He pushes a droplet flame to its extinction limit."),
        ("ask", "Ask NASA Records", "Ask a question and get an answer that cites NASA's own text, passage by passage."),
    ]
    for col, (key, name, line) in zip(st.columns(4), cards):
        with col.container(border=True):
            st.markdown(f"**{name}**")
            st.caption(line)
            if st.button(f"Open {name}", key=f"open_{key}", type="primary", width="stretch"):
                st.switch_page(PAGES[key])

    with st.expander("Sources and limitations"):
        fuels, bands, diluents = df["fuel"].value_counts(), df["pressure_band"].value_counts(), df["diluent"].value_counts()
        st.markdown(
            "**Sources**\n"
            "- NASA Physical Sciences Informatics (PSI), <https://psi.nasa.gov>: the records and experimental tables "
            f"of the {n['investigations']} Combustion Science investigations, fetched on 2026-11-14.\n"
            f"- **NASA PSI-69, Flame Extinguishment Experiment (FLEX)**, experimental table, CC0: "
            f"[doi.org/10.60555/mbq8-0451]({lab.PSI69_DOI_URL}). "
            f"{len(df)} droplet-combustion tests from {df['test_date'].min()} to {df['test_date'].max()}: "
            + ", ".join(f"{c} {f.lower()}" for f, c in fuels.items()) + "; "
            f"{bands.get('near_760', 0)} near 760 mmHg, {bands.get('near_535', 0)} near 535 mmHg, "
            f"{bands.get('above_900', 0)} above 900 mmHg; "
            f"{diluents.get('CO2', 0)} with CO2, {diluents.get('He', 0)} with He, {diluents.get('none', 0)} with "
            "neither.\n"
            f"- Column meanings and units are documented in [NASA/TP-2015-216046]({lab.FLEX_REPORT_URL}) "
            "(Table IX and Appendix A.1); the team has not yet confirmed them against that report.\n\n"
            "**Limitations**\n" + "\n".join(f"- {t}" for t in lab.LIMITS) + "\n\n"
            "Every number in this app is computed from NASA's tables or from the model trained on them; see "
            "reports/audit.md and reports/validation.md in the repository.")
    st.caption(f"Live app: [{LIVE_URL.removeprefix('https://').rstrip('/')}]({LIVE_URL}) · "
               "Data: NASA Physical Sciences Informatics (PSI), CC0. AI text is always labelled.")


PAGES = {
    "home": st.Page(landing, title="Home", icon=":material/home:", url_path="home", default=True),
    "catalog": st.Page("pages/1_Catalog.py", title="Catalog", icon=":material/format_list_numbered:",
                       url_path="catalog"),
    "unified": st.Page("pages/3_Unified_Data.py", title="Unified Data", icon=":material/scatter_plot:",
                       url_path="unified"),
    "lab": st.Page("pages/2_Suppression_Lab.py", title="Suppression Lab", icon=":material/science:",
                   url_path="lab"),
    "ask": st.Page("pages/4_Ask_NASA_Records.py", title="Ask NASA Records", icon=":material/forum:", url_path="ask"),
}

page = st.navigation(list(PAGES.values()))
theme.chrome()
page.run()
with st.sidebar:
    st.markdown(theme.FOOTER, unsafe_allow_html=True)
