"""Tests for the two AI checks, using fake model responses (no network, no key)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ai  # noqa: E402
import catalog as cat  # noqa: E402


@pytest.fixture
def df():
    return cat.read_catalog(cat.FIXTURE)


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    # no key from the environment or from a local .streamlit/secrets.toml: tests never call the service
    monkeypatch.delenv(ai.KEY_ENV, raising=False)
    monkeypatch.setattr(ai, "get_key", lambda: "")


def fake(reply):
    return lambda system, user: reply


# ---------------------------------------------------------------- numbers
FACTS = ["Suppressant: CO2 at mole fraction 0.30; chamber O2 0.210",
         "Predicted extinction ratio d_ext/d0: 0.57, 90% interval 0.42 to 0.71",
         "Threshold finding: likely needs at least 40% CO2 (best estimate 45%). NASA's tests stop at 50%",
         "Nearest NASA tests: test 109, test 111 (C10M303)",
         "Fuel: methanol droplet, initial diameter 3.48 mm"]
TEMPLATE = "template text"


def test_text_using_only_numbers_from_the_page_is_accepted():
    reply = ("At 30% CO2 the predicted ratio is 0.57, between 0.42 and 0.71 with 90% confidence. "
             "Reaching the limit likely needs at least 40% CO2, and NASA's tests stop at 0.50. "
             "Test 109 is the closest real test for this 3.48 mm droplet in O2 and d0 terms.")
    out = ai.explain_result(FACTS, TEMPLATE, llm=fake(reply))
    assert out["source"] == "ai" and out["text"] == reply and out["label"] == ai.AI_LABEL


def test_text_with_a_new_number_is_rejected():
    out = ai.explain_result(FACTS, TEMPLATE, llm=fake("The ratio is 0.57, so about 60% of the way to the limit."))
    assert out["source"] == "template" and out["text"] == TEMPLATE
    assert "60%" in out["note"]


def test_a_computed_difference_is_rejected():
    ok, why = ai.check_numbers("The interval is 0.29 wide.", FACTS)
    assert not ok and "0.29" in why


def test_names_containing_digits_are_not_treated_as_numbers():
    assert ai.numbers_in("CO2, O2, N2, d0, PSI-69, C10M201 and the d2-law") == []
    assert ai.check_numbers("CO2 lowers d_ext/d0 less than expected for PSI-69.", FACTS)[0]


def test_fraction_and_percent_forms_match_each_other():
    assert ai.check_numbers("CO2 at 30% gives 0.4 and 0.5.", FACTS)[0]
    assert not ai.check_numbers("CO2 at 3% gives 4.", FACTS)[0]


def test_explain_with_no_key_returns_the_template():
    out = ai.explain_result(FACTS, TEMPLATE)
    assert out["source"] == "template" and out["text"] == TEMPLATE and out["label"] == ai.TEMPLATE_LABEL


def test_the_lab_template_itself_only_uses_numbers_from_its_facts():
    import lab
    df = lab.load_clean()
    for preset in lab.PRESETS:
        for fuel in ("Methanol", "Heptane"):
            for sup in lab.SUPPRESSANTS:
                s = lab.slice_tests(df, preset, fuel, sup)
                p = lab.preset_pressure_mmhg(df, preset)
                d0, frac = float(round(s["d0_mm"].median(), 2)), 0.30 if sup in s["diluent"].values else 0.0
                lo, hi = lab.fraction_range(s)
                frac = min(frac, hi)
                q = lab.query(preset, p, fuel, sup, frac, d0)
                from model import predict
                ratio, rate = predict(**q, target="d_ext_over_d0"), predict(**q, target="burning_rate_k")
                c = lab.curve(preset, p, fuel, sup, d0, "d_ext_over_d0", lo, hi)
                sentence = lab.crossing_sentence(c, lab.DEFAULT_THRESHOLD, fuel, sup, d0)
                cv, _ = lab.trust_tables(lab.load_validation())
                facts, template = lab.explain_inputs(
                    preset, fuel, sup, frac, d0, lab.chamber(lab.PRESETS[preset]["o2_base"], frac), p,
                    lab.DEFAULT_THRESHOLD, ratio, rate, sentence, lab.evidence_table(df, q), cv)
                ok, why = ai.check_numbers(template, facts)
                assert ok, (preset, fuel, sup, why)
