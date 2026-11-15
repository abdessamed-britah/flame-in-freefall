"use client";
// A question box that calls /api/ask/ and shows the checked answer with its cited passages, or the
// search results when there is no AI summary. Used in the "Ask the archive" panel and on the Ask page.
import { useState } from "react";
import type { AskResult } from "@/lib/rag/checks";

const MAX = 500;

type P = AskResult["passages"][number];

function Quote({ p }: { p: P }) {
  const where = p.title + (p.section && p.section !== p.title ? `, ${p.section}` : "");
  return (
    <div className="mt-3 text-sm">
      <div>
        <span className="font-mono text-xs">[{p.id}]</span>{" "}
        <span className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${p.source_type === "data_card" ? "bg-[#4594ee]/20 text-cool-ink" : "bg-panel-2 text-muted"}`}>
          {p.source_label}
        </span>{" "}
        {where} - <a href={p.url}>open source</a>
      </div>
      <blockquote className="mt-1 border-l-2 border-line pl-3 whitespace-pre-line text-muted">{p.text}</blockquote>
    </div>
  );
}

export default function LiveAsk({ compact = false }: { compact?: boolean }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<(AskResult & { question: string }) | null>(null);
  const [err, setErr] = useState("");

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = q.trim();
    if (!question || busy) return;
    setBusy(true); setErr(""); setRes(null);
    try {
      const r = await fetch("/api/ask/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
      const body = await r.json();
      if (!r.ok) setErr(body.error ?? `The server returned ${r.status}.`);
      else setRes(body);
    } catch {
      setErr("Could not reach the server. Try again, or use the saved answers below.");
    } finally {
      setBusy(false);
    }
  };

  const weak = new Map((res?.support ?? []).filter((s) => s.weak).map((s) => [s.line, s]));
  const cited = res ? res.passages.filter((p) => res.citations.includes(p.id)) : [];

  return (
    <div className={compact ? "" : "rounded-lg border border-line bg-panel p-4"}>
      <form onSubmit={ask}>
        <label htmlFor={compact ? "q-panel" : "q-page"} className="font-mono text-[11px] uppercase tracking-wider text-muted">
          Ask a new question
        </label>
        <div className="mt-1 flex flex-col gap-2 sm:flex-row">
          <input id={compact ? "q-panel" : "q-page"} value={q} maxLength={MAX} onChange={(e) => setQ(e.target.value)}
            placeholder="What started the fire on the Mir space station?"
            className="min-w-0 flex-1 rounded-md border border-line bg-[#0b1020] px-3 py-2 text-ink placeholder:text-muted/70" />
          <button type="submit" disabled={busy || !q.trim()}
            className="rounded-md bg-flame px-4 py-2 font-semibold text-[#0b1020] hover:bg-flame-ink disabled:opacity-50">
            {busy ? "Asking…" : "Ask"}
          </button>
        </div>
        <p className="mt-1 font-mono text-[11px] text-muted">{q.length}/{MAX} · answered only from NASA&apos;s records, checked in code</p>
      </form>

      <div aria-live="polite">
        {busy && <p className="mt-3 text-sm text-muted" role="status">Searching NASA&apos;s records and writing a checked answer…</p>}
        {err && <p className="mt-3 text-sm text-warn">{err}</p>}
        {res && (
          <div className="mt-4">
            <h3 className="font-semibold">{res.question}</h3>
            {res.source === "ai" && (
              <>
                <p className="mt-1 font-mono text-[11px] text-flame-ink">{res.label}</p>
                <ul className="mt-2 ml-5 list-disc space-y-1 text-sm">
                  {res.text.split("\n").filter((l) => l.trim()).map((l) => {
                    const w = weak.get(l.trim());
                    return (
                      <li key={l}>{l.replace(/^\s*[-*]\s*/, "")}
                        {w && <span className="ml-2 rounded bg-warn-bg px-1.5 py-0.5 text-xs text-warn">
                          weakly supported: {Math.round(w.share * 100)}% of its words are in the cited text</span>}
                      </li>
                    );
                  })}
                </ul>
                {cited.length > 0 && <p className="mt-4 font-mono text-[11px] uppercase tracking-wider text-muted">Cited passages, word for word</p>}
                {cited.map((p) => <Quote key={p.id} p={p} />)}
              </>
            )}
            {res.source === "search" && (
              <>
                <p className="mt-1 text-sm font-semibold">{res.label}</p>
                {res.note && <p className="mt-1 text-xs text-muted">{res.note}</p>}
                {res.passages.map((p) => <Quote key={p.id} p={p} />)}
              </>
            )}
            {res.source === "none" && <p className="mt-2 text-sm text-muted">{res.text}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
