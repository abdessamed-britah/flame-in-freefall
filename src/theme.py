"""Shared look of the app: colours, one Plotly template, callouts and the sidebar footer.

The Streamlit theme itself is in .streamlit/config.toml; the colours here match it.
Series colours were checked for colour-blind separation on the dark background;
every series also has its own marker shape, so colour is never the only cue.
"""
from __future__ import annotations

import re
from html import escape

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

FLAME = "#e36a20"   # warm accent: primary series, key numbers
BLUE = "#4594ee"    # cool accent: secondary series
GREY = "#9aa3b5"    # reference data
TEXT = "#eef1fa"
MUTED = "#aab2c8"
GRID = "rgba(238,241,250,0.10)"
PANEL = "#151c33"
FONT = '"Source Sans", "Source Sans Pro", "Segoe UI", sans-serif'

# cycled together: an investigation is identified by its shape first, its colour second
SERIES_COLOURS = [FLAME, BLUE, GREY]
SERIES_SHAPES = ["circle", "diamond", "square", "triangle-up", "cross", "x", "triangle-down", "star",
                 "pentagon", "hexagram", "triangle-left", "triangle-right"]

TEMPLATE = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family=FONT, color=TEXT, size=14),
    colorway=SERIES_COLOURS,
    xaxis=dict(gridcolor=GRID, zeroline=False, linecolor="rgba(238,241,250,0.35)", ticks="outside",
               tickcolor="rgba(238,241,250,0.35)", title=dict(font=dict(color=MUTED)), automargin=True),
    yaxis=dict(gridcolor=GRID, zeroline=False, linecolor="rgba(238,241,250,0.35)", ticks="outside",
               tickcolor="rgba(238,241,250,0.35)", title=dict(font=dict(color=MUTED)), automargin=True),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
    hoverlabel=dict(bgcolor=PANEL, bordercolor="#2a3352", font=dict(family=FONT, color=TEXT)),
    margin=dict(l=10, r=10, t=70, b=10), hovermode="closest",
))
pio.templates["flame"] = TEMPLATE

CHART_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}


def chart(fig: go.Figure) -> None:
    """Every chart of the app goes through here: same template, SVG traces, no Streamlit re-theming."""
    fig.update_layout(template="flame")
    st.plotly_chart(fig, width="stretch", theme=None, config=CHART_CONFIG)


def header(title: str, purpose: str) -> None:
    st.title(title)
    st.markdown(f"<p class='purpose'>{purpose}</p>", unsafe_allow_html=True)


def caveat(text: str) -> None:
    """A limit of the data or the method."""
    st.warning(text, icon=":material/warning:")


def finding(text: str) -> None:
    """A result the reader should take away: a panel with the flame accent. `**bold**` is supported."""
    html = re.sub(r"\*\*(.+?)\*\*", lambda m: "<strong>" + m.group(1) + "</strong>", escape(text))
    st.markdown(f"<div class='finding'>{html}</div>", unsafe_allow_html=True)


def note(text: str) -> None:
    st.info(text, icon=":material/info:")


CSS = """
<style>
p.purpose {font-size: 1.1rem; color: #aab2c8; margin: -0.6rem 0 1rem 0;}
[data-testid="stMetricValue"] {color: #ff8a3d;}
.finding {background: #151c33; border-left: 4px solid #e36a20; border-radius: 0.5rem; padding: 0.9rem 1.1rem;
          margin: 0 0 1rem 0; font-size: 1.08rem; line-height: 1.5; color: #eef1fa;}
.finding strong {color: #ff8a3d;}
[data-testid="stSidebarNav"] {padding-bottom: 0.5rem;}
.side-footer {font-size: 0.8rem; color: #aab2c8; line-height: 1.5; border-top: 1px solid #2a3352; padding-top: 0.7rem;}
@media (max-width: 640px) {
  h1 {font-size: 1.9rem !important;}
  [data-testid="stMainBlockContainer"] {padding-left: 1rem; padding-right: 1rem;}
}
</style>
"""
FOOTER = ("<div class='side-footer'>Data: NASA Physical Sciences Informatics (PSI), CC0.<br>"
          "AI text is always labelled.</div>")


def chrome() -> None:
    """Called once per run by the router (app/Home.py)."""
    st.markdown(CSS, unsafe_allow_html=True)
