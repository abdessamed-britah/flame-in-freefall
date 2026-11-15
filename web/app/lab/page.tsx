"use client";
import { useEffect, useMemo, useState } from "react";
import {
  Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter,
  Symbols, Tooltip, XAxis, YAxis,
} from "recharts";
import validation from "@/public/data/validation.json";
import { Caveat, Finding, Loading, Metric, PageHeader, Panel, Section, Select, TableWrap, td, th } from "@/components/ui";
import { pick, useAudience } from "@/lib/audience";
import { STREAMLIT_URL, REPO_URL } from "@/lib/config";
import { getJSON, type LabGrid, type LabSlice, type SlicePoint } from "@/lib/types";

const COLOR = { CO2: "#e36a20", He: "#4594ee", none: "#9aa3b5" } as const;
const SHAPE = { CO2: "circle", He: "diamond", none: "square" } as const;
const INK = "#eef1fa";
const AXIS = "#aab2c8";
const X_MAX = 0.6; // as on the Streamlit page: the tested range plus 0.10, shaded
type Target = "d_ext_over_d0" | "burning_rate_k";

const f2 = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "" : v.toFixed(d));
const pct = (x: number) => `${Math.round(x * 100)}%`;

function seriesFor(s: LabSlice, target: Target) {
  // the model line and band are drawn only across the fractions NASA tested in this slice
  return s.grid[target].filter((p) => p.x <= s.tested[1] + 1e-9)
    .map((p) => ({ x: p.x, [`${s.dil}_mean`]: p.mean, [`${s.dil}_band`]: [p.lower, p.upper] as [number, number] }));
}

function merge(a: Record<string, unknown>[], b: Record<string, unknown>[]) {
  const m = new Map<number, Record<string, unknown>>();
  for (const r of [...a, ...b]) m.set(r.x as number, { ...(m.get(r.x as number) ?? {}), ...r });
  return [...m.values()].sort((p, q) => (p.x as number) - (q.x as number));
}

function PointShape({ cx, cy, dil }: { cx?: number; cy?: number; dil: keyof typeof COLOR }) {
  const open = dil === "none";
  return <Symbols cx={cx} cy={cy} type={SHAPE[dil]} size={48} fill={open ? "none" : COLOR[dil]}
    stroke={open ? COLOR[dil] : "#0b1020"} strokeWidth={open ? 1.5 : 1} />;
}

function PtTip({ active, payload }: { active?: boolean; payload?: { payload: Record<string, unknown> }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  if (p.test !== undefined) {
    const q = p as unknown as SlicePoint & { y: number };
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-2 text-xs">
        <div className="font-semibold">NASA test {q.test} ({q.id})</div>
        <div>{q.date}, d0 {f2(q.d0)} mm, test end: {q.end}</div>
        <div>Suppressant {f2(q.x)} · value {f2(q.y)}</div>
      </div>
    );
  }
  const rows = Object.entries(p).filter(([k]) => k.endsWith("_mean"));
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2 text-xs">
      <div className="font-semibold">Model at suppressant {f2(p.x as number, 3)}</div>
      {rows.map(([k, v]) => {
        const dil = k.split("_")[0];
        const band = p[`${dil}_band`] as [number, number];
        return <div key={k}>{dil}: mean {f2(v as number)}, 90% band {f2(band[0])} to {f2(band[1])}</div>;
      })}
    </div>
  );
}

function Chart({ slices, points, target, threshold, current, testedMax, label }: {
  slices: LabSlice[]; points: { dil: keyof typeof COLOR; rows: (SlicePoint & { y: number })[] }[]; target: Target;
  threshold?: number; current: number; testedMax: number; label: string;
}) {
  const data = slices.map((s) => seriesFor(s, target)).reduce((a, b) => merge(a, b), [] as Record<string, unknown>[]);
  const yMax = target === "d_ext_over_d0" ? 1.05
    : Math.ceil(Math.max(...slices.flatMap((s) => s.grid[target].filter((p) => p.x <= s.tested[1] + 1e-9).map((p) => p.upper)),
      ...points.flatMap((g) => g.rows.map((r) => r.y))) * 10) / 10 + 0.1;
  return (
    <div className="h-[440px] w-full min-w-0 rounded-lg border border-line bg-panel/30 p-2" role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 16, bottom: 30, left: 8 }}>
          <CartesianGrid stroke="rgba(238,241,250,0.10)" />
          <XAxis type="number" dataKey="x" domain={[0, X_MAX]} ticks={[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]} stroke={AXIS}
            label={{ value: "Suppressant (mole fraction)", position: "bottom", offset: 10, fill: AXIS }} />
          <YAxis type="number" domain={[0, yMax]} ticks={target === "d_ext_over_d0" ? [0, 0.2, 0.4, 0.6, 0.8, 1] : undefined} stroke={AXIS} width={56} tickFormatter={(v: number) => v.toFixed(1)}
            label={{ value: target === "d_ext_over_d0" ? "d_ext / d0 (no unit)" : "Burning rate K (unit unconfirmed)",
              angle: -90, position: "insideLeft", fill: AXIS, style: { textAnchor: "middle" }, dx: 4, dy: 60 }} />
          <ReferenceArea x1={testedMax} x2={X_MAX} fill="#9aa3b5" fillOpacity={0.16}
            label={{ value: "no NASA tests", position: "insideTop", fill: AXIS, fontSize: 12 }} />
          {threshold !== undefined && (
            <ReferenceLine y={threshold} stroke={INK} strokeDasharray="2 4"
              label={{ value: `near-limit threshold ${threshold.toFixed(2)} (team's choice)`, position: "insideBottomLeft", fill: INK, fontSize: 12 }} />
          )}
          <ReferenceLine x={current} stroke={AXIS} strokeDasharray="2 3"
            label={{ value: "your input", position: "insideBottomRight", fill: AXIS, fontSize: 12 }} />
          <Tooltip content={<PtTip />} />
          <Legend verticalAlign="top" wrapperStyle={{ paddingBottom: 8 }} />
          {slices.map((s) => (
            <Area key={`${s.dil}-band`} dataKey={`${s.dil}_band`} name={`90% band, ${s.dil}`} stroke="none"
              fill={COLOR[s.dil]} fillOpacity={0.22} isAnimationActive={false} connectNulls legendType="square" />
          ))}
          {slices.map((s) => (
            <Line key={`${s.dil}-mean`} dataKey={`${s.dil}_mean`} name={`Model mean, ${s.dil}, d0 ${s.d0.toFixed(2)} mm`}
              stroke={COLOR[s.dil]} strokeWidth={2.5} strokeDasharray={s.dil === "He" ? "7 4" : undefined} dot={false}
              isAnimationActive={false} connectNulls />
          ))}
          {points.map((g) => (
            <Scatter key={g.dil} data={g.rows} dataKey="y" name={`NASA tests, ${g.dil === "none" ? "no suppressant" : g.dil} (${g.rows.length})`}
              fill={g.dil === "none" ? "none" : COLOR[g.dil]} stroke={COLOR[g.dil]} legendType={SHAPE[g.dil]}
              isAnimationActive={false} shape={(p: { cx?: number; cy?: number }) => <PointShape cx={p.cx} cy={p.cy} dil={g.dil} />} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function LabPage() {
  const { audience } = useAudience();
  const [grid, setGrid] = useState<LabGrid | null>(null);
  const [err, setErr] = useState("");
  const [atm, setAtm] = useState<"moon" | "iss">("moon");
  const [fuel, setFuel] = useState("Methanol");
  const [dil, setDil] = useState<"CO2" | "He">("CO2");
  const [d0, setD0] = useState("3.48");
  const [xi, setXi] = useState(12); // 0.30
  useEffect(() => { getJSON<LabGrid>("lab_grid.json").then(setGrid, (e) => setErr(String(e))); }, []);

  const find = (g: LabGrid, d: "CO2" | "He") =>
    g.slices.find((s) => s.atm === atm && s.fuel === fuel && s.dil === d && s.d0 === Number(d0));
  const s = useMemo(() => (grid ? find(grid, dil) : undefined), [grid, atm, fuel, dil, d0]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <Caveat>Could not load the Suppression Lab data: {err}</Caveat>;
  if (!grid || !s) return <Loading what="the Suppression Lab grid" />;

  const maxIdx = grid.fractions.findLastIndex((x) => x <= s.tested[1] + 1e-9);
  const i = Math.min(xi, maxIdx);
  const x = grid.fractions[i];
  const ratio = s.grid.d_ext_over_d0[i];
  const rate = s.grid.burning_rate_k[i];
  const warnings = [...new Set([...ratio.warnings, ...rate.warnings])];
  const o2 = s.o2_base * (1 - x);
  const pts = grid.points[s.points_key];
  const ratioPts = (["none", dil] as const).map((d) => ({
    dil: d, rows: pts.filter((p) => p.dil === d && p.ratio !== null).map((p) => ({ ...p, y: p.ratio as number })),
  }));
  const both = (["CO2", "He"] as const).map((d) => find(grid, d)).filter((v): v is LabSlice => !!v)
    .filter((v) => grid.points[v.points_key].some((p) => p.dil === v.dil));
  const ratePts = [
    { dil: "none" as const, rows: pts.filter((p) => p.dil === "none" && p.k !== null).map((p) => ({ ...p, y: p.k as number })) },
    ...both.map((v) => ({ dil: v.dil, rows: grid.points[v.points_key].filter((p) => p.dil === v.dil && p.k !== null).map((p) => ({ ...p, y: p.k as number })) })),
  ];
  const nearest = s.nearest[i].map((n) => ({ ...grid.tests[String(n.test)], distance: n.distance }));
  const nRatio = pts.filter((p) => p.ratio !== null).length;
  const heK = validation.lodo.find((r) => r["Suppressant never seen in training"] === "He" && r.Target.startsWith("Burning"));

  return (
    <>
      <PageHeader title="Moon Base Suppression Lab"
        purpose={<>{pick(audience, {
          researcher: "Gaussian-process predictions of extinction ratio and burning rate against suppressant fraction, from NASA's FLEX tests",
          engineer: "How much CO2 or He pushes a burning fuel droplet to its extinction limit, from NASA's FLEX tests",
          student: "Add CO2 or helium to the air and see how soon a burning droplet goes out, using NASA's FLEX tests",
        })} (<a href="https://doi.org/10.60555/mbq8-0451">PSI-69</a>).</>} />
      <Caveat>Single fuel droplets, not cabin materials: this supports fire-safety reasoning, it does not predict a cabin fire.</Caveat>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Select label="Base atmosphere" value={atm} onChange={setAtm}
          options={(["moon", "iss"] as const).map((k) => ({ value: k, label: grid.atmospheres[k].label }))} />
        <Select label="Fuel" value={fuel} onChange={setFuel} options={grid.fuels.map((f) => ({ value: f, label: f }))} />
        <Select label="Suppressant" value={dil} onChange={setDil} options={grid.diluents.map((d) => ({ value: d, label: d }))} />
        <Select label="Droplet diameter d0 (mm)" value={d0} onChange={setD0}
          options={grid.d0_mm.map((d) => ({ value: String(d), label: d.toFixed(2) }))} />
        <Select label={`${dil} mole fraction`} value={String(i)} onChange={(v) => setXi(Number(v))}
          options={grid.fractions.slice(0, maxIdx + 1).map((f, k) => ({ value: String(k), label: f.toFixed(3) }))} />
      </div>
      <p className="mt-2 text-xs text-muted">
        Only the values on the exported grid can be chosen. The suppressant list stops where NASA&apos;s tests for this
        slice stop ({f2(s.tested[1])}). NASA tested droplets of {f2(s.d0_tested[0])} to {f2(s.d0_tested[1])} mm here.
      </p>

      {warnings.length > 0 && (
        <div role="alert" className="my-4 rounded-lg border border-[#7a2a2a] bg-[#3a1515] px-4 py-3 text-[#ffb4b4]">
          <strong>Outside the range of the NASA data.</strong> {warnings.join(" ")} Treat the numbers below as unsupported.
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Predicted d_ext / d0" value={f2(ratio.mean)} hint={`90% interval ${f2(ratio.lower)} to ${f2(ratio.upper)}`} />
        <Metric label="Predicted K, unit unconfirmed" value={f2(rate.mean)} hint={`90% interval ${f2(rate.lower)} to ${f2(rate.upper)}`} />
        <Metric label="Chamber O2 (mole fraction)" value={o2.toFixed(3)} hint={`${s.o2_base.toFixed(2)} x (1 - ${x.toFixed(3)})`} />
        <Metric label="Pressure (mmHg)" value={s.pressure_mmhg.toFixed(0)} hint="median of NASA's tests of this atmosphere" />
      </div>

      <Section title="1. How close to the extinction limit?">
        <Chart slices={[s]} points={ratioPts} target="d_ext_over_d0" threshold={grid.threshold} current={x}
          testedMax={s.tested[1]}
          label={`Extinction ratio against ${dil} fraction for a ${s.d0} mm ${fuel.toLowerCase()} droplet, with 90% band, NASA tests and the 0.90 threshold`} />
        <Finding>{s.sentence}</Finding>
        <Caveat>
          <strong>More {dil} also means less oxygen.</strong> Adding diluent at a fixed O2/N2 balance lowers O2 as well:
          40% {dil} brings {pct(s.o2_base)} O2 down to {pct(s.o2_base * 0.6)} ({s.o2_base.toFixed(2)} x (1 - 0.40)). The data
          cannot separate the diluent&apos;s effect from the lower oxygen.
        </Caveat>
        <Panel title="How to read this chart" open={audience === "student"} key={`read-${audience}`}>
          <ul className="ml-5 list-disc space-y-1 text-sm">
            <li>d_ext / d0 is the droplet size when the flame went out, divided by its size at ignition. Near 1: the flame
              went out almost at once (close to the limit). Small: most of the droplet burned.</li>
            <li>Points are the {nRatio} NASA tests of this slice that have an extinction ratio ({pts.length - nRatio} more have
              none and are not drawn). They cover droplets of {f2(s.d0_tested[0])} to {f2(s.d0_tested[1])} mm; the line is for{" "}
              {s.d0.toFixed(2)} mm. Hover a point for its test number.</li>
            <li>The ratio cannot exceed 1 (the flame cannot go out at a diameter larger than the droplet started with), so
              the model line and band are cut off at 1.</li>
            <li>&quot;At least&quot; is where the top of the 90% band reaches the threshold; the best estimate is where the model
              line does. Percentages are mole fractions of suppressant. The finding sentence uses the Streamlit app&apos;s
              finer curve (step 0.005); the chart shows the exported grid (step 0.025).</li>
            <li>The 0.90 threshold is the team&apos;s choice, not a NASA value.</li>
            <li>Chamber O2 is not a free input: in NASA&apos;s tests the suppressant replaces part of a fixed O2/N2 mix.</li>
          </ul>
        </Panel>
      </Section>

      <Section title="2. Burning rate: CO2 against He">
        <Chart slices={both} points={ratePts} target="burning_rate_k" current={x}
          testedMax={Math.max(...both.map((v) => v.tested[1]))}
          label={`Burning rate against suppressant fraction, CO2 and He, for a ${s.d0} mm ${fuel.toLowerCase()} droplet`} />
        <p className="mt-2 text-sm text-muted">Each model line stops where NASA&apos;s tests for that suppressant stop. The
          burning-rate unit is unconfirmed (the NASA header prints &quot;mm&quot;). CO2 is solid orange, He dashed blue.</p>
      </Section>

      <Section title="3. Evidence: the 5 nearest NASA tests">
        <Panel title={`Nearest tests to ${fuel.toLowerCase()}, ${dil} ${x.toFixed(3)}, d0 ${s.d0.toFixed(2)} mm`} open={audience !== "student"} key={`ev-${audience}`}>
          <TableWrap>
            <table className="w-full text-sm">
              <thead><tr>{["Test", "Identifier", "Date", "Pressure (mmHg)", "O2 (mole fraction)", "CO2 (mole fraction)",
                "He (mole fraction)", "d0 (mm)", "Burning rate K (unit unconfirmed)", "d_ext / d0", "Test end", "Quality flag", "Distance"]
                .map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
              <tbody>
                {nearest.map((t) => (
                  <tr key={t.test}>
                    <td className={td}>{t.test}</td><td className={td}>{t.id}</td><td className={`${td} whitespace-nowrap`}>{t.date}</td>
                    <td className={`${td} text-right`}>{f2(t.p_mmhg, 0)}</td><td className={`${td} text-right`}>{f2(t.o2)}</td>
                    <td className={`${td} text-right`}>{f2(t.co2)}</td><td className={`${td} text-right`}>{f2(t.he)}</td>
                    <td className={`${td} text-right`}>{f2(t.d0)}</td><td className={`${td} text-right`}>{f2(t.k, 3)}</td>
                    <td className={`${td} text-right`}>{f2(t.ratio)}</td><td className={td}>{t.end}</td><td className={td}>{t.flag}</td>
                    <td className={`${td} text-right`}>{f2(t.distance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          <p className="mt-2 text-xs text-muted">Same fuel only. Distance is over O2, pressure, CO2, He and d0, each divided by
            its standard deviation across the tests; smaller is closer. Empty cells are values NASA did not report.</p>
        </Panel>
      </Section>

      <Section title="4. How far to trust this">
        {heK && (
          <Caveat>
            <strong>The model fails on a suppressant it has not seen.</strong> Trained without any helium test, its burning-rate
            error on helium was {heK.MAE} against {heK["MAE of mean baseline"]} for simply predicting the average, and only{" "}
            {heK["Coverage of 90% interval"]} of helium tests fell inside its 90% interval. It is no better than the average
            there, so the app never extrapolates to a new suppressant.
          </Caveat>
        )}
        <Panel title="Validation tables" open={audience === "researcher"} key={`val-${audience}`}>
          <p className="text-sm"><strong>Tests the model has not seen, grouped by test date ({validation.n_folds} folds).</strong>{" "}
            MAE is the typical error; coverage is how often the measured value fell inside the 90% interval.</p>
          <div className="mt-2"><TableWrap><table className="w-full text-sm">
            <thead><tr>{Object.keys(validation.cv[0]).map((k) => <th key={k} className={th}>{k}</th>)}</tr></thead>
            <tbody>{validation.cv.map((r, k) => <tr key={k}>{Object.values(r).map((v, j) => <td key={j} className={td}>{String(v)}</td>)}</tr>)}</tbody>
          </table></TableWrap></div>
          <p className="mt-4 text-sm"><strong>Honesty test: a suppressant the model has never seen.</strong> Trained without any
            test of that suppressant, then scored on those tests.</p>
          <div className="mt-2"><TableWrap><table className="w-full text-sm">
            <thead><tr>{Object.keys(validation.lodo[0]).map((k) => <th key={k} className={th}>{k}</th>)}</tr></thead>
            <tbody>{validation.lodo.map((r, k) => (
              <tr key={k} className={r["Suppressant never seen in training"] === "He" ? "bg-[#4594ee]/10" : ""}>
                {Object.values(r).map((v, j) => <td key={j} className={td}>{String(v)}</td>)}
              </tr>))}</tbody>
          </table></TableWrap></div>
          <p className="mt-2 text-xs text-muted">Source: {validation.source}. If &quot;MAE&quot; is close to &quot;MAE of mean
            baseline&quot;, the model is no better than guessing the average for that suppressant.</p>
        </Panel>
      </Section>

      <Section title="Details">
        <Panel title="Limits of this tool" open={false}>
          <ul className="ml-5 list-disc space-y-1 text-sm">
            {grid.limits.map((l) => <li key={l}>{l}</li>)}
            <li>CO2 and He were never mixed in the NASA tests, and only 9 tests are above 900 mmHg; neither is offered here.</li>
          </ul>
        </Panel>
        <Panel title="Physics comparison (d2-law)" open={false}><p className="text-sm">d2-law baseline pending.</p></Panel>
        <Panel title="Explain this result (AI)" open={false}>
          <p className="text-sm">This static site does not call an AI service. The live, checked explanation is in the{" "}
            {STREAMLIT_URL ? <a href={STREAMLIT_URL}>Streamlit app</a> : <a href={REPO_URL}>Streamlit app (see the README)</a>}.</p>
        </Panel>
        <p className="mt-2 text-xs text-muted">{grid.note}</p>
      </Section>
    </>
  );
}
