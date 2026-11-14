"""Logic behind the Investigation Catalog page (Module A). No Streamlit here.

The catalog is filled by hand by the team from NASA PSI pages. Nothing in this
module adds or guesses a cell: a blank cell stays blank, scores zero in the
ranking and is displayed as "not stated".
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "investigations.csv"
FIXTURE = ROOT / "tests" / "fixtures" / "investigations_fixture.csv"

NOT_STATED = "not stated"

# Expected columns of investigations.csv.
TEXT_COLUMNS = ["psi_id", "name", "doi", "objective", "fuel", "fuel_phase", "sample_geometry", "hardware",
                "airflow", "measurements", "fire_safety_pillar", "data_table_available", "source_url"]
NUMERIC_COLUMNS = ["o2_min_frac", "o2_max_frac", "pressure_min_kpa", "pressure_max_kpa"]
REQUIRED = TEXT_COLUMNS + NUMERIC_COLUMNS
# Written by src/build_catalog.py; optional so that older files and the test fixture still load.
OPTIONAL_TEXT = ["acronym", "license", "sub_research_area", "project_type", "flight_platform",
                 "fuel_phase_basis", "fire_safety_pillar_basis", "o2_basis", "pressure_basis", "flow_speed_basis",
                 "o2_stream_basis"]
OPTIONAL_NUMERIC = ["flow_speed_min_cm_s", "flow_speed_max_cm_s", "o2_stream_min_frac", "o2_stream_max_frac"]
# display order
COLUMNS = ["psi_id", "acronym", "name", "fire_safety_pillar", "fire_safety_pillar_basis", "fuel_phase",
           "fuel_phase_basis", "fuel", "sample_geometry", "hardware", "flight_platform", "project_type",
           "sub_research_area", "o2_min_frac", "o2_max_frac", "o2_basis", "o2_stream_min_frac", "o2_stream_max_frac",
           "o2_stream_basis", "pressure_min_kpa", "pressure_max_kpa",
           "pressure_basis", "airflow", "flow_speed_min_cm_s", "flow_speed_max_cm_s", "flow_speed_basis",
           "measurements", "data_table_available", "objective", "doi", "license", "source_url"]

LABELS = {
    "acronym": "Acronym", "license": "License", "sub_research_area": "Sub research area",
    "project_type": "Project type", "flight_platform": "Flight platform",
    "fuel_phase_basis": "Fuel phase: basis", "fire_safety_pillar_basis": "Pillar: basis",
    "o2_basis": "O2: column used", "pressure_basis": "Pressure: column used",
    "flow_speed_basis": "Flow speed: column used", "flow_speed_min_cm_s": "Flow speed min (cm/s)",
    "flow_speed_max_cm_s": "Flow speed max (cm/s)",
    "o2_stream_min_frac": "Oxidizer-stream O2 min (mole fraction), not ambient",
    "o2_stream_max_frac": "Oxidizer-stream O2 max (mole fraction), not ambient",
    "o2_stream_basis": "Oxidizer-stream O2: column used",
    "psi_id": "PSI id", "name": "Name", "doi": "DOI", "objective": "Objective", "fuel": "Fuel",
    "fuel_phase": "Fuel phase", "sample_geometry": "Sample geometry", "hardware": "Hardware",
    "o2_min_frac": "O2 min (mole fraction)", "o2_max_frac": "O2 max (mole fraction)", "pressure_min_kpa": "Pressure min (kPa)",
    "pressure_max_kpa": "Pressure max (kPa)", "airflow": "Airflow", "measurements": "Measurements",
    "fire_safety_pillar": "Fire-safety pillar", "data_table_available": "Data table in PSI",
    "source_url": "PSI page",
}

# Habitats for the relevance ranking. o2_frac (mole fraction) and pressure_kpa are the targets a
# catalog row is checked against; the page lets the user edit both.
#   pressure_rule "at_or_below": the investigation's pressure range goes down to the target or lower
#   pressure_rule "covers":      the target lies inside the investigation's pressure range
HABITATS = {
    "Moon Base": {"o2_frac": 0.30, "pressure_kpa": 70.3, "pressure_rule": "at_or_below",
                  "note": "From the challenge brief: 30% O2 or more at 10.2 psi (70.3 kPa) or less."},
    "ISS": {"o2_frac": 0.21, "pressure_kpa": 101.3, "pressure_rule": "covers",
            "note": "Earth-like atmosphere: 21% O2 at 14.7 psi (101.3 kPa)."},
    "Pressurised rover": {"o2_frac": 0.30, "pressure_kpa": 70.3, "pressure_rule": "at_or_below",
                          "note": "No rover specification was given to the team; the Moon Base values are "
                                  "used as a starting point. Edit them if you have the real ones."},
}

# How much each fuel phase counts in the "fuel phase" criterion. Cabin
# materials are solids, so solids weigh most. These three values are the
# team's choice, shown on the page.
PHASE_SCORE = {"solid": 1.0, "liquid": 0.5, "gas": 0.25}

CRITERIA = {
    "pillar": "Fire-safety pillar matches the one chosen",
    "phase": "Fuel phase (solid 1, liquid 0.5, gas 0.25)",
    "o2": "O2 range reaches the habitat's O2",
    "pressure": "Pressure range reaches the habitat's pressure",
    "data": "Measured data table available in PSI",
}
DEFAULT_WEIGHTS = {"pillar": 2, "phase": 3, "o2": 2, "pressure": 2, "data": 1}


def load_catalog() -> tuple[pd.DataFrame, bool]:
    """Returns (catalog, is_fixture). Uses the team's file when it exists,
    otherwise the placeholder fixture used by the tests."""
    is_fixture = not CATALOG.exists()
    return read_catalog(FIXTURE if is_fixture else CATALOG), is_fixture


def read_catalog(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} is missing column(s): {', '.join(missing)}")
    for c in OPTIONAL_TEXT + OPTIONAL_NUMERIC:
        if c not in df.columns:
            df[c] = ""
    for c in TEXT_COLUMNS + OPTIONAL_TEXT:
        df[c] = df[c].str.strip()
    for c in ("fuel_phase", "fire_safety_pillar", "data_table_available"):
        df[c] = df[c].str.lower()
    for c in NUMERIC_COLUMNS + OPTIONAL_NUMERIC:  # blank stays missing; anything else must be a number
        col = df[c].str.strip()
        df[c] = pd.to_numeric(col.where(col != ""), errors="raise").astype(float)
    if df["psi_id"].eq("").any() or df["psi_id"].duplicated().any():
        raise ValueError(f"{path.name}: psi_id must be filled and unique on every row")
    return df


def stated(v) -> bool:
    return not (v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and v == ""))


def show(v) -> str:
    """A cell as displayed: blank becomes 'not stated'."""
    if not stated(v):
        return NOT_STATED
    return f"{v:g}" if isinstance(v, float) else str(v)


# ---------------------------------------------------------------------------
# filters
# ---------------------------------------------------------------------------
def filter_catalog(df: pd.DataFrame, pillars=None, phases=None, hardware=None,
                   o2_range: tuple[float, float] | None = None, keep_unstated_o2: bool = True) -> pd.DataFrame:
    out = df
    if pillars:
        out = out[out["fire_safety_pillar"].isin(pillars)]
    if phases:
        out = out[out["fuel_phase"].isin(phases)]
    if hardware:
        out = out[out["hardware"].isin(hardware)]
    if o2_range is not None:
        lo, hi = o2_range
        has = out["o2_min_frac"].notna() | out["o2_max_frac"].notna()
        row_lo = out["o2_min_frac"].fillna(out["o2_max_frac"])
        row_hi = out["o2_max_frac"].fillna(out["o2_min_frac"])
        overlap = has & (row_lo <= hi) & (row_hi >= lo)
        out = out[overlap | (~has & keep_unstated_o2)]
    return out


# ---------------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------------
def criterion_scores(row: pd.Series, pillar: str, o2_frac: float, pressure_kpa: float, pressure_rule: str) -> dict:
    """Each criterion scores between 0 and 1. A blank cell scores 0."""
    s = {"pillar": 1.0 if stated(row["fire_safety_pillar"]) and row["fire_safety_pillar"] == pillar else 0.0,
         "phase": PHASE_SCORE.get(row["fuel_phase"], 0.0),
         "o2": 1.0 if stated(row["o2_max_frac"]) and row["o2_max_frac"] >= o2_frac else 0.0,
         "data": 1.0 if row["data_table_available"] == "yes" else 0.0}
    lo, hi = row["pressure_min_kpa"], row["pressure_max_kpa"]
    if pressure_rule == "at_or_below":
        s["pressure"] = 1.0 if stated(lo) and lo <= pressure_kpa else 0.0
    else:
        s["pressure"] = 1.0 if stated(lo) and stated(hi) and lo <= pressure_kpa <= hi else 0.0
    return s


def criterion_inputs(row: pd.Series) -> dict:
    """The catalog cells each criterion was computed from, as displayed."""
    if stated(row["o2_max_frac"]):
        o2 = show(row["o2_max_frac"])
    elif stated(row.get("o2_stream_max_frac")):
        o2 = (f"scored 0: O2 mole fraction up to {show(row['o2_stream_max_frac'])} is oxidizer-stream O2, "
              "not ambient atmosphere")
    else:
        o2 = NOT_STATED
    return {"pillar": show(row["fire_safety_pillar"]), "phase": show(row["fuel_phase"]),
            "o2": o2,
            "pressure": (f"{show(row['pressure_min_kpa'])} to {show(row['pressure_max_kpa'])}"
                         if stated(row["pressure_min_kpa"]) or stated(row["pressure_max_kpa"]) else NOT_STATED),
            "data": show(row["data_table_available"])}


def rank(df: pd.DataFrame, weights: dict, pillar: str, o2_frac: float, pressure_kpa: float,
         pressure_rule: str) -> pd.DataFrame:
    """Score = 100 x sum(weight x criterion score) / sum(weights). One row per
    investigation, highest first, with the points each criterion contributed."""
    total = sum(weights.values())
    rows = []
    for _, r in df.iterrows():
        s = criterion_scores(r, pillar, o2_frac, pressure_kpa, pressure_rule)
        points = {k: (100 * weights[k] * s[k] / total if total else 0.0) for k in CRITERIA}
        rows.append({"psi_id": r["psi_id"], "acronym": r.get("acronym", ""), "name": r["name"],
                     "score": round(sum(points.values()), 6),
                     **{f"points_{k}": points[k] for k in CRITERIA},
                     **{f"cell_{k}": v for k, v in criterion_inputs(r).items()},
                     "source_url": r["source_url"]})
    out = pd.DataFrame(rows)
    if not len(out):
        return out
    # Highest score first; ties in alphabetical order of acronym (no acronym last), then PSI number.
    out["_no_acr"] = out["acronym"] == ""
    out["_acr"] = out["acronym"].str.lower()
    out["_num"] = pd.to_numeric(out["psi_id"].str.extract(r"(\d+)$")[0], errors="coerce").fillna(0)
    out = out.sort_values(["score", "_no_acr", "_acr", "_num", "psi_id"],
                          ascending=[False, True, True, True, True]).reset_index(drop=True)
    place = out["score"].rank(method="min", ascending=False).astype(int)
    tied = out["score"].duplicated(keep=False)
    out.insert(0, "rank", [f"={p}" if t else str(p) for p, t in zip(place, tied)])
    return out.drop(columns=["_no_acr", "_acr", "_num"])


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------
def compare(df: pd.DataFrame, psi_ids: list[str]) -> tuple[pd.DataFrame, list[bool]]:
    """Fields as rows, investigations as columns. Second value: per row, whether
    the investigations differ on that field."""
    sub = df.set_index("psi_id").loc[psi_ids]
    fields = [c for c in COLUMNS if c != "psi_id"]
    table = pd.DataFrame({pid: [show(sub.loc[pid, f]) for f in fields] for pid in psi_ids},
                         index=[LABELS[f] for f in fields])
    return table, [table.loc[LABELS[f]].nunique() > 1 for f in fields]


def as_context(df: pd.DataFrame) -> str:
    """The whole catalog as text for the AI layer; blanks are written 'not stated'."""
    blocks = []
    for _, r in df.iterrows():
        blocks.append("\n".join([f"psi_id: {r['psi_id']}"]
                                + [f"{LABELS[c]}: {show(r[c])}" for c in COLUMNS if c != "psi_id"]))
    return "\n\n".join(blocks)
