"""Build data/catalog/investigations.csv from the NASA PSI records saved by
src/fetch_psi.py in data/raw/psi/. Nothing here comes from memory.

Three kinds of cell:
1. Verbatim from the PSI record (only outer whitespace and line breaks are
   tidied): psi_id, name, acronym, doi, license, sub_research_area,
   project_type, flight_platform, hardware, objective. source_url is the PSI
   page of the record; data_table_available says whether the record lists an
   experimental table.
2. Computed from the investigation's experimental table(s), only from a column
   whose header states the quantity and its unit (rules in RULES below):
   O2 range, pressure range, flow-speed range. The column used is recorded in
   the matching *_basis cell. No matching column -> blank.
3. Curated labels (fire_safety_pillar, fuel_phase), read from
   data/catalog/curated_labels.csv, each with its own basis. That file is
   created once, pre-filled only with what the challenge brief states, and is
   never overwritten afterwards: it belongs to the science lead.

Columns that look relevant but do not meet rule 2 are listed, with the reason,
in data/catalog/columns_not_used.csv.

Run from anywhere:  python src/build_catalog.py
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "psi"
OUT_DIR = ROOT / "data" / "catalog"
CATALOG = OUT_DIR / "investigations.csv"
CURATED = OUT_DIR / "curated_labels.csv"
NOT_USED = OUT_DIR / "columns_not_used.csv"
PSI_PAGE = "https://psi.nasa.gov/physci/repo/data/investigations/{}"

# unit conversions (stated formulas)
PSI_PER_ATM = 14.6959
PSI_PER_BAR = 14.5038
PSI_PER_MMHG = PSI_PER_ATM / 760.0

# ---- rule 2: header patterns that state quantity and unit --------------------
# (quantity, regex on the lower-cased header, unit as stated, factor to the catalog unit)
# Headers that say "final", "after" or "mean" are not used: the range wanted is
# the one the tests were set up with.
EXCLUDE = re.compile(r"\b(final|after|mean)\b|pfinal|pmean")
RULES = [
    ("o2", re.compile(r"(\bo2\b|oxygen).*mole fraction"), "mole fraction", 100.0),
    ("o2", re.compile(r"(\bo2\b|oxygen).*(%|percent)|(%|percent).*(\bo2\b|oxygen)"), "percent", 1.0),
    ("pressure", re.compile(r"(pressure|^pinit|^approx p).*\(atm\)"), "atm", PSI_PER_ATM),
    ("pressure", re.compile(r"(pressure|^pinit|^approx p).*\(bar\)"), "bar", PSI_PER_BAR),
    ("pressure", re.compile(r"pressure.*mmhg"), "mmHg", PSI_PER_MMHG),
    ("pressure", re.compile(r"pressure.*\(psi\)"), "psi", 1.0),
    ("flow", re.compile(r"(air flow|flow velocity|inlet velocity|air rate).*\(cm/s\)"), "cm/s", 1.0),
]
# Columns that very probably hold the quantity but whose header does not state
# it in full. They are NOT used; their range is reported for the science lead.
PENDING = [
    ("o2", re.compile(r"^xo2"), "mole fraction", 100.0,
     "header is the symbol XO2; it does not state the unit"),
    ("o2", re.compile(r"^o initial ambient composition; mole fraction"), "mole fraction", 100.0,
     "header says \"O\", not O2 (lost subscript; unconfirmed)"),
]
# ---- team rulings of 2026-11-14 on the pending columns ------------------------
# PSI-69 FLEX: the "O" column is accepted as ambient O2. The build checks the
# stated reason (the four gas columns sum to 1) before using it.
FLEX_ID = "PSI-69"
FLEX_GAS = re.compile(r"^(o|n|co|he) initial ambient composition; mole fraction")
FLEX_SUM_TOLERANCE = 0.021  # fractions are printed to 2 decimals; sums run 0.98 to 1.01
# PSI-10 and PSI-159: XO2 is the O2 fraction of the oxidizer stream, not of the
# ambient atmosphere. It is shown in its own columns and never used for the
# habitat O2 criterion.
STREAM_O2_IDS = {"PSI-10", "PSI-159"}
STREAM_O2_LABEL = "oxidizer-stream O2, not ambient atmosphere"

# Other headers that mention the quantity without a unit.
CANDIDATE = {"o2": re.compile(r"\bo2\b|oxygen|atmosphere"), "pressure": re.compile(r"pressure"),
             "flow": re.compile(r"air flow|velocity|air rate")}
IGNORE = re.compile(r"co2|flow rate|\(mg/s\)|fuel")  # e.g. "O2 flow rate (mg/s)" is a mass flow

# ---- rule 3: what the challenge brief states --------------------------------
# keyed by the acronym exactly as PSI prints it
BRIEF = "challenge brief"
BRIEF_LABELS = {
    "BASS": ("prevention", "solid"), "BASS-II": ("prevention", "solid"),
    "SAFFIRE-I": ("prevention", "solid"), "SAFFIRE-II": ("prevention", "solid"),
    "SAFFIRE-III": ("prevention", "solid"),
    "SAME": ("detection", ""), "SAME-R": ("detection", ""), "DAFT / DAFT-2": ("detection", ""),
    "FLEX": ("suppression", "liquid"), "FLEX-2": ("", "liquid"), "CFI": ("", "liquid"),
    "ACME/Flame Design": ("", "gas"), "ACME BRE": ("prevention", "gas"), "ACME CLD Flame": ("", "gas"),
    "ACME E-FIELD Flames": ("", "gas"), "ACME s-Flame": ("", "gas"), "ACME CFI-G": ("", "gas"),
}
# pillar basis where it is more specific than "challenge brief" (team ruling 2026-11-14)
PILLAR_BASIS = {"ACME BRE": "challenge brief: prevention depends on material selection and flammability limits"}

# ids and DOIs read from PSI pages by the team, to cross-check
EXPECTED_DOI = {"PSI-69": ("FLEX", "10.60555/mbq8-0451"), "PSI-98": ("Saffire-I", "10.60555/0t15-1z43"),
                "PSI-25": ("BASS-II", "10.60555/4qc4-de67"), "PSI-102": ("SAME", "10.60555/gd4k-8h62"),
                "PSI-60": ("SPICE data analysis (ground)", "10.60555/mzjm-yv57")}

COLUMNS = ["psi_id", "name", "acronym", "doi", "license", "sub_research_area", "project_type", "flight_platform",
           "hardware", "objective", "fuel", "fuel_phase", "fuel_phase_basis", "sample_geometry",
           "o2_min_pct", "o2_max_pct", "o2_basis", "o2_stream_min_pct", "o2_stream_max_pct", "o2_stream_basis",
           "pressure_min_psi", "pressure_max_psi", "pressure_basis",
           "flow_speed_min_cm_s", "flow_speed_max_cm_s", "flow_speed_basis", "airflow", "measurements",
           "fire_safety_pillar", "fire_safety_pillar_basis", "data_table_available", "source_url"]


def tidy(v) -> str:
    return re.sub(r"[\r\n\t]+", " ", str(v or "")).strip()


def read_table(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return list(csv.reader(io.StringIO(text, newline="")))


def cell_numbers(cell: str, unit: str) -> list[float] | None:
    """Numbers in a cell such as '21', '21; 26.5; 40', '0.1 - 5', '~ 21.5', '20 cm/s'.
    None if the cell holds anything else (text, 'RAMPED', blank)."""
    s = re.sub(re.escape(unit), " ", cell, flags=re.I)
    s = re.sub(r"\bor\b|~", " ", s, flags=re.I).strip()
    if not s or not re.fullmatch(r"[\d.\s;,\-–]+", s):
        return None
    return [float(t) for t in re.findall(r"\d+\.?\d*|\.\d+", s)]


def column_values(rows: list[list[str]], j: int, unit: str) -> tuple[list[float], int]:
    vals, skipped = [], 0
    for r in rows[1:]:
        cell = r[j].strip() if j < len(r) else ""
        nums = cell_numbers(cell, unit)
        if nums is None:
            skipped += bool(cell)
        else:
            vals += nums
    return vals, skipped


def flex_gas_sums(rows: list[list[str]]) -> tuple[float, float, int]:
    """Check the reason given for reading FLEX's "O" column as O2: the four gas
    fractions of every row must sum to 1 within rounding. Stops the build if not."""
    cols = [j for j, h in enumerate(rows[0]) if FLEX_GAS.search(h.strip().lower())]
    if len(cols) != 4:
        raise ValueError("FLEX table: expected the four gas columns O, N, CO, He")
    sums = [round(sum(float(r[j]) for j in cols), 2) for r in rows[1:]]
    if any(abs(s - 1) > FLEX_SUM_TOLERANCE for s in sums):
        raise ValueError("FLEX table: gas fractions do not sum to 1; the ruling's reason no longer holds")
    return min(sums), max(sums), len(sums)


def scan_tables(pid: str) -> tuple[dict, list[dict]]:
    """Returns ({quantity: (min, max, basis)}, [columns not used])."""
    found: dict[str, list] = {"o2": [], "pressure": [], "flow": [], "o2_stream": []}
    basis: dict[str, list[str]] = {"o2": [], "pressure": [], "flow": [], "o2_stream": []}
    unused = []
    for path in sorted((RAW / "tables" / pid).glob("*.csv")) if (RAW / "tables" / pid).exists() else []:
        rows = read_table(path)
        for j, header in enumerate(rows[0]):
            h = header.strip().lower()
            if EXCLUDE.search(h):
                continue
            rule = next((r for r in RULES if r[1].search(h)), None)
            if rule:
                q, _, unit, factor = rule
                vals, skipped = column_values(rows, j, unit)
                note = ""
                if q == "pressure":
                    bad = [v for v in vals if v <= 0]
                    vals = [v for v in vals if v > 0]
                    note = f", {len(bad)} value(s) <= 0 not used" if bad else ""
                if vals:
                    found[q] += [v * factor for v in vals]
                    basis[q].append(f"{path.name} | column \"{header.strip()}\" ({unit}) | {len(vals)} values"
                                    + (f", {skipped} non-numeric cell(s) skipped" if skipped else "") + note)
                continue
            pend = next((p for p in PENDING if p[1].search(h)), None)
            if pend:
                q, _, unit, factor, why = pend
                vals, _ = column_values(rows, j, unit)
                if pid == FLEX_ID and h.startswith("o initial") and vals:
                    lo, hi, n = flex_gas_sums(rows)
                    found["o2"] += [v * factor for v in vals]
                    basis["o2"].append(
                        f"{path.name} | column \"{header.strip()}\" ({unit}) | {len(vals)} values | team ruling: "
                        f"header subscript lost; O+N+CO+He sum to 1 in every row "
                        f"({lo:.2f} to {hi:.2f} over {n} rows, rounding), so O = O2")
                    continue
                if pid in STREAM_O2_IDS and h.startswith("xo2") and vals:
                    found["o2_stream"] += [v * factor for v in vals]
                    basis["o2_stream"].append(f"{path.name} | column \"{header.strip()}\" | {len(vals)} values")
                    continue
                unused.append({"psi_id": pid, "file": path.name, "column": header.strip(), "quantity": q,
                               "reason": why, "status": "needs confirmation",
                               "would_give_min": round(min(vals) * factor, 2) if vals else "",
                               "would_give_max": round(max(vals) * factor, 2) if vals else ""})
                continue
            for q, pat in CANDIDATE.items():
                if pat.search(h) and not IGNORE.search(h):
                    unused.append({"psi_id": pid, "file": path.name, "column": header.strip(), "quantity": q,
                                   "reason": "header does not state the unit", "status": "not used",
                                   "would_give_min": "", "would_give_max": ""})
    out = {q: (round(min(v), 2), round(max(v), 2), " ; ".join(basis[q])) for q, v in found.items() if v}
    return out, unused


def curated_labels(records: list[dict]) -> pd.DataFrame:
    """Create curated_labels.csv once; afterwards only append rows for new ids."""
    cols = ["psi_id", "acronym", "name", "fire_safety_pillar", "fire_safety_pillar_basis", "fuel_phase",
            "fuel_phase_basis"]
    existing = (pd.read_csv(CURATED, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                if CURATED.exists() else pd.DataFrame(columns=cols))
    new = []
    for r in records:
        if r["accession"] in set(existing["psi_id"]):
            continue
        acr = tidy(r.get("investigationAcronym"))
        pillar, phase = BRIEF_LABELS.get(acr, ("", ""))
        new.append({"psi_id": r["accession"], "acronym": acr,
                    "name": tidy(r.get("title")), "fire_safety_pillar": pillar,
                    "fire_safety_pillar_basis": PILLAR_BASIS.get(acr, BRIEF) if pillar else "", "fuel_phase": phase,
                    "fuel_phase_basis": BRIEF if phase else ""})
    if new:
        existing = pd.concat([existing, pd.DataFrame(new, columns=cols)], ignore_index=True)
        existing.to_csv(CURATED, index=False, encoding="utf-8", lineterminator="\n")
        print(f"curated_labels.csv: {len(new)} row(s) added -> {CURATED}")
    else:
        print("curated_labels.csv: already has every investigation; left untouched")
    return existing


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted((RAW / "investigations").glob("PSI-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    records = [json.loads(p.read_bytes()) for p in paths]
    not_combustion = [r["accession"] for r in records if r.get("researchArea") != "Combustion Science"]
    if not_combustion:
        print("Records whose Research Area is not Combustion Science:", not_combustion)
        return 1

    labels = curated_labels(records).set_index("psi_id")
    rows, unused_all = [], []
    for r in records:
        pid = r["accession"]
        computed, unused = scan_tables(pid)
        unused_all += unused
        lab = labels.loc[pid]
        row = dict.fromkeys(COLUMNS, "")
        row.update({
            "psi_id": pid, "name": tidy(r.get("title")), "acronym": tidy(r.get("investigationAcronym")),
            "doi": tidy(r.get("doi")), "license": tidy(r.get("licenseIdentifier")),
            "sub_research_area": tidy(r.get("subResearchArea")), "project_type": tidy(r.get("projectType")),
            "flight_platform": tidy(r.get("flightProgram")), "hardware": tidy(r.get("experimentHardware")),
            "objective": tidy(r.get("objective")),
            "data_table_available": "yes" if r.get("experimentalTable") else "no",
            "source_url": PSI_PAGE.format(pid),
            "fire_safety_pillar": lab["fire_safety_pillar"].strip().lower(),
            "fire_safety_pillar_basis": lab["fire_safety_pillar_basis"].strip(),
            "fuel_phase": lab["fuel_phase"].strip().lower(), "fuel_phase_basis": lab["fuel_phase_basis"].strip(),
        })
        for q, (a, b, c) in (("o2", ("o2_min_pct", "o2_max_pct", "o2_basis")),
                             ("pressure", ("pressure_min_psi", "pressure_max_psi", "pressure_basis")),
                             ("flow", ("flow_speed_min_cm_s", "flow_speed_max_cm_s", "flow_speed_basis")),
                             ("o2_stream", ("o2_stream_min_pct", "o2_stream_max_pct", "o2_stream_basis"))):
            if q in computed:
                row[a], row[b], row[c] = computed[q]
        if "o2_stream" in computed:
            row["o2_stream_basis"] = f"{STREAM_O2_LABEL} (team ruling) | " + row["o2_stream_basis"]
        if "flow" in computed:
            lo, hi, _ = computed["flow"]
            row["airflow"] = f"{lo:g} cm/s" if lo == hi else f"{lo:g} to {hi:g} cm/s"
        rows.append(row)

    cat = pd.DataFrame(rows, columns=COLUMNS)
    cat.to_csv(CATALOG, index=False, encoding="utf-8", lineterminator="\n")
    pd.DataFrame(unused_all, columns=["psi_id", "file", "column", "quantity", "status", "reason",
                                      "would_give_min", "would_give_max"]).to_csv(
        NOT_USED, index=False, encoding="utf-8", lineterminator="\n")
    print(f"{len(cat)} investigations -> {CATALOG}")
    print(f"{len(unused_all)} relevant column(s) not used -> {NOT_USED}")

    print("\nCross-check of ids and DOIs read from PSI pages:")
    ok = True
    by_id = cat.set_index("psi_id")
    for pid, (label, doi) in EXPECTED_DOI.items():
        got = by_id.loc[pid, "doi"] if pid in by_id.index else "(id not in catalog)"
        match = got == doi
        ok &= match
        print(f"  {'match   ' if match else 'MISMATCH'} {pid} {label}: expected {doi}, PSI record has {got} "
              f"(acronym \"{by_id.loc[pid, 'acronym'] if pid in by_id.index else ''}\", "
              f"title \"{by_id.loc[pid, 'name'] if pid in by_id.index else ''}\")")

    print("\nBlank cells per column:")
    blanks = (cat == "").sum()
    for c in COLUMNS:
        print(f"  {c:26s} {int(blanks[c]):2d} of {len(cat)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
