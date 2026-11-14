"""Step 2 - clean the raw FLEX file.

Reads   data/raw/PSI-69_Experimental table_FLEX.csv   (never modified)
Writes  data/clean/flex_clean.csv                     (one row per raw row)
        data/clean/exclusions.csv                     (tests left out of modelling,
                                                       per target, with reason)

Rules followed (see CLAUDE.md):
- No row is dropped. 274 in, 274 out.
- Blank cells and the dash marker (byte 0x96) become missing. Nothing is
  estimated, zero-filled or renormalised.
- Raw values that look wrong (pressure 0, extinction diameter 0) are kept as
  printed and flagged in quality_flag. Columns derived from them
  (pressure_atm, d_ext_over_d0) are left missing for those rows.

Naming caveats, all UNCONFIRMED until checked against NASA/TP-2015-216046:
- The raw headers say "O", "N", "CO". The clean names o2_/n2_/co2_ assume the
  subscripts were lost.
- The raw header "Burning rate; mm" has a truncated unit, so the clean name
  burning_rate_k carries no unit.

Run from anywhere:  python src/clean.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "PSI-69_Experimental table_FLEX.csv"
CLEAN = ROOT / "data" / "clean" / "flex_clean.csv"
EXCLUSIONS = ROOT / "data" / "clean" / "exclusions.csv"

DASH = "–"  # byte 0x96 in cp1252
MMHG_PER_ATM = 760.0  # definition of the standard atmosphere

RENAME = {
    "FLEX Test #": "test_number",
    "FLEX Identifier": "flex_identifier",
    "Test Date": "test_date",
    "Test GMT": "test_gmt",
    "Fuel": "fuel",
    "Ambient pressure; mmHg": "pressure_mmhg",
    "O initial ambient composition; mole fraction": "o2_mole_frac",
    "N initial ambient composition; mole fraction": "n2_mole_frac",
    "CO initial ambient composition; mole fraction": "co2_mole_frac",
    "He initial ambient composition; mole fraction": "he_mole_frac",
    "Droplet initial diameter; mm": "d0_mm",
    "Visible flame extinction diameter; mm": "d_ext_mm",
    "Burning rate; mm": "burning_rate_k",
    "Burn time; s": "burn_time_s",
    "Test end": "test_end",
}

# Rulings from the team lead (2026-11-14):
# - test 114 (pressure printed as 0): pressure_atm stays missing and the test
#   is excluded from modelling, logged in exclusions.csv.
# - test 129 (d_ext slightly above d0): flag ratio_gt_1, keep the row.
# - test 130 (burning rate 0.05, next lowest 0.20): flag k_outlier, keep the row.
K_OUTLIER_BELOW = 0.10  # burning_rate_k below this is flagged k_outlier

# Pressure bands in mmHg. Observed groups: 526.3-544.4, 752-774.1, 1545.7-2319.9.
BAND_535_MAX = 600.0
BAND_760_MAX = 900.0

OUTPUT_ORDER = [
    "test_number", "flex_identifier", "test_date", "test_gmt", "fuel",
    "pressure_mmhg", "pressure_atm", "pressure_band",
    "o2_mole_frac", "n2_mole_frac", "co2_mole_frac", "he_mole_frac",
    "diluent", "diluent_frac", "o2_base", "gas_sum",
    "d0_mm", "d_ext_mm", "d_ext_over_d0",
    "burning_rate_k", "burn_time_s", "burn_time_approx",
    "test_end",
    "d0_raw_marker", "d_ext_raw_marker",
    "quality_flag",
]


def parse_date(s: str) -> str:
    """'3/5/2009' or '10/24/09' -> ISO date. A 2-digit year yy means 20yy."""
    m, d, y = (int(x) for x in s.split("/"))
    return date(2000 + y if y < 100 else y, m, d).isoformat()


def raw_marker(col: pd.Series) -> pd.Series:
    """Record how a missing value was printed, since blank and dash may differ."""
    return col.map(lambda s: "blank" if s == "" else "dash" if s == DASH else "value")


def to_number(col: pd.Series) -> pd.Series:
    """Blank and dash -> missing. Anything else must parse, or we stop."""
    return pd.to_numeric(col.where(~col.isin(["", DASH])), errors="raise")


def main() -> int:
    raw = pd.read_csv(RAW, encoding="cp1252", dtype=str, keep_default_na=False)
    missing_cols = [c for c in RENAME if c not in raw.columns]
    if missing_cols or len(raw.columns) != len(RENAME):
        print("Raw header is not what clean.py expects:", list(raw.columns))
        return 1
    n_in = len(raw)

    df = raw.rename(columns=RENAME)

    # ---- text columns ---------------------------------------------------
    df["test_number"] = df["test_number"].astype(int)
    df["test_date"] = df["test_date"].map(parse_date)
    df["test_gmt"] = df["test_gmt"].where(df["test_gmt"] != "")  # blank -> missing

    # ---- how missing values were printed (kept before they are erased) ---
    df["d0_raw_marker"] = raw_marker(df["d0_mm"])
    df["d_ext_raw_marker"] = raw_marker(df["d_ext_mm"])

    # ---- burn time: "~6" -> 6 with burn_time_approx = True ---------------
    df["burn_time_approx"] = df["burn_time_s"].str.startswith("~")
    df["burn_time_s"] = df["burn_time_s"].str.lstrip("~")

    # ---- numeric columns ------------------------------------------------
    for c in ["pressure_mmhg", "o2_mole_frac", "n2_mole_frac", "co2_mole_frac",
              "he_mole_frac", "d0_mm", "d_ext_mm", "burning_rate_k", "burn_time_s"]:
        df[c] = to_number(df[c])

    # ---- derived columns ------------------------------------------------
    has_co2 = df["co2_mole_frac"] > 0
    has_he = df["he_mole_frac"] > 0
    if (has_co2 & has_he).any():
        print("A row has both CO2 and He; the diluent column cannot describe it.")
        return 1
    df["diluent"] = "none"
    df.loc[has_co2, "diluent"] = "CO2"
    df.loc[has_he, "diluent"] = "He"

    # Raw fractions have 2 decimals; rounding only removes float noise.
    df["gas_sum"] = (df["o2_mole_frac"] + df["n2_mole_frac"]
                     + df["co2_mole_frac"] + df["he_mole_frac"]).round(2)

    pressure_zero = df["pressure_mmhg"] == 0
    d_ext_zero = df["d_ext_mm"] == 0

    # pressure_atm = pressure_mmhg / 760; missing where the pressure is printed as 0.
    df["pressure_atm"] = (df["pressure_mmhg"] / MMHG_PER_ATM).where(~pressure_zero).round(4)

    # d_ext_over_d0 = d_ext_mm / d0_mm; missing where d_ext is printed as exactly 0,
    # because that 0 is not confirmed to be a measured diameter.
    df["d_ext_over_d0"] = (df["d_ext_mm"] / df["d0_mm"]).where(~d_ext_zero).round(4)

    # pressure_band: which of the three observed pressure groups the test is in.
    # Missing where the pressure is printed as 0.
    df["pressure_band"] = "above_900"
    df.loc[df["pressure_mmhg"] < BAND_760_MAX, "pressure_band"] = "near_760"
    df.loc[df["pressure_mmhg"] < BAND_535_MAX, "pressure_band"] = "near_535"
    df["pressure_band"] = df["pressure_band"].where(~pressure_zero)

    # o2_base = o2 / (o2 + n2): oxygen share of the O2/N2 mix before diluent.
    # diluent_frac = co2 + he: total diluent mole fraction.
    df["o2_base"] = (df["o2_mole_frac"] / (df["o2_mole_frac"] + df["n2_mole_frac"])).round(4)
    df["diluent_frac"] = (df["co2_mole_frac"] + df["he_mole_frac"]).round(2)

    # ---- quality flags --------------------------------------------------
    flags = {
        "ratio_gt_1": df["d_ext_over_d0"] > 1,
        "k_outlier": df["burning_rate_k"] < K_OUTLIER_BELOW,
        "pressure_zero": pressure_zero,
        "duplicate_identifier": df["flex_identifier"].duplicated(keep=False),
        "d_ext_zero": d_ext_zero,
        "gas_sum_not_1": df["gas_sum"] != 1.00,
        # Same date and GMT time as another test (CLAUDE.md, known problems).
        "shared_date_gmt": df["test_gmt"].notna()
        & df.duplicated(subset=["test_date", "test_gmt"], keep=False),
    }
    df["quality_flag"] = [
        ";".join(name for name, mask in flags.items() if mask.iloc[i]) or "none"
        for i in range(len(df))
    ]

    # ---- write ----------------------------------------------------------
    df = df[OUTPUT_ORDER]
    if len(df) != n_in:
        print(f"Row count changed: {n_in} in, {len(df)} out.")
        return 1
    CLEAN.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLEAN, index=False, encoding="utf-8", lineterminator="\n")

    # ---- exclusions from modelling ---------------------------------------
    # No row leaves flex_clean.csv. exclusions.csv lists, per modelling target,
    # every test that cannot be used to fit or score that target, and why.
    # src/model.py removes exactly these rows.
    excl = []
    for target in ("burning_rate_k", "d_ext_over_d0"):
        for _, r in df.iterrows():
            if r["quality_flag"].find("pressure_zero") >= 0:
                reason = "pressure printed as 0 in the raw file, so pressure_atm is missing (team ruling 2026-11-14)"
            elif pd.isna(r["d0_mm"]):
                reason = "initial diameter missing (input feature d0_mm)"
            elif target == "d_ext_over_d0" and r["d_ext_mm"] == 0:
                reason = "extinction diameter printed as 0, not confirmed to be a measured diameter"
            elif pd.isna(r[target]):
                reason = ("burning rate missing" if target == "burning_rate_k"
                          else "extinction diameter missing")
            else:
                continue
            excl.append({"test_number": r["test_number"], "flex_identifier": r["flex_identifier"],
                         "target": target, "reason": reason})
    excl = pd.DataFrame(excl, columns=["test_number", "flex_identifier", "target", "reason"])
    excl.to_csv(EXCLUSIONS, index=False, encoding="utf-8", lineterminator="\n")

    # ---- summary --------------------------------------------------------
    print(f"{n_in} rows in, {len(df)} rows out, {df.shape[1]} columns -> {CLEAN}")
    print(f"exclusions from modelling -> {EXCLUSIONS}")
    for target, g in excl.groupby("target"):
        print(f"  {target}: {len(g)} excluded, {n_in - len(g)} usable")
        for reason, n in g["reason"].value_counts().items():
            print(f"      {n:3d}  {reason}")
    print("\nquality_flag counts (a row can carry more than one flag):")
    for name, mask in flags.items():
        print(f"  {name:22s} {int(mask.sum()):3d}  tests {list(df['test_number'][mask])}"
              if mask.sum() <= 10 else f"  {name:22s} {int(mask.sum()):3d}")
    print(f"  {'none':22s} {int((df['quality_flag'] == 'none').sum()):3d}")
    print(f"\nburn_time_approx true: {list(df['test_number'][df['burn_time_approx']])}")
    print("\nmissing per column:")
    print(df.isna().sum()[lambda s: s > 0].to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
