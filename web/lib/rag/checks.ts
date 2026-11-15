// The two checks of src/ai.py, ported: the citation check (every line cites a passage, and every cited
// passage was retrieved) and the support check (share of a bullet's content words found in the
// passages it cites). Plus the answer flow of ai.answer_from_passages(). Server-side only.
import type { RagIndex, Scored } from "./retrieve.ts";

export type LLM = (system: string, user: string) => Promise<string>;

export class AIUnavailable extends Error {}

export type Support = { line: string; share: number; weak: boolean; missing: string[] };
export type AskResult = {
  source: "ai" | "search" | "none";
  label: string;
  text: string;
  note: string;
  citations: string[];
  support: Support[];
  passages: Scored[];
};

const CITATION = /\[([^[\]]+)\]/g;

/** ai.cited_ids: ids in square brackets, comma-separated, in order of first appearance. */
export function citedIds(text: string): string[] {
  const ids: string[] = [];
  for (const m of text.matchAll(CITATION)) for (const p of m[1].split(",")) if (p.trim()) ids.push(p.trim());
  return [...new Set(ids)];
}

const lines = (text: string) => text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);

/** ai.check_passage_citations */
export function checkPassageCitations(text: string, retrieved: Set<string>): [boolean, string] {
  const ls = lines(text);
  if (!ls.length) return [false, "the answer is empty"];
  for (const ln of ls) if (!citedIds(ln).length) return [false, `a line has no passage citation: "${ln.slice(0, 80)}"`];
  const unknown = citedIds(text).filter((i) => !retrieved.has(i));
  if (unknown.length) return [false, `it cites passage(s) that were not retrieved: ${unknown.join(", ")}`];
  return [true, ""];
}

/** ai.content_words: lower-case words of 3+ characters or numbers, no citations, no stop words, no plural s. */
export function contentWords(text: string, stop: Set<string>): string[] {
  const words = text.replace(CITATION, " ").toLowerCase().match(/[a-z][a-z0-9]{2,}|\d+(?:\.\d+)?/g) ?? [];
  return words.filter((w) => !stop.has(w)).map((w) => (w.length > 4 && w.endsWith("s") && !w.endsWith("ss") ? w.slice(0, -1) : w));
}

/** ai.support: for each bullet, the share of its content words found in the passages it cites. */
export function support(text: string, passages: Scored[], stop: Set<string>, threshold: number): Support[] {
  const byId = new Map(passages.map((p) => [p.id, p]));
  return lines(text).map((line) => {
    const words = [...new Set(contentWords(line, stop))];
    const cited = citedIds(line).filter((i) => byId.has(i)).map((i) => `${byId.get(i)!.text} ${byId.get(i)!.title}`).join(" ");
    const have = new Set(contentWords(cited, stop));
    const share = words.length ? words.filter((w) => have.has(w)).length / words.length : 1;
    return { line, share: Math.round(share * 100) / 100, weak: share < threshold, missing: words.filter((w) => !have.has(w)) };
  });
}

/** ai.passages_as_context */
export function passagesAsContext(passages: Scored[]): string {
  return passages.map((p) => `[${p.id}] ${p.title}, ${p.section} (${p.source_type.replace(/_/g, " ")}):\n${p.text}`).join("\n\n");
}

/** ai.answer_from_passages: the model answers only from the retrieved passages; anything else falls back to search results. */
export async function answerFromPassages(question: string, passages: Scored[], ix: RagIndex, llm: LLM | null,
  unavailableNote = ""): Promise<AskResult> {
  const a = ix.ai;
  const stop = new Set(a.support_stop_words);
  const result = (source: AskResult["source"], text: string, note = "", citations: string[] = []): AskResult => ({
    source, label: source === "ai" ? a.ai_label : a.search_label, text, note, citations, passages,
    support: source === "ai" && citations.length ? support(text, passages, stop, a.support_threshold) : [],
  });
  if (!passages.length) return result("none", a.no_passages_reply);
  if (!llm) return result("search", "", unavailableNote);
  let reply: string;
  try {
    reply = (await llm(a.system, `Passages:\n\n${passagesAsContext(passages)}\n\nQuestion: ${question}`)).trim();
  } catch (e) {
    return result("search", "", `AI unavailable: ${e instanceof AIUnavailable ? e.message : "the AI call failed"}.`);
  }
  if (reply.replace(/^[-* ]+/, "").trim() === a.not_in_passages) return result("ai", a.not_in_passages_reply);
  const [ok, why] = checkPassageCitations(reply, new Set(passages.map((p) => p.id)));
  if (ok) return result("ai", reply, "", citedIds(reply));
  return result("search", "", `The AI answer was rejected because ${why}.`);
}
