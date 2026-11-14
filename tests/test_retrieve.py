"""Tests for the corpus, the retrieval, the passage-citation check (fake model replies) and the saved answers."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ai  # noqa: E402
import build_corpus  # noqa: E402
import retrieve  # noqa: E402

QUESTIONS = json.loads((ROOT / "tests" / "retrieval_questions.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.setattr(ai, "get_key", lambda: "")  # tests never call the service


@pytest.fixture(scope="module")
def index():
    return retrieve.build_index()


def fake(reply):
    return lambda system, user: reply


# ------------------------------------------------------------------ corpus
def test_corpus_file_matches_the_raw_records():
    built, _ = build_corpus.build()
    assert built == retrieve.load_passages()
    assert len({p["passage_id"] for p in built}) == len(built)
    assert len({p["psi_id"] for p in built}) == 24


def test_passage_text_is_verbatim_from_the_record():
    for p in retrieve.load_passages():
        rec = json.loads((build_corpus.RECORDS / f"{p['psi_id']}.json").read_text(encoding="utf-8"))
        if p["field"] == "publication title":
            sources = [build_corpus.clean(x.get("title") or "") for x in rec["publications"]]
        else:
            key = next(k for k, name, _ in build_corpus.FIELDS if name == p["field"])
            sources = [build_corpus.clean(rec[key]).replace("\r\n", "\n")]
        for line in p["text"].split("\n"):  # every line of the passage is a line of the source field
            assert any(line.strip() in s for s in sources), p["passage_id"]
        assert p["source_url"].endswith(p["psi_id"]) and "<" not in p["text"] and "&quot;" not in p["text"]


# ------------------------------------------------------------------ retrieval
def test_search_returns_at_most_six_best_first(index):
    r = index.search("smoke detection in microgravity")
    assert 0 < len(r) <= 6
    assert [p["score"] for p in r] == sorted((p["score"] for p in r), reverse=True)
    assert index.search("") == [] and index.search("zzzqqq xyzzy") == []


def test_search_filter_by_psi_id(index):
    r = index.search("flame extinction", psi_ids={"PSI-69"})
    assert r and {p["psi_id"] for p in r} == {"PSI-69"}


def test_hit_rate_at_top_6(index):
    assert len(QUESTIONS) == 10
    misses = [q["question"] for q in QUESTIONS
              if not {p["psi_id"] for p in index.search(q["question"])} & set(q["expected"])]
    assert len(misses) <= 2, misses  # measured 2026-11-14: 9 of 10


# ------------------------------------------------------------------ citation check
def test_answer_with_retrieved_citations_is_accepted(index):
    ps = index.search(QUESTIONS[1]["question"])
    reply = f"- FLEX measured suppressants [{ps[0]['passage_id']}]\n- Second claim [{ps[1]['passage_id']}, {ps[2]['passage_id']}]"
    out = ai.answer_from_passages("q", ps, llm=fake(reply))
    assert out["source"] == "ai" and out["label"] == ai.AI_LABEL
    assert out["citations"] == [ps[0]["passage_id"], ps[1]["passage_id"], ps[2]["passage_id"]]


def test_citation_of_a_passage_that_was_not_retrieved_is_rejected(index):
    ps = index.search(QUESTIONS[1]["question"])
    other = next(p["passage_id"] for p in index.passages if p["passage_id"] not in {x["passage_id"] for x in ps})
    out = ai.answer_from_passages("q", ps, llm=fake(f"- A real passage, but not retrieved [{other}]"))
    assert out["source"] == "search" and out["label"] == ai.SEARCH_LABEL and other in out["note"]
    out = ai.answer_from_passages("q", ps, llm=fake("- Invented id [PSI-999-objective-1]"))
    assert out["source"] == "search" and "PSI-999-objective-1" in out["note"]


def test_line_without_citation_is_rejected(index):
    ps = index.search(QUESTIONS[1]["question"])
    out = ai.answer_from_passages("q", ps, llm=fake(f"- Cited [{ps[0]['passage_id']}]\n- Not cited at all"))
    assert out["source"] == "search" and "no passage citation" in out["note"]


def test_model_says_passages_do_not_answer(index):
    ps = index.search(QUESTIONS[1]["question"])
    out = ai.answer_from_passages("q", ps, llm=fake(ai.NOT_IN_PASSAGES))
    assert out["source"] == "ai" and out["text"] == ai.NOT_IN_PASSAGES_REPLY and out["citations"] == []


def test_failure_and_missing_key_show_search_results(index):
    ps = index.search(QUESTIONS[1]["question"])

    def broken(system, user):
        raise ai.AIUnavailable("the AI service returned an error (504)")

    out = ai.answer_from_passages("q", ps, llm=broken)
    assert out["source"] == "search" and "504" in out["note"]
    out = ai.answer_from_passages("q", ps)  # no key
    assert out["source"] == "search" and ai.KEY_ENV in out["note"]
    assert ai.answer_from_passages("q", [], llm=fake("- x [PSI-1-title-1]"))["source"] == "none"


def test_model_sees_only_the_retrieved_passages(index):
    ps = index.search(QUESTIONS[0]["question"])
    seen = {}
    ai.answer_from_passages("q", ps, llm=lambda system, user: seen.setdefault("user", user) and ai.NOT_IN_PASSAGES)
    assert all(p["text"] in seen["user"] for p in ps)
    assert sum(f"[{p['passage_id']}]" in seen["user"] for p in index.passages) == len(ps)


# ------------------------------------------------------------------ saved answers
def test_saved_answers_pass_the_check(index):
    saved = json.loads((ROOT / "data" / "corpus" / "saved_answers.json").read_text(encoding="utf-8"))
    assert len(saved) == 5
    for a in saved:
        retrieved = [p["passage_id"] for p in index.search(a["question"])]
        assert a["retrieved_ids"] == retrieved, a["question"]
        ok, why = ai.check_passage_citations(a["text"], set(retrieved))
        assert ok and a["citations"] == ai.cited_ids(a["text"]), (a["question"], why)
