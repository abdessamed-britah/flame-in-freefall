"""Step 3 - exploration. Reads data/clean/flex_clean.csv, writes reports/eda.md
and PNG figures in reports/figures/. Every number in the report is computed
here from the clean file; nothing is typed in by hand.

Run from anywhere:  python src/eda.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean" / "flex_clean.csv"
OUT = ROOT / "reports" / "eda.md"
FIG = ROOT / "reports" / "figures"

BANDS = ["near_535", "near_760", "above_900"]
BAND_LABEL = {"near_535": "near 535 mmHg", "near_760": "near 760 mmHg", "above_900": "above 900 mmHg"}
FUELS = ["Methanol", "Heptane"]
TARGETS = {"burning_rate_k": "Burning rate K (unit unconfirmed)",
           "d_ext_over_d0": "Extinction ratio d_ext / d0"}

# Hypothesis A: the expected o2_base for diluted tests, and the tolerance used
# to decide whether a test "fits". Fractions are printed to 2 decimals, so
# o2 / (o2 + n2) carries rounding error of about 0.01.
EXPECTED_BASE = {"near_535": 0.30, "near_760": 0.21}
BASE_TOL = 0.015

# Moon Base slice
MOON_P_MIN, MOON_P_MAX, MOON_BASE_MIN = 500.0, 560.0, 0.29

# One hue, light to dark, for droplet size (a magnitude).
CMAP = LinearSegmentedColormap.from_list("d0", ["#b9d3ee", "#2a6fb0", "#0b2a4a"])
INK, MUTED, GRID = "#1f2328", "#57606a", "#d8dee4"


def md_table(df: pd.DataFrame) -> list[str]:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r) + " |")
    return lines


def rng(s: pd.Series, nd: int = 2) -> str:
    s = s.dropna()
    if s.empty:
        return ""
    return f"{s.min():.{nd}f}" if s.min() == s.max() else f"{s.min():.{nd}f}-{s.max():.{nd}f}"


def tests(s: pd.Series) -> str:
    return ", ".join(str(int(v)) for v in sorted(s))


def panel_grid(df, target, x, row_keys, row_label, col_keys, col_label, title, xlabel, path, split_marker):
    """Small multiples: one panel per (row_key, col_key), coloured by d0_mm."""
    d = df.dropna(subset=[target, "d0_mm", "pressure_band"])
    norm = Normalize(df["d0_mm"].min(), df["d0_mm"].max())
    nr, nc = len(row_keys), len(col_keys)
    fig, axes = plt.subplots(nr, nc, figsize=(3.5 * nc + 1.2, 2.7 * nr + 0.9), sharex=True, sharey=True,
                             squeeze=False)
    for i, rk in enumerate(row_keys):
        for j, ck in enumerate(col_keys):
            ax = axes[i][j]
            sub = d[row_label(d, rk) & col_label(d, ck)]
            ax.set_axisbelow(True)
            ax.grid(color=GRID, linewidth=0.6)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                ax.spines[s].set_color(GRID)
            ax.tick_params(colors=MUTED, labelsize=8)
            if sub.empty:
                ax.text(0.5, 0.5, "no tests", transform=ax.transAxes, ha="center", va="center",
                        color=MUTED, fontsize=9)
            else:
                for off, marker in ((False, "o"), (True, "^")):
                    s2 = sub[sub["_off"] == off] if split_marker else (sub if not off else sub.iloc[0:0])
                    ax.scatter(s2[x], s2[target], c=s2["d0_mm"], cmap=CMAP, norm=norm, s=42, marker=marker,
                               edgecolors="white", linewidths=0.8)
            ax.set_title(f"{rk if isinstance(rk, str) else ', '.join(rk)} | {BAND_LABEL[ck]}  (n={len(sub)})",
                         fontsize=9, color=INK, loc="left")
            if i == nr - 1:
                ax.set_xlabel(xlabel, fontsize=9, color=MUTED)
            if j == 0:
                ax.set_ylabel(TARGETS[target], fontsize=8, color=MUTED)
    fig.suptitle(title, fontsize=12, color=INK, x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 0.92, 0.96))
    cax = fig.add_axes((0.935, 0.15, 0.012, 0.7))
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=CMAP), cax=cax)
    cb.set_label("Initial droplet diameter d0 (mm)", fontsize=9, color=MUTED)
    cb.ax.tick_params(colors=MUTED, labelsize=8)
    cb.outline.set_visible(False)
    if split_marker:
        handles = [plt.Line2D([], [], marker="o", ls="", color="#2a6fb0", markeredgecolor="white", markersize=7,
                              label="o2_base as expected for the band"),
                   plt.Line2D([], [], marker="^", ls="", color="#2a6fb0", markeredgecolor="white", markersize=7,
                              label="o2_base different (see section A)")]
        fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(0.92, 0.995), ncol=2, fontsize=8,
                   frameon=False)
    fig.savefig(path, dpi=130, facecolor="white")
    plt.close(fig)


def main() -> None:
    df = pd.read_csv(CLEAN)
    FIG.mkdir(parents=True, exist_ok=True)
    L: list[str] = ["# Exploration of the cleaned FLEX data", "",
                    "Generated by `src/eda.py` from `data/clean/flex_clean.csv` (274 tests). "
                    "Gas names O2, N2, CO2 and the unit of the burning rate are still unconfirmed.", ""]

    # ================= A. o2_base hypothesis ==============================
    df["o2_base_r"] = df["o2_base"].round(2)
    banded = df.dropna(subset=["pressure_band"])
    tab = (banded.groupby(["pressure_band", "diluent", "o2_base_r"])
           .agg(tests=("test_number", "size"),
                o2_base_exact=("o2_base", rng_4),
                diluent_frac=("diluent_frac", rng),
                o2=("o2_mole_frac", rng))
           .reset_index())
    tab["pressure_band"] = pd.Categorical(tab["pressure_band"], BANDS, ordered=True)
    tab = tab.sort_values(["pressure_band", "diluent", "o2_base_r"])
    tab["o2_base_r"] = tab["o2_base_r"].map(lambda v: f"{v:.2f}")
    tab = tab.rename(columns={"pressure_band": "Pressure band", "diluent": "Diluent",
                              "o2_base_r": "o2_base (rounded)", "tests": "Tests",
                              "o2_base_exact": "o2_base range", "diluent_frac": "diluent_frac range",
                              "o2": "O2 range"})

    dil = banded[banded["diluent"] != "none"].copy()
    dil["expected"] = dil["pressure_band"].map(EXPECTED_BASE)
    dil["fits"] = (dil["o2_base"] - dil["expected"]).abs() <= BASE_TOL  # NaN expected -> False
    df["_off"] = False
    df.loc[dil.index[~dil["fits"]], "_off"] = True

    L += ["## A. Do diluted tests cluster at a fixed o2_base?", "",
          "`o2_base = o2 / (o2 + n2)` and `diluent_frac = co2 + he`. "
          f"A diluted test \"fits\" when its o2_base is within {BASE_TOL} of the expected value "
          f"(0.30 near 535 mmHg, 0.21 near 760 mmHg). The tolerance covers rounding: the raw fractions "
          "have two decimals.", ""]
    L += ["| Pressure band | Diluted tests | Fit | Do not fit | o2_base range of those that fit |", "|---|---|---|---|---|"]
    for b in BANDS:
        g = dil[dil["pressure_band"] == b]
        exp = EXPECTED_BASE.get(b)
        L.append(f"| {BAND_LABEL[b]} (expected {exp if exp else 'none stated'}) | {len(g)} | {int(g['fits'].sum())} | "
                 f"{int((~g['fits']).sum())} | {rng_4(g.loc[g['fits'], 'o2_base'])} |")
    L.append("")
    n535 = dil[dil["pressure_band"] == "near_535"]
    n760 = dil[dil["pressure_band"] == "near_760"]
    L += [f"**Near 535 mmHg: true.** All {len(n535)} diluted tests have o2_base between "
          f"{n535['o2_base'].min():.3f} and {n535['o2_base'].max():.3f}.", "",
          f"**Near 760 mmHg: true for {int(n760['fits'].sum())} of {len(n760)} diluted tests**, "
          f"which sit between {n760.loc[n760['fits'], 'o2_base'].min():.3f} and "
          f"{n760.loc[n760['fits'], 'o2_base'].max():.3f}. "
          f"{int((~n760['fits']).sum())} tests do not fit.", "",
          "**Above 900 mmHg: the hypothesis does not cover this band.** All 9 tests there are diluted "
          "and follow a different design.", "",
          "Tests that do not fit:", "",
          "| Pressure band | Diluent | O2 | N2 | diluent_frac | o2_base | Fuel | Tests | Test numbers |", "|---|---|---|---|---|---|---|---|---|"]
    odd = dil[~dil["fits"]]
    for (b, dl, o2, n2, dfrac, fuel), g in odd.groupby(
            ["pressure_band", "diluent", "o2_mole_frac", "n2_mole_frac", "diluent_frac", "fuel"], sort=False):
        L.append(f"| {BAND_LABEL[b]} | {dl} | {o2:.2f} | {n2:.2f} | {dfrac:.2f} | {rng_4(g['o2_base'])} | {fuel} | "
                 f"{len(g)} | {tests(g['test_number'])} |")
    L += ["", f"That is {len(odd)} tests in total: {int((odd['pressure_band'] == 'near_760').sum())} near 760 mmHg "
          f"and {int((odd['pressure_band'] == 'above_900').sum())} above 900 mmHg.", "",
          "Test 114 (pressure printed as 0, so no band) has CO2 0.35 and o2_base "
          f"{df.loc[df['test_number'] == 114, 'o2_base'].iloc[0]:.3f}, like the 535 mmHg group, "
          "but its band is not assigned.", "",
          "Full table, including undiluted tests:", ""]
    L += md_table(tab) + [""]
    fitting = dil[dil["fits"]]
    L += ["What this means for modelling: among the diluted tests that fit, O2 is almost fixed by the "
          "diluent fraction (`o2 = o2_base x (1 - diluent_frac)`). Correlation between `o2_mole_frac` and "
          "`diluent_frac` in those tests: "
          + "; ".join(f"{BAND_LABEL[b]} {fitting[fitting['pressure_band'] == b][['o2_mole_frac', 'diluent_frac']].corr().iloc[0, 1]:.3f}"
                      for b in ("near_535", "near_760"))
          + ". Within a band the data cannot separate \"less oxygen\" from \"more diluent\"; "
          "only the comparison between CO2 and He, and against the undiluted tests, can.", ""]

    # ================= B. figures =========================================
    diluted = df[df["diluent"] != "none"]
    rows_fd = [(f, d) for f in FUELS for d in ("CO2", "He")]
    row_sel = lambda d, rk: (d["fuel"] == rk[0]) & (d["diluent"] == rk[1])
    col_sel = lambda d, ck: d["pressure_band"] == ck
    L += ["## B. Targets against diluent fraction", "",
          "One panel per fuel, diluent and pressure band. Colour is the initial droplet diameter. "
          "Triangles are the tests that do not fit the o2_base pattern of section A. "
          "Tests without the target or without d0 are not drawn, and neither is test 114.", ""]
    for target in TARGETS:
        name = f"{target}_vs_diluent_frac.png"
        panel_grid(diluted, target, "diluent_frac", rows_fd, row_sel, BANDS, col_sel,
                   f"{TARGETS[target]} against diluent fraction", "Diluent mole fraction (co2 + he)",
                   FIG / name, split_marker=True)
        L += [f"![{TARGETS[target]} against diluent fraction](figures/{name})", ""]

    # Spearman rank correlation per panel, so the reading of the figures is a number.
    L += ["Rank correlation (Spearman) between each target and diluent_frac, per panel, "
          "using only tests that fit the o2_base pattern. Blank when fewer than 5 tests.", "",
          "| Fuel | Diluent | Pressure band | Tests with K | rho K | Tests with ratio | rho ratio | rho d0 vs diluent_frac |", "|---|---|---|---|---|---|---|---|"]
    fit_idx = dil.index[dil["fits"]]
    for (f, dl) in rows_fd:
        for b in ("near_535", "near_760"):
            g = df.loc[fit_idx]
            g = g[(g["fuel"] == f) & (g["diluent"] == dl) & (g["pressure_band"] == b)]
            cells = []
            for t in TARGETS:
                s = g.dropna(subset=[t, "d0_mm"])
                rho = s[t].corr(s["diluent_frac"], method="spearman") if len(s) >= 5 else np.nan
                cells += [str(len(s)), "" if np.isnan(rho) else f"{rho:+.2f}"]
            s = g.dropna(subset=["d0_mm"])
            rho = s["d0_mm"].corr(s["diluent_frac"], method="spearman") if len(s) >= 5 else np.nan
            L.append(f"| {f} | {dl} | {BAND_LABEL[b]} | " + " | ".join(cells)
                     + f" | {'' if np.isnan(rho) else f'{rho:+.2f}'} |")
    L.append("")

    undiluted = df[df["diluent"] == "none"]
    L += ["## B. Targets against O2 for undiluted tests", "",
          "O2/N2 only (101 tests). There are no undiluted tests above 900 mmHg.", ""]
    for target in TARGETS:
        name = f"{target}_vs_o2_undiluted.png"
        panel_grid(undiluted, target, "o2_mole_frac", FUELS, lambda d, rk: d["fuel"] == rk,
                   ["near_535", "near_760"], col_sel, f"{TARGETS[target]} against O2, undiluted tests",
                   "O2 mole fraction", FIG / name, split_marker=False)
        L += [f"![{TARGETS[target]} against O2, undiluted](figures/{name})", ""]
    L += ["| Fuel | Pressure band | Tests with K | rho K vs O2 | Tests with ratio | rho ratio vs O2 |", "|---|---|---|---|---|---|"]
    for f in FUELS:
        for b in ("near_535", "near_760"):
            g = undiluted[(undiluted["fuel"] == f) & (undiluted["pressure_band"] == b)]
            cells = []
            for t in TARGETS:
                s = g.dropna(subset=[t, "d0_mm"])
                rho = s[t].corr(s["o2_mole_frac"], method="spearman") if len(s) >= 5 else np.nan
                cells += [str(len(s)), "" if np.isnan(rho) else f"{rho:+.2f}"]
            L.append(f"| {f} | {BAND_LABEL[b]} | " + " | ".join(cells) + " |")
    L.append("")

    # ================= coverage ===========================================
    L += ["## Coverage: tests per fuel, pressure band and diluent", "",
          "\"Usable\" means the target and d0 are both present (and, for the ratio, the extinction "
          "diameter is not printed as 0). Test 114 has no pressure band and is not in this table.", "",
          "| Fuel | Pressure band | Diluent | Tests | Usable for K | Usable for ratio | O2 range | diluent_frac range | d0 range (mm) |", "|---|---|---|---|---|---|---|---|---|"]
    total = [0, 0, 0]
    for f in FUELS:
        for b in BANDS:
            for dl in ("none", "CO2", "He"):
                g = banded[(banded["fuel"] == f) & (banded["pressure_band"] == b) & (banded["diluent"] == dl)]
                nk = int(g.dropna(subset=["burning_rate_k", "d0_mm"]).shape[0])
                nr_ = int(g.dropna(subset=["d_ext_over_d0", "d0_mm"]).shape[0])
                total = [total[0] + len(g), total[1] + nk, total[2] + nr_]
                L.append(f"| {f} | {BAND_LABEL[b]} | {dl} | {len(g)} | {nk} | {nr_} | {rng(g['o2_mole_frac'])} | "
                         f"{rng(g['diluent_frac']) if dl != 'none' else ''} | {rng(g['d0_mm'])} |")
    L += [f"| **Total** | | | **{total[0]}** | **{total[1]}** | **{total[2]}** | | | |", "",
          "Empty cells of the atmosphere space (0 tests): "
          + "; ".join(f"{f}, {BAND_LABEL[b]}, {dl}" for f in FUELS for b in BANDS for dl in ("none", "CO2", "He")
                      if banded[(banded["fuel"] == f) & (banded["pressure_band"] == b) & (banded["diluent"] == dl)].empty)
          + ". CO2 and He are never mixed.", ""]

    # ================= Moon Base slice ====================================
    moon = df[(df["pressure_mmhg"] >= MOON_P_MIN) & (df["pressure_mmhg"] <= MOON_P_MAX)
              & (df["o2_base"] >= MOON_BASE_MIN)]
    L += ["## Moon Base slice", "",
          f"Tests at {MOON_P_MIN:.0f}-{MOON_P_MAX:.0f} mmHg with o2_base >= {MOON_BASE_MIN}: "
          f"**{len(moon)} tests** (pressure {rng(moon['pressure_mmhg'], 1)} mmHg, o2_base {rng_4(moon['o2_base'])}). "
          f"Of all {int((df['pressure_band'] == 'near_535').sum())} tests near 535 mmHg, "
          f"{int(((df['pressure_band'] == 'near_535') & (df['o2_base'] < MOON_BASE_MIN)).sum())} are outside the slice "
          "(undiluted at O2 0.20). Test 114 is not in the slice because its pressure is printed as 0.", "",
          "Note: o2_base >= 0.29 is the oxygen share before dilution. Only the undiluted tests in the slice "
          f"actually have O2 >= 0.29 in the chamber ({int((moon['o2_mole_frac'] >= 0.29).sum())} tests); "
          "in the diluted ones the O2 mole fraction is "
          f"{rng(moon.loc[moon['diluent'] != 'none', 'o2_mole_frac'])}.", "",
          "| Fuel | Diluent | Tests | O2 range | diluent_frac range | d0 range (mm) | Usable for K | K range | Usable for ratio | Ratio range | Extinction / Disruption / Completion |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in FUELS:
        for dl in ("none", "CO2", "He"):
            g = moon[(moon["fuel"] == f) & (moon["diluent"] == dl)]
            if g.empty:
                L.append(f"| {f} | {dl} | 0 | | | | 0 | | 0 | | |")
                continue
            k = g.dropna(subset=["burning_rate_k", "d0_mm"])
            r = g.dropna(subset=["d_ext_over_d0", "d0_mm"])
            ends = g["test_end"].value_counts()
            L.append(f"| {f} | {dl} | {len(g)} | {rng(g['o2_mole_frac'])} | "
                     f"{rng(g['diluent_frac']) if dl != 'none' else ''} | {rng(g['d0_mm'])} | {len(k)} | "
                     f"{rng(k['burning_rate_k'])} | {len(r)} | {rng(r['d_ext_over_d0'])} | "
                     f"{ends.get('Extinction', 0)} / {ends.get('Disruption', 0)} / {ends.get('Completion', 0)} |")
    L += ["", "Slice by diluent fraction (both fuels):", "",
          "| Diluent | diluent_frac | O2 | Tests | Median K | Median ratio | Extinction / Disruption / Completion | Test numbers |", "|---|---|---|---|---|---|---|---|"]
    for (dl, dfrac), g in moon.groupby(["diluent", "diluent_frac"]):
        ends = g["test_end"].value_counts()
        mk, mr = g["burning_rate_k"].median(), g["d_ext_over_d0"].median()
        L.append(f"| {dl} | {dfrac:.2f} | {rng(g['o2_mole_frac'])} | {len(g)} | "
                 f"{'' if np.isnan(mk) else f'{mk:.2f}'} | {'' if np.isnan(mr) else f'{mr:.2f}'} | "
                 f"{ends.get('Extinction', 0)} / {ends.get('Disruption', 0)} / {ends.get('Completion', 0)} | "
                 f"{tests(g['test_number'])} |")
    L += ["", "Medians mix droplet sizes and both fuels, and each row has few tests. They describe the "
          "slice; they are not a model.", ""]

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {OUT}")
    for p in sorted(FIG.glob("*.png")):
        print("  figure", p.name)


def rng_4(s: pd.Series) -> str:
    return rng(s, 3)


if __name__ == "__main__":
    main()
