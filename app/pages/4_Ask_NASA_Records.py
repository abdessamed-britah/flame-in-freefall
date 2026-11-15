"""Ask NASA's records - questions answered only from passages of the PSI records, with citations."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import ai  # noqa: E402
import catalog as cat  # noqa: E402
import retrieve  # noqa: E402
import theme  # noqa: E402

SAVED = ROOT / "data" / "corpus" / "saved_answers.json"


@st.cache_resource
def index():
    return retrieve.build_index()


@st.cache_data
def catalog():
    return cat.load_catalog()[0]


@st.cache_data
def saved_answers():
    return json.loads(SAVED.read_text(encoding="utf-8")) if SAVED.exists() else []


def show_passage(p: dict) -> None:
    name = f"{p['psi_id']} {p['acronym'] or p['investigation']}"
    st.markdown(f"**[{p['passage_id']}]** {name}, {p['field']} - [open PSI page]({p['source_url']})")
    st.markdown("> " + p["text"].replace("\n", "  \n> "))


def show_publications(passages: list[dict], cited: list[str]) -> None:
    pubs = [p for p in passages if p["field"] == retrieve.PUBLICATION]
    if pubs:
        st.markdown("**Related publications**")
        for p in pubs:
            mark = " (cited above)" if p["passage_id"] in cited else ""
            st.markdown(f"- {p['text']} - {p['psi_id']} {p['acronym'] or p['investigation']}, "
                        f"[open PSI page]({p['source_url']}) **[{p['passage_id']}]**{mark}")


theme.header("Ask NASA's records",
             "Ask a question and get an answer that cites NASA's own text, passage by passage.")
if not retrieve.PASSAGES.exists():
    st.error("data/corpus/passages.jsonl is missing. Run `python src/build_corpus.py`.")
    st.stop()
ix = index()
by_id = {p["passage_id"]: p for p in ix.passages}
df = catalog()
if not ai.has_key():
    theme.note(f"No AI key is set ({ai.KEY_ENV}), so typed questions return search results without a summary.")

# ---------------------------------------------------------------- filters
with st.sidebar:
    st.header("Search only in")
    names = df.set_index("psi_id")["name"]
    picked = st.multiselect("Investigation", list(names.index), format_func=lambda i: f"{i} - {names[i][:40]}")
    pillars = st.multiselect("Fire-safety pillar (team label)",
                             sorted(v for v in df["fire_safety_pillar"].unique() if v))
    st.caption("Filters apply to typed questions, not to saved answers.")
allowed = None
if picked or pillars:
    sel = df
    if picked:
        sel = sel[sel["psi_id"].isin(picked)]
    if pillars:
        sel = sel[sel["fire_safety_pillar"].isin(pillars)]
    allowed = set(sel["psi_id"])

# ---------------------------------------------------------------- questions
with st.form("ask_form", border=False):
    q_col, b_col = st.columns([5, 1], vertical_alignment="bottom")
    typed = q_col.text_input("Your question", placeholder="What did NASA want to learn about fire detection?")
    if b_col.form_submit_button("Ask", type="primary", width="stretch") and typed.strip():
        st.session_state["ask"] = {"kind": "live", "question": typed.strip(), "allowed": allowed}
saved = saved_answers()
if saved:
    st.caption("Or try an example (saved answers, shown instantly):")
    for k, a in enumerate(saved):
        if st.button(a["question"], key=f"example_{k}", icon=":material/bolt:"):
            st.session_state["ask"] = {"kind": "saved", "k": k}

# ---------------------------------------------------------------- answer
state = st.session_state.get("ask")
if state:
    if state["kind"] == "saved":
        a = saved[state["k"]]
        question = a["question"]
        passages = [by_id[i] for i in a["retrieved_ids"] if i in by_id]
        ok, why = ai.check_passage_citations(a["text"], {p["passage_id"] for p in passages})
        if ok:
            out = {"text": a["text"], "source": "ai", "citations": a["citations"], "note": "",
                   "label": f"Saved answer: AI-generated ({a['model']}) on {a['saved_utc']} UTC, checked against "
                            "the passages below, and stored in the repository. Not a live call."}
        else:  # the corpus changed since the answer was saved
            out = {"text": "", "source": "search", "citations": [], "label": ai.SEARCH_LABEL,
                   "note": f"The saved answer no longer passes the citation check ({why})."}
    else:
        question = state["question"]
        passages = ix.search(question, psi_ids=state["allowed"])
        with st.spinner("Reading the retrieved passages..."):
            out = ai.answer_from_passages(question, passages)

    st.subheader(question)
    text_passages = [p for p in passages if p["field"] != retrieve.PUBLICATION]
    if out["source"] == "ai":
        st.caption(out["label"])
        st.markdown(out["text"])
        cited = [by_id[i] for i in out["citations"] if by_id[i]["field"] != retrieve.PUBLICATION]
        if cited:
            st.markdown("**Cited passages, word for word**")
            for p in cited:
                show_passage(p)
        show_publications(passages, out["citations"])
        rest = [p for p in text_passages if p["passage_id"] not in out["citations"]]
        if rest:
            with st.expander(f"Other retrieved passages, not cited ({len(rest)})"):
                for p in rest:
                    show_passage(p)
    elif out["source"] == "search":
        st.markdown(f"**{out['label']}**")
        if out["note"]:
            st.caption(out["note"])
        for p in text_passages:
            show_passage(p)
        show_publications(passages, [])
    else:
        theme.note(out["text"])

with st.expander("How this works, and its limits"):
    st.markdown(
        f"- The corpus is {len(ix.passages)} passages copied word for word from the "
        f"{len({p['psi_id'] for p in ix.passages})} NASA PSI Combustion Science records: objectives, approach, "
        "hypotheses, research impacts, hardware and publication titles.\n"
        f"- For each question, the {retrieve.TOP_DESCRIPTIVE} closest descriptive passages and the "
        f"{retrieve.TOP_PUBLICATIONS} closest publication titles are retrieved by word matching (TF-IDF). "
        "No AI is involved in the search.\n"
        "- The AI sees only those passages and must cite one for every claim. If it cites a passage that was not "
        "retrieved, or leaves a claim uncited, the answer is rejected and the search results are shown instead.\n"
        "- These records describe what each investigation set out to do and how; they contain few measured "
        "results. For numbers, use the Suppression Lab and the Unified Data page.")
