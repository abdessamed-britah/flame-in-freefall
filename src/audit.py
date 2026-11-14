"""Step 1 - audit of the raw FLEX file. Read-only on data/raw/.

Re-derives every number in the "Verified facts" and "Known problems" sections
of CLAUDE.md from the raw bytes, compares each with the value CLAUDE.md states,
and writes reports/audit.md. Exits with code 1 if any number does not match.

Run from anywhere:  python src/audit.py
"""
from __future__ import annotations

import hashlib
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "PSI-69_Experimental table_FLEX.csv"
OUT = ROOT / "reports" / "audit.md"

DASH = "–"  # byte 0x96 in cp1252

EXPECTED_COLUMNS = [
    "FLEX Test #",
    "FLEX Identifier",
    "Test Date",
    "Test GMT",
    "Fuel",
    "Ambient pressure; mmHg",
    "O initial ambient composition; mole fraction",
    "N initial ambient composition; mole fraction",
    "CO initial ambient composition; mole fraction",
    "He initial ambient composition; mole fraction",
    "Droplet initial diameter; mm",
    "Visible flame extinction diameter; mm",
    "Burning rate; mm",
    "Burn time; s",
    "Test end",
]
(C_NUM, C_ID, C_DATE, C_GMT, C_FUEL, C_P, C_O, C_N, C_CO, C_HE,
 C_D0, C_DEXT, C_K, C_TBURN, C_END) = EXPECTED_COLUMNS

checks: list[tuple[str, str, object, object]] = []  # section, claim, expected, found


def check(section: str, claim: str, expected, found) -> None:
    checks.append((section, claim, expected, found))


def parse_date(s: str) -> date:
    m, d, y = (int(x) for x in s.split("/"))
    return date(2000 + y if y < 100 else y, m, d)


def is_num(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def main() -> int:
    raw = RAW.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()

    # ---- encoding -------------------------------------------------------
    try:
        raw.decode("utf-8")
        utf8_ok = True
    except UnicodeDecodeError:
        utf8_ok = False
    non_ascii = sorted({b for b in raw if b > 127})
    V, K = "Verified facts", "Known problems"
    check(V, "File is not valid UTF-8", True, not utf8_ok)
    check(V, "Only non-ASCII byte value", "0x96", ", ".join(f"0x{b:02X}" for b in non_ascii))
    check(V, "Count of byte 0x96", 34, raw.count(b"\x96"))

    df = pd.read_csv(RAW, encoding="cp1252", dtype=str, keep_default_na=False)

    # ---- shape and columns ---------------------------------------------
    check(V, "Rows", 274, len(df))
    check(V, "Columns", 15, df.shape[1])
    check(V, "Column names exactly as listed", True, list(df.columns) == EXPECTED_COLUMNS)
    if list(df.columns) != EXPECTED_COLUMNS:
        print("Column names differ from CLAUDE.md; cannot continue:", list(df.columns))
        return 1

    dates = df[C_DATE].map(parse_date)
    check(V, "Distinct test dates", 80, dates.nunique())
    check(V, "Years covered", "2009-2011", f"{dates.min().year}-{dates.max().year}")

    # ---- dash marker ----------------------------------------------------
    dash_cols = {c: int((df[c] == DASH).sum()) for c in df.columns if (df[c] == DASH).any()}
    check(V, "Dash cells in initial diameter", 6, dash_cols.get(C_D0, 0))
    check(V, "Dash cells in extinction diameter", 28, dash_cols.get(C_DEXT, 0))
    check(V, "Dash appears in no other column", True, set(dash_cols) <= {C_D0, C_DEXT})

    # ---- categories -----------------------------------------------------
    fuel = df[C_FUEL].value_counts().to_dict()
    check(V, "Fuel counts", {"Methanol": 157, "Heptane": 117}, fuel)
    end = df[C_END].value_counts().to_dict()
    check(V, "Test end counts", {"Extinction": 186, "Disruption": 61, "Completion": 27}, end)

    # ---- gases ----------------------------------------------------------
    o, n, co, he = (df[c].astype(float) for c in (C_O, C_N, C_CO, C_HE))
    check(V, '"O" min', 0.12, o.min())
    check(V, '"O" max', 0.34, o.max())
    check(V, 'Tests with "CO" > 0', 123, int((co > 0).sum()))
    check(V, '"CO" max', 0.70, co.max())
    check(V, "Tests with He > 0", 50, int((he > 0).sum()))
    check(V, "He max", 0.45, he.max())
    check(V, 'Tests with both "CO" > 0 and He > 0', 0, int(((co > 0) & (he > 0)).sum()))
    check(V, 'Tests with "CO" = 0 and He = 0', 101, int(((co == 0) & (he == 0)).sum()))

    # ---- pressure -------------------------------------------------------
    p = df[C_P].astype(float)
    near760 = p[(p >= 600) & (p < 900)]
    near535 = p[(p > 0) & (p < 600)]
    high = p[p >= 900]
    check(V, "Tests near 760 mmHg (600 <= p < 900)", 161, len(near760))
    check(V, "Tests near 535 mmHg (0 < p < 600)", 103, len(near535))
    check(V, "Tests at high pressure (p >= 900)", 9, len(high))
    check(V, "High-pressure range inside 1500-2320 mmHg", True,
          bool(high.min() >= 1500 and high.max() <= 2320))

    # ---- missing --------------------------------------------------------
    def n_missing(c: str) -> int:
        return int(df[c].isin(["", DASH]).sum())

    check(V, "Missing initial diameter (blank or dash)", 12, n_missing(C_D0))
    check(V, "Missing extinction diameter (blank or dash)", 77, n_missing(C_DEXT))
    check(V, "Missing burning rate", 16, n_missing(C_K))
    check(V, "Missing burn time", 6, n_missing(C_TBURN))

    # ---- known problems -------------------------------------------------
    num = df[C_NUM].astype(int)
    p0 = df[p == 0]
    check(K, "Tests with pressure printed as 0", "114 (C11M201)",
          ", ".join(f"{a} ({b})" for a, b in zip(p0[C_NUM], p0[C_ID])))

    dup_ids = df[C_ID][df[C_ID].duplicated(keep=False)]
    dup = df[df[C_ID].isin(dup_ids)]
    check(K, "Duplicated identifiers", "193F001", ", ".join(sorted(set(dup_ids))))
    check(K, "Tests carrying the duplicated identifier", "70, 73", ", ".join(dup[C_NUM]))
    check(K, "Duplicate pair has same date and time", True,
          bool(dup[C_DATE].nunique() == 1 and dup[C_GMT].nunique() == 1))
    meas = [C_D0, C_DEXT, C_K, C_TBURN]
    check(K, "Duplicate pair has different measurements", True,
          bool(len(dup) == 2 and (dup.iloc[0][meas] != dup.iloc[1][meas]).any()))

    g = df[df[C_NUM].isin(["114", "118"])]
    check(K, "Tests 114 and 118 share the same GMT time", True, bool(g[C_GMT].nunique() == 1))

    approx = df[df[C_TBURN].str.contains("~")]
    check(K, "Approximate burn times", "223: ~6, 224: ~9",
          ", ".join(f"{a}: {b}" for a, b in zip(approx[C_NUM], approx[C_TBURN])))

    z = df[df[C_DEXT].map(lambda s: is_num(s) and float(s) == 0)]
    check(K, "Tests with extinction diameter exactly 0", 8, len(z))
    check(K, "Test end of those tests", {"Completion": 4, "Disruption": 4},
          z[C_END].value_counts().to_dict())

    gas_sum = (o + n + co + he).round(2)
    off = gas_sum[gas_sum != 1.00]
    check(K, "Rows where gas fractions do not sum to 1.00", 29, len(off))
    check(K, "Range of those sums", "0.98-1.01", f"{gas_sum.min():.2f}-{gas_sum.max():.2f}")

    y_len = df[C_DATE].str.split("/").str[2].str.len()
    check(K, "Dates mix 4-digit and 2-digit years", True, set(y_len) == {2, 4})

    # ---- targets --------------------------------------------------------
    T = "Targets"
    d0_num = df[C_D0].map(is_num)
    dext_num = df[C_DEXT].map(is_num)
    k_num = df[C_K].map(is_num)
    check(T, "Rows with a numeric burning rate", 258, int(k_num.sum()))
    # ---- team rulings of 2026-11-14 (flags added in src/clean.py) ---------
    R = "Team rulings"
    both_num = df[d0_num & dext_num]
    over = both_num[both_num[C_DEXT].astype(float) > both_num[C_D0].astype(float)]
    check(R, "Tests with extinction diameter above initial diameter (flag ratio_gt_1, kept)",
          "129", ", ".join(over[C_NUM]))
    low_k = df[k_num][df[k_num][C_K].astype(float) < 0.10]
    check(R, "Tests with burning rate below 0.10 (flag k_outlier, kept)", "130", ", ".join(low_k[C_NUM]))
    check(R, "Tests with pressure 0 (flag pressure_zero, excluded from modelling)", "114",
          ", ".join(p0[C_NUM]))

    n_ratio_all = int((d0_num & dext_num).sum())
    n_ratio_nz = n_ratio_all - len(z[z[C_D0].map(is_num)])

    # ---- write report ---------------------------------------------------
    def same(e, f) -> bool:
        if isinstance(e, float) or isinstance(f, float):
            return abs(float(e) - float(f)) < 1e-9
        return e == f

    def show(v) -> str:
        if isinstance(v, dict):
            return ", ".join(f"{k} {n}" for k, n in sorted(v.items()))
        if isinstance(v, float):
            return f"{v:g}"
        return str(v)

    n_bad = sum(not same(e, f) for _, _, e, f in checks)
    L: list[str] = []
    L += ["# Audit of the raw FLEX file", ""]
    L += [f"Generated by `src/audit.py` from `data/raw/{RAW.name}`.", ""]
    L += [f"- Size: {len(raw)} bytes", f"- SHA-256: `{sha}`",
          "- Read with encoding cp1252, every cell as text, nothing converted on load.", ""]
    L += [f"**Result: {len(checks) - n_bad} of {len(checks)} checks match CLAUDE.md"
          + ("." if n_bad == 0 else f"; {n_bad} MISMATCH.") + "**", ""]

    for section in (V, K, T, R):
        L += [f"## {section}", "", "| Claim | CLAUDE.md | Found in file | Result |", "|---|---|---|---|"]
        for s, claim, e, f in checks:
            if s == section:
                L.append(f"| {claim} | {show(e)} | {show(f)} | {'match' if same(e, f) else '**MISMATCH**'} |")
        L.append("")

    L += ["CLAUDE.md says the extinction ratio d_ext/d0 has \"about 190 rows\". "
          f"The file has {n_ratio_all} rows where both diameters are numeric; "
          f"{n_ratio_nz} of them have a non-zero extinction diameter.", ""]

    L += ["## Columns", "",
          "| # | Header (verbatim) | Blank | Dash | Numeric cells | Min | Max |", "|---|---|---|---|---|---|---|"]
    for i, c in enumerate(df.columns):
        col = df[c]
        nums = col[col.map(is_num)].astype(float)
        numeric_col = i == 0 or i >= 5 and i <= 13
        L.append(f"| {i} | `{c}` | {(col == '').sum()} | {(col == DASH).sum()} | "
                 + (f"{len(nums)} | {nums.min():g} | {nums.max():g} |" if numeric_col else "text | | |"))
    L.append("")

    L += ["## Pressure groups", "", "| Group | Tests | Min mmHg | Max mmHg |", "|---|---|---|---|"]
    for name, s in (("Near 760", near760), ("Near 535", near535), ("High", high)):
        L.append(f"| {name} | {len(s)} | {s.min():g} | {s.max():g} |")
    L += [f"| Printed as 0 | {len(p0)} | 0 | 0 |", ""]

    L += ["## Gas-fraction sums", "", "| Sum | Rows |", "|---|---|"]
    for v, cnt in gas_sum.value_counts().sort_index().items():
        L.append(f"| {v:.2f} | {cnt} |")
    L.append("")

    # ---- observations not in CLAUDE.md -----------------------------------
    back = int((dates.diff().dropna().map(lambda d: d.days) < 0).sum())
    both = df[d0_num & dext_num]
    gt = both[both[C_DEXT].astype(float) > both[C_D0].astype(float)]
    kk = df[k_num]
    kv = kk[C_K].astype(float)
    empty = df[(df[meas] == "").all(axis=1) | df[meas].isin(["", DASH]).all(axis=1)]
    L += ["## Observations not listed in CLAUDE.md", "",
          "These are not mismatches. They are extra facts found during the audit.", "",
          f"- Blank versus dash: initial diameter has {(df[C_D0] == '').sum()} blank and "
          f"{(df[C_D0] == DASH).sum()} dash; extinction diameter has {(df[C_DEXT] == '').sum()} blank and "
          f"{(df[C_DEXT] == DASH).sum()} dash.",
          f"- Test GMT is blank in test(s) {', '.join(df[C_NUM][df[C_GMT] == ''])}.",
          f"- Tests with no measurement at all (diameters, burning rate, burn time): "
          f"{', '.join(empty[C_NUM])}.",
          "- Extinction diameter larger than initial diameter: "
          + "; ".join(f"test {a} ({b} vs {c})" for a, b, c in zip(gt[C_NUM], gt[C_DEXT], gt[C_D0])) + ".",
          f"- Burning rate extremes: lowest {kv.min():g} (test {kk[C_NUM][kv.idxmin()]}), "
          f"next lowest {kv.nsmallest(2).iloc[1]:g}; highest {kv.max():g} (test {kk[C_NUM][kv.idxmax()]}).",
          f"- Test number runs 1 to {num.max()} without gaps, but is not strictly chronological: "
          f"the date steps backwards {back} times.",
          f"- Date formats: {(y_len == 4).sum()} rows with a 4-digit year, {(y_len == 2).sum()} with a 2-digit year.",
          "- Tests 114 and 118 share the date as well as the GMT time (9/6/2010 19:14:22). "
          "Tests 113, 115 and 116, which have neighbouring identifiers to test 114, are dated 9/1/2010.",
          f"- Rows with a numeric value in every measurement and atmosphere column: "
          f"{int((d0_num & dext_num & k_num & df[C_TBURN].map(is_num)).sum())}.",
          ""]

    L += ["## Still unconfirmed", "",
          "Nothing in the file settles these; see CLAUDE.md.", "",
          '- Whether "O", "N", "CO" mean O2, N2, CO2.',
          '- The unit of "Burning rate; mm".',
          "- What Extinction, Disruption and Completion mean operationally.",
          "- What dash, blank and 0 each mean in the extinction diameter.",
          "- Which tests are space tests and which are ground tests.", ""]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")

    for s, claim, e, f in checks:
        print(f"{'ok      ' if same(e, f) else 'MISMATCH'} [{s}] {claim}: expected {show(e)} | found {show(f)}")
    print(f"\n{len(checks) - n_bad}/{len(checks)} checks match. Report: {OUT}")
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
