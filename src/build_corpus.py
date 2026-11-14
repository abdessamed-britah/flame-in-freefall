"""Build the text corpus for the "Ask NASA's records" page.

Reads the 24 raw PSI records in data/raw/psi/investigations/ (never modified)
and writes data/corpus/passages.jsonl: one passage per paragraph of every
descriptive text field. The text is copied verbatim. The only changes are:
HTML tags are removed and HTML entities (&quot; &#x27; &amp;) are decoded, and
leading/trailing whitespace of a paragraph is dropped.

A paragraph is one line of the field. Lines of a numbered or bulleted list
("1. ...", "A. ...", "- ...") stay in the same passage as the line that
introduces them, so a list is not cut into one-line passages.

Run:  python src/build_corpus.py
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "data" / "raw" / "psi" / "investigations"
OUT = ROOT / "data" / "corpus" / "passages.jsonl"
PSI_PAGE = "https://psi.nasa.gov/physci/repo/data/investigations/{}"

# (key in the PSI record, field name in the corpus, short tag used in passage_id)
FIELDS = [
    ("title", "title", "title"),
    ("proposalTitle", "proposal title", "proposal"),
    ("description", "description", "description"),
    ("objective", "objective", "objective"),
    ("approach", "approach", "approach"),
    ("hypothesis", "hypothesis", "hypothesis"),
    ("researchImpacts", "research impacts", "impacts"),
    ("experimentHardware", "experiment hardware", "hardware"),
]
PUBLICATION = ("publications[].title", "publication title", "pub")

_TAG = re.compile(r"<[a-zA-Z/][^<>]*>")
_LIST_ITEM = re.compile(r"^\s*(?:\d{1,2}[.)]|[A-Za-z][.)]|[-*•])\s+\S")


def clean(text: str) -> str:
    """Strip HTML tags and decode HTML entities. Nothing else."""
    return html.unescape(_TAG.sub("", text))


def paragraphs(text: str) -> list[str]:
    out: list[str] = []
    for line in clean(text).replace("\r\n", "\n").split("\n"):
        if not line.strip():
            continue
        if out and _LIST_ITEM.match(line):
            out[-1] += "\n" + line.rstrip()
        else:
            out.append(line.strip())
    return out


def psi_number(path: Path) -> int:
    return int(path.stem.split("-")[1])


def build() -> tuple[list[dict], dict]:
    passages, found = [], {}
    for path in sorted(RECORDS.glob("PSI-*.json"), key=psi_number):
        rec = json.loads(path.read_text(encoding="utf-8"))
        psi_id = rec["accession"]
        base = {"psi_id": psi_id, "acronym": (rec.get("investigationAcronym") or "").strip(),
                "investigation": (rec.get("title") or "").strip(), "source_url": PSI_PAGE.format(psi_id)}
        for key, name, tag in FIELDS:
            value = rec.get(key)
            paras = paragraphs(value) if isinstance(value, str) else []
            found.setdefault(name, {"key": key, "records": 0, "passages": 0})
            found[name]["records"] += bool(paras)
            found[name]["passages"] += len(paras)
            for n, p in enumerate(paras, 1):
                passages.append({"passage_id": f"{psi_id}-{tag}-{n}", **base, "field": name, "text": p})
        key, name, tag = PUBLICATION
        titles = [(n, clean(p.get("title") or "").strip()) for n, p in enumerate(rec.get("publications") or [], 1)]
        titles = [(n, t) for n, t in titles if t]
        found.setdefault(name, {"key": key, "records": 0, "passages": 0})
        found[name]["records"] += bool(titles)
        found[name]["passages"] += len(titles)
        for n, t in titles:
            passages.append({"passage_id": f"{psi_id}-{tag}-{n}", **base, "field": name, "text": t})
    return passages, found


def main() -> None:
    passages, found = build()
    ids = [p["passage_id"] for p in passages]
    assert len(ids) == len(set(ids)), "passage ids must be unique"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for p in passages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"{len(passages)} passages -> {OUT.relative_to(ROOT)}")
    print("\nField | PSI record key | records with text | passages")
    for name, s in found.items():
        print(f"{name} | {s['key']} | {s['records']} | {s['passages']}")
    print("\nPSI id | acronym | passages | of which publication titles")
    per: dict[str, list[int]] = {}
    for p in passages:
        row = per.setdefault(f"{p['psi_id']} | {p['acronym']}", [0, 0])
        row[0] += 1
        row[1] += p["field"] == "publication title"
    for k, (n, pubs) in per.items():
        print(f"{k} | {n} | {pubs}")


if __name__ == "__main__":
    main()
