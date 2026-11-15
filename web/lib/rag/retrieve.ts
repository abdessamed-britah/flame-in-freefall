// TF-IDF retrieval, a port of src/retrieve.py. The vocabulary, idf and passage vectors come from
// the vectorizer fitted in Python (web/data/rag_index.json); this file only reproduces its
// tokenisation, the query weighting, cosine scoring and the quota per kind of source.
// Server-side only: imported by app/api/ask/route.ts and by the tests.

export type Passage = {
  id: string; text: string; source_type: string; source_label: string; title: string; section: string;
  url: string; psi_id: string; psi_ids: string[]; field: string;
};

export type RagIndex = {
  passages: Passage[];
  tokenizer: { token_pattern: string; stop_words: string[]; ngram_range: [number, number] };
  vocabulary: string[];
  idf: number[];
  vectors: [number[], number[]][];
  top_k: number;
  quota: Record<string, number>;
  publication_field: string;
  ai: {
    model: string; system: string; not_in_passages: string; not_in_passages_reply: string;
    no_passages_reply: string; search_label: string; ai_label: string; support_threshold: number;
    support_stop_words: string[];
  };
  parity: { question: string; ids: string[] }[];
};

export type Scored = Passage & { score: number };

// scikit-learn token_pattern "(?u)\b\w\w+\b": maximal runs of 2 or more word characters, where a
// Python Unicode word character is a letter, a number or "_".
const WORD_RUN = /[\p{L}\p{N}_]+/gu;

export class Index {
  readonly ix: RagIndex;
  private readonly col: Map<string, number>;
  private readonly stop: Set<string>;

  constructor(ix: RagIndex) {
    if (ix.tokenizer.token_pattern !== "(?u)\\b\\w\\w+\\b") throw new Error("unexpected token pattern");
    this.ix = ix;
    this.col = new Map(ix.vocabulary.map((t, i) => [t, i]));
    this.stop = new Set(ix.tokenizer.stop_words);
  }

  /** Same terms as TfidfVectorizer(lowercase, stop_words="english", ngram_range=(1, 2)).build_analyzer(). */
  terms(text: string): string[] {
    const tokens = (text.toLowerCase().match(WORD_RUN) ?? [])
      .filter((t) => [...t].length >= 2 && !this.stop.has(t));
    const out = [...tokens];
    for (let i = 0; i + 1 < tokens.length; i++) out.push(`${tokens[i]} ${tokens[i + 1]}`);
    return out;
  }

  /** Query vector: sublinear tf (1 + ln tf) x idf, L2-normalised; terms outside the vocabulary are ignored. */
  queryVector(text: string): Map<number, number> {
    const tf = new Map<number, number>();
    for (const t of this.terms(text)) {
      const j = this.col.get(t);
      if (j !== undefined) tf.set(j, (tf.get(j) ?? 0) + 1);
    }
    const v = new Map<number, number>();
    let norm = 0;
    for (const [j, n] of tf) {
      const w = (1 + Math.log(n)) * this.ix.idf[j];
      v.set(j, w);
      norm += w * w;
    }
    norm = Math.sqrt(norm);
    if (norm > 0) for (const [j, w] of v) v.set(j, w / norm);
    return v;
  }

  /** The k best passages within the quota per kind, best first; zero scores are never returned. */
  search(question: string, k = this.ix.top_k): Scored[] {
    if (!question.trim()) return [];
    const q = this.queryVector(question);
    const scores = this.ix.vectors.map(([cols, vals]) => {
      let s = 0;
      for (let i = 0; i < cols.length; i++) {
        const w = q.get(cols[i]);
        if (w !== undefined) s += w * vals[i];
      }
      return s;
    });
    const order = scores.map((s, i) => i).filter((i) => scores[i] > 0)
      .sort((a, b) => scores[b] - scores[a] || a - b);
    const out: Scored[] = [];
    const used = new Map<string, number>();
    for (const i of order) {
      if (out.length === k) break;
      const p = this.ix.passages[i];
      const kind = p.field === this.ix.publication_field ? "psi_publication" : p.source_type;
      const n = used.get(kind) ?? 0;
      if (n >= (this.ix.quota[kind] ?? 1)) continue;
      used.set(kind, n + 1);
      out.push({ ...p, score: Math.round(scores[i] * 1e4) / 1e4 });
    }
    return out;
  }
}
