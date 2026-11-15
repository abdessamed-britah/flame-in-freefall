"""Hit rate of the retrieval on tests/retrieval_questions.json, per group of questions.

A hit: one of the 6 retrieved passages belongs to an expected document or is linked to an
expected investigation.

Run:  python src/eval_retrieval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import retrieve  # noqa: E402

QUESTIONS = ROOT / "tests" / "retrieval_questions.json"


def evaluate(index: retrieve.Index) -> tuple[dict, list[dict]]:
    rows = []
    for q in json.loads(QUESTIONS.read_text(encoding="utf-8")):
        got = index.search(q["question"])
        rows.append({**q, "hit": retrieve.is_hit(got, q["expected"]),
                     "retrieved": [f"{p['doc_id']}|{retrieve.kind(p)}" for p in got]})
    rates: dict[str, list[int]] = {}
    for r in rows:
        g = rates.setdefault(r["group"], [0, 0])
        g[0] += r["hit"]
        g[1] += 1
    return rates, rows


def main() -> None:
    index = retrieve.build_index()
    rates, rows = evaluate(index)
    for r in rows:
        print("HIT " if r["hit"] else "MISS", f"[{r['group']}]", r["question"][:70], "| expected", r["expected"],
              "" if r["hit"] else f"| got {r['retrieved']}")
    print()
    for g, (h, n) in rates.items():
        print(f"{g}: {h} / {n}")
    print("all:", sum(h for h, _ in rates.values()), "/", sum(n for _, n in rates.values()))


if __name__ == "__main__":
    main()
