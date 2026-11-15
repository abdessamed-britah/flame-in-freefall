"use client";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Symbols, Tooltip, XAxis, YAxis,
  type SymbolType,
} from "recharts";
import { Caveat, Loading, Note, PageHeader, Panel } from "@/components/ui";
import { pick, useAudience } from "@/lib/audience";
import { getJSON, type Unified, type UnifiedRow } from "@/lib/types";

const SHAPES: SymbolType[] = ["circle", "diamond", "square", "triangle", "cross", "wye", "star"];
const COLOUR = { ambient: "#e36a20", "oxidizer stream": "#4594ee" } as Record<string, string>;
const INK = "#eef1fa";

function csv(rows: UnifiedRow[]) {
  const head = ["psi_id", "investigation", "test_id", "fuel", "o2_mole_frac", "o2_basis", "pressure_kpa", "source_row"];
  const q = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [head.join(","), ...rows.map((r) => [r.id, r.inv, r.test, r.fuel, r.o2, r.basis, r.p, r.row].map(q).join(","))].join("\n");
}

type Pt = UnifiedRow & { x: number; y: number };

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Pt }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2 text-xs">
      <div className="font-semibold">{p.id} {p.inv}</div>
      {p.test && <div>Test {p.test} (row {p.row})</div>}
      {p.fuel && <div>Fuel: {p.fuel}</div>}
      <div>O2 {p.x.toPrecision(4)} ({p.basis}) · {p.y.toPrecision(4)} kPa</div>
    </div>
  );
}

export default function UnifiedPage() {
  const { audience } = useAudience();
  const [data, setData] = useState<Unified | null>(null);
  const [err, setErr] = useState("");
  const [inv, setInv] = useState<string>("all");
  const [onlyTests, setOnlyTests] = useState(false);
  useEffect(() => { getJSON<Unified>("unified.json").then(setData, (e) => setErr(String(e))); }, []);

  const view = useMemo(() => (data ? data.rows.filter((r) => (inv === "all" || r.id === inv) && (!onlyTests || !r.notTest)) : []), [data, inv, onlyTests]);
  const pts = view.filter((r) => r.o2 !== null && r.p !== null).map((r) => ({ ...r, x: r.o2 as number, y: r.p as number }));
  const ids = data ? [...new Set(data.rows.filter((r) => r.o2 !== null && r.p !== null).map((r) => r.id))] : [];
  const shapeOf = (id: string) => SHAPES[Math.max(0, ids.indexOf(id)) % SHAPES.length];
  const groups = [...new Set(pts.map((p) => `${p.id}|${p.basis}`))];

  const download = () => {
    const blob = new Blob([csv(view)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "tests_conditions_selection.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <PageHeader title="Unified Data"
        purpose={pick(audience, {
          researcher: "The test conditions of every PSI experimental table in one schema: mole fraction and kPa, converted only where the source states its unit.",
          engineer: "The test conditions of every NASA combustion investigation in one table, in the same units.",
          student: "Where did NASA test fires? Each mark is one row of a NASA table, placed by its oxygen and pressure.",
        })} />
      {err && <Caveat>Could not load the data: {err}</Caveat>}
      {!data ? <Loading what="2,009 rows" /> : (
        <>
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted">Investigation</span>
              <select value={inv} onChange={(e) => setInv(e.target.value)} className="rounded-md border border-line bg-panel px-3 py-2">
                <option value="all">all</option>
                {Object.keys(data.rows_per_investigation).map((id) => <option key={id} value={id}>{id}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-2 pb-2 text-sm">
              <input type="checkbox" checked={onlyTests} onChange={(e) => setOnlyTests(e.target.checked)} />
              Hide rows that are not single tests (test days, summaries)
            </label>
          </div>

          <div className="mt-4 h-[460px] w-full min-w-0 rounded-lg border border-line bg-panel/30 p-2" role="img"
            aria-label={`Scatter of O2 mole fraction against pressure in kPa: ${pts.length} rows, Moon Base marked at O2 0.30 and 70.3 kPa`}>
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 10, right: 16, bottom: 30, left: 8 }}>
                <CartesianGrid stroke="rgba(238,241,250,0.10)" />
                <XAxis type="number" dataKey="x" name="O2" domain={[0, 0.9]} tickCount={10} stroke="#aab2c8"
                  label={{ value: "O2 (mole fraction)", position: "bottom", offset: 10, fill: "#aab2c8" }} />
                <YAxis type="number" dataKey="y" name="Pressure" domain={[0, 350]} ticks={[0, 50, 100, 150, 200, 250, 300, 350]} stroke="#aab2c8" width={56}
                  label={{ value: "Pressure (kPa)", angle: -90, position: "insideLeft", fill: "#aab2c8" }} />
                <Tooltip content={<Tip />} />
                <Legend verticalAlign="top" wrapperStyle={{ paddingBottom: 8 }} />
                {groups.map((g) => {
                  const [id, basis] = g.split("|");
                  const rows = pts.filter((p) => p.id === id && p.basis === basis);
                  const open = basis === "oxidizer stream";
                  const colour = COLOUR[basis] ?? "#9aa3b5";
                  return (
                    <Scatter key={g} name={`${id} ${rows[0]?.inv ?? ""}, ${basis} O2 (${rows.length})`} data={rows}
                      fill={open ? "none" : colour} stroke={colour} isAnimationActive={false}
                      legendType={shapeOf(id) as never}
                      shape={(props: { cx?: number; cy?: number }) => (
                        <Symbols cx={props.cx} cy={props.cy} type={shapeOf(id)} size={46}
                          fill={open ? "none" : colour} stroke={open ? colour : "#0b1020"} strokeWidth={open ? 1.5 : 1} />
                      )} />
                  );
                })}
                <Scatter name="Moon Base (0.30 O2, 70.3 kPa)" data={[{ x: data.moon.o2, y: data.moon.p_kpa }]} fill={INK}
                  legendType="star" isAnimationActive={false}
                  shape={(props: { cx?: number; cy?: number }) => (
                    <g>
                      <Symbols cx={props.cx} cy={props.cy} type="star" size={260} fill={INK} stroke="#0b1020" />
                      <text x={(props.cx ?? 0) + 12} y={(props.cy ?? 0) - 10} fill={INK} fontSize={12}>Moon Base</text>
                    </g>
                  )} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-sm text-muted">
            {pts.length} of {view.length} selected rows, from {new Set(pts.map((p) => p.id)).size} investigations, have both
            values. Shape = investigation; orange filled = ambient O2; blue open = oxidizer-stream O2. The white star is
            the Moon Base atmosphere from the challenge brief.
          </p>
          {pts.some((p) => p.basis === "oxidizer stream") && (
            <Caveat>Blue open markers are oxidizer-stream O2 (the gas fed through the burner), not the ambient atmosphere,
              so they are not comparable with a habitat atmosphere.</Caveat>
          )}

          <div className="mt-4 flex flex-wrap gap-3">
            <a href="/data/tests_conditions.csv" download
              className="rounded-md bg-flame px-4 py-2 font-medium text-[#0b1020] hover:bg-flame-ink hover:no-underline">
              Download the unified table (CSV, all {data.total_rows.toLocaleString("en-US")} rows)
            </a>
            <button onClick={download} className="rounded-md border border-line px-4 py-2 hover:bg-panel-2">
              Download the current selection (CSV, {view.length} rows)
            </button>
          </div>
          <p className="mt-2 text-xs text-muted">
            The selection holds the rows that have an O2 or a pressure value; the full table holds all {data.total_rows} rows
            with every column, at NASA&apos;s full precision.
          </p>

          <Panel title="Where each value comes from" open={audience === "researcher"}>
            <ul className="ml-5 list-disc space-y-1 text-sm">
              <li>One row per row of a NASA experimental table (22 tables, 24 investigations). Some rows are test days or
                summaries, flagged and hideable above.</li>
              <li>A value is converted only when the column header or the PSI record states its unit (atm, bar, mmHg,
                percent). Otherwise the cell is blank. The full units map is data/unified/units_map.csv in the repository.</li>
              <li>CFI (PSI-39) and SAFFIRE-III (PSI-100) write units inside the cells, not the headers, so those conditions
                are blank.</li>
              <li>No table states per row whether a test ran in microgravity or normal gravity, so that is not shown.</li>
            </ul>
          </Panel>
          {pts.length === 0 && <Note>No row in the current selection has both an O2 and a pressure value.</Note>}
        </>
      )}
    </>
  );
}
