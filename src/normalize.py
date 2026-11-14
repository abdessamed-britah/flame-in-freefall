"""Centralise the test conditions of every PSI experimental table in one file.

Reads   data/raw/psi/tables/<PSI-id>/*.csv   (22 tables, never modified)
Writes  data/unified/tests_conditions.csv    one row per row of a source table
        data/unified/units_map.csv           every source column used or set aside

Only test CONDITIONS are centralised (fuel, O2, pressure, flow, diluent, size).
Measurements stay in their original tables; each unified row points back to its
source with psi_id + source_file + source_row (and test_id where the table has
one).

Units of the unified table: mole fraction, kPa, cm/s, mm.

Rules
- A value is converted only when the column header states its unit. A column
  whose header gives no unit is left out and listed as "unit not stated".
- A cell is used only when it holds a single number ("21.5", "~ 21.5",
  "20 cm/s" under a header in cm/s). A cell holding several values or a range
  ("21; 26.5; 40", "0.1 - 5") is left blank and the row is flagged.
- Team rulings of 2026-11-14: in FLEX (PSI-69) the column "O" is ambient O2 and
  "CO" is CO2; in PSI-10 and PSI-159 XO2 is the O2 mole fraction of the
  oxidizer stream, not of the ambient atmosphere.
- gravity is left blank everywhere: no table has a column that says whether a
  row was run in microgravity or in normal gravity.
- fuel_phase is the team's label for the investigation
  (data/catalog/curated_labels.csv), not a value from the table.

Run from anywhere:  python src/normalize.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

from build_catalog import read_table

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "psi"
CURATED = ROOT / "data" / "catalog" / "curated_labels.csv"
OUT_DIR = ROOT / "data" / "unified"
UNIFIED = OUT_DIR / "tests_conditions.csv"
UNITS_MAP = OUT_DIR / "units_map.csv"

# conversion factors to the unified units
KPA_PER_ATM = 101.325
KPA_PER_BAR = 100.0
KPA_PER_MMHG = 101.325 / 760.0
KPA_PER_PSI = 6.894757
FRAC_PER_PERCENT = 0.01
CONVERSION_TEXT = {KPA_PER_ATM: "x 101.325 (atm to kPa)", KPA_PER_BAR: "x 100 (bar to kPa)",
                   KPA_PER_MMHG: "x 101.325 / 760 (mmHg to kPa)", KPA_PER_PSI: "x 6.894757 (psi to kPa)",
                   FRAC_PER_PERCENT: "x 0.01 (percent to fraction)", 1.0: "none"}

SCHEMA = ["psi_id", "investigation", "test_id", "source_file", "source_row", "fuel", "fuel_phase", "gravity",
          "o2_mole_frac", "o2_basis", "pressure_kpa", "flow_speed_cm_s", "diluent", "diluent_mole_frac",
          "sample_size_mm", "quality_flag"]
NUMERIC = ["o2_mole_frac", "pressure_kpa", "flow_speed_cm_s", "diluent_mole_frac", "sample_size_mm"]
MISSING = {"", "–", "-", "n/a", "none"}  # how the tables print "no value"

AMBIENT, STREAM = "ambient", "oxidizer stream"
RULING_O2 = "team ruling 2026-11-14: header subscript lost; the four gas fractions sum to 1, so O = O2"
RULING_STREAM = "team ruling 2026-11-14: XO2 is the oxidizer-stream O2 mole fraction, not ambient"
RULING_CO2 = "header subscript lost (CO read as CO2, as for O); diluent is CO2 where this column is > 0"


def col(header, target, unit, factor, note=""):
    return {"header": header, "target": target, "unit": unit, "factor": factor, "note": note}


def skip(header, target, status, note):
    return {"header": header, "target": target, "status": status, "note": note}


NO_UNIT = "unit not stated"
NOT_MAPPED = "not mapped"

# One entry per source table. test_id: the column(s) that identify a test.
SPECS = [
    {"psi_id": "PSI-10", "file": "PSI-10_Experimental table_Flame Design_Inverse Flame.csv", "test_id": ["Test"],
     "fuel": None, "o2_basis": STREAM,
     "cols": [col("XO2", "o2_mole_frac", "mole fraction", 1.0, RULING_STREAM),
              col("pinit (atm)", "pressure_kpa", "atm", KPA_PER_ATM, "initial pressure")]},
    {"psi_id": "PSI-10", "file": "PSI-10_Experimental table_Flame Design_Normal Flame.csv", "test_id": ["Test"],
     "fuel": "Fuel", "o2_basis": STREAM,
     "cols": [col("XO2 (init)", "o2_mole_frac", "mole fraction", 1.0, RULING_STREAM),
              col("pinit (atm)", "pressure_kpa", "atm", KPA_PER_ATM, "initial pressure")]},
    {"psi_id": "PSI-20", "file": "PSI-20_Experimental table_ACME BRE.csv", "test_id": ["Year", "Month", "Date"],
     "fuel": "Fuel Bottle", "o2_basis": AMBIENT, "row_flag": "row_is_a_test_day_not_one_test",
     "cols": [col("Oxygen Conc (percent)", "o2_mole_frac", "percent", FRAC_PER_PERCENT),
              col("Burner Size (mm)", "sample_size_mm", "mm", 1.0, "burner size")]},
    {"psi_id": "PSI-21", "file": "PSI-21_Experimental table_CLD Flame.csv", "test_id": ["Test Day"],
     "fuel": "Fuel Bottle", "row_flag": "row_is_a_test_day_not_one_test", "cols": []},
    {"psi_id": "PSI-22", "file": "PSI-22_Experimental table_ACME E-FIELD Flames.csv", "test_id": ["Test Day"],
     "fuel": "Fuel Bottle", "row_flag": "row_is_a_test_day_not_one_test", "cols": []},
    {"psi_id": "PSI-23", "file": "PSI-23_Experimental table_ACME s-Flame.csv", "test_id": ["Test Day*"],
     "fuel": "Fuel Bottle", "row_flag": "row_is_a_test_day_not_one_test", "cols": [],
     "skip": [skip("Atmosphere*", "o2_mole_frac", NO_UNIT, "cells read e.g. \"~21% O2 with N2\"")]},
    {"psi_id": "PSI-25", "file": "PSI-25_Experimental table_BASS-II.csv", "test_id": ["Test #"],
     "fuel": "Fuel Sample Material", "o2_basis": AMBIENT,
     "cols": [col("Calibrated  initial O2 % by vol", "o2_mole_frac", "percent by volume", FRAC_PER_PERCENT,
                  "volume fraction taken as mole fraction (ideal gas)")],
     "skip": [skip("Initial CO2 % by vol", "", NOT_MAPPED, "ambient CO2 reading, not an added diluent")]},
    {"psi_id": "PSI-26", "file": "PSI-26_Experimental table_BASS.csv", "test_id": ["Test #"],
     "fuel": "Fuel Sample Material", "cols": []},
    {"psi_id": "PSI-39", "file": "PSI-39_Experimental table_CFI.csv", "test_id": ["Flex Number"], "fuel": "Fuel",
     "cols": [],
     "skip": [skip("Pressure", "pressure_kpa", NO_UNIT, "unit is in the cells (\"1 atm\"), not in the header"),
              skip("Oxygen", "o2_mole_frac", NO_UNIT, "cells read e.g. 0.21"),
              skip("Helium", "diluent_mole_frac", NO_UNIT, "cells read e.g. 0"),
              skip("Nitrogen", "", NO_UNIT, "cells read e.g. 0.79")]},
    {"psi_id": "PSI-47", "file": "PSI-47_Experimental table_DAFT.csv", "test_id": ["Session Name"], "fuel": None,
     "row_flag": "row_is_a_session_not_one_test", "cols": []},
    {"psi_id": "PSI-68", "file": "PSI-68_Experimental table_Flex2.csv", "test_id": [], "fuel": "Sample (Fuel Type)",
     "o2_basis": AMBIENT, "row_flag": "row_is_a_summary_per_fuel_not_one_test",
     "cols": [col("Oxygen Mole Fraction", "o2_mole_frac", "mole fraction", 1.0),
              col("Ambient Pressure (atm)", "pressure_kpa", "atm", KPA_PER_ATM),
              col("Flow Velocity (cm/s)", "flow_speed_cm_s", "cm/s", 1.0),
              col("Initial Droplet Diameter (mm)", "sample_size_mm", "mm", 1.0, "initial droplet diameter")]},
    {"psi_id": "PSI-69", "file": "PSI-69_Experimental table_FLEX.csv", "test_id": ["FLEX Test #"], "fuel": "Fuel",
     "o2_basis": AMBIENT, "flex": True,
     "cols": [col("O initial ambient composition; mole fraction", "o2_mole_frac", "mole fraction", 1.0, RULING_O2),
              col("Ambient pressure; mmHg", "pressure_kpa", "mmHg", KPA_PER_MMHG,
                  "a pressure printed as 0 is left blank and flagged"),
              col("CO initial ambient composition; mole fraction", "diluent_mole_frac", "mole fraction", 1.0,
                  RULING_CO2),
              col("He initial ambient composition; mole fraction", "diluent_mole_frac", "mole fraction", 1.0,
                  "diluent is He where this column is > 0"),
              col("Droplet initial diameter; mm", "sample_size_mm", "mm", 1.0, "initial droplet diameter")]},
    {"psi_id": "PSI-98", "file": "PSI-98_Experimental table_SAFFIRE-1.csv", "test_id": ["Sample Number"],
     "fuel": "Material", "o2_basis": AMBIENT,
     "cols": [col("Percent O2", "o2_mole_frac", "percent", FRAC_PER_PERCENT),
              col("Air Flow (cm/s)", "flow_speed_cm_s", "cm/s", 1.0)],
     "skip": [skip("Sample Thickness (cm)", "", NOT_MAPPED, "flat sample: three dimensions, no single size")]},
    {"psi_id": "PSI-99", "file": "PSI-99_Experimental table_SAFFIRE-2.csv", "test_id": ["Sample Number"],
     "fuel": "Material", "o2_basis": AMBIENT,
     "cols": [col("Percent O2 (Note 1)", "o2_mole_frac", "percent", FRAC_PER_PERCENT),
              col("Air Flow (cm/s)", "flow_speed_cm_s", "cm/s", 1.0)],
     "skip": [skip("Samle Thickness", "", NO_UNIT, "unit is in the cells (\"0.27 mm\"), not in the header")]},
    {"psi_id": "PSI-100", "file": "PSI-100_Experimental table_SAFFIRE-3.csv", "test_id": ["Sample Number"],
     "fuel": "Material", "cols": [],
     "skip": [skip("Air Flow", "flow_speed_cm_s", NO_UNIT, "unit is in the cells (\"30 cm/s\"), not in the header"),
              skip("Sample Thickness", "", NO_UNIT, "unit is in the cells (\".33 cm\"), not in the header")]},
    {"psi_id": "PSI-101", "file": "PSI-101_Experimental table_SAME-R.csv", "test_id": ["SAME Test #"],
     "fuel": "Sample Type",
     "cols": [col("Inlet velocity (cm/s)", "flow_speed_cm_s", "cm/s", 1.0)]},
    {"psi_id": "PSI-102", "file": "PSI-102_Experimental table_SAME.csv", "test_id": ["Sample #"],
     "fuel": "Sample Material",
     "cols": [col("Air Flow (cm/s)", "flow_speed_cm_s", "cm/s", 1.0)]},
    {"psi_id": "PSI-106", "file": "PSI-106_Experimental table_Slice.csv", "test_id": ["Test Date"],
     "fuel": "Fuel Type", "row_flag": "row_is_a_test_day_not_one_test", "cols": []},
    {"psi_id": "PSI-107", "file": "PSI-107_Experimental table_Spice.csv", "test_id": ["GMT date", "GMT ignition"],
     "fuel": "Fuel",
     "cols": [col("Air Rate (cm/s)", "flow_speed_cm_s", "cm/s", 1.0, "coflow air speed"),
              col("Nozzle (mm)", "sample_size_mm", "mm", 1.0, "burner nozzle diameter")]},
    {"psi_id": "PSI-142", "file": "PSI-142_Experimental table_Data Summary Table.csv", "test_id": ["Data ID"],
     "fuel": None, "row_flag": "row_is_a_published_data_set_not_one_test", "cols": []},
    {"psi_id": "PSI-159", "file": "PSI-159_Experimental table_CFI-G_Inverse Flames.csv", "test_id": ["Test"],
     "fuel": "Fuel", "o2_basis": STREAM,
     "cols": [col("XO2", "o2_mole_frac", "mole fraction", 1.0, RULING_STREAM),
              col("approx p (bar)", "pressure_kpa", "bar", KPA_PER_BAR, "header says approximate")]},
    {"psi_id": "PSI-159", "file": "PSI-159_Experimental table_CFI-G_Normal Flames.csv", "test_id": ["Test"],
     "fuel": "Fuel", "o2_basis": STREAM,
     "cols": [col("XO2 before test", "o2_mole_frac", "mole fraction", 1.0, RULING_STREAM),
              col("approx p (bar)", "pressure_kpa", "bar", KPA_PER_BAR, "header says approximate")]},
]

_SINGLE = re.compile(r"^(~)?\s*(\d+\.?\d*|\.\d+)\s*$")


def parse_cell(cell: str, unit: str) -> tuple[float | None, str]:
    """Returns (value, status): status is '' (single number), 'approx' (written
    with ~), 'missing' (blank or a dash), or 'not_single' (several values, a
    range, or text)."""
    s = cell.strip()
    if s.lower() in MISSING:
        return None, "missing"
    if unit and s.lower().endswith(unit.lower()):
        s = s[: -len(unit)].strip()
    m = _SINGLE.match(s)
    if not m:
        return None, "not_single"
    return float(m.group(2)), "approx" if m.group(1) else ""


def convert(value: float, factor: float) -> float:
    return round(value * factor, 10)  # keeps every digit of the source; only removes float noise


def header_index(headers: list[str], name: str) -> int:
    clean = [h.strip() for h in headers]
    if clean.count(name) != 1:
        raise ValueError(f"column {name!r} not found exactly once in {clean}")
    return clean.index(name)


def normalise_table(spec: dict, investigation: str, fuel_phase: str) -> list[dict]:
    rows = read_table(RAW / "tables" / spec["psi_id"] / spec["file"])
    head = rows[0]
    idx = {c["header"]: header_index(head, c["header"]) for c in spec["cols"]}
    id_idx = [header_index(head, h) for h in spec["test_id"]]
    fuel_idx = header_index(head, spec["fuel"]) if spec.get("fuel") else None
    out = []
    for n, r in enumerate(rows[1:], start=2):  # source_row: line number in the file, header = 1
        if not any(c.strip() for c in r):
            continue
        cell = lambda j: r[j].strip() if j < len(r) else ""  # noqa: E731
        row = dict.fromkeys(SCHEMA, "")
        flags = [spec["row_flag"]] if spec.get("row_flag") else []
        row.update({"psi_id": spec["psi_id"], "investigation": investigation, "source_file": spec["file"],
                    "source_row": n, "test_id": " ".join(cell(j) for j in id_idx).strip(),
                    "fuel": cell(fuel_idx) if fuel_idx is not None else "", "fuel_phase": fuel_phase})
        for c in spec["cols"]:
            value, status = parse_cell(cell(idx[c["header"]]), c["unit"])
            target = c["target"]
            if status == "not_single":
                flags.append(f"{target}_not_a_single_value")
                continue
            if value is None:
                continue
            if spec.get("flex") and target == "diluent_mole_frac":
                if value > 0:  # the CO or He column that is > 0 names the diluent
                    row["diluent"] = "CO2" if c["header"].startswith("CO") else "He"
                    row[target] = convert(value, c["factor"])
                continue
            if target == "pressure_kpa" and value <= 0:
                flags.append("pressure_zero")
                continue
            row[target] = convert(value, c["factor"])
            if status == "approx" or c["header"].startswith("approx"):
                flags.append(f"{target}_approximate")
        if spec.get("flex") and row["diluent"] == "":
            row["diluent"], row["diluent_mole_frac"] = "none", 0.0
        if row["o2_mole_frac"] != "":
            row["o2_basis"] = spec["o2_basis"]
        row["quality_flag"] = ";".join(dict.fromkeys(flags))
        out.append(row)
    return out


def units_rows(spec: dict) -> list[dict]:
    rows = []
    for c in spec["cols"]:
        rows.append({"psi_id": spec["psi_id"], "source_file": spec["file"], "source_column": c["header"],
                     "original_unit": c["unit"], "conversion": CONVERSION_TEXT[c["factor"]],
                     "factor": c["factor"], "target_column": c["target"],
                     "status": "converted" if c["factor"] != 1.0 else "copied", "note": c["note"]})
    for s in spec.get("skip", []):
        rows.append({"psi_id": spec["psi_id"], "source_file": spec["file"], "source_column": s["header"],
                     "original_unit": "", "conversion": "", "factor": "", "target_column": s["target"],
                     "status": s["status"], "note": s["note"]})
    for name, target in (("test_id", "test_id"), ("fuel", "fuel")):
        heads = spec["test_id"] if name == "test_id" else ([spec["fuel"]] if spec.get("fuel") else [])
        for h in heads:
            rows.append({"psi_id": spec["psi_id"], "source_file": spec["file"], "source_column": h,
                         "original_unit": "text", "conversion": "none", "factor": "", "target_column": target,
                         "status": "copied", "note": ""})
    return rows


def main() -> int:
    on_disk = {(p.parent.name, p.name) for p in (RAW / "tables").glob("*/*.csv")}
    in_spec = {(s["psi_id"], s["file"]) for s in SPECS}
    if on_disk != in_spec:
        print("Tables without a spec:", sorted(on_disk - in_spec), "| specs without a table:",
              sorted(in_spec - on_disk))
        return 1
    labels = pd.read_csv(CURATED, dtype=str, keep_default_na=False).set_index("psi_id")
    data, units = [], []
    for spec in SPECS:
        rec = json.loads((RAW / "investigations" / f"{spec['psi_id']}.json").read_bytes())
        name = (rec.get("investigationAcronym") or rec.get("title") or "").strip()
        data += normalise_table(spec, name, labels.loc[spec["psi_id"], "fuel_phase"])
        units += units_rows(spec)
    df = pd.DataFrame(data, columns=SCHEMA)
    dup = df["test_id"].ne("") & df.duplicated(["psi_id", "source_file", "test_id"], keep=False)
    df.loc[dup, "quality_flag"] = df.loc[dup, "quality_flag"].map(
        lambda f: ";".join(x for x in (f, "test_id_repeated_in_source") if x))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(UNIFIED, index=False, encoding="utf-8", lineterminator="\n")
    um = pd.DataFrame(units, columns=["psi_id", "source_file", "source_column", "original_unit", "conversion",
                                      "factor", "target_column", "status", "note"])
    um.to_csv(UNITS_MAP, index=False, encoding="utf-8", lineterminator="\n")

    print(f"{len(df)} rows from {len(SPECS)} tables -> {UNIFIED}")
    print(f"{len(um)} source columns -> {UNITS_MAP}\n")
    print("Rows per investigation:")
    per = df.groupby(["psi_id", "investigation"], sort=False).agg(
        rows=("psi_id", "size"), **{c: (c, lambda s: int((s != "").sum())) for c in NUMERIC}).reset_index()
    print(per.to_string(index=False))
    print("\nBlank cells per column:")
    for c in SCHEMA:
        print(f"  {c:20s} {int((df[c] == '').sum()):5d} of {len(df)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
