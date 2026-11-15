"""Module B - Moon Base Suppression Lab (FLEX, NASA PSI-69)."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import ai  # noqa: E402
import lab  # noqa: E402
import theme  # noqa: E402
from model import predict  # noqa: E402


@st.cache_data
def clean_data():
    return lab.load_clean()


@st.cache_data
def validation():
    return lab.load_validation()


@st.cache_data
def model_curve(preset, pressure_mmhg, fuel, suppressant, d0_mm, target, lo, hi):
    return lab.curve(preset, pressure_mmhg, fuel, suppressant, d0_mm, target, lo, hi)


@st.cache_data
def point(q: dict, target: str):
    return predict(**q, target=target)


df = clean_data()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Atmosphere and droplet")
    preset = st.radio("Base atmosphere", list(lab.PRESETS), index=0)
    fuel = st.selectbox("Fuel", sorted(df["fuel"].unique(), reverse=True))
    suppressant = st.radio("Suppressant", lab.SUPPRESSANTS, horizontal=True)

    s = lab.slice_tests(df, preset, fuel, suppressant)
    d_lo, d_hi = lab.d0_range(s)
    d0_mm = st.slider("Droplet diameter d0 (mm)", d_lo, d_hi, float(round(s["d0_mm"].median(), 2)), 0.01,
                      help=f"Limited to the droplets NASA tested in this slice: {d_lo:.2f} to {d_hi:.2f} mm.")
    f_lo, f_hi = lab.fraction_range(s)
    diluted = s[s["diluent"] == suppressant]
    fraction = st.slider(f"{suppressant} mole fraction", f_lo, f_hi, float(diluted["diluent_frac"].median()), 0.01,
                         help=f"Limited to the range NASA tested in this slice: {f_lo:.2f} to {f_hi:.2f}.")
    threshold = st.slider("Near-limit threshold for d_ext / d0", 0.50, 1.00, lab.DEFAULT_THRESHOLD, 0.01,
                          help="The team's adjustable choice, not a NASA value. A ratio near 1 means the "
                               "flame went out almost at once.")

o2_base = lab.PRESETS[preset]["o2_base"]
pressure_mmhg = lab.preset_pressure_mmhg(df, preset)
gas = lab.chamber(o2_base, fraction)
q = lab.query(preset, pressure_mmhg, fuel, suppressant, fraction, d0_mm)

# ---------------------------------------------------------------- header
theme.header("Moon Base Suppression Lab",
             f"How much CO2 or He pushes a burning fuel droplet to its extinction limit, from NASA's FLEX tests "
             f"(<a href='{lab.PSI69_DOI_URL}'>PSI-69</a>).")
theme.caveat("Single fuel droplets, not cabin materials: this supports fire-safety reasoning, it does not predict "
             "a cabin fire.")

n_preset = len(lab.preset_tests(df, preset))
ratio_now, rate_now = point(q, "d_ext_over_d0"), point(q, "burning_rate_k")
if not (ratio_now["in_range"] and rate_now["in_range"]):
    st.error("**Outside the range of the NASA data.** " + " ".join(
        sorted(set(ratio_now["warnings"] + rate_now["warnings"]))) + " Treat the numbers below as unsupported.",
        icon=":material/error:")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Predicted d_ext / d0", f"{ratio_now['mean']:.2f}",
          f"90% interval {ratio_now['lower']:.2f} to {ratio_now['upper']:.2f}", delta_color="off", delta_arrow="off",
          help="Extinction ratio. Near 1: the flame went out almost at once (close to the limit). Small: most of the droplet burned.")
m2.metric("Predicted K, unit unconfirmed", f"{rate_now['mean']:.2f}",
          f"90% interval {rate_now['lower']:.2f} to {rate_now['upper']:.2f}", delta_color="off", delta_arrow="off",
          help="Burning rate K. The NASA header prints the unit as \"mm\"; it is still unconfirmed.")
m3.metric("Chamber O2 (mole frac.)", f"{gas['o2']:.3f}",
          help=f"o2_base x (1 - suppressant fraction) = {o2_base:.2f} x (1 - {fraction:.2f})")
m4.metric("Pressure (mmHg)", f"{pressure_mmhg:.0f}",
          help=f"Median of the {n_preset} NASA tests of this base atmosphere.")

# ---------------------------------------------------------------- 1
st.subheader("1. How close to the extinction limit?")
ratio_curve = model_curve(preset, pressure_mmhg, fuel, suppressant, d0_mm, "d_ext_over_d0", f_lo, f_hi)
theme.chart(lab.ratio_figure(s, ratio_curve, suppressant, d0_mm, threshold, fraction))
sentence = lab.crossing_sentence(ratio_curve, threshold, fuel, suppressant, d0_mm)
theme.finding(sentence)
theme.caveat(f"**More {suppressant} also means less oxygen.** Adding diluent at a fixed O2/N2 balance lowers "
             f"O2 as well: 40% {suppressant} brings {o2_base:.0%} O2 down to {o2_base * 0.6:.0%} "
             f"({o2_base:.2f} x (1 - 0.40)). The data cannot separate the diluent's effect from the lower oxygen.")
n_ratio = int(s["d_ext_over_d0"].notna().sum())
with st.expander("How to read this chart"):
    st.markdown(
        f"- Points are the {n_ratio} NASA tests of this slice that have an extinction ratio ({len(s) - n_ratio} "
        f"more tests have none and are not drawn). They cover droplets of {d_lo:.2f} to {d_hi:.2f} mm; the line "
        f"is for {d0_mm:.2f} mm. Hover a point for its test number.\n"
        "- The ratio cannot exceed 1 (the flame cannot go out at a diameter larger than the droplet started "
        "with), so the model line and band are cut off at 1.\n"
        "- \"At least\" is where the top of the 90% band reaches the threshold; the best estimate is where the "
        "model line does. Percentages are mole fractions of suppressant.\n"
        "- The threshold is the team's adjustable choice, not a NASA value.\n"
        f"- Chamber: O2 {gas['o2']:.3f}, N2 {gas['n2']:.3f}, {suppressant} {gas['suppressant']:.2f}. O2 is not a "
        "free input because in NASA's tests the suppressant replaces part of a fixed O2/N2 mix.")

# ---------------------------------------------------------------- 2
st.subheader("2. Burning rate: CO2 against He")
slices = {sup: lab.slice_tests(df, preset, fuel, sup) for sup in lab.SUPPRESSANTS}
slices = {sup: sl for sup, sl in slices.items() if (sl["diluent"] == sup).any()}
curves = {sup: model_curve(preset, pressure_mmhg, fuel, sup, d0_mm, "burning_rate_k", *lab.fraction_range(sl))
          for sup, sl in slices.items()}
theme.chart(lab.rate_figure(slices, curves, d0_mm, (suppressant, fraction)))
st.caption("Each model line stops where NASA's tests for that suppressant stop. "
           "The burning-rate unit is unconfirmed (the NASA header prints \"mm\").")

# ---------------------------------------------------------------- 3
st.subheader("3. Evidence: the 5 nearest NASA tests")
evidence = lab.evidence_table(df, q)
st.dataframe(evidence, hide_index=True, width="stretch", column_config={
    "O2": st.column_config.NumberColumn("O2 (mole fraction)", format="%.2f"),
    "CO2": st.column_config.NumberColumn("CO2 (mole fraction)", format="%.2f"),
    "He": st.column_config.NumberColumn("He (mole fraction)", format="%.2f"),
    "Pressure (mmHg)": st.column_config.NumberColumn(format="%.0f"),
    "d0 (mm)": st.column_config.NumberColumn(format="%.2f"),
    "Burning rate K": st.column_config.NumberColumn("Burning rate K (unit unconfirmed)", format="%.3f"),
    "d_ext / d0": st.column_config.ProgressColumn("d_ext / d0 (0 to 1)", format="%.2f", min_value=0, max_value=1),
    "Distance": st.column_config.NumberColumn(format="%.2f", help="Over O2, pressure, CO2, He and d0, each divided "
                                              "by its standard deviation across the tests; smaller is closer.")})
st.caption("Same fuel only. Empty cells are values NASA did not report.")

# ---------------------------------------------------------------- explain
st.subheader("4. Explain this result")
if st.button("Explain this result", type="primary"):
    cv_now, _ = lab.trust_tables(validation())
    facts, template = lab.explain_inputs(preset, fuel, suppressant, fraction, d0_mm, gas, pressure_mmhg,
                                         threshold, ratio_now, rate_now, sentence, evidence, cv_now)
    with st.spinner("Writing the explanation..."):
        out = ai.explain_result(facts, template)
    st.caption(out["label"])
    st.write(out["text"])
    if out["note"]:
        st.caption(out["note"])
else:
    st.caption("Writes a short interpretation of the numbers on this page. "
               + ("Uses AI; the text may only use numbers already shown here." if ai.has_key()
                  else f"No AI key is set ({ai.KEY_ENV}), so a template summary is shown instead."))

# ---------------------------------------------------------------- details
st.subheader("Details")
with st.expander("How far to trust this (validation)"):
    v = validation()
    cv, lodo = lab.trust_tables(v)
    st.markdown(f"**Tests the model has not seen, grouped by test date ({v['n_folds']} folds).** "
                "MAE is the typical error; coverage is how often the measured value fell inside the 90% interval.")
    st.dataframe(cv, hide_index=True, width="stretch")
    st.markdown("**Honesty test: a suppressant the model has never seen.** Trained without any test of that "
                "suppressant, then scored on those tests.")
    st.dataframe(lodo, hide_index=True, width="stretch")
    st.caption("Source: reports/validation.json, written by src/model.py. If \"MAE\" is close to \"MAE of mean "
               "baseline\", the model is no better than guessing the average for that suppressant.")
with st.expander("Limits of this tool"):
    st.markdown("\n".join(f"- {t}" for t in lab.LIMITS))
with st.expander("Physics comparison (d2-law)"):
    if lab.PHYSICS_NOTE.exists():
        st.markdown(lab.PHYSICS_NOTE.read_text(encoding="utf-8"))
    else:
        st.markdown("d2-law baseline pending.")
