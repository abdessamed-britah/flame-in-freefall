# Flame in Freefall — NASA Space Apps 2026

## Challenge (from the official brief)
Build an AI-powered, web-based dashboard that summarizes, ranks and interprets
NASA PSI combustion investigations to deliver fire-safety insights for crewed
habitats. Suggested user abilities: (a) identify the investigations most
relevant to habitat fire safety, (b) extract data that supports predictive
modelling of flammability, (c) highlight research that informs fire-safety
controls and equipment. Audience: researchers, engineers, students.

Key fact from the brief: the Moon Base atmosphere will likely be 30% O2 or
more at 10.2 psi (527 mmHg) or less. FLEX has 103 tests near 535 mmHg with O2
up to 0.34, and the brief names FLEX as the suppression study (CO2 and He).

## Goal: one dashboard, two modules
Module A, Investigation Catalog (answers a and c; required by the brief):
- `data/catalog/investigations.csv`, one row per PSI combustion investigation,
  filled by hand from PSI pages by teammates: psi_id, name, doi, objective,
  fuel and phase (solid/liquid/gas), sample geometry, hardware (CIR/MDCA, MSG,
  ACME, Cygnus), O2 range, pressure range, airflow, measurements, fire-safety
  pillar (prevention/detection/suppression), source URL. Blank when PSI does
  not say; never guessed.
- Filter, compare side by side, and rank by relevance to a chosen habitat.
  The ranking is a transparent score with visible criteria and weights the
  user can change. It is never an opaque AI score.
- AI summaries and Q&A answer only from catalog rows and cite psi_id. If the
  catalog does not contain the answer, say so.

Module B, Moon Base Suppression Lab (answers b; our differentiator), built on
FLEX (PSI-69). For an atmosphere the user picks, with a Moon Base preset:
1. Predicted burning rate and how close the flame is to its extinction limit,
   with uncertainty.
2. The classical d2-law physics estimate next to the model.
3. The nearest real NASA tests as evidence.
4. How much CO2 or He would push that atmosphere to the extinction limit.

Team of 4, 10 working hours, CPU only (no GPU), Python in a conda env.
The app must be web-based: Streamlit, deployed to a public URL.

## Data
Raw file: `data/raw/PSI-69_Experimental table_FLEX.csv` (NASA PSI-69, CC0).

### Verified facts about the raw file (audited 2026-11-14)
- 274 rows, 15 columns, one row per test, 80 distinct test dates (2009-2011).
- Encoding cp1252. The only non-ASCII byte is 0x96 (en dash), used 34 times as
  a "no value" marker: 6 in initial diameter, 28 in extinction diameter.
- Columns: FLEX Test #, FLEX Identifier, Test Date, Test GMT, Fuel,
  Ambient pressure; mmHg, then O / N / CO / He initial ambient composition;
  mole fraction, Droplet initial diameter; mm, Visible flame extinction
  diameter; mm, Burning rate; mm, Burn time; s, Test end.
- Fuel: Methanol 157, Heptane 117.
- Test end: Extinction 186, Disruption 61, Completion 27.
- O2 0.12-0.34. CO2 > 0 in 123 tests (max 0.70), He > 0 in 50 tests
  (max 0.45), never both. 101 tests are O2/N2 only.
- Pressure: 161 tests near 760 mmHg, 103 near 535 mmHg, 9 at 1500-2320 mmHg.
- Missing (blank or dash): initial diameter 12, extinction diameter 77,
  burning rate 16, burn time 6.

### Known problems — flag, never silently fix
- Test 114 (C11M201): pressure printed as 0.
- Identifier 193F001 appears twice (tests 70 and 73), same date and time,
  slightly different measurements.
- Tests 114 and 118 share the same GMT time.
- Burn time contains "~6" and "~9" (tests 223, 224): approximate values.
- Extinction diameter is exactly 0 in 8 tests (4 Completion, 4 Disruption).
  Meaning unconfirmed; do not treat as a measured diameter until confirmed.
- Gas fractions sum to 0.98-1.01 in 29 rows (rounding). Do not renormalise
  the raw values; keep the sum as a column.
- Dates mix 4-digit and 2-digit years.

### Unconfirmed — the science lead must confirm from NASA/TP-2015-216046
(Table IX and Appendix A.1). Label these "unconfirmed" until then.
- Header subscripts are lost: "O", "N", "CO" are presumably O2, N2, CO2.
- "Burning rate; mm" has a truncated unit, presumably mm^2/s (d2-law K).
- What Disruption, Completion and Extinction mean operationally.
- What dash versus blank versus 0 means in the extinction diameter.
- The file has no column separating space tests from ground tests; never
  claim a given row is one or the other.

## Targets
- Primary 1: burning rate K (regression), 258 rows available.
- Primary 2: extinction ratio d_ext/d0 (regression), about 190 rows. Near 1
  means the flame went out almost at once (close to the flammability limit);
  small means most of the droplet burned. This is the "limit map" quantity.
- Secondary: Test end (classification). Disruption may be an experimental
  artefact, not chemistry; report it but do not build the story on it.
- Caution: "visible flame extinction" is not always the end of burning.
  FLEX found heptane droplets can keep burning in an invisible cool flame.

## Rules (non-negotiable)
- Never modify anything in `data/raw/`. Write cleaned data to `data/clean/`.
- Never invent, estimate or zero-fill a missing value. Missing stays missing.
- Flag odd rows in a `quality_flag` column; log every excluded row and reason
  in `data/clean/exclusions.csv`.
- Do not guess a unit or a column meaning.
- Small data: simple models only (linear/ridge, gradient boosting, Gaussian
  process). No deep learning.
- Validate with grouped cross-validation, grouped by test date, so tests from
  the same day never sit in both train and test. For classification report
  balanced accuracy and per-class recall.
- Always report a trivial baseline (mean, majority class) beside each model.
- The app must warn when a query is outside the range of the data. CO2 and He
  were never mixed, and high pressure has only 9 tests.
- No overclaiming: these are fuel droplets, not cabin materials. The tool
  supports fire-safety reasoning; it does not predict a cabin fire.
- Every number shown in the app must trace to a row or a stated formula.

## Layout
```
data/raw/      NASA files, untouched
data/clean/    flex_clean.csv, exclusions.csv
src/           clean.py, features.py, model.py, physics.py
app/           app.py (Streamlit)
reports/       audit.md, eda.md, validation.md, figures
docs/          NASA PDF, notes, sources
```

## Environment
```
conda create -n flame python=3.11 -y
conda activate flame
pip install pandas scikit-learn plotly streamlit
```

## Work order — one step at a time, stop for review after each
1. Audit: reproduce the verified facts above from the raw file and write
   `reports/audit.md`. Report any number that does not match.
2. Clean: `src/clean.py` -> `data/clean/flex_clean.csv` with tidy names,
   parsed dates, numeric columns, `quality_flag`, derived columns
   (diluent type, gas sum, d_ext/d0, pressure in atm), and `exclusions.csv`.
3. Explore: `reports/eda.md` with K and d_ext/d0 against O2, by fuel, diluent
   and pressure; coverage of the atmosphere space.
4. Model: K and d_ext/d0 regressors with the validation above and prediction
   intervals; write `reports/validation.md`.
5. Physics: `src/physics.py` with the d2-law baseline (formula and property
   values supplied by the science lead; do not make them up).
6. Suppression Lab page (Module B): inputs with a Moon Base preset,
   prediction with uncertainty, physics comparison, nearest NASA tests,
   out-of-range warning, CO2 or He fraction needed to reach the predicted
   extinction limit, sources panel.
7. Catalog page (Module A): load `data/catalog/investigations.csv`, filters,
   side-by-side compare, transparent relevance ranking with editable weights.
8. AI layer: summaries and Q&A grounded in the catalog and the FLEX table,
   with psi_id citations. Must degrade gracefully when no API key is set.
9. Deploy to a public URL; write README with data sources, limits, AI use.