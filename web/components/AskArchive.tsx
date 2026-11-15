"use client";
// Floating "Ask the archive" button and panel, on every page. Shows the saved, checked answers from
// public/data/rag_saved.json (loaded when the panel first opens), and a box for live questions (/api/ask/).
import { useEffect, useRef, useState } from "react";
import { STREAMLIT_URL } from "@/lib/config";
import LiveAsk from "@/components/LiveAsk";

type Passage = { passage_id: string; source_label: string; doc_title: string; section: string; source_url: string;
  text: string; cited: boolean; field: string };
type Answer = { question: string; text: string; model: string; saved_utc: string; passages: Passage[] };

export default function AskArchive() {
  const [open, setOpen] = useState(false);
  const [answers, setAnswers] = useState<Answer[] | null>(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const closeBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    if (!answers) {
      fetch("/data/rag_saved.json").then((r) => r.json()).then((d) => setAnswers(d.answers), (e) => setErr(String(e)));
    }
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); trigger.current?.focus(); }
      if (e.key === "Tab" && panel.current) { // keep keyboard focus inside the panel while it is open
        const f = panel.current.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input");
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, answers]);

  const close = () => { setOpen(false); trigger.current?.focus(); };
  const a = sel !== null && answers ? answers[sel] : null;

  return (
    <>
      <button ref={trigger} type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}
        className="fixed right-4 bottom-4 z-40 rounded-full bg-flame px-5 py-3 font-semibold text-[#0b1020] shadow-lg shadow-black/40 hover:bg-flame-ink">
        Ask the archive
      </button>
      {open && (
        <div ref={panel} role="dialog" aria-modal="true" aria-labelledby="archive-title"
          className="fixed inset-x-2 bottom-2 z-50 flex max-h-[85vh] flex-col rounded-xl border border-line bg-[#0f1528] shadow-2xl shadow-black/60 sm:inset-x-auto sm:right-4 sm:bottom-4 sm:w-[30rem]">
          <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
            <h2 id="archive-title" className="font-semibold">
              {a ? (
                <button type="button" onClick={() => setSel(null)} className="font-mono text-xs text-cool-ink hover:underline">← all questions</button>
              ) : "Ask the archive"}
            </h2>
            <button ref={closeBtn} type="button" onClick={close} aria-label="Close"
              className="rounded-md px-2 py-1 text-xl leading-none text-muted hover:bg-panel-2 hover:text-ink">×</button>
          </div>
          <div className="min-h-0 overflow-y-auto px-4 py-3">
            {err && <p className="text-sm text-warn">Could not load the saved answers: {err}</p>}
            {!answers && !err && <p className="text-sm text-muted" role="status">Loading…</p>}
            {!a && <div className="mb-5"><LiveAsk compact /></div>}
            {answers && !a && (
              <>
                <p className="font-mono text-[11px] uppercase tracking-wider text-muted">Saved, checked answers</p>
                <ul className="mt-2 space-y-2">
                  {answers.map((x, i) => (
                    <li key={x.question}>
                      <button type="button" onClick={() => setSel(i)}
                        className="w-full rounded-md border border-line bg-panel px-3 py-2 text-left text-sm hover:border-flame-ink">
                        {x.question}
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {a && (
              <article>
                <h3 className="font-semibold">{a.question}</h3>
                <p className="mt-1 font-mono text-[11px] text-muted">
                  AI-generated (Gemini, {a.model}) on {a.saved_utc} UTC, checked: every claim cites a retrieved passage.
                </p>
                <ul className="mt-3 ml-5 list-disc space-y-1 text-sm">
                  {a.text.split("\n").filter((l) => l.trim()).map((l) => <li key={l}>{l.replace(/^\s*[-*]\s*/, "")}</li>)}
                </ul>
                <p className="mt-4 font-mono text-[11px] uppercase tracking-wider text-muted">Cited passages, word for word</p>
                {a.passages.filter((p) => p.cited).map((p) => (
                  <div key={p.passage_id} className="mt-3 text-sm">
                    <div><span className="font-mono text-xs">[{p.passage_id}]</span>{" "}
                      <span className="rounded bg-panel-2 px-1.5 py-0.5 font-mono text-[11px] text-muted">{p.source_label}</span>{" "}
                      {p.doc_title} - <a href={p.source_url}>open source</a></div>
                    <blockquote className="mt-1 border-l-2 border-line pl-3 whitespace-pre-line text-muted">{p.text}</blockquote>
                  </div>
                ))}
              </article>
            )}
          </div>
          <p className="border-t border-line px-4 py-3 text-sm">
            Also live in the Streamlit app: <a href={STREAMLIT_URL}>{STREAMLIT_URL.replace(/^https:\/\//, "").replace(/\/$/, "")}</a>
          </p>
        </div>
      )}
    </>
  );
}
