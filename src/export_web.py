"""Export everything the static Next.js front end (web/) shows, as JSON, once.

No number is computed in the browser except the catalog's weighted sum (the formula shown on the
page) when the user moves a weight slider. Everything else comes from these files:

  web/public/data/catalog.json     24 investigations; 0/1 criterion scores per habitat and pillar;
                                   the Python ranking with default weights for each habitat
  web/public/data/unified.json     2,009 rows, only the columns the chart and its tooltip need
  web/public/data/tests_conditions.csv   copy of data/unified/tests_conditions.csv for download
  web/public/data/lab_grid.json    predict() on a grid: fuel x diluent x base atmosphere x droplet
                                   size x suppressant fraction 0 to 0.50 step 0.025, both targets;
                                   the 0.90 threshold crossing and the finding sentence from the
                                   Suppression Lab's own fine curve; NASA test points per slice;
                                   the 5 nearest tests per grid point
  web/public/data/validation.json  the Suppression Lab's validation tables
  web/public/data/rag_saved.json   the saved, checked answers with every retrieved passage verbatim
  web/public/data/meta.json        counts, sources, DOIs, limits, export time, git commit
  web/data/rag_index.json          SERVER-SIDE ONLY (not in public/): the passages, the fitted TF-IDF
                                   vocabulary, idf and L2-normalised sparse passage vectors, the
                                   tokeniser settings, the quotas, the prompt and check constants of
                                   src/ai.py, and the Python top 6 for the 30 check questions (parity test)

Run:  python src/export_web.py              everything (about 5 minutes: some 7,000 calls to predict())
      python src/export_web.py rag_index    only web/data/rag_index.json
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ai  # noqa: E402
import catalog as cat  # noqa: E402
import lab  # noqa: E402
import retrieve  # noqa: E402
from model import predict  # noqa: E402

OUT = ROOT / "web" / "public" / "data"
UNIFIED = ROOT / "data" / "unified" / "tests_conditions.csv"
SAVED = ROOT / "data" / "corpus" / "saved_answers.json"

FUELS = ["Methanol", "Heptane"]
DILUENTS = ["CO2", "He"]
ATMOSPHERES = {  # web key -> Suppression Lab preset (same o2_base, same pressure: median of that preset's tests)
    "moon": "Moon Base (30% O2, ~535 mmHg)",
    "iss": "Earth-like / ISS (21% O2, ~760 mmHg)",
}
D0_MM = [2.0, 2.5, 3.0, 3.48, 4.0]
FRACTIONS = [round(i * 0.025, 3) for i in range(21)]  # 0 to 0.50
THRESHOLD = lab.DEFAULT_THRESHOLD  # 0.90
TARGETS = ["d_ext_over_d0", "burning_rate_k"]
PILLARS = ["prevention", "detection", "suppression"]


def clean(v):
    """JSON-safe value: NaN and numpy types become None and Python numbers."""
    if v is None:
        return None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(float(v)) else float(v)
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def write(name: str, obj) -> None:
    path = OUT / name
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{name}: {path.stat().st_size / 1024:.0f} kB")


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# ---------------------------------------------------------------------------
def export_catalog() -> dict:
    df, is_fixture = cat.load_catalog()
    assert not is_fixture, "data/catalog/investigations.csv is missing"
    rows = []
    for _, r in df.iterrows():
        scores = {}
        for h_name, h in cat.HABITATS.items():
            scores[h_name] = {p: cat.criterion_scores(r, p, h["o2_frac"], h["pressure_kpa"], h["pressure_rule"])
                              for p in PILLARS}
        rows.append({
            **{c: (cat.show(r[c]) if c != "source_url" else r[c]) for c in cat.COLUMNS},
            "cells": cat.criterion_inputs(r),
            "criteria": scores,  # 0/1 (fuel phase: 0.25/0.5/1) per habitat and pillar, from catalog.criterion_scores
        })
    default_rank = {}
    for h_name, h in cat.HABITATS.items():
        ranked = cat.rank(df, cat.DEFAULT_WEIGHTS, "suppression", h["o2_frac"], h["pressure_kpa"], h["pressure_rule"])
        default_rank[h_name] = [{"rank": x["rank"], "psi_id": x["psi_id"], "score": round(float(x["score"]), 6)}
                                for x in ranked.to_dict("records")]
    out = {"columns": cat.COLUMNS, "labels": cat.LABELS, "criteria": cat.CRITERIA,
           "default_weights": cat.DEFAULT_WEIGHTS, "phase_score": cat.PHASE_SCORE, "pillars": PILLARS,
           "default_pillar": "suppression",
           "habitats": {k: {kk: vv for kk, vv in v.items()} for k, v in cat.HABITATS.items()},
           "formula": "Score = 100 x sum(weight x criterion) / sum(weights). A blank cell scores 0.",
           "rows": rows, "python_default_ranking": default_rank}
    write("catalog.json", out)
    return out


def export_unified() -> int:
    u = pd.read_csv(UNIFIED, dtype=str, keep_default_na=False)
    keep = ["psi_id", "investigation", "test_id", "fuel", "o2_mole_frac", "o2_basis", "pressure_kpa",
            "quality_flag", "source_row"]
    rows = []
    for r in u[keep].to_dict("records"):
        if r["o2_mole_frac"] == "" and r["pressure_kpa"] == "":
            continue  # a row with neither value cannot appear on the O2-pressure chart
        rows.append({"id": r["psi_id"], "inv": r["investigation"], "test": r["test_id"], "fuel": r["fuel"],
                     "o2": float(r["o2_mole_frac"]) if r["o2_mole_frac"] else None, "basis": r["o2_basis"],
                     "p": float(r["pressure_kpa"]) if r["pressure_kpa"] else None,
                     "notTest": "row_is_" in r["quality_flag"], "row": int(r["source_row"])})
    counts = u.groupby("psi_id").size().to_dict()
    write("unified.json", {"total_rows": len(u), "rows_per_investigation": counts,
                           "moon": {"o2": 0.30, "p_kpa": 70.3}, "rows": rows})
    shutil.copyfile(UNIFIED, OUT / "tests_conditions.csv")
    return len(u)


def export_lab() -> dict:
    df = lab.load_clean()
    tests: dict[int, dict] = {}

    def test_ref(t: dict) -> int:
        n = int(t["test_number"])
        if n not in tests:
            row = df[df["test_number"] == n].iloc[0]
            tests[n] = {k: clean(v) for k, v in {
                "test": n, "id": t["flex_identifier"], "date": row["test_date"], "fuel": t["fuel"],
                "p_mmhg": row["pressure_mmhg"], "o2": t["o2_mole_frac"], "co2": t["co2_mole_frac"],
                "he": t["he_mole_frac"], "d0": t["d0_mm"], "k": t["burning_rate_k"], "ratio": t["d_ext_over_d0"],
                "end": t["test_end"], "flag": t["quality_flag"]}.items()}
        return n

    slices, n_calls = [], 0
    for atm, preset in ATMOSPHERES.items():
        pressure = lab.preset_pressure_mmhg(df, preset)
        for fuel in FUELS:
            for dil in DILUENTS:
                s = lab.slice_tests(df, preset, fuel, dil)
                lo, hi = lab.fraction_range(s)
                points = [{k: clean(v) for k, v in {
                    "test": r["test_number"], "id": r["flex_identifier"], "x": r["diluent_frac"], "dil": r["diluent"],
                    "ratio": r["d_ext_over_d0"], "k": r["burning_rate_k"], "d0": r["d0_mm"], "date": r["test_date"],
                    "end": r["test_end"]}.items()} for r in s.to_dict("records")]
                for d0 in D0_MM:
                    grid = {t: [] for t in TARGETS}
                    nearest = []
                    for x in FRACTIONS:
                        q = lab.query(preset, pressure, fuel, dil, x, d0)
                        for t in TARGETS:
                            r = predict(**q, target=t, n_nearest=5 if t == "d_ext_over_d0" else 0)
                            n_calls += 1
                            grid[t].append({"x": x, "mean": r["mean"], "lower": r["lower"], "upper": r["upper"],
                                            "in_range": bool(r["in_range"]), "warnings": r["warnings"]})
                            if t == "d_ext_over_d0":
                                nearest.append([{"test": test_ref(n), "distance": n["distance"]}
                                                for n in r["nearest_tests"]])
                    # the finding sentence and crossing, from the Suppression Lab's own curve (step 0.005)
                    fine = lab.curve(preset, pressure, fuel, dil, d0, "d_ext_over_d0", lo, hi)
                    n_calls += len(fine)
                    slices.append({
                        "atm": atm, "fuel": fuel, "dil": dil, "d0": d0, "pressure_mmhg": pressure,
                        "o2_base": lab.PRESETS[preset]["o2_base"], "tested": [lo, hi], "d0_tested": list(lab.d0_range(s)),
                        "grid": grid, "nearest": nearest,
                        "crossing": lab.crossing(fine, THRESHOLD),
                        "sentence": lab.crossing_sentence(fine, THRESHOLD, fuel, dil, d0),
                        "points_key": f"{atm}|{fuel}|{dil}"})
                slices_points[f"{atm}|{fuel}|{dil}"] = points
                print(f"  {atm} {fuel} {dil}: {len(s)} tests, tested {lo:.2f}-{hi:.2f}", flush=True)
    out = {"threshold": THRESHOLD, "fractions": FRACTIONS, "d0_mm": D0_MM, "fuels": FUELS, "diluents": DILUENTS,
           "atmospheres": {k: {"label": v, "o2_base": lab.PRESETS[v]["o2_base"],
                               "pressure_mmhg": lab.preset_pressure_mmhg(df, v)} for k, v in ATMOSPHERES.items()},
           "slices": slices, "points": slices_points, "tests": tests, "limits": lab.LIMITS,
           "note": "mean, lower, upper and in_range are model.predict() output; the d_ext/d0 mean and interval are "
                   "clipped to [0, 1] by predict(). crossing and sentence come from lab.curve() with step 0.005 "
                   "over the tested range of the slice, as on the Streamlit Suppression Lab."}
    print(f"  {n_calls} predict() calls")
    write("lab_grid.json", out)
    return out


slices_points: dict[str, list] = {}


def export_validation() -> None:
    v = lab.load_validation()
    cv, lodo = lab.trust_tables(v)
    write("validation.json", {"n_folds": v["n_folds"], "chosen": v["chosen"], "cv": records(cv), "lodo": records(lodo),
                              "source": "reports/validation.json, written by src/model.py"})


def export_rag() -> int:
    by_id = {p["passage_id"]: p for p in retrieve.load_passages()}
    out = []
    for a in json.loads(SAVED.read_text(encoding="utf-8")):
        passages = [by_id[i] for i in a["retrieved_ids"]]
        ok, why = ai.check_passage_citations(a["text"], {p["passage_id"] for p in passages})
        assert ok, (a["question"], why)
        out.append({**a, "check": "passed", "support": ai.support(a["text"], passages),
                    "passages": [{k: p[k] for k in ("passage_id", "source_type", "doc_title", "section", "source_url",
                                                     "text", "psi_ids", "field")}
                                 | {"source_label": retrieve.SOURCE_LABEL[p["source_type"]],
                                    "cited": p["passage_id"] in a["citations"]} for p in passages]})
    write("rag_saved.json", {"model": ai.MODEL, "support_threshold": ai.SUPPORT_THRESHOLD,
                             "answers": out, "corpus_passages": len(by_id),
                             "by_source_type": pd.Series([p["source_type"] for p in by_id.values()]).value_counts().to_dict(),
                             "source_labels": retrieve.SOURCE_LABEL})
    return len(by_id)


def export_rag_index() -> None:
    """Everything the Next.js route needs to retrieve and check exactly as src/retrieve.py and src/ai.py do."""
    ix = retrieve.build_index()
    v = ix.vectorizer
    assert v.ngram_range == (1, 2) and v.lowercase and v.sublinear_tf and v.norm == "l2" and v.analyzer == "word"
    m = ix.matrix.tocsr()
    vocab = sorted(v.vocabulary_, key=v.vocabulary_.get)  # position = column index
    vectors = [[m.indices[m.indptr[i]:m.indptr[i + 1]].tolist(), m.data[m.indptr[i]:m.indptr[i + 1]].tolist()]
               for i in range(m.shape[0])]
    questions = json.loads((ROOT / "tests" / "retrieval_questions.json").read_text(encoding="utf-8"))
    out = {
        "passages": [{"id": p["passage_id"], "text": p["text"], "source_type": p["source_type"],
                      "source_label": retrieve.SOURCE_LABEL[p["source_type"]], "title": p["doc_title"],
                      "section": p["section"], "url": p["source_url"], "psi_id": p["psi_id"], "psi_ids": p["psi_ids"],
                      "field": p["field"]} for p in ix.passages],
        "tokenizer": {"token_pattern": v.token_pattern, "lowercase": True, "ngram_range": [1, 2],
                      "stop_words": sorted(v.get_stop_words()), "sublinear_tf": True, "norm": "l2"},
        "vocabulary": vocab, "idf": v.idf_.tolist(), "vectors": vectors,
        "top_k": retrieve.TOP_K, "quota": retrieve.QUOTA, "publication_field": retrieve.PUBLICATION,
        "ai": {"model": ai.MODEL, "system": ai.RAG_SYSTEM, "not_in_passages": ai.NOT_IN_PASSAGES,
               "not_in_passages_reply": ai.NOT_IN_PASSAGES_REPLY, "no_passages_reply": ai.NO_PASSAGES_REPLY,
               "search_label": ai.SEARCH_LABEL, "ai_label": "AI-generated (Gemini), checked",
               "support_threshold": ai.SUPPORT_THRESHOLD, "support_stop_words": sorted(ai._STOP)},
        "parity": [{"question": q["question"], "ids": [p["passage_id"] for p in ix.search(q["question"])]}
                   for q in questions],
    }
    path = ROOT / "web" / "data" / "rag_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"web/data/rag_index.json: {path.stat().st_size / 1024:.0f} kB, {len(vocab)} terms, {len(vectors)} passages")


def export_meta(catalog: dict, n_unified: int, n_passages: int, grid: dict) -> None:
    flex = lab.load_clean()
    key = next(s for s in grid["slices"] if s["atm"] == "moon" and s["fuel"] == "Methanol" and s["dil"] == "CO2"
               and s["d0"] == 3.48)
    write("meta.json", {
        "counts": {"investigations": len(catalog["rows"]), "unified_rows": n_unified, "passages": n_passages,
                   "flex_tests": len(flex)},
        "key_finding": {"sentence": key["sentence"], "o2_base": key["o2_base"], "pressure_mmhg": key["pressure_mmhg"],
                        "tests": len(grid["points"][key["points_key"]]),
                        "o2_at_40": round(key["o2_base"] * (1 - 0.40), 4)},
        "sources": [{"psi_id": r["psi_id"], "acronym": r["acronym"], "name": r["name"], "doi": r["doi"],
                     "url": r["source_url"]} for r in catalog["rows"]],
        "flex": {"doi_url": lab.PSI69_DOI_URL, "report_url": lab.FLEX_REPORT_URL,
                 "first_date": flex["test_date"].min(), "last_date": flex["test_date"].max(),
                 "fuels": flex["fuel"].value_counts().to_dict(), "diluents": flex["diluent"].value_counts().to_dict(),
                 "pressure_bands": flex["pressure_band"].value_counts().to_dict()},
        "limits": lab.LIMITS,
        "exported_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git_commit(),
    })


def main() -> None:
    if sys.argv[1:] == ["rag_index"]:
        export_rag_index()
        return
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = export_catalog()
    n_unified = export_unified()
    grid = export_lab()
    export_validation()
    n_passages = export_rag()
    export_meta(catalog, n_unified, n_passages, grid)
    export_rag_index()


if __name__ == "__main__":
    main()
