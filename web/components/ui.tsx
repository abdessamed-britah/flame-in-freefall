import type { ReactNode } from "react";

export function PageHeader({ title, purpose, children }: { title: string; purpose: ReactNode; children?: ReactNode }) {
  return (
    <header className="mb-6">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>
      <p className="mt-2 text-lg text-muted">{purpose}</p>
      {children}
    </header>
  );
}

export function Caveat({ children }: { children: ReactNode }) {
  return (
    <div role="note" className="my-4 flex gap-3 rounded-lg border border-[#5a4a1c] bg-warn-bg px-4 py-3 text-warn">
      <span aria-hidden className="mt-0.5 shrink-0">⚠</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Finding({ children }: { children: ReactNode }) {
  return (
    <div className="my-4 rounded-lg border-l-4 border-flame bg-panel px-4 py-3 text-[1.05rem] leading-relaxed">
      {children}
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return <div className="my-4 rounded-lg border border-line bg-panel px-4 py-3 text-muted">{children}</div>;
}

export function Panel({ title, open, children }: { title: string; open?: boolean; children: ReactNode }) {
  // keyed by `open` where used, so a change of audience re-opens the right panels
  return (
    <details open={open} className="my-3 rounded-lg border border-line bg-panel/40">
      <summary className="px-4 py-3 font-medium">{title}</summary>
      <div className="min-w-0 px-4 pb-4">{children}</div>
    </details>
  );
}

export function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel px-4 py-3">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-1 text-3xl font-semibold text-flame-ink">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="mb-3 text-2xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="max-w-full overflow-x-auto rounded-lg border border-line">{children}</div>;
}

export const th = "whitespace-nowrap bg-panel px-3 py-2 text-left font-medium text-muted";
export const td = "border-t border-line px-3 py-2 align-top";

export function Select<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-sm">
      <span className="text-muted">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value as T)}
        className="rounded-md border border-line bg-panel px-3 py-2 text-ink">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="text-muted" role="status">Loading {what}…</p>;
}
