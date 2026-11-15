"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import catalog from "@/public/data/catalog.json";
import { AUDIENCES, useAudience, type AudienceId } from "@/lib/audience";

const label = "font-mono text-[11px] uppercase tracking-wider text-muted";

/* ------------------------------------------------------------------ gravity strip */
const GRAVITY = [
  { place: "Orbit / ISS", value: "~0", unit: "g", note: "microgravity" },
  { place: "Moon", value: "1.62", unit: "m/s²", note: "0.17 g" },
  { place: "Mars", value: "3.71", unit: "m/s²", note: "0.38 g" },
  { place: "Earth", value: "9.81", unit: "m/s²", note: "1 g" },
];

export function GravityStrip() {
  return (
    <section aria-labelledby="gravity" className="mt-16">
      <h2 id="gravity" className={label}>Gravity where a fire might burn</h2>
      <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {GRAVITY.map((g) => (
          <li key={g.place} className="rounded-lg border border-line bg-panel px-4 py-3">
            <div className={label}>{g.place}</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">
              {g.value} <span className="font-mono text-sm font-normal text-muted">{g.unit}</span>
            </div>
            <div className="font-mono text-xs text-muted">{g.note}</div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm text-muted">
        All NASA PSI combustion data comes from orbit or Earth; no Moon or Mars data exists yet.
      </p>
    </section>
  );
}

/* ------------------------------------------------------------------ audience cards */
const PATHS: Record<AudienceId, { line: string; path: { href: string; name: string }[] }> = {
  everyone: { line: "Start with the main question, then read what NASA wrote.",
    path: [{ href: "/lab/", name: "Suppression Lab" }, { href: "/ask/", name: "Ask" }, { href: "/catalog/", name: "Catalog" }] },
  undergraduate: { line: "See a real experiment's data, then the tests behind it.",
    path: [{ href: "/lab/", name: "Suppression Lab" }, { href: "/unified/", name: "Unified Data" }, { href: "/ask/", name: "Ask" }] },
  graduate: { line: "Explore the test conditions, then the model and its validation.",
    path: [{ href: "/unified/", name: "Unified Data" }, { href: "/lab/", name: "Suppression Lab" }, { href: "/catalog/", name: "Catalog" }] },
  professor: { line: "Survey the investigations and their sources for teaching or review.",
    path: [{ href: "/catalog/", name: "Catalog" }, { href: "/ask/", name: "Ask" }, { href: "/lab/", name: "Suppression Lab" }] },
  aero_researcher: { line: "Check the model's honesty tests, then the data coverage.",
    path: [{ href: "/lab/", name: "Suppression Lab" }, { href: "/unified/", name: "Unified Data" }, { href: "/catalog/", name: "Catalog" }] },
  aero_engineer: { line: "Suppressant needed at habitat conditions, nearest real tests, relevant studies.",
    path: [{ href: "/lab/", name: "Suppression Lab" }, { href: "/catalog/", name: "Catalog" }, { href: "/ask/", name: "Ask" }] },
};

export function AudienceCards() {
  const { audienceId, setAudienceId } = useAudience();
  const router = useRouter();
  return (
    <section aria-labelledby="audiences" className="mt-16">
      <h2 id="audiences" className="text-2xl font-semibold">Where to start</h2>
      <p className="mt-1 text-sm text-muted">Choosing a card sets the wording of the whole site for you and opens the first page.
        The numbers and caveats are the same for everyone.</p>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {AUDIENCES.map((a) => {
          const p = PATHS[a.id];
          const current = a.id === audienceId;
          return (
            <li key={a.id}>
              <button type="button" onClick={() => { setAudienceId(a.id); router.push(p.path[0].href); }}
                aria-label={`${a.label}: set this view and open ${p.path[0].name}`}
                className={`h-full w-full rounded-lg border bg-panel p-4 text-left transition-colors hover:border-flame-ink ${current ? "border-flame" : "border-line"}`}>
                <span className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{a.label}</span>
                  {current && <span className="font-mono text-[11px] uppercase text-flame-ink">current view</span>}
                </span>
                <span className="mt-1 block text-sm text-muted">{p.line}</span>
                <span className="mt-3 block font-mono text-xs text-ink">
                  {p.path.map((x) => x.name).join(" → ")}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------------ investigation cards */
const START = ["FLEX", "FLEX-2", "BASS-II", "SAFFIRE-I", "SAME-R", "ACME CFI-G"];
type Visual = "liquid" | "solid" | "gas" | "smoke";

/** Decorative flame, CSS gradients only. Chosen by the catalog's fuel phase; smoke for detection studies. */
function FlameArt({ kind }: { kind: Visual }) {
  const common = "absolute left-1/2 -translate-x-1/2";
  return (
    <div aria-hidden className="relative h-28 overflow-hidden rounded-md bg-[#070b17]">
      {kind === "liquid" && (
        <div className={`${common} top-1/2 h-16 w-16 -translate-y-1/2 rounded-full`}
          style={{ background: "radial-gradient(circle at 42% 38%, #e8f3ff 0 6%, #6fb0ff 22%, #2f6fd0 48%, rgba(69,148,238,0.18) 68%, transparent 72%)",
            boxShadow: "0 0 28px 8px rgba(69,148,238,0.35)" }} />
      )}
      {kind === "solid" && (
        <div className={`${common} bottom-0 h-24 w-10`}
          style={{ borderRadius: "50% 50% 35% 35% / 70% 70% 30% 30%",
            background: "linear-gradient(to top, #2f6fd0 0%, #4594ee 18%, #e36a20 45%, #ff8a3d 70%, rgba(255,176,103,0) 100%)",
            filter: "blur(1px)", boxShadow: "0 0 24px 4px rgba(227,106,32,0.35)" }} />
      )}
      {kind === "gas" && (
        <div className={`${common} top-1/2 h-24 w-32 -translate-y-1/2`}
          style={{ background: "radial-gradient(ellipse at 50% 55%, rgba(255,138,61,0.55) 0%, rgba(227,106,32,0.35) 25%, rgba(69,148,238,0.35) 50%, transparent 72%)",
            filter: "blur(6px)" }} />
      )}
      {kind === "smoke" && (
        <div className="absolute inset-0"
          style={{ background: "radial-gradient(ellipse at 35% 60%, rgba(170,178,200,0.35), transparent 55%), radial-gradient(ellipse at 65% 40%, rgba(154,163,181,0.3), transparent 50%), radial-gradient(ellipse at 50% 80%, rgba(120,128,145,0.3), transparent 60%)",
            filter: "blur(8px)" }} />
      )}
    </div>
  );
}

export function StartInvestigations() {
  const rows = START.map((a) => catalog.rows.find((r) => r.acronym === a)).filter((r): r is (typeof catalog.rows)[number] => !!r);
  return (
    <section aria-labelledby="start" className="mt-16">
      <h2 id="start" className="text-2xl font-semibold">Six investigations to start with</h2>
      <ul className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {rows.map((r) => {
          const kind: Visual = r.fire_safety_pillar === "detection" ? "smoke"
            : (["liquid", "solid", "gas"].includes(r.fuel_phase) ? r.fuel_phase : "gas") as Visual;
          const word = r.fire_safety_pillar !== "not stated" ? r.fire_safety_pillar : r.fuel_phase;
          return (
            <li key={r.psi_id}>
              <Link href="/catalog/" className="block h-full rounded-lg border border-line bg-panel p-3 text-ink hover:border-flame-ink hover:no-underline"
                aria-label={`${r.acronym} (${r.psi_id}), ${word}: open the Catalog`}>
                <FlameArt kind={kind} />
                <div className="mt-3 font-semibold">{r.acronym}</div>
                <div className="font-mono text-xs text-muted">{r.psi_id} · {word}</div>
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-muted">
        Pictures are decorative, chosen by the catalog&apos;s fuel phase (liquid droplet, solid flame front, gas flame) or
        smoke for a detection study. They are not images of the experiments.
      </p>
    </section>
  );
}
