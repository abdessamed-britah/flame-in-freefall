"use client";
import Link from "next/link";
import meta from "@/public/data/meta.json";
import { Caveat, Finding, Metric, Panel } from "@/components/ui";
import { pick, useAudience } from "@/lib/audience";

const fmt = (n: number) => n.toLocaleString("en-US");
const pct = (x: number) => `${Math.round(x * 100)}%`;

const CARDS = [
  { href: "/catalog/", name: "Catalog", line: "Rank NASA's combustion investigations by relevance to a habitat, with weights you set." },
  { href: "/unified/", name: "Unified Data", line: "Plot and download the test conditions of every investigation, in the same units." },
  { href: "/lab/", name: "Suppression Lab", line: "See how much CO2 or He pushes a droplet flame to its extinction limit." },
  { href: "/ask/", name: "Ask NASA Records", line: "Read answers that cite NASA's own text, passage by passage." },
];

export default function Home() {
  const { audience } = useAudience();
  const k = meta.key_finding;
  const c = meta.counts;
  return (
    <>
      <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Flame in Freefall</h1>
      <p className="mt-3 max-w-3xl text-lg text-muted">
        {pick(audience, {
          researcher: "A Moon Base will likely run on 30% O2 or more at 527 mmHg or less. This dashboard summarises what NASA's microgravity combustion investigations measured in and near that atmosphere.",
          engineer: "A Moon Base will run on more oxygen at lower pressure than Earth: this is what NASA's microgravity combustion tests say about putting a fire out there.",
          student: "A Moon Base will have more oxygen and less pressure than the air on Earth. Here is what NASA's experiments in space say about how fires burn and go out there.",
        })}
      </p>

      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="NASA investigations" value={fmt(c.investigations)} hint="PSI, Combustion Science" />
        <Metric label="Unified test rows" value={fmt(c.unified_rows)} hint="from 22 NASA tables" />
        <Metric label="Passages of NASA text" value={fmt(c.passages)} hint="searchable, cited verbatim" />
        <Metric label="FLEX droplet tests" value={fmt(c.flex_tests)} hint="NASA PSI-69" />
      </div>

      <Finding>
        <strong className="text-flame-ink">
          Key finding, Moon Base atmosphere ({pct(k.o2_base)} O2 at about {Math.round(k.pressure_mmhg)} mmHg).
        </strong>{" "}
        {k.sentence}
      </Finding>
      <Caveat>
        <strong>Caveat.</strong> This comes from {k.tests} NASA tests on single fuel droplets, not cabin materials.
        Adding CO2 at a fixed O2/N2 balance also lowers O2 (40% CO2 brings {pct(k.o2_base)} O2 down to{" "}
        {pct(k.o2_at_40)}), so the data cannot separate the suppressant&apos;s effect from the lower oxygen.
      </Caveat>

      <h2 className="mt-10 mb-3 text-2xl font-semibold">Explore</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {CARDS.map((card) => (
          <div key={card.href} className="flex flex-col rounded-lg border border-line bg-panel p-4">
            <h3 className="font-semibold">{card.name}</h3>
            <p className="mt-2 flex-1 text-sm text-muted">{card.line}</p>
            <Link href={card.href}
              className="mt-4 rounded-md bg-flame px-4 py-2 text-center font-medium text-[#0b1020] hover:bg-flame-ink hover:no-underline">
              Open {card.name}
            </Link>
          </div>
        ))}
      </div>

      <Panel title="Sources and limitations" open={audience === "researcher"}>
        <h3 className="mt-2 font-semibold">Sources</h3>
        <ul className="ml-5 list-disc space-y-1 text-sm">
          <li>NASA Physical Sciences Informatics (PSI), <a href="https://psi.nasa.gov">psi.nasa.gov</a>: the records and
            experimental tables of the {c.investigations} Combustion Science investigations.</li>
          <li><strong>NASA PSI-69, Flame Extinguishment Experiment (FLEX)</strong>, experimental table, CC0:{" "}
            <a href={meta.flex.doi_url}>doi.org/10.60555/mbq8-0451</a>. {c.flex_tests} droplet-combustion tests from{" "}
            {meta.flex.first_date} to {meta.flex.last_date}: {meta.flex.fuels.Methanol} methanol, {meta.flex.fuels.Heptane}{" "}
            heptane; {meta.flex.pressure_bands.near_760} near 760 mmHg, {meta.flex.pressure_bands.near_535} near 535 mmHg,{" "}
            {meta.flex.pressure_bands.above_900} above 900 mmHg; {meta.flex.diluents.CO2} with CO2, {meta.flex.diluents.He}{" "}
            with He, {meta.flex.diluents.none} with neither.</li>
          <li>Column meanings and units are documented in <a href={meta.flex.report_url}>NASA/TP-2015-216046</a> (Table IX
            and Appendix A.1); the team has not yet confirmed them against that report.</li>
        </ul>
        <details className="mt-3 text-sm">
          <summary className="text-muted">All {meta.sources.length} PSI investigations with DOIs</summary>
          <ul className="mt-2 ml-5 list-disc space-y-1">
            {meta.sources.map((s) => (
              <li key={s.psi_id}>
                <a href={s.url}>{s.psi_id}</a> {s.acronym !== "not stated" ? s.acronym : ""} - {s.name}
                {s.doi !== "not stated" && <> - <a href={`https://doi.org/${s.doi}`}>{s.doi}</a></>}
              </li>
            ))}
          </ul>
        </details>
        <h3 className="mt-4 font-semibold">Limitations</h3>
        <ul className="ml-5 list-disc space-y-1 text-sm">
          {meta.limits.map((l) => <li key={l}>{l}</li>)}
          <li>CO2 and He were never mixed in the NASA tests; only 9 tests are above 900 mmHg.</li>
          <li>No partial-gravity data exists in PSI, and no table states per row whether a test ran in space or on the ground.</li>
        </ul>
        <p className="mt-3 text-xs text-muted">
          Every number is computed from NASA&apos;s tables or from the model trained on them (reports/audit.md,
          reports/validation.md). Exported {meta.exported_utc} from commit {meta.git_commit}.
        </p>
      </Panel>
    </>
  );
}
