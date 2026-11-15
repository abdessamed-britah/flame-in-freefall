// The citation and support checks with fake model replies (no network, no key). Mirrors
// tests/test_ai.py and tests/test_retrieve.py on the Python side.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Index, type RagIndex } from "./retrieve.ts";
import { AIUnavailable, answerFromPassages, checkPassageCitations, citedIds, support, type LLM } from "./checks.ts";

const ix = JSON.parse(readFileSync(new URL("../../data/rag_index.json", import.meta.url), "utf-8")) as RagIndex;
const index = new Index(ix);
const STOP = new Set(ix.ai.support_stop_words);
const fake = (reply: string): LLM => async () => reply;
const Q = "How effective are CO2 and helium at suppressing a burning fuel droplet?";
const ps = index.search(Q);

test("cited ids: brackets, commas, order of first appearance", () => {
  assert.deepEqual(citedIds("- a [X-1, Y-2]\n- b [X-1] [Z-3]"), ["X-1", "Y-2", "Z-3"]);
  assert.deepEqual(citedIds("no citation"), []);
});

test("an answer citing only retrieved passages is accepted", async () => {
  const reply = `- First claim [${ps[0].id}]\n- Second claim [${ps[1].id}, ${ps[2].id}]`;
  const out = await answerFromPassages(Q, ps, ix, fake(reply));
  assert.equal(out.source, "ai");
  assert.equal(out.label, "AI-generated (Gemini), checked");
  assert.deepEqual(out.citations, [ps[0].id, ps[1].id, ps[2].id]);
});

test("a citation of a passage that was not retrieved is rejected", async () => {
  const other = ix.passages.find((p) => !ps.some((x) => x.id === p.id))!.id;
  const out = await answerFromPassages(Q, ps, ix, fake(`- Real passage, not retrieved [${other}]`));
  assert.equal(out.source, "search");
  assert.equal(out.label, ix.ai.search_label);
  assert.match(out.note, new RegExp(other));
  const invented = await answerFromPassages(Q, ps, ix, fake("- Invented [PSI-999-objective-1]"));
  assert.equal(invented.source, "search");
});

test("a line without a citation is rejected", async () => {
  const out = await answerFromPassages(Q, ps, ix, fake(`- Cited [${ps[0].id}]\n- Not cited at all`));
  assert.equal(out.source, "search");
  assert.match(out.note, /no passage citation/);
  assert.deepEqual(checkPassageCitations("", new Set()), [false, "the answer is empty"]);
});

test("the not-in-passages sentinel, with or without a bullet, says so", async () => {
  for (const r of [ix.ai.not_in_passages, `- ${ix.ai.not_in_passages}`]) {
    const out = await answerFromPassages(Q, ps, ix, fake(r));
    assert.equal(out.source, "ai");
    assert.equal(out.text, ix.ai.not_in_passages_reply);
    assert.deepEqual(out.citations, []);
  }
});

test("errors, timeouts and a missing key give the search results", async () => {
  const broken: LLM = async () => { throw new AIUnavailable("no answer within 20 s"); };
  const out = await answerFromPassages(Q, ps, ix, broken);
  assert.equal(out.source, "search");
  assert.match(out.note, /20 s/);
  assert.equal(out.passages.length, ps.length);
  const nokey = await answerFromPassages(Q, ps, ix, null, "No AI key is set on the server (GEMINI_API_KEY).");
  assert.equal(nokey.source, "search");
  assert.equal((await answerFromPassages(Q, [], ix, fake("- x [y]"))).source, "none");
});

test("support: a bullet copied from its passage is supported", () => {
  const p = ps.find((x) => x.text.length > 200)!;
  const s = support(`- ${p.text.slice(0, 160)} [${p.id}]`, ps, STOP, ix.ai.support_threshold)[0];
  assert.ok(s.share >= 0.9 && !s.weak, JSON.stringify(s));
});

test("support: a bullet whose words are not in its cited passage is flagged, not hidden", async () => {
  const out = await answerFromPassages(Q, ps, ix, fake(`- Penguins prefer violet submarines during orchestral rehearsals [${ps[0].id}]`));
  assert.equal(out.source, "ai");
  assert.ok(out.support[0].weak && out.support[0].share < ix.ai.support_threshold);
  assert.equal(ix.ai.support_threshold, 0.5);
});

test("support matches the Python saved answers", () => {
  // the saved answers were scored by src/ai.py support(); the port must give the same shares
  const saved = JSON.parse(readFileSync(new URL("../../public/data/rag_saved.json", import.meta.url), "utf-8")) as {
    answers: { text: string; retrieved_ids: string[]; support: { share: number }[] }[] };
  const byId = new Map(ix.passages.map((p) => [p.id, p]));
  for (const a of saved.answers) {
    const passages = a.retrieved_ids.map((i) => ({ ...byId.get(i)!, score: 0 }));
    assert.deepEqual(support(a.text, passages, STOP, 0.5).map((s) => s.share), a.support.map((s) => s.share));
  }
});
