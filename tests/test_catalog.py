"""Tests for the catalog logic, on the 3-row placeholder fixture."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import catalog as cat  # noqa: E402

MOON = cat.HABITATS["Moon Base"]


@pytest.fixture
def df():
    return cat.read_catalog(cat.FIXTURE)


def ranked(df, weights=None, pillar="suppression", habitat=MOON):
    return cat.rank(df, weights or cat.DEFAULT_WEIGHTS, pillar, habitat["o2_pct"], habitat["pressure_psi"],
                    habitat["pressure_rule"]).set_index("psi_id")


def test_fixture_loads_with_blanks_kept_missing(df):
    assert len(df) == 3 and list(df["psi_id"]) == ["FIXTURE-A", "FIXTURE-B", "FIXTURE-C"]
    c = df.set_index("psi_id").loc["FIXTURE-C"]
    assert pd.isna(c["o2_max_pct"]) and pd.isna(c["pressure_min_psi"]) and c["measurements"] == ""
    assert cat.show(c["o2_max_pct"]) == cat.NOT_STATED and cat.show(c["measurements"]) == cat.NOT_STATED


def test_score_is_the_weighted_sum_of_the_criteria(df):
    r = ranked(df)
    # FIXTURE-A: pillar prevention (no match 0), solid 1, O2 max 34 >= 30 (1), pressure min 8.0 <= 10.2 (1), data yes (1)
    assert r.loc["FIXTURE-A", "score"] == pytest.approx(100 * (0 + 3 + 2 + 2 + 1) / 10)
    # FIXTURE-B: pillar match 1, liquid 0.5, O2 max 25 < 30 (0), pressure min 14.7 > 10.2 (0), data yes (1)
    assert r.loc["FIXTURE-B", "score"] == pytest.approx(100 * (2 + 1.5 + 0 + 0 + 1) / 10)
    assert r.loc["FIXTURE-A", "points_phase"] == pytest.approx(30)


def test_blank_cells_score_zero_and_show_not_stated(df):
    r = ranked(df)
    # FIXTURE-C: only fuel phase (gas 0.25) is usable; O2, pressure and data table are blank
    assert r.loc["FIXTURE-C", "score"] == pytest.approx(100 * (3 * 0.25) / 10)
    for k in ("o2", "pressure", "data"):
        assert r.loc["FIXTURE-C", f"points_{k}"] == 0
        assert r.loc["FIXTURE-C", f"cell_{k}"] == cat.NOT_STATED


def test_ranking_is_sorted_and_follows_the_weights(df):
    assert list(ranked(df).index) == ["FIXTURE-A", "FIXTURE-B", "FIXTURE-C"]
    only_pillar = {"pillar": 10, "phase": 0, "o2": 0, "pressure": 0, "data": 0}
    r = ranked(df, only_pillar)
    assert r.index[0] == "FIXTURE-B" and r.loc["FIXTURE-B", "score"] == 100 and r.loc["FIXTURE-A", "score"] == 0


def test_all_weights_zero_gives_zero_scores(df):
    assert (ranked(df, dict.fromkeys(cat.CRITERIA, 0))["score"] == 0).all()


def test_tied_ranks_are_marked_and_ordered_by_acronym(df):
    df = df.assign(acronym=["ZED", "", "ALPHA"])
    r = cat.rank(df, dict.fromkeys(cat.CRITERIA, 0), "suppression", 30, 10.2, "at_or_below")
    assert list(r["rank"]) == ["=1", "=1", "=1"]
    assert list(r["acronym"]) == ["ALPHA", "ZED", ""]       # alphabetical, no acronym last
    assert list(ranked(df)["rank"]) == ["1", "2", "3"]      # no ties -> plain ranks


def test_oxidizer_stream_o2_is_shown_but_scores_zero(df):
    df = df.assign(o2_stream_max_pct=[float("nan"), float("nan"), 85.0])
    r = ranked(df)
    assert r.loc["FIXTURE-C", "points_o2"] == 0
    assert "oxidizer-stream" in r.loc["FIXTURE-C", "cell_o2"] and "85" in r.loc["FIXTURE-C", "cell_o2"]


def test_iss_pressure_rule_needs_the_range_to_contain_the_target(df):
    r = ranked(df, habitat=cat.HABITATS["ISS"])
    assert r.loc["FIXTURE-A", "points_pressure"] > 0   # 8.0 to 14.7 contains 14.7
    assert r.loc["FIXTURE-B", "points_pressure"] > 0   # 14.7 to 14.7
    assert r.loc["FIXTURE-C", "points_pressure"] == 0  # not stated


def test_filters(df):
    assert list(cat.filter_catalog(df, pillars=["suppression"])["psi_id"]) == ["FIXTURE-B"]
    assert list(cat.filter_catalog(df, phases=["solid", "gas"])["psi_id"]) == ["FIXTURE-A", "FIXTURE-C"]
    assert list(cat.filter_catalog(df, hardware=["PLACEHOLDER-RIG-1"])["psi_id"]) == ["FIXTURE-A", "FIXTURE-C"]
    assert list(cat.filter_catalog(df, o2_range=(28, 34))["psi_id"]) == ["FIXTURE-A", "FIXTURE-C"]
    assert list(cat.filter_catalog(df, o2_range=(28, 34), keep_unstated_o2=False)["psi_id"]) == ["FIXTURE-A"]


def test_compare_marks_the_fields_that_differ(df):
    table, differs = cat.compare(df, ["FIXTURE-A", "FIXTURE-C"])
    marks = dict(zip(table.index, differs))
    assert marks["Hardware"] is False          # same rig
    assert marks["Fuel phase"] is True
    assert table.loc["O2 max (%)", "FIXTURE-C"] == cat.NOT_STATED


def test_every_row_has_a_link(df):
    assert df["source_url"].str.startswith("http").all()


def test_a_file_with_a_missing_column_is_refused(tmp_path, df):
    bad = tmp_path / "investigations.csv"
    df.drop(columns=["hardware"]).to_csv(bad, index=False)
    with pytest.raises(ValueError, match="hardware"):
        cat.read_catalog(bad)
