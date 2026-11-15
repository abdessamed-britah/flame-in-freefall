"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AUDIENCES, useAudience, type AudienceId } from "@/lib/audience";

const PAGES = [
  { href: "/", label: "Home" },
  { href: "/catalog/", label: "Catalog" },
  { href: "/unified/", label: "Unified Data" },
  { href: "/lab/", label: "Suppression Lab" },
  { href: "/ask/", label: "Ask NASA Records" },
];

export default function Nav() {
  const path = usePathname() || "/";
  const { audienceId, setAudienceId } = useAudience();
  return (
    <nav aria-label="Main" className="border-b border-line bg-[#0f1528]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <Link href="/" className="mr-2 font-bold text-ink">Flame in Freefall</Link>
        <ul className="flex flex-wrap gap-1 text-sm">
          {PAGES.map((p) => {
            const active = p.href === "/" ? path === "/" : path.startsWith(p.href.slice(0, -1));
            return (
              <li key={p.href}>
                <Link href={p.href} aria-current={active ? "page" : undefined}
                  className={`block rounded-md px-3 py-1.5 ${active ? "bg-panel-2 font-semibold text-ink" : "text-muted hover:text-ink"}`}>
                  {p.label}
                </Link>
              </li>
            );
          })}
        </ul>
        <label className="ml-auto flex items-center gap-2 text-sm text-muted">
          View for
          <select value={audienceId} onChange={(e) => setAudienceId(e.target.value as AudienceId)}
            className="rounded-md border border-line bg-panel px-2 py-1 text-ink">
            {AUDIENCES.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </select>
        </label>
      </div>
    </nav>
  );
}
