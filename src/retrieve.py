"""Retrieval over data/corpus/passages.jsonl: TF-IDF (word 1-2 grams), cosine similarity:
the top 4 passages from descriptive fields plus the top 2 publication titles.

No network and no dependency beyond scikit-learn. The index is fitted once per
process (the app caches it). A passage with zero similarity is never returned.
"""
from __future__ import annotations

import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

ROOT = Path(__file__).resolve().parents[1]
PASSAGES = ROOT / "data" / "corpus" / "passages.jsonl"
TOP_DESCRIPTIVE = 4   # objective, approach, hypothesis, research impacts, hardware, titles of the investigation
TOP_PUBLICATIONS = 2  # publication titles: short, so they would otherwise outrank the descriptive paragraphs
PUBLICATION = "publication title"


def load_passages(path: Path = PASSAGES) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Index:
    def __init__(self, passages: list[dict]):
        self.passages = passages
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), lowercase=True, stop_words="english",
                                          sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform(p["text"] for p in passages)

    def search(self, question: str, psi_ids: set[str] | None = None, k_descriptive: int = TOP_DESCRIPTIVE,
               k_publications: int = TOP_PUBLICATIONS) -> list[dict]:
        """The best `k_descriptive` passages from descriptive fields, then the best `k_publications`
        publication titles; each group best first, each passage with its `score`.
        psi_ids: if given, only passages of these investigations are considered
        (the page turns a fire-safety pillar into the set of its psi_ids)."""
        if not question.strip():
            return []
        scores = linear_kernel(self.vectorizer.transform([question]), self.matrix).ravel()  # rows are L2-normalised
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        text, pubs = [], []
        for i in order:
            if scores[i] <= 0 or (len(text) == k_descriptive and len(pubs) == k_publications):
                break
            p = self.passages[i]
            if psi_ids is not None and p["psi_id"] not in psi_ids:
                continue
            group, limit = (pubs, k_publications) if p["field"] == PUBLICATION else (text, k_descriptive)
            if len(group) < limit:
                group.append({**p, "score": round(float(scores[i]), 4)})
        return text + pubs


def build_index(path: Path = PASSAGES) -> Index:
    return Index(load_passages(path))
