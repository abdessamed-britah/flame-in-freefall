"""AI layer: "ask NASA's records" and "explain this result". Provider: Google Gemini (google-genai SDK).

The key is read from GEMINI_API_KEY, first in Streamlit secrets, then in the
environment, and is never stored in the repository. With no key, or if the call fails, or if the model's
text fails its check, both features return a plain template built from the
data, so the app always works.

Two checks run on every model answer before it is shown:
- ask NASA's records: every line must cite a passage_id in square brackets, and
  every cited passage must be one of the retrieved ones; otherwise the answer is
  rejected and the retrieved passages are shown as search results.
- explain this result: every number in the text must be one of the numbers the
  page already shows; otherwise the text is rejected.
"""
from __future__ import annotations

import os
import re
from typing import Callable


# Flash model listed by the API for our key and answering on 2026-11-14
# (gemini-3.6/3.7/3.8-flash returned 503 "high demand" that day).
MODEL = "gemini-3.5-flash-lite"
TIMEOUT_MS = 90_000  # the service was slow on 2026-11-14: one catalog answer took 51 s
KEY_ENV = "GEMINI_API_KEY"
AI_LABEL = "AI-generated text (Gemini). Checked automatically against the data shown on this page; may still be wrong."
TEMPLATE_LABEL = "Template summary built from the data, not AI-generated."

LLM = Callable[[str, str], str]  # (system prompt, user message) -> reply text


class AIUnavailable(Exception):
    pass


def get_key() -> str:
    """The key from Streamlit secrets (.streamlit/secrets.toml or the deployed app's Secrets), else the environment."""
    value = ""
    try:
        import streamlit as st
        value = str(st.secrets.get(KEY_ENV, ""))
    except Exception:  # no secrets file, or streamlit not installed
        value = ""
    return (value or os.environ.get(KEY_ENV, "")).strip()


def has_key() -> bool:
    return bool(get_key())


def call_gemini(system: str, user: str) -> str:
    """One request to Gemini. Raises AIUnavailable on any failure or block."""
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as e:  # app still works without the package
        raise AIUnavailable("the google-genai package is not installed") from e
    try:
        client = genai.Client(api_key=get_key(), http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        resp = client.models.generate_content(
            model=MODEL,
            contents=user,
            # low thinking: at the default level the catalog question took over 60 s
            config=types.GenerateContentConfig(system_instruction=system, temperature=0, max_output_tokens=8000,
                                               thinking_config=types.ThinkingConfig(thinking_level="low")),
        )
    except errors.APIError as e:
        if e.code in (400, 401, 403):
            raise AIUnavailable(f"the API key or request was rejected ({e.code} {e.status})") from e
        if e.code == 429:
            raise AIUnavailable("the AI service is rate-limiting requests (429)") from e
        raise AIUnavailable(f"the AI service returned an error ({e.code})") from e
    except Exception as e:  # network failure
        raise AIUnavailable("could not reach the AI service") from e
    text = (resp.text or "").strip()
    if not text:
        raise AIUnavailable("the AI service returned no text")
    return text


def _result(text: str, source: str, note: str = "", citations: list[str] | None = None) -> dict:
    return {"text": text, "source": source, "label": AI_LABEL if source == "ai" else TEMPLATE_LABEL,
            "note": note, "citations": citations or []}


def _run(llm: LLM | None, system: str, user: str) -> tuple[str | None, str]:
    """Returns (reply, note). reply is None when no model answer is available."""
    if llm is None:
        if not has_key():
            return None, f"No AI key is set ({KEY_ENV})."
        llm = call_gemini
    try:
        return llm(system, user), ""
    except AIUnavailable as e:
        return None, f"AI unavailable: {e}."


# ---------------------------------------------------------------------------
# citations in square brackets, e.g. [PSI-69-objective-1]
# ---------------------------------------------------------------------------
_CITATION = re.compile(r"\[([^\[\]]+)\]")


def cited_ids(text: str) -> list[str]:
    ids = []
    for group in _CITATION.findall(text):
        ids += [p.strip() for p in group.split(",") if p.strip()]
    return list(dict.fromkeys(ids))


# ---------------------------------------------------------------------------
# explain this result
# ---------------------------------------------------------------------------
EXPLAIN_SYSTEM = """You explain one result of a fire-safety dashboard built on NASA's FLEX droplet-combustion \
tests to an engineer or student. The user message lists the facts the page already shows.

Rules:
- Write 3 to 5 plain sentences. No headings, no bullet points.
- Use only the facts given. Every number you write must appear in the facts exactly as written there. \
Do not compute, round, convert or estimate any new number, and do not write numbers as words.
- Say what the result means, how sure the model is, and what the main caution is.
- These are single fuel droplets, not cabin materials: do not make claims about a cabin fire."""

# words such as CO2, d0, O2, PSI-69, C10M201 contain digits but are names, not numbers
_NAME_WITH_DIGITS = re.compile(r"\b[A-Za-z][A-Za-z_\-]*\d[\w\-]*")
_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")


def numbers_in(text: str) -> list[str]:
    return _NUMBER.findall(_NAME_WITH_DIGITS.sub(" ", text))


def check_numbers(text: str, facts: list[str]) -> tuple[bool, str]:
    """True if every number in `text` is one of the numbers in `facts`.
    A fraction in the facts (0.40) may be written as a percentage (40%) and the other way round."""
    allowed: set[float] = set()
    for tok in numbers_in("\n".join(facts)):
        v = float(tok.rstrip("%"))
        allowed |= {round(v, 6), round(v / 100, 6)} if tok.endswith("%") else {round(v, 6)}
    new = []
    for tok in numbers_in(text):
        v = float(tok.rstrip("%"))
        ok = (round(v, 6) in allowed) or (tok.endswith("%") and round(v / 100, 6) in allowed)
        if not ok:
            new.append(tok)
    if new:
        return False, "it contains number(s) that are not on the page: " + ", ".join(dict.fromkeys(new))
    return True, ""


def explain_result(facts: list[str], template: str, llm: LLM | None = None) -> dict:
    """facts: the lines the page already shows. template: the no-AI text built from the same facts."""
    reply, note = _run(llm, EXPLAIN_SYSTEM, "Facts shown on the page:\n" + "\n".join(f"- {f}" for f in facts))
    if reply is not None:
        ok, why = check_numbers(reply, facts)
        if ok:
            return _result(reply.strip(), "ai")
        note = f"The AI text was rejected because {why}."
    return _result(template, "template", note)


# ---------------------------------------------------------------------------
# ask NASA's records (retrieval-augmented: the model sees only the retrieved passages)
# ---------------------------------------------------------------------------
NOT_IN_PASSAGES = "NOT_IN_PASSAGES"
NOT_IN_PASSAGES_REPLY = "The passages retrieved from NASA's records do not answer this question."
NO_PASSAGES_REPLY = "No passage in NASA's records shares a word with this question."
SEARCH_LABEL = "Search results from NASA's records (no AI summary)"

RAG_SYSTEM = f"""You answer questions for a spacecraft fire-safety dashboard using passages copied from NASA's \
Physical Sciences Informatics (PSI) records of combustion investigations. The passages are given in the user \
message; they are your only source.

Rules:
- Use only what the passages say. Do not add anything you know from elsewhere.
- Write the answer as short bullet lines, one claim per line, each line starting with "- ".
- End every line with the passage_id(s) it is based on in square brackets, exactly as written in the \
passages, for example [PSI-123-objective-1] or [PSI-123-objective-1, PSI-456-approach-2]. A line without a \
citation will be discarded.
- If the passages do not answer the question, reply with exactly {NOT_IN_PASSAGES} and nothing else."""


def passages_as_context(passages: list[dict]) -> str:
    return "\n\n".join(f"[{p['passage_id']}] {p['doc_title']}, {p['section']} ({p['source_type'].replace('_', ' ')}):\n"
                       f"{p['text']}" for p in passages)


# ---------------------------------------------------------------------------
# support check: are the words of a bullet in the passages it cites?
# ---------------------------------------------------------------------------
# Threshold chosen on 2026-11-15 from the model's own checked answers (see reports/rag_eval.md):
# bullets scored against the passages they cite, and the same bullets scored against passages they do not cite.
SUPPORT_THRESHOLD = 0.5
_STOP = set("""a an and are as at be been being but by can could did do does for from had has have how if in into is it
its may might more most must not of on or our such than that the their them then there these they this those to
was were what when where which while who will with would also about above after all any both each few other some
only own same so too very use used using uses include includes including aim aims aimed investigation investigations
experiment experiments study studies nasa""".split())


def content_words(text: str) -> list[str]:
    """Lower-case words of 3+ letters or any number, without citations, stop words and a plural s."""
    text = _CITATION.sub(" ", text)
    words = re.findall(r"[a-z][a-z0-9]{2,}|\d+(?:\.\d+)?", text.lower())
    return [w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w for w in words if w not in _STOP]


def support(text: str, passages: list[dict]) -> list[dict]:
    """For each bullet: the share of its content words that occur in the passages it cites."""
    by_id = {p["passage_id"]: p for p in passages}
    out = []
    for line in [ln.strip() for ln in text.splitlines() if ln.strip()]:
        words = list(dict.fromkeys(content_words(line)))
        cited = " ".join(by_id[i]["text"] + " " + by_id[i]["doc_title"] for i in cited_ids(line) if i in by_id)
        have = set(content_words(cited))
        share = sum(w in have for w in words) / len(words) if words else 1.0
        out.append({"line": line, "share": round(share, 2), "weak": share < SUPPORT_THRESHOLD,
                    "missing": [w for w in words if w not in have]})
    return out


_HOW_MUCH = re.compile(r"(?i)\b(how much|what (?:amount|fraction|percentage|percent|concentration|level)|"
                       r"amount of|quantity of|enough)\b")
_SUPPRESSANT = re.compile(r"(?i)\b(suppress\w*|extinguish\w*|co2|carbon dioxide|helium|diluent\w*|inert gas\w*|put out)\b")


def asks_how_much_suppressant(question: str) -> bool:
    """True for questions such as "How much CO2 is needed to put the flame out?": the Suppression Lab answers those."""
    return bool(_HOW_MUCH.search(question) and _SUPPRESSANT.search(question))


def check_passage_citations(text: str, retrieved_ids: set[str]) -> tuple[bool, str]:
    """True if every non-empty line cites at least one passage_id and every cited id was among the retrieved ones."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False, "the answer is empty"
    for ln in lines:
        if not cited_ids(ln):
            return False, f"a line has no passage citation: \"{ln[:80]}\""
    unknown = [i for i in cited_ids(text) if i not in retrieved_ids]
    if unknown:
        return False, "it cites passage(s) that were not retrieved: " + ", ".join(unknown)
    return True, ""


def answer_from_passages(question: str, passages: list[dict], llm: LLM | None = None) -> dict:
    """passages: the retrieved passages (src/retrieve.py). The model answers only from them.
    source is "ai" (checked answer), "search" (no AI summary: show the passages) or "none" (nothing retrieved)."""
    def result(text, source, label, note="", citations=None):
        return {"text": text, "source": source, "label": label, "note": note, "citations": citations or [],
                "support": support(text, passages) if source == "ai" and citations else []}

    if not passages:
        return result(NO_PASSAGES_REPLY, "none", SEARCH_LABEL)
    reply, note = _run(llm, RAG_SYSTEM, f"Passages:\n\n{passages_as_context(passages)}\n\nQuestion: {question}")
    if reply is not None:
        reply = reply.strip()
        if reply.lstrip("-* ").strip() == NOT_IN_PASSAGES:  # the sentinel, with or without a bullet mark
            return result(NOT_IN_PASSAGES_REPLY, "ai", AI_LABEL)
        ok, why = check_passage_citations(reply, {p["passage_id"] for p in passages})
        if ok:
            return result(reply, "ai", AI_LABEL, citations=cited_ids(reply))
        note = f"The AI answer was rejected because {why}."
    return result("", "search", SEARCH_LABEL, note)
