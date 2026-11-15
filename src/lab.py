"""Logic behind the Suppression Lab page (Module B). No Streamlit in here, so
everything can be tested and reused.

Every number produced here comes from data/clean/flex_clean.csv, from
model.predict(), or from reports/validation.json (written by src/model.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from model import MMHG_PER_ATM, predict

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean" / "flex_clean.csv"
VALIDATION_JSON = ROOT / "reports" / "validation.json"
PHYSICS_NOTE = ROOT / "docs" / "physics_note.md"

PSI69_DOI_URL = "https://doi.org/10.60555/mbq8-0451"  # resolves to NASA's PSI-69 record
FLEX_REPORT_URL = "https://ntrs.nasa.gov/citations/20150023456"  # NASA/TP-2015-216046

# Base atmospheres. o2_base is the oxygen share of the O2/N2 mix before any
# suppressant is added; `band` is the group of NASA tests it is compared with.
PRESETS = {
    "Moon Base (30% O2, ~535 mmHg)": {"o2_base": 0.30, "band": "near_535"},
    "Earth-like / ISS (21% O2, ~760 mmHg)": {"o2_base": 0.21, "band": "near_760"},
}
BASE_TOL = 0.015        # a test belongs to a preset if its o2_base is this close (see reports/eda.md, A)
SUPPRESSANTS = ["CO2", "He"]
DEFAULT_THRESHOLD = 0.90  # the team's adjustable choice, not a NASA value
GRID_STEP = 0.005
BEYOND = 0.10           # how far past the tested range the charts extend, shaded

TARGET_LABEL = {"d_ext_over_d0": "Extinction ratio d_ext / d0",
                "burning_rate_k": "Burning rate K (unit unconfirmed)"}
AXIS_LABEL = {"d_ext_over_d0": "Extinction ratio d_ext / d0 (no unit)",
              "burning_rate_k": "Burning rate K (unit unconfirmed)"}
# CO2 is the warm accent, He the cool one, tests without suppressant are grey reference data (src/theme.py).
# Each series also has its own marker shape and line dash, so colour is never the only cue.
COLOR = {"CO2": "#e36a20", "He": "#4594ee", "none": "#9aa3b5"}
BAND_FILL = {"CO2": "rgba(227,106,32,0.20)", "He": "rgba(69,148,238,0.20)"}
SHAPE = {"CO2": "circle", "He": "diamond", "none": "square-open"}
DASH = {"CO2": "solid", "He": "dash"}
INK = "#eef1fa"
SERIES_NAME = {"CO2": "CO2", "He": "He", "none": "no suppressant"}

LIMITS = [
    "These are single fuel droplets (methanol, heptane), not cabin materials. "
    "The tool supports fire-safety reasoning; it does not predict a cabin fire.",
    "\"Visible flame extinction\" may not be the end of burning: FLEX found heptane droplets can keep "
    "burning in an invisible cool flame.",
    "Suppressant is added at constant total pressure, replacing part of the O2/N2 mix, as in the NASA tests.",
    "The burning-rate unit and the gas labels (O2, N2, CO2) are still unconfirmed: the NASA file header "
    "prints \"mm\" and \"O\", \"N\", \"CO\".",
    "The NASA table does not separate space tests from ground tests.",
]


def load_clean() -> pd.DataFrame:
    return pd.read_csv(CLEAN)


def load_validation() -> dict:
    return json.loads(VALIDATION_JSON.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# slices of the NASA table
# ---------------------------------------------------------------------------
def preset_tests(df: pd.DataFrame, preset: str) -> pd.DataFrame:
    """All tests of a preset: its pressure band and its o2_base, any fuel, any diluent."""
    p = PRESETS[preset]
    return df[(df["pressure_band"] == p["band"]) & ((df["o2_base"] - p["o2_base"]).abs() <= BASE_TOL)]


def slice_tests(df: pd.DataFrame, preset: str, fuel: str, suppressant: str) -> pd.DataFrame:
    """Tests of a preset for one fuel: those with the suppressant, plus the undiluted ones."""
    s = preset_tests(df, preset)
    return s[(s["fuel"] == fuel) & s["diluent"].isin([suppressant, "none"])]


def preset_pressure_mmhg(df: pd.DataFrame, preset: str) -> float:
    """Pressure used for predictions: the median pressure of the preset's tests."""
    return float(preset_tests(df, preset)["pressure_mmhg"].median())


def fraction_range(s: pd.DataFrame) -> tuple[float, float]:
    """Tested range of suppressant fraction in a slice (0 if undiluted tests exist)."""
    return float(s["diluent_frac"].min()), float(s["diluent_frac"].max())


def d0_range(s: pd.DataFrame) -> tuple[float, float]:
    return float(s["d0_mm"].min()), float(s["d0_mm"].max())


def chamber(o2_base: float, fraction: float) -> dict:
    """Gas fractions in the chamber once `fraction` of suppressant replaces the O2/N2 mix."""
    return {"o2": o2_base * (1 - fraction), "n2": (1 - o2_base) * (1 - fraction), "suppressant": fraction}


# ---------------------------------------------------------------------------
# model curves
# ---------------------------------------------------------------------------
def query(preset: str, pressure_mmhg: float, fuel: str, suppressant: str, fraction: float, d0_mm: float) -> dict:
    """Arguments for model.predict() for one point of a preset."""
    return {"fuel": fuel, "o2": chamber(PRESETS[preset]["o2_base"], fraction)["o2"],
            "pressure_atm": pressure_mmhg / MMHG_PER_ATM,
            "co2": fraction if suppressant == "CO2" else 0.0,
            "he": fraction if suppressant == "He" else 0.0, "d0_mm": d0_mm}


def curve(preset: str, pressure_mmhg: float, fuel: str, suppressant: str, d0_mm: float, target: str,
          lo: float, hi: float) -> pd.DataFrame:
    """predict() along the tested range [lo, hi] of suppressant fraction."""
    xs = np.round(np.arange(lo, hi + GRID_STEP / 2, GRID_STEP), 4)
    rows = []
    for x in xs:
        r = predict(**query(preset, pressure_mmhg, fuel, suppressant, float(x), d0_mm), target=target, n_nearest=0)
        rows.append({"fraction": float(x), "mean": r["mean"], "lower": r["lower"], "upper": r["upper"],
                     "in_range": r["in_range"]})
    return pd.DataFrame(rows)


def crossing(c: pd.DataFrame, threshold: float) -> dict:
    """First suppressant fraction at which the band's upper edge, the mean and
    the band's lower edge reach the threshold. None if not reached."""
    def first(col):
        hit = c.loc[c[col] >= threshold, "fraction"]
        return None if hit.empty else float(hit.iloc[0])
    return {"upper": first("upper"), "mean": first("mean"), "lower": first("lower")}


def crossing_sentence(c: pd.DataFrame, threshold: float, fuel: str, suppressant: str, d0_mm: float) -> str:
    """Plain-words answer to "how much suppressant to get near the limit?".
    "At least" is where the top of the 90% band reaches the threshold, the best
    estimate is where the model mean does, and the upper bound is where the
    bottom of the band does."""
    x = crossing(c, threshold)
    pct = lambda v: f"{int(np.ceil(v * 100 - 1e-9))}%"  # whole percent, rounded up ("at least")  # noqa: E731
    who = f"For a {d0_mm:.2f} mm {fuel.lower()} droplet: "
    stop = f"NASA's tests stop at {pct(c['fraction'].max())}"
    if x["upper"] is None:
        return (f"{who}not reached within the tested range. {stop} {suppressant}, and up to there the "
                f"prediction stays below the near-limit threshold of {threshold:.2f}.")
    best = (f"best estimate {pct(x['mean'])}" if x["mean"] is not None
            else "the best estimate lies beyond the tested range")
    if x["lower"] is None:
        return (f"{who}likely needs at least {pct(x['upper'])} {suppressant} ({best}). "
                f"{stop}, so the data cannot give an upper bound.")
    return f"{who}likely needs between {pct(x['upper'])} and {pct(x['lower'])} {suppressant} ({best})."


def explain_inputs(preset: str, fuel: str, suppressant: str, fraction: float, d0_mm: float, gas: dict,
                   pressure_mmhg: float, threshold: float, ratio: dict, rate: dict, sentence: str,
                   evidence: pd.DataFrame, cv: pd.DataFrame) -> tuple[list[str], str]:
    """For the "Explain this result" button: the facts the page already shows,
    and a plain template summary built from them (used when no AI is available)."""
    tests = ", ".join(f"test {int(t)}" for t in evidence["Test"])
    seen = evidence["d_ext / d0"].dropna()
    cv_ratio = cv[cv["Target"] == TARGET_LABEL["d_ext_over_d0"]].iloc[0]
    facts = [
        f"Base atmosphere: {preset}; pressure {pressure_mmhg:.0f} mmHg",
        f"Fuel: {fuel.lower()} droplet, initial diameter {d0_mm:.2f} mm",
        f"Suppressant: {suppressant} at mole fraction {fraction:.2f}; chamber O2 {gas['o2']:.3f}",
        f"Predicted extinction ratio d_ext/d0: {ratio['mean']:.2f}, 90% interval {ratio['lower']:.2f} to "
        f"{ratio['upper']:.2f} (near 1 means the flame went out almost at once; it cannot exceed 1)",
        f"Predicted burning rate K (unit unconfirmed): {rate['mean']:.2f}, 90% interval {rate['lower']:.2f} to "
        f"{rate['upper']:.2f}",
        f"Near-limit threshold chosen by the team (not a NASA value): {threshold:.2f}",
        f"Threshold finding: {sentence}",
        f"Inputs inside the range of NASA's tests: {'yes' if ratio['in_range'] and rate['in_range'] else 'no'}",
        f"Nearest NASA tests: {tests}"
        + (f"; their measured extinction ratios run from {seen.min():.2f} to {seen.max():.2f}" if len(seen) else ""),
        f"Typical model error for the extinction ratio on unseen tests (MAE): {cv_ratio['MAE']}; "
        f"mean baseline {cv_ratio['MAE of mean baseline']}",
        "Limits: single fuel droplets, not cabin materials; visible flame extinction may not be the end of burning",
    ]
    template = (
        f"With {fraction:.0%} {suppressant} in the {preset.split(' (')[0]} atmosphere, the model predicts an "
        f"extinction ratio of {ratio['mean']:.2f} (90% interval {ratio['lower']:.2f} to {ratio['upper']:.2f}) "
        f"for a {d0_mm:.2f} mm {fuel.lower()} droplet, against the team's near-limit threshold of "
        f"{threshold:.2f}. It {sentence.split(': ', 1)[-1]} The predicted burning rate is {rate['mean']:.2f} "
        f"(90% interval {rate['lower']:.2f} to {rate['upper']:.2f}; unit unconfirmed). "
        f"The closest real NASA tests are {tests}. "
        f"On tests it had not seen, the model's typical error for the extinction ratio was {cv_ratio['MAE']}. "
        "These are single fuel droplets, not cabin materials.")
    return facts, template


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
def _points(fig: go.Figure, s: pd.DataFrame, target: str, diluent: str) -> int:
    d = s[(s["diluent"] == diluent)].dropna(subset=[target])
    if d.empty:
        return 0
    fig.add_trace(go.Scatter(
        x=d["diluent_frac"], y=d[target], mode="markers",
        name=f"NASA tests, {SERIES_NAME[diluent]} ({len(d)})",
        marker=dict(color=COLOR[diluent], size=9, symbol=SHAPE[diluent],
                    line=dict(color=COLOR[diluent] if diluent == "none" else "#0b1020", width=1.5 if diluent == "none" else 1)),
        customdata=d[["test_number", "flex_identifier", "d0_mm", "test_date", "test_end"]].to_numpy(),
        hovertemplate=("Test %{customdata[0]} (%{customdata[1]})<br>d0 %{customdata[2]} mm<br>"
                       "%{customdata[3]}<br>Test end: %{customdata[4]}<br>"
                       "Suppressant fraction %{x:.2f}<br>Value %{y:.2f}<extra></extra>")))
    return len(d)


def _model(fig: go.Figure, c: pd.DataFrame, suppressant: str, d0_mm: float) -> None:
    fig.add_trace(go.Scatter(x=list(c["fraction"]) + list(c["fraction"][::-1]),
                             y=list(c["upper"]) + list(c["lower"][::-1]),
                             fill="toself", fillcolor=BAND_FILL[suppressant], line=dict(width=0),
                             name=f"90% band, {suppressant}", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=c["fraction"], y=c["mean"], mode="lines",
                             line=dict(color=COLOR[suppressant], width=2.5, dash=DASH[suppressant]),
                             name=f"Model mean, {suppressant}, d0 {d0_mm:.2f} mm",
                             customdata=c[["lower", "upper"]].to_numpy(),
                             hovertemplate=("Model, " + suppressant + " %{x:.3f}<br>mean %{y:.2f}<br>"
                                            "90% band %{customdata[0]:.2f} to %{customdata[1]:.2f}<extra></extra>")))


def _frame(fig: go.Figure, target: str, tested_hi: float, tested_lo: float, y_max: float, current: float | None):
    x_max = tested_hi + BEYOND
    fig.add_vrect(x0=tested_hi, x1=x_max, fillcolor="rgba(154,163,181,0.16)", line_width=0, layer="below",
                  annotation_text="no NASA tests", annotation_position="top right")
    if tested_lo > 0:
        fig.add_vrect(x0=0, x1=tested_lo, fillcolor="rgba(154,163,181,0.16)", line_width=0, layer="below",
                      annotation_text="no NASA tests here", annotation_position="top left")
    if current is not None:
        fig.add_vline(x=current, line=dict(color=COLOR["none"], width=1, dash="dot"),
                      annotation_text="your input", annotation_position="bottom right")
    fig.update_layout(xaxis_title="Suppressant (mole fraction)", yaxis_title=AXIS_LABEL[target],
                      xaxis=dict(range=[-0.01, x_max]), yaxis=dict(range=[0, y_max]), height=440)


def ratio_figure(s: pd.DataFrame, c: pd.DataFrame, suppressant: str, d0_mm: float, threshold: float,
                 current: float | None = None) -> go.Figure:
    """Output 1: d_ext_over_d0 against suppressant fraction, one suppressant."""
    fig = go.Figure()
    _model(fig, c, suppressant, d0_mm)
    _points(fig, s, "d_ext_over_d0", "none")
    _points(fig, s, "d_ext_over_d0", suppressant)
    fig.add_hline(y=threshold, line=dict(color=INK, width=1.5, dash="dot"),
                  annotation_text=f"near-limit threshold {threshold:.2f} (team's choice)",
                  annotation_position="bottom left")
    lo, hi = fraction_range(s)
    _frame(fig, "d_ext_over_d0", hi, lo, 1.05, current)
    return fig


def rate_figure(slices: dict[str, pd.DataFrame], curves: dict[str, pd.DataFrame], d0_mm: float,
                current: tuple[str, float] | None = None) -> go.Figure:
    """Output 3: burning rate against suppressant fraction, CO2 and He overlaid."""
    fig = go.Figure()
    for sup, c in curves.items():
        _model(fig, c, sup, d0_mm)
    any_slice = next(iter(slices.values()))
    _points(fig, any_slice, "burning_rate_k", "none")
    for sup, s in slices.items():
        _points(fig, s, "burning_rate_k", sup)
    his = [fraction_range(s)[1] for s in slices.values()]
    los = [fraction_range(s)[0] for s in slices.values()]
    y_top = max(max(c["upper"].max() for c in curves.values()),
                max(s["burning_rate_k"].max() for s in slices.values()))
    _frame(fig, "burning_rate_k", max(his), min(los), float(np.ceil(y_top * 10) / 10 + 0.1),
           current[1] if current else None)
    return fig


# ---------------------------------------------------------------------------
# evidence and trust
# ---------------------------------------------------------------------------
def evidence_table(df: pd.DataFrame, q: dict) -> pd.DataFrame:
    """The 5 nearest real tests for the current inputs, from predict()."""
    near = pd.DataFrame(predict(**q, target="d_ext_over_d0")["nearest_tests"])
    near = near.merge(df[["test_number", "test_date", "pressure_mmhg"]], on="test_number", how="left")
    return near.rename(columns={
        "test_number": "Test", "flex_identifier": "Identifier", "test_date": "Date", "fuel": "Fuel",
        "pressure_mmhg": "Pressure (mmHg)", "o2_mole_frac": "O2", "co2_mole_frac": "CO2", "he_mole_frac": "He",
        "d0_mm": "d0 (mm)", "burning_rate_k": "Burning rate K", "d_ext_over_d0": "d_ext / d0",
        "test_end": "Test end", "quality_flag": "Quality flag", "distance": "Distance"})[
        ["Test", "Identifier", "Date", "Fuel", "Pressure (mmHg)", "O2", "CO2", "He", "d0 (mm)",
         "Burning rate K", "d_ext / d0", "Test end", "Quality flag", "Distance"]]


def trust_tables(v: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Grouped-CV and leave-one-diluent-out results of the chosen models, with
    the mean baseline beside them. All values come from reports/validation.json."""
    def pick(rows, target, model, feats, **extra):
        for r in rows:
            if (r["target"] == target and r["model"] == model and r["features"] == feats
                    and r["k_outlier_included"] and all(r[k] == val for k, val in extra.items())):
                return r
        raise KeyError((target, model, feats, extra))

    cv, lodo = [], []
    for target, ch in v["chosen"].items():
        m = pick(v["group_kfold"], target, ch["model"], ch["features"])
        b = pick(v["group_kfold"], target, "Mean baseline", "none")
        cv.append({"Target": TARGET_LABEL[target], "Model": ch["model"], "Tests": m["n"],
                   "MAE": round(m["mae"], 3), "MAE of mean baseline": round(b["mae"], 3),
                   "R2": round(m["r2"], 2), "Coverage of 90% interval": f"{m['coverage']:.0%}"})
        for held in SUPPRESSANTS:
            m = pick(v["leave_diluent_out"], target, ch["model"], ch["features"], held_out=held)
            b = pick(v["leave_diluent_out"], target, "Mean baseline", "none", held_out=held)
            lodo.append({"Target": TARGET_LABEL[target], "Suppressant never seen in training": held,
                         "Tests": m["n"], "MAE": round(m["mae"], 3),
                         "MAE when it was seen": round(m["mae_group_kfold"], 3),
                         "Times worse": f"{m['times_worse']:.1f}x",
                         "MAE of mean baseline": round(b["mae"], 3),
                         "Coverage of 90% interval": f"{m['coverage']:.0%}"})
    return pd.DataFrame(cv), pd.DataFrame(lodo)
