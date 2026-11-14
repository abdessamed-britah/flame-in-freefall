"""Step 4 - models for burning_rate_k and d_ext_over_d0.

    python src/model.py        validate, write reports/validation.md, save models/
    from model import predict  use the saved models (see predict() below)

Inputs allowed as features: fuel, o2, pressure_atm, co2, he, d0_mm, and the two
quantities computed from them, o2_base and diluent_frac. burn_time_s, d_ext_mm,
test_end and the other target are never used: they are outcomes of the test.

90% prediction intervals
- Gaussian process: mean +/- 1.645 x predictive standard deviation (the kernel
  includes a noise term, so this is an interval for a new observation).
- Mean baseline, ridge, gradient boosting: mean +/- q, where q is the 90th
  percentile of the absolute out-of-fold residuals on the training data
  (5-fold, grouped by test date).
"""
from __future__ import annotations

import json
import sys
import warnings
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean" / "flex_clean.csv"
EXCLUSIONS = ROOT / "data" / "clean" / "exclusions.csv"
REPORT = ROOT / "reports" / "validation.md"
VALIDATION_JSON = ROOT / "reports" / "validation.json"
MODEL_DIR = ROOT / "models"

# in_range pressure rule (team ruling 2026-11-14): a query is in range only if
# its pressure is within 40 mmHg of the tests of the "near 535" or "near 760"
# band, and never above 900 mmHg (only 9 tests there, all at CO2 0.70).
IN_RANGE_BANDS = ("near_535", "near_760")
BAND_MARGIN_MMHG = 40.0
HIGH_PRESSURE_MMHG = 900.0
# d_ext_over_d0 is a ratio of diameters; predict() clips it to this interval.
RATIO_BOUNDS = (0.0, 1.0)

TARGETS = ["burning_rate_k", "d_ext_over_d0"]
BASE = ["is_heptane", "o2_mole_frac", "pressure_atm", "co2_mole_frac", "he_mole_frac", "d0_mm"]
EXTENDED = BASE + ["o2_base", "diluent_frac"]
FEATURE_SETS = {"base": BASE, "base + o2_base, diluent_frac": EXTENDED}
NUMERIC_INPUTS = ["o2_mole_frac", "pressure_atm", "co2_mole_frac", "he_mole_frac", "d0_mm"]
Z90 = 1.645
N_FOLDS = 5
MMHG_PER_ATM = 760.0

# ---- final choice, made after reading reports/validation.md -----------------
CHOSEN = {
    "burning_rate_k": ("Gaussian process", "base"),
    "d_ext_over_d0": ("Gaussian process", "base"),
}
# The k_outlier row (test 130) stays in the clean data. Whether the saved
# models are trained on it is decided here.
FINAL_DROP_K_OUTLIER = False
RATIONALE = {
    "burning_rate_k": (
        "The Gaussian process has the lowest grouped-CV error (MAE 0.048 against 0.107 for the mean baseline) "
        "with 91% coverage from its own uncertainty, and it degrades least when CO2 is held out. "
        "The base features are kept because adding o2_base and diluent_frac does not improve grouped CV "
        "(MAE 0.047) and makes the held-out-CO2 error almost three times larger (0.155 against 0.057)."),
    "d_ext_over_d0": (
        "The Gaussian process is clearly ahead in grouped CV (MAE 0.086, R2 0.77, against 0.114 and 0.61 for "
        "gradient boosting) with the narrowest interval at 91% coverage, and it is also the best model in both "
        "leave-one-diluent-out tests. The base features are kept because the two extra features change "
        "nothing (MAE 0.086 either way) and the simpler input set is easier to explain."),
}
RATIO_VERDICT = (
    "No, it can be modelled, but only coarsely. With 188 tests the Gaussian process reaches MAE 0.086 and "
    "R2 0.77 in grouped CV, against MAE 0.207 for the mean baseline, so there is real signal. "
    "The 90% interval is about 0.36 wide on a quantity that only spans 0.04 to 1.00: the model can say "
    "\"far from the limit\", \"in between\" or \"close to the limit\", not much finer. "
    "Coverage also drops to 79-86% when a whole diluent is held out, and 8 tests with extinction diameter "
    "printed as 0 are left out until their meaning is confirmed.")
HONESTY = (
    "Burning rate: when the model has never seen helium, its error on the helium tests is 0.137, which is "
    "2.4 times its grouped-CV error on the same tests (0.057) and no better than predicting the mean (0.142); "
    "only 45% of the measured values fall inside the 90% interval. Holding out CO2 is milder: 1.6 times worse "
    "(0.057 against 0.036) with 92% coverage. In plain words, the burning-rate model does not transfer to a "
    "diluent it has not seen; helium raises the burning rate where CO2 lowers it, and nothing in the inputs "
    "tells the model that in advance. Extinction ratio: 1.2 times worse without helium and 1.4 times worse "
    "without CO2, still well ahead of the mean baseline, with coverage of 79% and 86%. "
    "Removing the k_outlier row changes the burning-rate MAE from 0.048 to 0.046 and nothing else of note.")


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def load_rows(target: str, drop_k_outlier: bool) -> pd.DataFrame:
    """Clean rows usable for `target`: everything not listed in exclusions.csv."""
    df = pd.read_csv(CLEAN)
    excl = pd.read_csv(EXCLUSIONS)
    out = set(excl.loc[excl["target"] == target, "test_number"])
    df = df[~df["test_number"].isin(out)].copy()
    if drop_k_outlier:
        df = df[~df["quality_flag"].str.contains("k_outlier")]
    df["is_heptane"] = (df["fuel"] == "Heptane").astype(float)
    need = EXTENDED + [target]
    if df[need].isna().any().any():
        raise ValueError(f"missing values left in modelling rows for {target}; exclusions.csv is incomplete")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------
def make_model(name: str, n_features: int):
    if name == "Mean baseline":
        return DummyRegressor(strategy="mean")
    if name == "Ridge, pairwise interactions":
        return make_pipeline(StandardScaler(),
                             PolynomialFeatures(degree=2, interaction_only=True, include_bias=False),
                             RidgeCV(alphas=np.logspace(-2, 2, 5)))
    if name == "Gradient boosting":
        return GradientBoostingRegressor(random_state=0)
    if name == "Gaussian process":
        kernel = (ConstantKernel(1.0, (1e-2, 1e2))
                  * RBF(length_scale=np.ones(n_features), length_scale_bounds=(1e-1, 1e2))
                  + WhiteKernel(0.1, (1e-3, 1e1)))
        return make_pipeline(StandardScaler(),
                             GaussianProcessRegressor(kernel=kernel, normalize_y=True,
                                                      n_restarts_optimizer=1, random_state=0))
    raise KeyError(name)


MODEL_NAMES = ["Mean baseline", "Ridge, pairwise interactions", "Gradient boosting", "Gaussian process"]


def conformal_half_width(name: str, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> float:
    """90th percentile of absolute out-of-fold residuals, folds grouped by date."""
    k = min(N_FOLDS, len(np.unique(groups)))
    resid = np.empty(len(y))
    for tr, te in GroupKFold(n_splits=k).split(X, y, groups):
        m = make_model(name, X.shape[1]).fit(X[tr], y[tr])
        resid[te] = np.abs(y[te] - m.predict(X[te]))
    return float(np.quantile(resid, 0.90))


def fit_with_interval(name: str, X: np.ndarray, y: np.ndarray, groups: np.ndarray):
    """Fit and return (fitted model, interval spec)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        model = make_model(name, X.shape[1]).fit(X, y)
        if name == "Gaussian process":
            return model, {"kind": "gp"}
        return model, {"kind": "conformal", "half_width": conformal_half_width(name, X, y, groups)}


def predict_with_interval(model, interval: dict, X: np.ndarray):
    if interval["kind"] == "gp":
        mean, std = model.predict(X, return_std=True)
        return mean, mean - Z90 * std, mean + Z90 * std
    mean = model.predict(X)
    return mean, mean - interval["half_width"], mean + interval["half_width"]


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def metrics(y, mean, lo, hi) -> dict:
    return {"n": len(y), "mae": mean_absolute_error(y, mean), "r2": r2_score(y, mean),
            "coverage": float(np.mean((y >= lo) & (y <= hi))), "width": float(np.mean(hi - lo))}


def group_kfold(df: pd.DataFrame, target: str, name: str, feats: list[str]):
    X, y, g = df[feats].to_numpy(float), df[target].to_numpy(float), df["test_date"].to_numpy()
    mean, lo, hi = (np.empty(len(y)) for _ in range(3))
    for tr, te in GroupKFold(n_splits=N_FOLDS).split(X, y, g):
        model, interval = fit_with_interval(name, X[tr], y[tr], g[tr])
        mean[te], lo[te], hi[te] = predict_with_interval(model, interval, X[te])
    return mean, lo, hi


def leave_diluent_out(df: pd.DataFrame, target: str, name: str, feats: list[str], held: str):
    tr, te = df[df["diluent"] != held], df[df["diluent"] == held]
    model, interval = fit_with_interval(name, tr[feats].to_numpy(float), tr[target].to_numpy(float),
                                        tr["test_date"].to_numpy())
    return te.index.to_numpy(), predict_with_interval(model, interval, te[feats].to_numpy(float))


def configs():
    yield "Mean baseline", "none", BASE
    for name in MODEL_NAMES[1:]:
        for fs_name, feats in FEATURE_SETS.items():
            yield name, fs_name, feats


def validate() -> tuple[list[str], dict]:
    L: list[str] = []
    out = {"group_kfold": [], "leave_diluent_out": []}
    for target in TARGETS:
        for drop in (False, True):
            df = load_rows(target, drop)
            y = df[target].to_numpy(float)
            label = "without the k_outlier row (test 130)" if drop else "with the k_outlier row (test 130)"
            print(f"\n=== {target}, {label}: {len(df)} rows, {df['test_date'].nunique()} dates")
            L += [f"### {target}, {label}", "",
                  f"{len(df)} tests on {df['test_date'].nunique()} dates. Target mean {y.mean():.3f}, "
                  f"standard deviation {y.std(ddof=1):.3f}, range {y.min():.2f}-{y.max():.2f}.", "",
                  f"Validation 1: GroupKFold, {N_FOLDS} folds, grouped by test date. "
                  "Metrics are computed on the pooled out-of-fold predictions.", "",
                  "| Model | Features | MAE | R2 | Coverage of 90% interval | Mean interval width |", "|---|---|---|---|---|---|"]
            oof = {}
            for name, fs_name, feats in configs():
                mean, lo, hi = group_kfold(df, target, name, feats)
                oof[(name, fs_name)] = (mean, lo, hi)
                m = metrics(y, mean, lo, hi)
                out["group_kfold"].append({"target": target, "k_outlier_included": not drop, "model": name,
                                           "features": fs_name, **m})
                L.append(f"| {name} | {fs_name} | {m['mae']:.3f} | {m['r2']:.2f} | {m['coverage']:.0%} | {m['width']:.2f} |")
                print(f"  CV   {name:30s} {fs_name:28s} MAE {m['mae']:.3f} R2 {m['r2']:+.2f} cov {m['coverage']:.0%} width {m['width']:.2f}")
            L += ["", "Validation 2: leave one diluent out. The model is trained on every test that does not "
                  "contain the held-out diluent and scored on the tests that do. \"MAE in GroupKFold\" is the "
                  "error of the same model on the same tests in validation 1, where it had seen that diluent.", "",
                  "| Held out | Tests | Model | Features | MAE held out | MAE in GroupKFold | Times worse | R2 held out | Coverage of 90% interval |", "|---|---|---|---|---|---|---|---|---|"]
            for held in ("He", "CO2"):
                for name, fs_name, feats in configs():
                    idx, (mean, lo, hi) = leave_diluent_out(df, target, name, feats, held)
                    m = metrics(y[idx], mean, lo, hi)
                    ref = mean_absolute_error(y[idx], oof[(name, fs_name)][0][idx])
                    out["leave_diluent_out"].append(
                        {"target": target, "k_outlier_included": not drop, "held_out": held, "model": name,
                         "features": fs_name, **m, "mae_group_kfold": ref, "times_worse": m["mae"] / ref})
                    L.append(f"| {held} | {len(idx)} | {name} | {fs_name} | {m['mae']:.3f} | {ref:.3f} | "
                             f"{m['mae'] / ref:.1f}x | {m['r2']:.2f} | {m['coverage']:.0%} |")
                    print(f"  LODO {held:3s} {name:30s} {fs_name:28s} MAE {m['mae']:.3f} vs {ref:.3f} "
                          f"({m['mae'] / ref:.1f}x) R2 {m['r2']:+.2f} cov {m['coverage']:.0%}")
            L.append("")
    return L, out


# ---------------------------------------------------------------------------
# final models
# ---------------------------------------------------------------------------
def train_final() -> list[str]:
    MODEL_DIR.mkdir(exist_ok=True)
    clean = pd.read_csv(CLEAN)
    L = []
    for target in TARGETS:
        name, fs_name = CHOSEN[target]
        feats = FEATURE_SETS[fs_name]
        df = load_rows(target, FINAL_DROP_K_OUTLIER)
        X, y, g = df[feats].to_numpy(float), df[target].to_numpy(float), df["test_date"].to_numpy()
        model, interval = fit_with_interval(name, X, y, g)

        # Pool for "nearest real tests": every test with complete inputs,
        # whether or not it has this target.
        pool = clean.dropna(subset=NUMERIC_INPUTS).copy()
        bands = (clean.dropna(subset=["pressure_band"]).groupby("pressure_band")["pressure_mmhg"]
                 .agg(["min", "max", "size"]).to_dict("index"))
        bundle = {
            "target": target, "model_name": name, "feature_set": fs_name, "features": feats,
            "model": model, "interval": interval,
            "n_train": len(df), "trained_with_k_outlier": not FINAL_DROP_K_OUTLIER,
            "ranges": {c: (float(df[c].min()), float(df[c].max())) for c in NUMERIC_INPUTS},
            "fuels": sorted(df["fuel"].unique()),
            "pressure_bands_mmhg": bands,
            "pool": pool[["test_number", "flex_identifier", "fuel", *NUMERIC_INPUTS, "diluent",
                          "burning_rate_k", "d_ext_over_d0", "test_end", "quality_flag"]].reset_index(drop=True),
            "pool_scale": {c: float(pool[c].std(ddof=1)) for c in NUMERIC_INPUTS},
            "sklearn_version": sklearn.__version__,
        }
        path = MODEL_DIR / f"{target}.joblib"
        joblib.dump(bundle, path)
        print(f"saved {path}  ({name}, {fs_name}, {len(df)} rows)")
        gp = model[-1] if name == "Gaussian process" else None
        L += [f"### {target}: {name}, features: {fs_name}", "", RATIONALE[target], "",
              f"Saved to `models/{target}.joblib`, trained on {len(df)} tests "
              f"({'without' if FINAL_DROP_K_OUTLIER else 'including'} the k_outlier row, test 130).", ""]
        if gp is not None:
            L += [f"Fitted kernel (inputs standardised, order {', '.join(feats)}): `{gp.kernel_}`", ""]
        L += ["Training range used for `in_range`:", "", "| Input | Min | Max |", "|---|---|---|"]
        L += [f"| {c} | {lo:.4g} | {hi:.4g} |" for c, (lo, hi) in bundle["ranges"].items()]
        L.append("")
    return L


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _bundle(target: str) -> dict:
    return joblib.load(MODEL_DIR / f"{target}.joblib")


def predict(fuel: str, o2: float, pressure_atm: float, co2: float, he: float, d0_mm: float,
            target: str = "burning_rate_k", n_nearest: int = 5) -> dict:
    """Predict `target` for one atmosphere and droplet.

    fuel            "Methanol" or "Heptane"
    o2, co2, he     mole fractions; nitrogen is taken as 1 - o2 - co2 - he
    pressure_atm    pressure in atm (mmHg / 760)
    d0_mm           initial droplet diameter in mm
    target          "burning_rate_k" (default) or "d_ext_over_d0"

    Returns a dict with
      mean, lower, upper   prediction and its 90% interval; for d_ext_over_d0
                           all three are clipped to [0, 1]
      in_range             False if o2, co2, he or d0_mm is outside the range of
                           the training tests, the fuel is unknown, co2 and he
                           are both > 0, the pressure is above 900 mmHg, or the
                           pressure is not within 40 mmHg of the tests near
                           535 or near 760 mmHg
      warnings             plain-language reasons for in_range = False
      nearest_tests        the 5 closest real tests of the same fuel, each
                           with test_number, flex_identifier, its inputs and
                           its measured values (None where NASA has no value).
                           Distance is Euclidean over o2, pressure_atm, co2,
                           he, d0_mm, each divided by its standard deviation
                           across the tests.
    """
    b = _bundle(target)
    n2 = 1.0 - o2 - co2 - he
    if min(o2, co2, he) < 0 or n2 < -1e-9:
        raise ValueError("gas fractions must be >= 0 and o2 + co2 + he must not exceed 1")
    if o2 + n2 <= 0:
        raise ValueError("o2 + n2 must be > 0")
    q = {"is_heptane": 1.0 if fuel == "Heptane" else 0.0, "o2_mole_frac": o2, "pressure_atm": pressure_atm,
         "co2_mole_frac": co2, "he_mole_frac": he, "d0_mm": d0_mm,
         "o2_base": o2 / (o2 + n2), "diluent_frac": co2 + he}

    warn = []
    in_range = True
    if fuel not in b["fuels"]:
        in_range = False
        warn.append(f"fuel {fuel!r} is not in the data ({', '.join(b['fuels'])})")
    for c in NUMERIC_INPUTS:
        if c == "pressure_atm":
            continue  # pressure is judged by the band rule below, not by min and max
        lo, hi = b["ranges"][c]
        if not lo <= q[c] <= hi:
            in_range = False
            warn.append(f"{c} = {q[c]:g} is outside the training range {lo:g} to {hi:g}")
    if co2 > 0 and he > 0:
        in_range = False
        warn.append("CO2 and He are both > 0; no FLEX test mixes them")
    bands = b["pressure_bands_mmhg"]
    p_mmhg = pressure_atm * MMHG_PER_ATM
    if p_mmhg > HIGH_PRESSURE_MMHG:
        in_range = False
        n_high = bands.get("above_900", {}).get("size", 0)
        warn.append(f"pressure {p_mmhg:.0f} mmHg is above {HIGH_PRESSURE_MMHG:.0f} mmHg, where only "
                    f"{n_high} tests exist, all with CO2 0.70")
    elif not any(bands[k]["min"] - BAND_MARGIN_MMHG <= p_mmhg <= bands[k]["max"] + BAND_MARGIN_MMHG
                 for k in IN_RANGE_BANDS):
        in_range = False
        warn.append(f"pressure {p_mmhg:.0f} mmHg is not within {BAND_MARGIN_MMHG:.0f} mmHg of a tested band ("
                    + " or ".join(f"{bands[k]['min']:.0f}-{bands[k]['max']:.0f} mmHg, {bands[k]['size']} tests"
                                  for k in IN_RANGE_BANDS) + ")")

    X = np.array([[q[c] for c in b["features"]]])
    mean, lo, hi = predict_with_interval(b["model"], b["interval"], X)
    if target == "d_ext_over_d0":  # a ratio of diameters cannot leave [0, 1]
        mean, lo, hi = (np.clip(v, *RATIO_BOUNDS) for v in (mean, lo, hi))

    pool = b["pool"]
    pool = pool[pool["fuel"] == fuel] if fuel in b["fuels"] else pool
    dist = np.sqrt(sum(((pool[c] - q[c]) / b["pool_scale"][c]) ** 2 for c in NUMERIC_INPUTS))
    nearest = []
    for i in dist.nsmallest(n_nearest).index:
        r = pool.loc[i]
        rec = {"test_number": int(r["test_number"]), "flex_identifier": r["flex_identifier"],
               "distance": round(float(dist[i]), 3), "fuel": r["fuel"], "test_end": r["test_end"],
               "quality_flag": r["quality_flag"]}
        for c in NUMERIC_INPUTS + ["burning_rate_k", "d_ext_over_d0"]:
            rec[c] = None if pd.isna(r[c]) else float(r[c])
        nearest.append(rec)

    return {"target": target, "model": b["model_name"], "mean": float(mean[0]), "lower": float(lo[0]),
            "upper": float(hi[0]), "interval_level": 0.90, "in_range": in_range, "warnings": warn,
            "nearest_tests": nearest}


# ---------------------------------------------------------------------------
def main() -> int:
    excl = pd.read_csv(EXCLUSIONS)
    L = ["# Model validation", "",
         "Generated by `src/model.py` from `data/clean/flex_clean.csv` and `data/clean/exclusions.csv`. "
         f"scikit-learn {sklearn.__version__}, default settings; the only searches are 5 ridge penalties "
         "and the Gaussian-process kernel fit.", "",
         "## Setup", "",
         "- Targets: `burning_rate_k` (unit unconfirmed) and `d_ext_over_d0`.",
         "- Features, \"base\": fuel (as is_heptane), o2, pressure_atm, co2, he, d0_mm. "
         "The second feature set adds o2_base and diluent_frac, which are computed from the same inputs.",
         "- Never used as features: burn_time_s, d_ext_mm, test_end, the other target.",
         "- Rows: all 274 tests minus those listed per target in `exclusions.csv` "
         + "(" + "; ".join(f"{t}: {int((excl['target'] == t).sum())} excluded, {274 - int((excl['target'] == t).sum())} used"
                           for t in TARGETS) + ").",
         "- 90% interval: Gaussian process, mean +/- 1.645 x predictive standard deviation. Other models, "
         "mean +/- the 90th percentile of absolute out-of-fold residuals on the training data.",
         "- Coverage is the share of held-out tests whose measured value falls inside the interval. "
         "The aim is 90%.", "",
         "## Validation tables", ""]
    tables, results = validate()
    L += tables
    # Same numbers as the tables above, for the app's "How far to trust this" panel.
    results = {"generated_by": "src/model.py", "sklearn_version": sklearn.__version__,
               "n_folds": N_FOLDS, "interval_level": 0.90,
               "chosen": {t: {"model": CHOSEN[t][0], "features": CHOSEN[t][1],
                              "trained_with_k_outlier": not FINAL_DROP_K_OUTLIER} for t in TARGETS},
               **results}
    VALIDATION_JSON.write_text(json.dumps(results, indent=1), encoding="utf-8")
    L += ["## Honesty test in plain words (chosen models)", "", HONESTY, "",
          "## Is d_ext_over_d0 too noisy to model?", "", RATIO_VERDICT, "", "## Chosen models", ""]
    L += train_final()
    L += ["## Limits", "",
          "- Among diluted tests O2 and diluent fraction move together (see `reports/eda.md`, section A), "
          "so the models cannot attribute an effect to one or the other inside a pressure band.",
          "- Above 900 mmHg there are 9 tests, all at CO2 0.70; between the three pressure groups there are none.",
          "- CO2 and He are never mixed. `predict` returns `in_range = False` for such a query, for any "
          "pressure above 900 mmHg, and for any pressure more than 40 mmHg away from the tests near 535 or "
          "near 760 mmHg.",
          "- `predict` clips the d_ext_over_d0 mean and interval to [0, 1]. The validation tables above "
          "use the unclipped model output.",
          "- These are single fuel droplets. Nothing here predicts a cabin fire.", ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"\nwrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
