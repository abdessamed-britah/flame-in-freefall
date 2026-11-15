"use client";
import { useMemo, useState } from "react";
import catalog from "@/public/data/catalog.json";
import { Caveat, Note, PageHeader, Panel, Section, Select, TableWrap, td, th } from "@/components/ui";
import { pick, useAudience } from "@/lib/audience";

type Habitat = keyof typeof catalog.habitats;
type Pillar = "prevention" | "detection" | "suppression";
type Crit = keyof typeof catalog.default_weights;
type Row = (typeof catalog.rows)[number];

const CRITS = Object.keys(catalog.criteria) as Crit[];
const NS = "not stated";

/** catalog.formula: Score = 100 x sum(weight x criterion) / sum(weights). The 0/1 criterion values come from Python. */
function rank(habitat: Habitat, pillar: Pillar, w: Record<Crit, number>) {
  const total = CRITS.reduce((s, k) => s + w[k], 0);
  const rows = catalog.rows.map((r) => {
    const c = (r.criteria as Record<string, Record<string, Record<Crit, number>>>)[habitat][pillar];
    const points = Object.fromEntries(CRITS.map((k) => [k, total ? (100 * w[k] * c[k]) / total : 0])) as Record<Crit, number>;
    const score = Math.round(CRITS.reduce((s, k) => s + points[k], 0) * 1e6) / 1e6;
    return { r, points, score };
  });
  // highest score first; ties by acronym (no acronym last), then PSI number - as in src/catalog.py
  const num = (id: string) => Number(id.replace(/\D+/g, ""));
  rows.sort((a, b) => b.score - a.score
    || Number(a.r.acronym === NS) - Number(b.r.acronym === NS)
    || a.r.acronym.toLowerCase().localeCompare(b.r.acronym.toLowerCase())
    || num(a.r.psi_id) - num(b.r.psi_id));
  return rows.map((x) => {
    const place = 1 + rows.filter((y) => y.score > x.score).length;
    const tied = rows.filter((y) => y.score === x.score).length > 1;
    return { ...x, rank: `${tied ? "=" : ""}${place}` };
  });
}

const show = (v: string | null | undefined) => (v === null || v === undefined || v === "" ? NS : v);

export default function CatalogPage() {
  const { audience } = useAudience();
  const [habitat, setHabitat] = useState<Habitat>("Moon Base");
  const [pillar, setPillar] = useState<Pillar>(catalog.default_pillar as Pillar);
  const [w, setW] = useState<Record<Crit, number>>({ ...catalog.default_weights });
  const [picked, setPicked] = useState<string[]>([]);
  const [phase, setPhase] = useState("all");
  const ranked = useMemo(() => rank(habitat, pillar, w), [habitat, pillar, w]);
  const shown = ranked.filter((x) => phase === "all" || x.r.fuel_phase === phase);
  const h = catalog.habitats[habitat];
  const byId = Object.fromEntries(catalog.rows.map((r) => [r.psi_id, r])) as Record<string, Row>;
  const allZero = CRITS.every((k) => w[k] === 0);

  return (
    <>
      <PageHeader title="Investigation Catalog"
        purpose={pick(audience, {
          researcher: "Rank NASA's 24 combustion investigations by a transparent weighted score, and check every cell behind it.",
          engineer: "Rank, filter and compare NASA's combustion investigations by relevance to a habitat.",
          plain: "Which NASA fire experiments matter most for a Moon Base? Change the weights and see the order change.",
        })} />

      <div className="grid gap-3 sm:grid-cols-3">
        <Select label="Habitat" value={habitat} onChange={setHabitat}
          options={Object.keys(catalog.habitats).map((k) => ({ value: k as Habitat, label: k }))} />
        <Select label="Fire-safety pillar of interest" value={pillar} onChange={setPillar}
          options={catalog.pillars.map((p) => ({ value: p as Pillar, label: p }))} />
        <Select label="Fuel phase (team label)" value={phase} onChange={setPhase}
          options={[{ value: "all", label: "all" }, ...["solid", "liquid", "gas"].map((p) => ({ value: p, label: p }))]} />
      </div>
      <p className="mt-2 text-sm text-muted">{h.note} Target: O2 {h.o2_frac} (mole fraction) at {h.pressure_kpa} kPa.</p>

      <Panel title="Weights (0 to 10)" open={audience !== "plain"}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {CRITS.map((k) => (
            <label key={k} className="flex flex-col gap-1 text-sm">
              <span className="text-muted">{(catalog.criteria as Record<string, string>)[k]}</span>
              <span className="flex items-center gap-2">
                <input type="range" min={0} max={10} step={1} value={w[k]} className="w-full"
                  onChange={(e) => setW({ ...w, [k]: Number(e.target.value) })} aria-label={`Weight: ${k}`} />
                <span className="w-6 text-right tabular-nums text-ink">{w[k]}</span>
              </span>
            </label>
          ))}
        </div>
        <button onClick={() => setW({ ...catalog.default_weights })}
          className="mt-3 rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel-2">Reset to default weights</button>
      </Panel>
      {allZero && <Caveat>All weights are 0, so every score is 0.</Caveat>}

      <Section title={`Relevance ranking (${shown.length} of ${catalog.rows.length})`}>
        <TableWrap>
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className={th}>Rank</th><th className={th}>PSI id</th><th className={th}>Acronym</th>
                <th className={th}>Name</th><th className={th}>Score (0-100)</th>
                {CRITS.map((k) => <th key={k} className={th} title={(catalog.criteria as Record<string, string>)[k]}>Points: {k}</th>)}
                <th className={th}>Compare</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(({ r, points, score, rank: rk }) => (
                <tr key={r.psi_id}>
                  <td className={td}>{rk}</td>
                  <td className={`${td} whitespace-nowrap font-mono text-xs`}><a href={r.source_url}>{r.psi_id}</a></td>
                  <td className={`${td} whitespace-nowrap`}>{r.acronym}</td>
                  <td className={`${td} min-w-56`}>{r.name}</td>
                  <td className={td}>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 rounded bg-panel-2" role="img" aria-label={`score ${score.toFixed(0)} of 100`}>
                        <div className="h-2 rounded bg-flame" style={{ width: `${score}%` }} />
                      </div>
                      <span className="tabular-nums">{score.toFixed(0)}</span>
                    </div>
                  </td>
                  {CRITS.map((k) => <td key={k} className={`${td} text-right tabular-nums`}>{points[k].toFixed(0)}</td>)}
                  <td className={td}>
                    <input type="checkbox" aria-label={`Compare ${r.psi_id}`} checked={picked.includes(r.psi_id)}
                      disabled={!picked.includes(r.psi_id) && picked.length >= 3}
                      onChange={(e) => setPicked(e.target.checked ? [...picked, r.psi_id] : picked.filter((p) => p !== r.psi_id))} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
        <p className="mt-2 text-sm text-muted">
          {catalog.formula} A transparent weighted sum, not an AI score. &quot;=&quot; marks a tie; tied investigations are
          listed in alphabetical order of acronym. The criterion values are computed by the team&apos;s Python code
          (src/catalog.py); only the weighted sum runs in your browser.
        </p>
        <Panel title="How the score is computed, and the catalog cells behind it" open={audience === "researcher"}>
          <p className="text-sm">
            An investigation meets the O2 criterion when its highest ambient O2 mole fraction is at least {h.o2_frac}, and
            the pressure criterion when{" "}
            {h.pressure_rule === "at_or_below" ? "its lowest pressure is at or below" : "its pressure range contains"}{" "}
            {h.pressure_kpa} kPa. Fuel phase scores solid 1, liquid 0.5, gas 0.25 (the team&apos;s choice: cabin materials
            are solids). A blank cell scores zero. For ACME Flame Design and CFI-G the O2 values are oxidizer-stream O2,
            not ambient atmosphere, so they score 0 on the O2 criterion.
          </p>
          <div className="mt-3"><TableWrap>
            <table className="w-full text-sm">
              <thead><tr><th className={th}>PSI id</th><th className={th}>Pillar</th><th className={th}>Fuel phase</th>
                <th className={th}>Ambient O2 max (mole fraction)</th><th className={th}>Pressure (kPa)</th><th className={th}>Data table in PSI</th></tr></thead>
              <tbody>
                {shown.map(({ r }) => (
                  <tr key={r.psi_id}><td className={td}>{r.psi_id}</td><td className={td}>{r.cells.pillar}</td>
                    <td className={td}>{r.cells.phase}</td><td className={td}>{r.cells.o2}</td>
                    <td className={td}>{r.cells.pressure}</td><td className={td}>{r.cells.data}</td></tr>
                ))}
              </tbody>
            </table>
          </TableWrap></div>
        </Panel>
      </Section>

      <Section title="Compare side by side">
        {picked.length < 2 ? (
          <Note>Tick 2 or 3 investigations in the ranking table to compare them.</Note>
        ) : (
          <>
            <TableWrap>
              <table className="w-full text-sm">
                <thead><tr><th className={th}>Field</th>{picked.map((p) => <th key={p} className={th}>{p}</th>)}</tr></thead>
                <tbody>
                  {catalog.columns.filter((c) => c !== "psi_id").map((c) => {
                    const vals = picked.map((p) => show((byId[p] as unknown as Record<string, string>)[c]));
                    const differs = new Set(vals).size > 1;
                    return (
                      <tr key={c} className={differs ? "bg-[#e36a20]/15" : ""}>
                        <td className={`${td} whitespace-nowrap text-muted`}>{(catalog.labels as Record<string, string>)[c]}</td>
                        {vals.map((v, i) => (
                          <td key={i} className={`${td} min-w-48`}>
                            {c === "source_url" ? <a href={v}>Open PSI page</a> : v}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </TableWrap>
            <p className="mt-2 text-sm text-muted">Highlighted rows are the fields on which these investigations differ.</p>
          </>
        )}
      </Section>

      <Panel title="Where these values come from" open={false}>
        <p className="text-sm">
          Built from NASA&apos;s own PSI records. O2 (mole fraction), pressure (kPa) and flow ranges are computed from an
          investigation&apos;s experimental table only when a column header states the quantity and unit. Pillar and fuel
          phase are the team&apos;s labels, each with its basis. A cell with no source is left blank and shown as
          &quot;not stated&quot;. CFI (PSI-39) and SAFFIRE-III (PSI-100) write their units inside the cells, not the
          headers, so those conditions are not read.
        </p>
      </Panel>
    </>
  );
}
