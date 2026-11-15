"""How the support share separates real citations from wrong ones, on the saved answers.

For every bullet of data/corpus/saved_answers.json (AI answers that passed the citation check):
- "cited":     its support share against the passages it cites;
- "not cited": the same bullet scored against each retrieved passage it does NOT cite
               (what the share would be if the citation were wrong).
The threshold in src/ai.py (SUPPORT_THRESHOLD) should sit between the two groups.

Run:  python src/support_calibration.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ai  # noqa: E402
import retrieve  # noqa: E402


def main() -> None:
    by_id = {p["passage_id"]: p for p in retrieve.load_passages()}
    saved = json.loads((ROOT / "data" / "corpus" / "saved_answers.json").read_text(encoding="utf-8"))
    cited, wrong = [], []
    for a in saved:
        passages = [by_id[i] for i in a["retrieved_ids"]]
        for s in ai.support(a["text"], passages):
            cited.append(s["share"])
            ids = ai.cited_ids(s["line"])
            body = ai._CITATION.sub("", s["line"]).strip()
            for p in passages:
                if p["passage_id"] not in ids:
                    wrong.append(ai.support(f"{body} [{p['passage_id']}]", passages)[0]["share"])
    t = ai.SUPPORT_THRESHOLD

    def line(name, v):
        return (f"{name}: n={len(v)}, min {min(v):.2f}, median {statistics.median(v):.2f}, max {max(v):.2f}, "
                f"below {t:.2f}: {sum(x < t for x in v)} of {len(v)}")
    print(f"{len(saved)} saved answers, threshold {t:.2f}")
    print(line("bullets against the passages they cite", cited))
    print(line("bullets against passages they do not cite", wrong))


if __name__ == "__main__":
    main()
