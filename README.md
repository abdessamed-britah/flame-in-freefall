# Flame in Freefall

NASA Space Apps 2026. A dashboard that helps researchers, engineers and students
read NASA's microgravity combustion investigations for fire-safety insight in
crewed habitats.

- **Investigation Catalog** (Module A): filter, compare and rank NASA PSI
  combustion investigations by relevance to a habitat, with a transparent score.
- **Moon Base Suppression Lab** (Module B): how much CO2 or He pushes a burning
  fuel droplet towards its extinction limit, built on NASA's FLEX tests.

## Data source

NASA PSI-69, Flame Extinguishment Experiment (FLEX), experimental table, CC0:
<https://doi.org/10.60555/mbq8-0451>. The file is kept unmodified in `data/raw/`.

## Run

```
conda create -n flame python=3.11 -y
conda activate flame
pip install -r requirements.txt
streamlit run app/Home.py
```

To regenerate everything from the raw file and run the tests:

```
pip install -r requirements-dev.txt
python src/audit.py     # reports/audit.md
python src/clean.py     # data/clean/flex_clean.csv, exclusions.csv
python src/eda.py       # reports/eda.md, reports/figures/
python src/model.py     # reports/validation.md, validation.json, models/
python -m pytest tests -q
```

## Catalog file

The Catalog page reads `data/catalog/investigations.csv` (UTF-8, one row per PSI
investigation, filled by hand from the PSI pages). Until that file exists the
page shows three made-up placeholder rows from `tests/fixtures/` under a red
banner. Leave a cell blank when PSI does not say; never guess. Columns:

| Column | Content |
|---|---|
| `psi_id` | PSI identifier, unique, required |
| `name`, `doi`, `objective`, `fuel`, `sample_geometry`, `hardware`, `airflow`, `measurements` | free text |
| `fuel_phase` | `solid`, `liquid` or `gas` |
| `o2_min_pct`, `o2_max_pct` | O2 range tested, in percent (numbers only) |
| `pressure_min_psi`, `pressure_max_psi` | pressure range tested, in psi (numbers only) |
| `fire_safety_pillar` | `prevention`, `detection` or `suppression` |
| `data_table_available` | `yes` if PSI offers a measured data table, `no` if not |
| `source_url` | link to the PSI page |

The relevance score is `100 x sum(weight x criterion) / sum(weights)` over five
criteria (pillar match, fuel phase, O2 reaches the habitat's O2, pressure reaches
the habitat's pressure, data table available). A blank cell scores zero.

## AI features

Catalog Q&A and "Explain this result" use Claude through the Anthropic API. Set
the key in the environment, never in the repository:

```
set ANTHROPIC_API_KEY=...        (Windows)
export ANTHROPIC_API_KEY=...     (macOS, Linux)
```

On Streamlit Community Cloud, add `ANTHROPIC_API_KEY = "..."` as a root-level
secret. Without a key the app still works and shows template summaries built
from the data. Every AI text is labelled and checked before display: a catalog
answer is rejected if any line lacks a `psi_id` citation or cites an id that is
not in the catalog; an explanation is rejected if it contains a number that is
not already on the page.

## Layout

```
data/raw/      NASA file, untouched
data/clean/    flex_clean.csv (274 rows), exclusions.csv (tests left out of modelling, per target)
data/catalog/  investigations.csv (added by the team; not present yet)
src/           audit.py, clean.py, eda.py, model.py, lab.py, catalog.py, ai.py
models/        saved models (joblib), one per target, written by src/model.py
app/           Home.py, pages/1_Catalog.py, pages/2_Suppression_Lab.py
reports/       audit.md, eda.md, validation.md, validation.json, figures/
tests/         test_predict.py, test_catalog.py, test_ai.py, fixtures/
```

Notes on parts that are not in the original plan:

- `models/` holds `burning_rate_k.joblib` and `d_ext_over_d0.joblib`. They load
  only with the package versions pinned in `requirements.txt`.
- `src/eda.py` writes `reports/eda.md` and the figures (needs matplotlib).
- `src/lab.py` holds the logic of the Suppression Lab page (slices, model
  curves, charts), separate from Streamlit so it can be tested.
- `pressure_band` is a column of `flex_clean.csv`: `near_535` (below 600 mmHg),
  `near_760` (600 to 900 mmHg), `above_900`, and missing for test 114, whose
  pressure is printed as 0.

## Limits

- These are single fuel droplets (methanol, heptane), not cabin materials. The
  tool supports fire-safety reasoning; it does not predict a cabin fire.
- "Visible flame extinction" may not be the end of burning.
- Suppressant is added at constant total pressure.
- The burning-rate unit and the gas labels (O2, N2, CO2) are still unconfirmed
  against NASA/TP-2015-216046.
- The NASA table does not separate space tests from ground tests.
- CO2 and He were never mixed; only 9 tests exist above 900 mmHg.
