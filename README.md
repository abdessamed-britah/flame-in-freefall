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

**AI layer.** Ask the catalog a question, or ask for a short explanation of a
Suppression Lab result. Both are checked before display (see below) and both
fall back to a plain template when no key is set.

## NASA data sources

All data comes from NASA PSI, <https://psi.nasa.gov>. Records were fetched on
2026-11-14 through the public JSON API behind the PSI search page and are stored
untouched in `data/raw/psi/`, with the URL, access time and SHA-256 of every
file in `data/raw/psi/manifest.csv`. Only metadata and the small
"Experimental table" CSV files were fetched.

<!--PSI_TABLE-->

Column meanings and units of the FLEX table are documented in
[NASA/TP-2015-216046](https://ntrs.nasa.gov/citations/20150023456) (Table IX
and Appendix A.1); the team has not yet confirmed them against that report.

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
and 53 automated tests cover the prediction range checks, the catalog scoring
and the two AI checks.

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
- **O2 and suppressant vary together.** In FLEX the suppressant replaces part of
  a fixed O2/N2 mix at constant pressure, so the data cannot separate "less
  oxygen" from "more suppressant" within one pressure group.
- **"Visible flame extinction" may not be the end of burning**: FLEX found
  heptane droplets can keep burning in an invisible cool flame.
- **No partial-gravity data in PSI.** All 24 records are labelled by PSI as
  either Microgravity Investigation (19) or Ground Investigation (5).
- **The NASA table does not separate space tests from ground tests.**
- **Catalog gaps are shown, not filled.** A cell with no source is blank and
  scores zero. O2, pressure and flow ranges are computed only from table columns
  whose header states the quantity and unit. For ACME Flame Design and CFI-G the
  O2 values are those of the oxidizer stream, not the ambient atmosphere, so
  they are displayed but do not count towards the habitat O2 criterion.

## How AI is used, and how its output is checked

The app calls Claude (`claude-haiku-5-5`, Anthropic API) for two things. All AI
text is labelled as AI-generated.

| Feature | What the model receives | Check before display |
|---|---|---|
| Ask the catalog | The whole catalog and the question | Every line must end with a `[psi_id]` citation, and every cited id must exist in the catalog. Otherwise the answer is rejected. If the catalog has no answer the model must say so. |
| Explain this result | The numbers already on the Suppression Lab page | Every number in the text must be one of those numbers. Otherwise the text is rejected. |

A rejected answer, a failed call, or a missing key all lead to the same place:
a plain template summary built from the data, labelled as not AI-generated. The
relevance ranking and the predictions never use AI.

AI assistance was also used to write the code (Claude Code).

## Run it locally

```
conda create -n flame python=3.11 -y
conda activate flame
pip install -r requirements.txt
streamlit run app/Home.py
```

Optional, to switch the AI features on (the key is read from the environment and
never stored in the repository):

```
set ANTHROPIC_API_KEY=...        (Windows)
export ANTHROPIC_API_KEY=...     (macOS, Linux)
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
python -m pytest tests -q
```

## Deploy (Streamlit Community Cloud)

Repository `abdessamed-britah/flame-in-freefall`, branch `main`, main file
`app/Home.py`, Python 3.11. Add `ANTHROPIC_API_KEY = "..."` under the app's
Secrets to switch the AI features on. `requirements.txt` pins the versions the
saved models were trained with.

## Layout

```
data/raw/      NASA FLEX table, untouched
data/raw/psi/  PSI records, experimental tables and manifest.csv, untouched
data/clean/    flex_clean.csv (274 rows), exclusions.csv (tests left out of modelling, per target)
data/catalog/  investigations.csv, curated_labels.csv, columns_not_used.csv
src/           audit.py, clean.py, eda.py, model.py, lab.py, catalog.py, ai.py,
               fetch_psi.py, build_catalog.py
models/        saved models (joblib), one per target, written by src/model.py
app/           Home.py, pages/1_Catalog.py, pages/2_Suppression_Lab.py
reports/       audit.md, eda.md, validation.md, validation.json, figures/
tests/         test_predict.py, test_catalog.py, test_ai.py, fixtures/
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
