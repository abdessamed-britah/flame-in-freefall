# Flame in Freefall

NASA Space Apps 2026.

## The problem

The challenge, as recorded in the team's project notes from the official brief:

> Build an AI-powered, web-based dashboard that summarizes, ranks and interprets
> NASA PSI combustion investigations to deliver fire-safety insights for crewed
> habitats.

The brief adds that a Moon Base atmosphere will likely be 30% O2 or more at
10.2 psi (527 mmHg) or less. Fire behaves differently in that atmosphere and
without buoyancy, so the evidence has to come from NASA's microgravity
combustion investigations.

## What the dashboard does

Four pages: **Home** (purpose, data sources, limits), **Catalog**,
**Suppression Lab** and **Unified Data**.

**Investigation Catalog.** The 24 investigations that NASA's Physical Sciences
Informatics (PSI) system lists under Combustion Science, built from NASA's own
records. Filter them (fire-safety pillar, fuel phase, hardware, O2 range),
compare two or three side by side with differences highlighted, and rank them
for a habitat (Moon Base, ISS, pressurised rover). The ranking is a visible
weighted sum of five criteria with sliders for the weights, not an AI score,
and every row links to its PSI page.

**Moon Base Suppression Lab.** Built on FLEX (PSI-69), the suppression study
named in the brief. Pick a base atmosphere, a fuel, a droplet size and a
suppressant (CO2 or He), and see:

1. how close the flame is to its extinction limit as suppressant is added, with
   a 90% uncertainty band, drawn only across the range NASA tested;
2. one plain sentence, for example "likely needs at least 40% CO2. NASA's tests
   stop at 50%, so the data cannot give an upper bound";
3. the burning rate with CO2 and He overlaid;
4. the five nearest real NASA tests as evidence;
5. how far to trust the model, including its failure on a suppressant it has
   never seen.

**Unified data.** The test conditions of all 22 experimental tables that PSI
offers for these investigations, centralised in one file with the same units
for every investigation (mole fraction, kPa, cm/s, mm): 2,009 rows. Filter
across investigations, plot any condition against any other, download the CSV,
and see where the Moon Base atmosphere (O2 0.30 at 70.3 kPa) sits among NASA's
tests. A value is converted only when the source column states its unit;
`data/unified/units_map.csv` lists every source column, its original unit and
the conversion applied. Measurements stay in NASA's original tables, linked by
PSI id, file and row.

**AI layer.** Ask the catalog a question, or ask for a short explanation of a
Suppression Lab result. Both are checked before display (see below) and both
fall back to a plain template when no key is set.

## NASA data sources

All data comes from NASA PSI, <https://psi.nasa.gov>. Records were fetched on
2026-11-14 through the public JSON API behind the PSI search page and are stored
untouched in `data/raw/psi/`, with the URL, access time and SHA-256 of every
file in `data/raw/psi/manifest.csv`. Only metadata and the small
"Experimental table" CSV files were fetched.

| PSI id | Acronym | Investigation | DOI | License |
|---|---|---|---|---|
| [PSI-10](https://psi.nasa.gov/physci/repo/data/investigations/PSI-10) | ACME/Flame Design | Advanced Combustion via Microgravity Experiments / Flame Design | [10.60555/w4zy-bt45](https://doi.org/10.60555/w4zy-bt45) | not stated |
| [PSI-20](https://psi.nasa.gov/physci/repo/data/investigations/PSI-20) | ACME BRE | Advanced Combustion via Microgravity Experiments - Burning Rate Emulator | [10.60555/vb93-3y72](https://doi.org/10.60555/vb93-3y72) | CC0-1.0 |
| [PSI-21](https://psi.nasa.gov/physci/repo/data/investigations/PSI-21) | ACME CLD Flame | Advanced Combustion via Microgravity Experiments / Coflow Laminar Diffusion Flame | [10.60555/23e1-9950](https://doi.org/10.60555/23e1-9950) | CC0-1.0 |
| [PSI-22](https://psi.nasa.gov/physci/repo/data/investigations/PSI-22) | ACME E-FIELD Flames | Advanced Combustion via Microgravity Experiments Electric-Field Effects on Laminar Diffusion Flames | [10.60555/se5a-8c73](https://doi.org/10.60555/se5a-8c73) | CC0-1.0 |
| [PSI-23](https://psi.nasa.gov/physci/repo/data/investigations/PSI-23) | ACME s-Flame | Advanced Combustion via Microgravity Experiments-Structure and Response of Spherical Diffusion Flames | [10.60555/k57n-p030](https://doi.org/10.60555/k57n-p030) | CC0-1.0 |
| [PSI-25](https://psi.nasa.gov/physci/repo/data/investigations/PSI-25) | BASS-II | Burning and Suppression of Solids - II | [10.60555/4qc4-de67](https://doi.org/10.60555/4qc4-de67) | CC0-1.0 |
| [PSI-26](https://psi.nasa.gov/physci/repo/data/investigations/PSI-26) | BASS | Burning and Suppression of Solids | [10.60555/58h4-dy80](https://doi.org/10.60555/58h4-dy80) | CC0-1.0 |
| [PSI-39](https://psi.nasa.gov/physci/repo/data/investigations/PSI-39) | CFI | Cool Flames Investigation | [10.60555/m6pj-a914](https://doi.org/10.60555/m6pj-a914) | CC0-1.0 |
| [PSI-47](https://psi.nasa.gov/physci/repo/data/investigations/PSI-47) | DAFT / DAFT-2 | Dust and Aerosol Measurement Feasibility Test / Dust and Aerosol Measurement Feasibility Test-2 | [10.60555/ztgj-d202](https://doi.org/10.60555/ztgj-d202) | CC0-1.0 |
| [PSI-60](https://psi.nasa.gov/physci/repo/data/investigations/PSI-60) |  | Computational and Experimental Analysis of SPICE Data Sets | [10.60555/mzjm-yv57](https://doi.org/10.60555/mzjm-yv57) | CC0-1.0 |
| [PSI-62](https://psi.nasa.gov/physci/repo/data/investigations/PSI-62) |  | Concurrent Flame Spread Modeling using Flamelet Generated Manifolds in Microgravity with Comparison to BASS Experiments using Two-Color Tomography | [10.60555/e9xp-ex83](https://doi.org/10.60555/e9xp-ex83) | CC0-1.0 |
| [PSI-68](https://psi.nasa.gov/physci/repo/data/investigations/PSI-68) | FLEX-2 | Flame Extinguishment Experiment - 2 | [10.60555/byp8-h018](https://doi.org/10.60555/byp8-h018) | CC0-1.0 |
| [PSI-69](https://psi.nasa.gov/physci/repo/data/investigations/PSI-69) | FLEX | Flame Extinguishment Experiment | [10.60555/mbq8-0451](https://doi.org/10.60555/mbq8-0451) | CC0-1.0 |
| [PSI-98](https://psi.nasa.gov/physci/repo/data/investigations/PSI-98) | SAFFIRE-I | Spacecraft Fire Safety Experiment-I | [10.60555/0t15-1z43](https://doi.org/10.60555/0t15-1z43) | CC0-1.0 |
| [PSI-99](https://psi.nasa.gov/physci/repo/data/investigations/PSI-99) | SAFFIRE-II | Spacecraft Fire Experiment-II | [10.60555/2chp-m469](https://doi.org/10.60555/2chp-m469) | CC0-1.0 |
| [PSI-100](https://psi.nasa.gov/physci/repo/data/investigations/PSI-100) | SAFFIRE-III | Spacecraft Fire Experiment-III | [10.60555/040q-4h36](https://doi.org/10.60555/040q-4h36) | CC0-1.0 |
| [PSI-101](https://psi.nasa.gov/physci/repo/data/investigations/PSI-101) | SAME-R | Smoke Aerosol Measurement Experiment-Reflight | [10.60555/2np7-jv14](https://doi.org/10.60555/2np7-jv14) | CC0-1.0 |
| [PSI-102](https://psi.nasa.gov/physci/repo/data/investigations/PSI-102) | SAME | Smoke and Aerosol Measurement Experiment | [10.60555/gd4k-8h62](https://doi.org/10.60555/gd4k-8h62) | CC0-1.0 |
| [PSI-106](https://psi.nasa.gov/physci/repo/data/investigations/PSI-106) | SLICE | Structure and Liftoff In Combustion Experiment | [10.60555/pm12-rg61](https://doi.org/10.60555/pm12-rg61) | CC0-1.0 |
| [PSI-107](https://psi.nasa.gov/physci/repo/data/investigations/PSI-107) | SPICE | Smoke Point In Co-flow Experiment | [10.60555/9kbh-e962](https://doi.org/10.60555/9kbh-e962) | CC0-1.0 |
| [PSI-115](https://psi.nasa.gov/physci/repo/data/investigations/PSI-115) |  | Utilization of the Smoke Aerosol Measurement Experiment Data for Advanced Modeling and Simulation of Smoke Generation in Micro-Gravity | [10.60555/q0v5-1v28](https://doi.org/10.60555/q0v5-1v28) | CC0-1.0 |
| [PSI-117](https://psi.nasa.gov/physci/repo/data/investigations/PSI-117) |  | Effect of External Thermo-Convective Perturbation on Cool Flame Dynamics: A Multidimensional Multi-Physics CFD Analysis | [10.60555/gz0q-b577](https://doi.org/10.60555/gz0q-b577) | CC0-1.0 |
| [PSI-142](https://psi.nasa.gov/physci/repo/data/investigations/PSI-142) |  | Quantitative Studies of Cool Flame Transitions at Radiation / Stretch Extinction Using Counterflow Flames | [10.60555/80qf-vj95](https://doi.org/10.60555/80qf-vj95) | CC0-1.0 |
| [PSI-159](https://psi.nasa.gov/physci/repo/data/investigations/PSI-159) | ACME CFI-G | Advanced Combustion via Microgravity Experiments / Cool Flames Investigation with Gases | [10.60555/cyt1-kh64](https://doi.org/10.60555/cyt1-kh64) | CC0-1.0 |

Column meanings and units of the FLEX table are documented in
[NASA/TP-2015-216046](https://ntrs.nasa.gov/citations/20150023456) (Table IX
and Appendix A.1); the team has not yet confirmed them against that report.

## Unified schema and units map

`src/normalize.py` reads the 22 experimental tables in `data/raw/psi/tables/`
and writes `data/unified/tests_conditions.csv`, one row per source-table row
(2,009 rows), with the same columns and units for every investigation:

| Column | Meaning | Unit |
|---|---|---|
| `psi_id`, `investigation` | PSI id and name | |
| `test_id` | test identifier as printed in the source table | |
| `source_file`, `source_row` | the NASA table and row the values come from (always unique) | |
| `fuel` | as printed in the source table | |
| `fuel_phase` | solid, liquid or gas (team label, from `curated_labels.csv`) | |
| `gravity` | blank in every row: no table states it per row | |
| `o2_mole_frac` | O2 | mole fraction |
| `o2_basis` | "ambient" or "oxidizer stream" (gas fed through the burner) | |
| `pressure_kpa` | pressure | kPa |
| `flow_speed_cm_s` | air or inlet flow speed | cm/s |
| `diluent`, `diluent_mole_frac` | added CO2 or He (FLEX only) | mole fraction |
| `sample_size_mm` | droplet diameter, burner size or nozzle diameter; the units map says which | mm |
| `quality_flag` | approximate values, cells with several values, rows that are not one test | |

`data/unified/units_map.csv` has one row per source column (81 rows): original
header, original unit, conversion, factor, target column and status.

| Status | Columns | Meaning |
|---|---|---|
| converted | 10 | atm x 101.325, bar x 100, mmHg x 101.325/760 to kPa; percent x 0.01 to mole fraction |
| copied | 61 | already in the target unit, or text (test id, fuel) |
| unit not stated | 8 | header gives no unit; not used, cell left blank |
| not mapped | 2 | unit stated but no matching target column |

A value is converted only when the column header or the PSI record states the
unit. Units written inside the cells are not read.

## Validation

Two Gaussian-process models, one per target, trained on the FLEX table. Inputs:
fuel, O2, pressure, CO2, He, initial droplet diameter. Full tables for every
model tried are in `reports/validation.md`.

Tests the model has not seen (5-fold cross-validation grouped by test date):

| Target | Tests | MAE | MAE of mean baseline | R2 | Coverage of 90% interval |
|---|---|---|---|---|---|
| Burning rate K | 257 | 0.048 | 0.107 | 0.69 | 91% |
| Extinction ratio d_ext/d0 | 188 | 0.086 | 0.207 | 0.77 | 91% |

Honesty test, a suppressant the model has never seen (trained without it,
scored on it):

| Target | Suppressant held out | MAE | MAE when it was seen | Times worse | MAE of mean baseline | Coverage of 90% interval |
|---|---|---|---|---|---|---|
| Burning rate K | CO2 | 0.057 | 0.036 | 1.6x | 0.113 | 92% |
| Burning rate K | He | 0.137 | 0.057 | 2.4x | 0.142 | 45% |
| Extinction ratio | CO2 | 0.113 | 0.080 | 1.4x | 0.218 | 86% |
| Extinction ratio | He | 0.117 | 0.095 | 1.2x | 0.191 | 79% |

The burning-rate model does not transfer to a suppressant it has not seen: on
helium it is no better than predicting the average. The app therefore never
extrapolates to a new suppressant, and `predict()` reports `in_range = False`
outside the tested conditions.

The raw FLEX file is audited by `src/audit.py` (45 checks, `reports/audit.md`),
and 60 automated tests cover the prediction range checks, the catalog scoring,
the two AI checks and the unified table (every converted value is traced back
to its source cell, and the FLEX rows are compared with `flex_clean.csv`).

## Limitations

- **Droplets are not cabin materials.** FLEX burned single droplets of methanol
  and heptane. The tool supports fire-safety reasoning; it does not predict a
  cabin fire.
- **No He + CO2 mixtures.** NASA never mixed the two suppressants in FLEX, so
  the app does not either.
- **Only 9 high-pressure tests** (above 900 mmHg), all with 70% CO2. Queries
  above 900 mmHg, or more than 40 mmHg away from the tests near 535 or 760 mmHg,
  are flagged as out of range.
- **Unconfirmed units and labels.** The FLEX header prints the burning rate in
  "mm" and the gases as "O", "N", "CO". The team reads "O" as O2 because the
  four gas fractions sum to 1 in every row (0.98 to 1.01, rounding); the
  burning-rate unit is still unconfirmed.
- **More diluent also means less oxygen.** In FLEX the suppressant replaces part
  of a fixed O2/N2 mix at constant pressure. Adding diluent at a fixed O2/N2
  balance therefore also lowers O2 (40% CO2 brings 30% O2 down to 18%:
  0.30 x (1 - 0.40)), so the data cannot separate the diluent's effect from the
  lower oxygen. The Suppression Lab shows this caveat under its chart.
- **"Visible flame extinction" may not be the end of burning**: FLEX found
  heptane droplets can keep burning in an invisible cool flame.
- **No partial-gravity data in PSI.** All 24 records are labelled by PSI as
  either Microgravity Investigation (19) or Ground Investigation (5).
- **The NASA table does not separate space tests from ground tests.**
- **Many tables do not state their units.** In the unified table, O2 is filled
  for 1,060 of 2,009 rows and pressure for 933; the rest are blank because the
  source column gives no unit, holds several values in one cell, or does not
  exist. No table says per row whether a test ran in microgravity or normal
  gravity, so that column is blank throughout.
- **Known gap: CFI and SAFFIRE-III.** CFI (PSI-39, 87 rows) prints its pressure
  as "1 atm" and its O2, N2 and He as bare numbers under headers with no unit;
  SAFFIRE-III (PSI-100) prints "30 cm/s" and ".33 cm" the same way. Units
  written in the cells are not read, so these conditions are blank in the
  unified table and the catalog. The values are in NASA's original tables.
- **Catalog gaps are shown, not filled.** A cell with no source is blank and
  scores zero. O2 (mole fraction), pressure (kPa) and flow ranges are computed only from table columns
  whose header states the quantity and unit. For ACME Flame Design and CFI-G the
  O2 values are those of the oxidizer stream, not the ambient atmosphere, so
  they are displayed but do not count towards the habitat O2 criterion.

## How AI is used, and how its output is checked

The app calls Google Gemini (`gemini-3.5-flash`, through the `google-genai`
SDK) for two things. All AI text is labelled as AI-generated.

| Feature | What the model receives | Check before display |
|---|---|---|
| Ask the catalog | The whole catalog and the question | Every line must end with a `[psi_id]` citation, and every cited id must exist in the catalog. Otherwise the answer is rejected. If the catalog has no answer the model must say so. |
| Explain this result | The numbers already on the Suppression Lab page | Every number in the text must be one of those numbers. Otherwise the text is rejected. |

A rejected answer, a failed call, or a missing key all lead to the same place:
a plain template summary built from the data, labelled as not AI-generated. The
relevance ranking and the predictions never use AI.

### AI tools used to build the project

Claude Code (Anthropic) was used to write the code, the tests and this README
under the team's direction. The team set the rules (never fill a missing value,
never guess a unit), made the rulings on ambiguous columns, and reviewed each
step. No AI generated or altered any NASA data value.

## Run it locally

```
conda create -n flame python=3.11 -y
conda activate flame
pip install -r requirements.txt
streamlit run app/Home.py
```

Optional, to switch the AI features on, put the key in
`.streamlit/secrets.toml` (git-ignored, never stored in the repository):

```
GEMINI_API_KEY = "..."
```

or set it in the environment (the app reads the secrets file first):

```
set GEMINI_API_KEY=...        (Windows)
export GEMINI_API_KEY=...     (macOS, Linux)
```

To rebuild everything from NASA's files and run the tests:

```
pip install -r requirements-dev.txt
python src/audit.py           # reports/audit.md
python src/clean.py           # data/clean/flex_clean.csv, exclusions.csv
python src/eda.py             # reports/eda.md, reports/figures/
python src/model.py           # reports/validation.md, validation.json, models/
python src/fetch_psi.py       # data/raw/psi/ (skips files already saved)
python src/build_catalog.py   # data/catalog/investigations.csv
python src/normalize.py       # data/unified/tests_conditions.csv, units_map.csv
python -m pytest tests -q
```

## Deploy (Streamlit Community Cloud)

Repository `abdessamed-britah/flame-in-freefall`, branch `main`, main file
`app/Home.py`, Python 3.11. Add `GEMINI_API_KEY = "..."` under the app's
Secrets to switch the AI features on. `requirements.txt` pins the versions the
saved models were trained with.

## Layout

```
data/raw/      NASA FLEX table, untouched
data/raw/psi/  PSI records, experimental tables and manifest.csv, untouched
data/clean/    flex_clean.csv (274 rows), exclusions.csv (tests left out of modelling, per target)
data/catalog/  investigations.csv, curated_labels.csv, columns_not_used.csv
data/unified/  tests_conditions.csv (one row per source-table row), units_map.csv
src/           audit.py, clean.py, eda.py, model.py, lab.py, catalog.py, ai.py,
               fetch_psi.py, build_catalog.py, normalize.py
models/        saved models (joblib), one per target, written by src/model.py
app/           Home.py, pages/1_Catalog.py, pages/2_Suppression_Lab.py, pages/3_Unified_Data.py
reports/       audit.md, eda.md, validation.md, validation.json, figures/
tests/         test_predict.py, test_catalog.py, test_ai.py, test_normalize.py, fixtures/
```

- `models/` holds `burning_rate_k.joblib` and `d_ext_over_d0.joblib`. They load
  only with the package versions pinned in `requirements.txt`.
- `src/eda.py` writes `reports/eda.md` and the figures (needs matplotlib).
- `pressure_band` is a column of `flex_clean.csv`: `near_535` (below 600 mmHg),
  `near_760` (600 to 900 mmHg), `above_900`, and missing for test 114, whose
  pressure is printed as 0.
- `data/catalog/curated_labels.csv` holds the team's labels (fire-safety pillar,
  fuel phase), each with its basis. The build never overwrites it: edit it, then
  rerun `src/build_catalog.py`.
- `data/catalog/columns_not_used.csv` lists table columns that looked relevant
  but whose header does not state the unit.
