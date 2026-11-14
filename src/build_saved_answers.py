"""Save checked AI answers for the example questions of the "Ask NASA's records" page.

Calls the live model once per question (needs GEMINI_API_KEY) and writes
data/corpus/saved_answers.json. Only answers that pass the citation check are
saved. A question that already has a saved answer is not asked again unless
--refresh is given.

Run:  python src/build_saved_answers.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ai  # noqa: E402
import retrieve  # noqa: E402

OUT = ROOT / "data" / "corpus" / "saved_answers.json"
QUESTIONS = [
    "What does the FLEX investigation aim to learn about fire suppressants such as CO2 and helium?",
    "Why did NASA measure smoke particle sizes in low gravity?",
    "How rapidly does a large-scale fire grow in low gravity?",
    "Which experiment uses a gas burner to emulate the burning of solid and liquid fuels?",
    "How do low-gravity flammability limits compare with NASA's normal-gravity material screening test?",
]


def main() -> None:
    index = retrieve.build_index()
    old = {a["question"]: a for a in json.loads(OUT.read_text(encoding="utf-8"))} if OUT.exists() else {}
    saved = []
    for q in QUESTIONS:
        passages = index.search(q)
        if q in old and "--refresh" not in sys.argv:  # already saved: no call
            saved.append(old[q])
            print("have    |", q)
            continue
        out = None
        for _ in range(3):  # the service is sometimes busy
            out = ai.answer_from_passages(q, passages)
            if out["source"] == "ai":
                break
        if out["source"] == "ai" and out["citations"]:
            saved.append({"question": q, "text": out["text"], "citations": out["citations"],
                          "retrieved_ids": [p["passage_id"] for p in passages], "model": ai.MODEL,
                          "saved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")})
            print("saved   |", q)
        elif q in old:
            saved.append(old[q])
            print("kept old|", q, "|", out["note"] or out["text"])
        else:
            print("NOT SAVED |", q, "|", out["note"] or out["text"])
    OUT.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(saved)} of {len(QUESTIONS)} answers in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
