// POST /api/ask/ {question} -> retrieve 6 passages -> Gemini -> citation and support checks.
// On any failure the retrieved passages come back as search results without an AI summary.
import { readFileSync } from "node:fs";
import path from "node:path";
import { answerFromPassages } from "@/lib/rag/checks";
import { gemini } from "@/lib/rag/gemini";
import { Index, type RagIndex } from "@/lib/rag/retrieve";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_CHARS = 500;
const WINDOW_MS = 10 * 60 * 1000;
const MAX_PER_WINDOW = 10; // per IP and per server instance: a simple guard, not a quota system

let index: Index | null = null;
function getIndex(): Index {
  // web/data/ is not in public/: the index is read on the server and never sent to the browser
  index ??= new Index(JSON.parse(readFileSync(path.join(process.cwd(), "data", "rag_index.json"), "utf-8")) as RagIndex);
  return index;
}

const hits = new Map<string, number[]>();
function limited(ip: string): boolean {
  const now = Date.now();
  const recent = (hits.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  recent.push(now);
  hits.set(ip, recent);
  if (hits.size > 5000) hits.clear();
  return recent.length > MAX_PER_WINDOW;
}

export async function POST(req: Request) {
  let question = "";
  try {
    question = String(((await req.json()) as { question?: unknown }).question ?? "").trim();
  } catch {
    return Response.json({ error: "Send JSON: {\"question\": \"...\"}" }, { status: 400 });
  }
  if (!question) return Response.json({ error: "The question is empty." }, { status: 400 });
  if (question.length > MAX_CHARS) {
    return Response.json({ error: `Please keep the question under ${MAX_CHARS} characters.` }, { status: 400 });
  }
  const ix = getIndex();
  const passages = ix.search(question);
  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "unknown";
  const key = process.env.GEMINI_API_KEY ?? "";
  let llm = null;
  let note = "";
  if (limited(ip)) note = "Too many questions from this address in the last 10 minutes; showing search results only.";
  else if (!key) note = "No AI key is set on the server (GEMINI_API_KEY).";
  else llm = gemini(ix.ix.ai.model, key, 20_000);
  const out = await answerFromPassages(question, passages, ix.ix, llm, note);
  return Response.json({ question, ...out }, { headers: { "Cache-Control": "no-store" } });
}
