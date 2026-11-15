// Parity: the TypeScript top 6 must equal the Python top 6 for the 30 check questions.
// Run: npm test   (node --test, Node 22.18+ strips the TypeScript types)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Index, type RagIndex } from "./retrieve.ts";

const ix = JSON.parse(readFileSync(new URL("../../data/rag_index.json", import.meta.url), "utf-8")) as RagIndex;
const index = new Index(ix);

test("TypeScript top 6 equals Python top 6 for the 30 check questions", () => {
  assert.equal(ix.parity.length, 30);
  const differ = ix.parity.filter((q) => JSON.stringify(index.search(q.question).map((p) => p.id)) !== JSON.stringify(q.ids));
  for (const q of differ) console.log("differs:", q.question, "\n  python:", q.ids, "\n  ts:    ", index.search(q.question).map((p) => p.id));
  assert.equal(differ.length, 0);
});

test("empty and unknown questions return nothing", () => {
  assert.deepEqual(index.search(""), []);
  assert.deepEqual(index.search("zzzqqq xyzzy"), []);
});

test("quota per kind of source holds", () => {
  for (const q of ix.parity) {
    const kinds = index.search(q.question).map((p) => (p.field === ix.publication_field ? "psi_publication" : p.source_type));
    for (const k of new Set(kinds)) assert.ok(kinds.filter((x) => x === k).length <= ix.quota[k]);
  }
});
