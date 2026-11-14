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

SAVED = ROOT / "data" / "corpus" / "saved_answers.json"

st.set_page_config(page_title="Ask NASA's records", layout="wide")


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


st.title("Ask NASA's records")
if not retrieve.PASSAGES.exists():
    st.error("data/corpus/passages.jsonl is missing. Run `python src/build_corpus.py`.")
    st.stop()
ix = index()
by_id = {p["passage_id"]: p for p in ix.passages}
df = catalog()

st.caption(f"Search {len(ix.passages)} passages copied word for word from the {len({p['psi_id'] for p in ix.passages})} "
           "NASA PSI Combustion Science records (objectives, approach, hypotheses, research impacts, hardware, "
           "publication titles). The 6 passages closest to the question are retrieved by word matching (TF-IDF); "
           "the AI may answer only from those 6 and must cite a passage for every claim. A cited passage that was "
           "not retrieved makes the answer invalid, and the search results are shown instead. "
           + ("" if ai.has_key() else f"No AI key is set ({ai.KEY_ENV}), so only search results are shown."))

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
saved = saved_answers()
if saved:
    st.markdown("**Example questions** (saved answers, shown instantly)")
    for k, a in enumerate(saved):
        if st.button(a["question"], key=f"example_{k}"):
            st.session_state["ask"] = {"kind": "saved", "k": k}
with st.form("ask_form"):
    typed = st.text_input("Your question", placeholder="What did NASA learn about fire detection in microgravity?")
    if st.form_submit_button("Ask") and typed.strip():
        st.session_state["ask"] = {"kind": "live", "question": typed.strip(), "allowed": allowed}

state = st.session_state.get("ask")
if not state:
    st.stop()

# ---------------------------------------------------------------- answer
if state["kind"] == "saved":
    a = saved[state["k"]]
    question = a["question"]
    passages = [by_id[i] for i in a["retrieved_ids"] if i in by_id]
    ok, why = ai.check_passage_citations(a["text"], {p["passage_id"] for p in passages})
    if ok:
        out = {"text": a["text"], "source": "ai", "citations": a["citations"], "note": "",
               "label": f"Saved answer: AI-generated ({a['model']}) on {a['saved_utc']} UTC, checked against the "
                        "passages below, and stored in the repository. Not a live call."}
    else:  # the corpus changed since the answer was saved
        out = {"text": "", "source": "search", "citations": [], "label": ai.SEARCH_LABEL,
               "note": f"The saved answer no longer passes the citation check ({why})."}
else:
    question = state["question"]
    passages = ix.search(question, psi_ids=state["allowed"])
    with st.spinner("Reading the retrieved passages..."):
        out = ai.answer_from_passages(question, passages)

st.subheader(question)
if out["source"] == "ai":
    st.caption(out["label"])
    st.markdown(out["text"])
    if out["citations"]:
        st.markdown("**Cited passages, word for word**")
        for i in out["citations"]:
            show_passage(by_id[i])
    rest = [p for p in passages if p["passage_id"] not in out["citations"]]
    if rest:
        with st.expander(f"Other retrieved passages, not cited ({len(rest)})"):
            for p in rest:
                show_passage(p)
elif out["source"] == "search":
    st.markdown(f"**{out['label']}**")
    if out["note"]:
        st.caption(out["note"])
    for p in passages:
        show_passage(p)
else:
    st.info(out["text"])
st.caption("These records describe what each investigation set out to do and how; they contain few measured "
           "results. For numbers, use the Suppression Lab and the Unified Data page.")
