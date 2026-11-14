"""Tests for data/unified/: every converted value traces back to its source cell,
the FLEX rows agree with flex_clean.csv, and the catalog ranges agree with the
unified table. Run `python src/normalize.py` first if the files are missing."""
import csv
import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import normalize as nz  # noqa: E402
from build_catalog import read_table  # noqa: E402

TABLES = ROOT / "data" / "raw" / "psi" / "tables"


@pytest.fixture(scope="module")
def unified():
    return pd.read_csv(nz.UNIFIED, dtype=str, keep_default_na=False)


@pytest.fixture(scope="module")
def units():
    return pd.read_csv(nz.UNITS_MAP, dtype=str, keep_default_na=False)


def source_number(cell: str, unit: str):
    """Independent reading of a source cell: a single number, optionally with ~ or the header's unit."""
    m = re.fullmatch(r"~?\s*(\d+\.?\d*|\.\d+)\s*(" + re.escape(unit) + r")?", cell.strip(), flags=re.I)
    return float(m.group(1)) if m else None


def test_schema_and_row_links(unified):
    assert list(unified.columns) == nz.SCHEMA
    assert len(unified) == 2009 and unified["source_file"].nunique() == 22
    assert not unified.duplicated(["source_file", "source_row"]).any()
    assert set(unified["o2_basis"]) <= {"", "ambient", "oxidizer stream"}
    assert (unified["gravity"] == "").all()  # no table states it per row


def test_raw_tables_are_untouched():
    with (ROOT / "data" / "raw" / "psi" / "manifest.csv").open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["kind"] == "experimental_table"]
    assert len(rows) == 22
    for r in rows:
        assert hashlib.sha256((ROOT / r["saved_as"]).read_bytes()).hexdigest() == r["sha256"], r["saved_as"]


def test_every_converted_value_round_trips_to_its_source_cell(unified, units):
    used = units[units["status"].isin(["converted", "copied"]) & units["target_column"].isin(nz.NUMERIC)]
    assert len(used) >= 25
    checked = 0
    for (psi_id, file), cols in used.groupby(["psi_id", "source_file"]):
        rows = read_table(TABLES / psi_id / file)
        head = [h.strip() for h in rows[0]]
        part = unified[unified["source_file"] == file]
        for _, u in part.iterrows():
            src = rows[int(u["source_row"]) - 1]
            for target, group in cols.groupby("target_column"):
                # values this row's source cells would give for the target
                given = []
                for _, c in group.iterrows():
                    j = head.index(c["source_column"])
                    v = source_number(src[j] if j < len(src) else "", c["original_unit"])
                    if v is not None:
                        given.append(v * float(c["factor"]))
                got = u[target]
                if file.endswith("FLEX.csv") and target == "diluent_mole_frac":
                    assert float(got) == pytest.approx(max(given)), (file, u["source_row"])  # CO or He, else 0
                elif got == "":
                    # blank only if the cell was not a single number, or a pressure printed as 0
                    assert not given or (target == "pressure_kpa" and given[0] <= 0), (file, u["source_row"], target)
                    continue
                else:
                    assert len(given) == 1 and float(got) == pytest.approx(given[0], rel=1e-6), (
                        file, u["source_row"], target, got, given)
                    # and back: unified value / factor is the number printed in the source cell
                    factor = float(group.iloc[0]["factor"])
                    assert float(got) / factor == pytest.approx(given[0] / factor, rel=1e-6)
                checked += 1
    assert checked > 3000


def test_flex_rows_match_flex_clean(unified):
    clean = pd.read_csv(ROOT / "data" / "clean" / "flex_clean.csv")
    flex = unified[unified["psi_id"] == "PSI-69"].copy()
    flex["test_number"] = flex["test_id"].astype(int)
    m = clean.merge(flex, on="test_number", how="outer", validate="one_to_one", suffixes=("_clean", ""))
    assert len(m) == 274 and m["fuel_clean"].eq(m["fuel"]).all()
    num = lambda c: pd.to_numeric(m[c].replace("", None))  # noqa: E731
    assert (num("o2_mole_frac") == m["o2_mole_frac_clean"]).all()
    assert (m["o2_basis"] == "ambient").all()
    assert (m["diluent"] == m["diluent_clean"]).all()
    assert (num("diluent_mole_frac") - m["diluent_frac"]).abs().max() < 1e-9
    kpa, expect = num("pressure_kpa"), m["pressure_mmhg"] * 101.325 / 760
    assert kpa.isna().equals(m["pressure_atm"].isna())          # blank exactly where flex_clean has no pressure
    assert ((kpa - expect).abs()[kpa.notna()] < 1e-5).all()
    assert (kpa / 101.325 - m["pressure_atm"]).abs().max() < 1e-4  # same as pressure_atm, rounded there to 4 places
    d0 = num("sample_size_mm")
    assert d0.isna().equals(m["d0_mm"].isna()) and (d0.dropna() == m["d0_mm"].dropna()).all()
    assert m.loc[m["test_number"] == 114, "quality_flag"].item() == "pressure_zero"


def test_o2_rulings_are_applied(unified):
    basis = unified[unified["o2_mole_frac"] != ""].groupby("psi_id")["o2_basis"].agg(set)
    assert basis["PSI-69"] == {"ambient"}
    assert basis["PSI-10"] == {"oxidizer stream"} and basis["PSI-159"] == {"oxidizer stream"}


def test_catalog_ranges_agree_with_the_unified_table(unified):
    cat = pd.read_csv(ROOT / "data" / "catalog" / "investigations.csv", dtype=str, keep_default_na=False)
    cat = cat.set_index("psi_id")
    pairs = [("o2_mole_frac", "ambient", "o2_min_frac", "o2_max_frac"),
             ("o2_mole_frac", "oxidizer stream", "o2_stream_min_frac", "o2_stream_max_frac"),
             ("pressure_kpa", None, "pressure_min_kpa", "pressure_max_kpa")]
    compared = 0
    for col, basis, lo_c, hi_c in pairs:
        part = unified[unified[col] != ""]
        if basis:
            part = part[part["o2_basis"] == basis]
        for pid, g in part.groupby("psi_id"):
            v = g[col].astype(float)
            lo, hi = float(cat.loc[pid, lo_c]), float(cat.loc[pid, hi_c])
            # every unified value lies inside the catalog range ...
            assert lo - 1e-4 <= v.min() and v.max() <= hi + 1e-4, (pid, col)
            # ... and the range is exactly the unified one when no source cell was set aside
            set_aside = unified[(unified["psi_id"] == pid)
                                & unified["quality_flag"].str.contains(f"{col}_not_a_single_value")]
            if set_aside.empty:
                assert v.min() == pytest.approx(lo, abs=1e-4) and v.max() == pytest.approx(hi, abs=1e-4), (pid, col)
            compared += 1
    assert compared >= 9


def test_units_map_lists_columns_without_a_stated_unit(units):
    no_unit = units[units["status"] == "unit not stated"]
    assert {"Pressure", "Oxygen", "Air Flow", "Atmosphere*"} <= set(no_unit["source_column"])
    assert (no_unit["factor"] == "").all()
