"""Tests for model.predict(): range checks and the [0, 1] clip of the ratio.

Run from the project root:  python -m pytest tests -q
"""
import itertools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from model import predict  # noqa: E402

TARGETS = ["burning_rate_k", "d_ext_over_d0"]
MOON = dict(fuel="Methanol", o2=0.21, pressure_atm=535 / 760, co2=0.30, he=0.0, d0_mm=3.0)


@pytest.mark.parametrize("target", TARGETS)
def test_tested_condition_is_in_range(target):
    r = predict(**MOON, target=target)
    assert r["in_range"] is True
    assert r["warnings"] == []
    assert r["lower"] <= r["mean"] <= r["upper"]


@pytest.mark.parametrize("target", TARGETS)
def test_co2_he_mixture_is_out_of_range(target):
    r = predict(fuel="Heptane", o2=0.21, pressure_atm=1.0, co2=0.10, he=0.10, d0_mm=3.0, target=target)
    assert r["in_range"] is False


@pytest.mark.parametrize("target", TARGETS)
def test_1_5_atm_is_out_of_range(target):
    r = predict(fuel="Methanol", o2=0.21, pressure_atm=1.5, co2=0.0, he=0.0, d0_mm=3.0, target=target)
    assert r["in_range"] is False


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("mmhg", [901, 1545.7, 2074.2, 2319.9])
def test_above_900_mmhg_is_out_of_range(target, mmhg):
    # 0.21 O2 with 0.70 CO2 is what NASA actually tested at high pressure.
    r = predict(fuel="Methanol", o2=0.21, pressure_atm=mmhg / 760, co2=0.70, he=0.0, d0_mm=3.0, target=target)
    assert r["in_range"] is False


@pytest.mark.parametrize("mmhg,expected", [(535, True), (760, True), (495, True), (480, False),
                                           (590, False), (650, False), (705, False), (820, False)])
def test_pressure_must_be_within_40_mmhg_of_a_tested_band(mmhg, expected):
    r = predict(fuel="Methanol", o2=0.21, pressure_atm=mmhg / 760, co2=0.0, he=0.0, d0_mm=3.0)
    assert r["in_range"] is expected


def test_ratio_output_stays_within_0_and_1():
    grid = itertools.product(["Methanol", "Heptane"], [0.12, 0.21, 0.34, 0.50], [0.7, 1.0, 1.5, 3.0],
                             [("co2", 0.0), ("co2", 0.5), ("co2", 0.7), ("he", 0.45)], [0.5, 1.1, 3.0, 4.7, 6.0])
    for fuel, o2, p, (gas, frac), d0 in grid:
        if o2 + frac > 1:
            continue
        kw = dict(fuel=fuel, o2=o2, pressure_atm=p, co2=0.0, he=0.0, d0_mm=d0)
        kw[gas] = frac
        r = predict(**kw, target="d_ext_over_d0", n_nearest=0)
        assert 0.0 <= r["lower"] <= r["mean"] <= r["upper"] <= 1.0, (kw, r)


def test_nearest_tests_are_five_real_tests_of_the_same_fuel():
    near = predict(**MOON)["nearest_tests"]
    assert len(near) == 5
    assert all(n["fuel"] == "Methanol" for n in near)
    assert all(isinstance(n["test_number"], int) and n["flex_identifier"] for n in near)
    assert [n["distance"] for n in near] == sorted(n["distance"] for n in near)


def test_invalid_gas_fractions_raise():
    with pytest.raises(ValueError):
        predict(fuel="Methanol", o2=0.6, pressure_atm=1.0, co2=0.5, he=0.0, d0_mm=3.0)
