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
@pytest.fixture(scope="module")
def corpus():
    return retrieve.load_passages()


def test_corpus_file_matches_a_fresh_build(corpus):
    built = build_corpus.build()[0]  # needs pypdf (requirements-dev.txt)
    assert built == corpus
    assert len({p["passage_id"] for p in built}) == len(built)
    assert {p["source_type"] for p in built} == set(retrieve.SOURCE_LABEL)
    assert len({p["doc_id"] for p in built if p["source_type"] == "psi_record"}) == 24
    for p in built:
        assert p["text"].strip() and p["doc_id"] and p["doc_title"] and p["source_url"].startswith("http"), p["passage_id"]
        assert p["psi_id"] == (p["psi_ids"][0] if len(p["psi_ids"]) == 1 else "")


def test_psi_passage_text_is_verbatim_from_the_record(corpus):
    for p in corpus:
        if p["source_type"] != "psi_record":
            continue
        rec = json.loads((build_corpus.RECORDS / f"{p['psi_id']}.json").read_text(encoding="utf-8"))
        if p["field"] == "publication title":
            sources = [build_corpus.clean(x.get("title") or "") for x in rec["publications"]]
        else:
            key = next(k for k, name, _ in build_corpus.FIELDS if name == p["field"])
            sources = [build_corpus.clean(rec[key]).replace("\r\n", "\n")]
        for line in p["text"].split("\n"):  # every line of the passage is a line of the source field
            assert any(line.strip() in s for s in sources), p["passage_id"]
        assert p["source_url"].endswith(p["psi_id"]) and "<" not in p["text"] and "&quot;" not in p["text"]


def test_web_page_and_abstract_text_is_verbatim_from_the_raw_file(corpus):
    import html_text
    rows = {r["doc_id"]: r for r in build_corpus.manifest()}
    pages, checked = {}, 0
    for p in corpus:
        if p["source_type"] == "nasa_page":
            if p["doc_id"] not in pages:
                raw = (ROOT / rows[p["doc_id"]]["saved_as"]).read_text(encoding="utf-8", errors="replace")
                pages[p["doc_id"]] = {t for _, t in html_text.paragraphs(raw)[1]}
            assert p["text"] in pages[p["doc_id"]], p["passage_id"]
            checked += 1
        elif p["source_type"] == "ntrs_abstract":
            raw = "".join((ROOT / r["saved_as"]).read_text(encoding="utf-8") for r in rows.values()
                          if r["kind"] in ("ntrs_search", "ntrs_record") and r["saved_as"]
                          and p["doc_id"].split("-")[1] in (ROOT / r["saved_as"]).read_text(encoding="utf-8")[:200000])
            first = p["text"].split("\n")[0][:60]
            assert json.dumps(first, ensure_ascii=False)[1:-1][:40] in raw or json.dumps(first)[1:-1][:40] in raw, p["passage_id"]
            checked += 1
    assert checked > 40


def test_raw_documents_match_the_manifest():
    import hashlib
    rows = [r for r in build_corpus.manifest() if r["saved_as"]]
    assert len(rows) > 50
    for r in rows:
        assert hashlib.sha256((ROOT / r["saved_as"]).read_bytes()).hexdigest() == r["sha256"], r["saved_as"]


def test_only_public_use_abstracts_are_in_the_corpus(corpus):
    import csv
    with build_corpus.DOCUMENTS.open(encoding="utf-8", newline="") as f:
        docs = {d["doc_id"]: d for d in csv.DictReader(f)}
    assert all(d["rights_basis"] for d in docs.values())
    used = {p["doc_id"] for p in corpus}
    assert used == {i for i, d in docs.items() if d["text_used"] == "yes"}
    for i in used:
        if docs[i]["source_type"] == "ntrs_abstract":
            assert any(k in docs[i]["rights_basis"] for k in build_corpus.NTRS_PUBLIC), docs[i]
    assert "ntrs-20150023456" in used  # NASA/TP-2015-216046


def test_data_cards_name_their_source_file_and_match_the_tables(corpus):
    import pandas as pd
    cards = [p for p in corpus if p["source_type"] == "data_card"]
    assert len(cards) == 24 + 4
    assert all("computed from data/" in p["text"].lower() for p in cards)
    f = pd.read_csv(ROOT / "data" / "clean" / "flex_clean.csv")
    text = " ".join(p["text"] for p in cards if p["doc_id"] == "card-flex")
    assert f"{len(f)} tests on {f['test_date'].nunique()} test dates" in text
    assert f"{int((f['diluent'] == 'He').sum())} tests used helium" in text
    assert f"{int((f['diluent'] == 'CO2').sum())} tests used CO2" in text


# ------------------------------------------------------------------ retrieval
def test_search_returns_at_most_six_best_first_within_the_quota(index):
    for q in QUESTIONS:
        r = index.search(q["question"])
        assert 0 < len(r) <= retrieve.TOP_K
        assert [p["score"] for p in r] == sorted((p["score"] for p in r), reverse=True)
        kinds = [retrieve.kind(p) for p in r]
        assert all(kinds.count(k) <= retrieve.QUOTA[k] for k in set(kinds)), kinds
        assert max(kinds.count(k) for k in set(kinds)) < retrieve.TOP_K  # one kind never fills all places
    assert index.search("") == [] and index.search("zzzqqq xyzzy") == []


def test_search_filter_by_psi_id(index):
    r = index.search("flame extinction", psi_ids={"PSI-69"})
    assert r and all("PSI-69" in p["psi_ids"] for p in r)


def test_hit_rate_at_top_6_per_group(index):
    import eval_retrieval
    rates, _ = eval_retrieval.evaluate(index)
    assert {g: n for g, (_, n) in rates.items()} == {"original": 10, "findings": 10, "reworded": 10}
    # measured 2026-11-15 with TF-IDF alone: 10, 10 and 8 of 10 (reports/rag_eval.md)
    assert rates["original"][0] >= 9 and rates["findings"][0] >= 8 and rates["reworded"][0] >= 7, rates


# ------------------------------------------------------------------ support check
def test_support_share_is_high_for_a_bullet_taken_from_its_passage(index):
    ps = index.search(QUESTIONS[1]["question"])
    p = next(x for x in ps if len(x["text"]) > 200)
    bullet = "- " + p["text"][:160] + f" [{p['passage_id']}]"
    s = ai.support(bullet, ps)[0]
    assert s["share"] >= 0.9 and not s["weak"]


def test_support_flags_a_bullet_whose_words_are_not_in_the_cited_passage(index):
    ps = index.search(QUESTIONS[1]["question"])
    out = ai.answer_from_passages("q", ps, llm=fake(
        f"- Penguins prefer violet submarines during orchestral rehearsals [{ps[0]['passage_id']}]"))
    assert out["source"] == "ai"  # flagged, not hidden
    assert out["support"][0]["weak"] and out["support"][0]["share"] < ai.SUPPORT_THRESHOLD


def test_how_much_suppressant_questions_are_recognised():
    assert ai.asks_how_much_suppressant("How much CO2 is needed to put out a methanol droplet?")
    assert ai.asks_how_much_suppressant("What concentration of helium extinguishes the flame?")
    assert not ai.asks_how_much_suppressant("What caused the Apollo 1 fire?")
    assert not ai.asks_how_much_suppressant("Which suppressants did FLEX test?")
    assert not ai.asks_how_much_suppressant("How many FLEX tests used helium as the diluent?")


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
    assert len(saved) == 7
    for a in saved:
        retrieved = [p["passage_id"] for p in index.search(a["question"])]
        assert a["retrieved_ids"] == retrieved, a["question"]
        ok, why = ai.check_passage_citations(a["text"], set(retrieved))
        assert ok and a["citations"] == ai.cited_ids(a["text"]), (a["question"], why)
