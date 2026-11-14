# Flame in Freefall

NASA Space Apps 2026. A dashboard that helps researchers, engineers and students
read NASA's microgravity combustion investigations for fire-safety insight in
crewed habitats.

- **Investigation Catalog** (Module A): in progress on another branch.
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

## Layout

```
data/raw/      NASA file, untouched
data/clean/    flex_clean.csv (274 rows), exclusions.csv (tests left out of modelling, per target)
src/           audit.py, clean.py, eda.py, model.py, lab.py
models/        saved models (joblib), one per target, written by src/model.py
app/           Home.py, pages/2_Suppression_Lab.py
reports/       audit.md, eda.md, validation.md, validation.json, figures/
tests/         test_predict.py
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
