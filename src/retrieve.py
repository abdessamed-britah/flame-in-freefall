"""Retrieval over data/corpus/passages.jsonl.

Ranking: TF-IDF (word 1-2 grams) cosine similarity. No network and no dependency beyond
scikit-learn; the index is fitted once per process (the app caches it). A passage with zero
similarity is never returned.

Selection: the 6 best passages, best first, with a quota per kind of source so that one kind
cannot fill all 6 places (publication titles are short and would otherwise outrank paragraphs).

Embeddings were considered as a second ranker and not added: on the 30 check questions TF-IDF
alone scored 8 of 10 on the reworded group, above the bar set for adding them (reports/rag_eval.md).
"""
from __future__ import annotations

import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

ROOT = Path(__file__).resolve().parents[1]
PASSAGES = ROOT / "data" / "corpus" / "passages.jsonl"
TOP_K = 6
PUBLICATION = "publication title"
# the most passages of one kind among the 6 retrieved
QUOTA = {"psi_record": 3, "psi_publication": 1, "nasa_page": 3, "nasa_report": 2, "ntrs_abstract": 2, "data_card": 1}
SOURCE_LABEL = {"psi_record": "NASA PSI record", "nasa_page": "NASA web page", "nasa_report": "NASA report",
                "ntrs_abstract": "NASA NTRS abstract", "data_card": "Computed from NASA table"}


def load_passages(path: Path = PASSAGES) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def kind(p: dict) -> str:
    """The quota group of a passage."""
    return "psi_publication" if p["field"] == PUBLICATION else p["source_type"]


class Index:
    def __init__(self, passages: list[dict]):
        self.passages = passages
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), lowercase=True, stop_words="english",
                                          sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform(p["text"] for p in passages)

    def tfidf_order(self, question: str) -> list[tuple[int, float]]:
        """(passage index, score), best first, zero scores left out."""
        scores = linear_kernel(self.vectorizer.transform([question]), self.matrix).ravel()  # rows are L2-normalised
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        return [(i, float(scores[i])) for i in order if scores[i] > 0]

    def search(self, question: str, psi_ids: set[str] | None = None, k: int = TOP_K) -> list[dict]:
        """The k best passages, best first, each with its `score`, within the quota per kind.
        psi_ids: if given, only passages linked to these investigations are considered."""
        if not question.strip():
            return []
        ranked = self.tfidf_order(question)
        out, used = [], {}
        for i, score in ranked:
            if len(out) == k:
                break
            p = self.passages[i]
            if psi_ids is not None and not set(p["psi_ids"]) & psi_ids:
                continue
            g = kind(p)
            if used.get(g, 0) >= QUOTA.get(g, 1):
                continue
            used[g] = used.get(g, 0) + 1
            out.append({**p, "score": round(score, 4)})
        return out


def is_hit(passages: list[dict], expected: list[str]) -> bool:
    """True if a retrieved passage belongs to an expected document or is linked to an expected investigation."""
    want = set(expected)
    return any(p["doc_id"] in want or set(p["psi_ids"]) & want for p in passages)


def build_index(path: Path = PASSAGES) -> Index:
    return Index(load_passages(path))
