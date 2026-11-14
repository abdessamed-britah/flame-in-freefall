"""AI layer: catalog Q&A and "explain this result". Provider: Google Gemini (google-genai SDK).

The key is read from GEMINI_API_KEY, first in Streamlit secrets, then in the
environment, and is never stored in the repository. With no key, or if the call fails, or if the model's
text fails its check, both features return a plain template built from the
data, so the app always works.

Two checks run on every model answer before it is shown:
- catalog Q&A: every line must cite a psi_id in square brackets, and every
  cited id must exist in the catalog; otherwise the answer is rejected.
- explain this result: every number in the text must be one of the numbers the
  page already shows; otherwise the text is rejected.
"""
from __future__ import annotations

import os
import re
from typing import Callable

import pandas as pd

import catalog as cat

# Flash model listed by the API for our key and answering on 2026-11-14
# (gemini-3.6/3.7/3.8-flash returned 503 "high demand" that day).
MODEL = "gemini-3.5-flash"
TIMEOUT_MS = 90_000  # the service was slow on 2026-11-14: one catalog answer took 51 s
KEY_ENV = "GEMINI_API_KEY"
NOT_IN_CATALOG = "NOT_IN_CATALOG"
NOT_IN_CATALOG_REPLY = "The catalog does not contain the answer to this question."
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
# catalog Q&A
# ---------------------------------------------------------------------------
QA_SYSTEM = f"""You answer questions about a small catalog of NASA combustion investigations for a \
fire-safety dashboard. The catalog is given in the user message; it is your only source.

Rules:
- Use only what the catalog says. Do not add anything you know from elsewhere. A cell that reads \
"not stated" means the catalog has no information; never fill it in.
- Write the answer as short bullet lines, one claim per line, each line starting with "- ".
- End every line with the psi_id(s) it is based on in square brackets, exactly as written in the \
catalog, for example [PSI-123] or [PSI-123, PSI-456]. A line without a citation will be discarded.
- If the catalog does not contain the answer, reply with exactly {NOT_IN_CATALOG} and nothing else."""

_CITATION = re.compile(r"\[([^\[\]]+)\]")


def cited_ids(text: str) -> list[str]:
    ids = []
    for group in _CITATION.findall(text):
        ids += [p.strip() for p in group.split(",") if p.strip()]
    return list(dict.fromkeys(ids))


def check_citations(text: str, known_ids: set[str]) -> tuple[bool, str]:
    """True if every non-empty line cites at least one psi_id and every cited id exists in the catalog."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False, "the answer is empty"
    for ln in lines:
        if not cited_ids(ln):
            return False, f"a line has no psi_id citation: \"{ln[:80]}\""
    unknown = [i for i in cited_ids(text) if i not in known_ids]
    if unknown:
        return False, "it cites id(s) that are not in the catalog: " + ", ".join(unknown)
    return True, ""


def catalog_template(question: str, df: pd.DataFrame) -> tuple[str, list[str]]:
    """No-AI answer: the catalog rows that contain words of the question."""
    words = {w for w in re.findall(r"[a-z0-9]{4,}", question.lower())}
    hits = []
    for _, r in df.iterrows():
        blob = " ".join(cat.show(r[c]) for c in cat.COLUMNS).lower()
        n = sum(w in blob for w in words)
        if n:
            hits.append((n, r))
    if not hits:
        return ("No catalog row contains the words of this question. " + NOT_IN_CATALOG_REPLY), []
    hits.sort(key=lambda h: -h[0])
    lines = ["Catalog rows that mention words from your question:"]
    for _, r in hits[:5]:
        lines.append(f"- {r['name']}: pillar {cat.show(r['fire_safety_pillar'])}, fuel phase "
                     f"{cat.show(r['fuel_phase'])}, hardware {cat.show(r['hardware'])}, O2 "
                     f"{cat.show(r['o2_min_frac'])} to {cat.show(r['o2_max_frac'])} (mole fraction) [{r['psi_id']}]")
    return "\n".join(lines), [r["psi_id"] for _, r in hits[:5]]


def answer_catalog_question(question: str, df: pd.DataFrame, llm: LLM | None = None) -> dict:
    known = set(df["psi_id"])
    reply, note = _run(llm, QA_SYSTEM, f"Catalog:\n\n{cat.as_context(df)}\n\nQuestion: {question}")
    if reply is not None:
        reply = reply.strip()
        if reply == NOT_IN_CATALOG:
            return _result(NOT_IN_CATALOG_REPLY, "ai")
        ok, why = check_citations(reply, known)
        if ok:
            return _result(reply, "ai", citations=cited_ids(reply))
        note = f"The AI answer was rejected because {why}."
    text, ids = catalog_template(question, df)
    return _result(text, "template", note, ids)


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
