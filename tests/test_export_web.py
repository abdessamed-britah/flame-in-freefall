"""The static front end's numbers must be the Python numbers: grid values equal predict() at 20
random points, and the other exported files agree with their sources.
Run `python src/export_web.py` first if web/public/data/ is missing."""
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import catalog as cat  # noqa: E402
import export_web as ex  # noqa: E402
import lab  # noqa: E402
from model import predict  # noqa: E402

DATA = ROOT / "web" / "public" / "data"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def grid():
    return load("lab_grid.json")


def test_grid_values_equal_predict_at_20_random_points(grid):
    df = lab.load_clean()
    rng = random.Random(20261115)
    for _ in range(20):
        s = rng.choice(grid["slices"])
        i = rng.randrange(len(grid["fractions"]))
        target = rng.choice(ex.TARGETS)
        preset = ex.ATMOSPHERES[s["atm"]]
        assert s["pressure_mmhg"] == lab.preset_pressure_mmhg(df, preset)
        r = predict(**lab.query(preset, s["pressure_mmhg"], s["fuel"], s["dil"], grid["fractions"][i], s["d0"]),
                    target=target, n_nearest=5)
        g = s["grid"][target][i]
        assert g["x"] == grid["fractions"][i]
        for k in ("mean", "lower", "upper"):
            assert g[k] == pytest.approx(r[k], abs=1e-12), (s["atm"], s["fuel"], s["dil"], s["d0"], g["x"], target, k)
        assert g["in_range"] == r["in_range"] and g["warnings"] == r["warnings"]
        if target == "d_ext_over_d0":
            assert [n["test"] for n in s["nearest"][i]] == [n["test_number"] for n in r["nearest_tests"]]


def test_grid_covers_every_combination(grid):
    keys = {(s["atm"], s["fuel"], s["dil"], s["d0"]) for s in grid["slices"]}
    assert len(keys) == len(grid["slices"]) == 2 * 2 * 2 * 5
    assert grid["fractions"][0] == 0 and grid["fractions"][-1] == 0.5 and len(grid["fractions"]) == 21
    for s in grid["slices"]:
        for t in ex.TARGETS:
            assert len(s["grid"][t]) == 21
        ratio = s["grid"]["d_ext_over_d0"]
        assert all(0 <= p["lower"] <= p["mean"] <= p["upper"] <= 1 for p in ratio)  # clipped by predict()


def test_key_finding_matches_the_suppression_lab(grid):
    df = lab.load_clean()
    preset = ex.ATMOSPHERES["moon"]
    s = lab.slice_tests(df, preset, "Methanol", "CO2")
    c = lab.curve(preset, lab.preset_pressure_mmhg(df, preset), "Methanol", "CO2", 3.48, "d_ext_over_d0",
                  *lab.fraction_range(s))
    meta = load("meta.json")
    assert meta["key_finding"]["sentence"] == lab.crossing_sentence(c, 0.90, "Methanol", "CO2", 3.48)
    assert meta["counts"] == {"investigations": 24, "unified_rows": 2009, "passages": 874, "flex_tests": 274}


def test_catalog_criteria_reproduce_the_python_ranking():
    c = load("catalog.json")
    for habitat, ranking in c["python_default_ranking"].items():
        w, total = c["default_weights"], sum(c["default_weights"].values())
        mine = {r["psi_id"]: 100 * sum(w[k] * r["criteria"][habitat]["suppression"][k] for k in w) / total
                for r in c["rows"]}
        for x in ranking:
            assert mine[x["psi_id"]] == pytest.approx(x["score"], abs=1e-6), (habitat, x["psi_id"])
    assert len(c["rows"]) == 24 and c["default_weights"] == cat.DEFAULT_WEIGHTS


def test_saved_answers_and_validation_are_exported():
    rag = load("rag_saved.json")
    assert len(rag["answers"]) == 7 and all(a["check"] == "passed" for a in rag["answers"])
    for a in rag["answers"]:
        assert {p["passage_id"] for p in a["passages"] if p["cited"]} == set(a["citations"])
    v = load("validation.json")
    he = [r for r in v["lodo"] if r["Suppressant never seen in training"] == "He"]
    assert he and all(r["MAE"] > 0 for r in he)


def test_rag_index_matches_the_fitted_vectorizer():
    import retrieve
    d = json.loads((ROOT / "web" / "data" / "rag_index.json").read_text(encoding="utf-8"))
    ix = retrieve.build_index()
    assert d["vocabulary"] == sorted(ix.vectorizer.vocabulary_, key=ix.vectorizer.vocabulary_.get)
    assert [p["id"] for p in d["passages"]] == [p["passage_id"] for p in ix.passages]
    for q in d["parity"]:
        assert q["ids"] == [p["passage_id"] for p in ix.search(q["question"])]
