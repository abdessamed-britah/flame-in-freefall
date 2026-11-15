"use client";
// The audience selector changes wording and which panels open first. Never numbers, never caveats.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

/** The register of the wording. Pages write each text once per register. */
export type Register = "plain" | "researcher" | "engineer";
export type AudienceId = "everyone" | "undergraduate" | "graduate" | "professor" | "aero_researcher" | "aero_engineer";

// The six audiences of the challenge brief, in the brief's order. Plain wording for Everyone and
// Undergraduate students; technical wording for the rest.
export const AUDIENCES: { id: AudienceId; label: string; register: Register }[] = [
  { id: "everyone", label: "Everyone", register: "plain" },
  { id: "undergraduate", label: "Undergraduate students", register: "plain" },
  { id: "graduate", label: "Graduate students", register: "researcher" },
  { id: "professor", label: "Professors", register: "researcher" },
  { id: "aero_researcher", label: "Aerospace researchers", register: "researcher" },
  { id: "aero_engineer", label: "Aerospace engineers", register: "engineer" },
];
const DEFAULT: AudienceId = "everyone";
const registerOf = (id: AudienceId) => AUDIENCES.find((a) => a.id === id)?.register ?? "plain";

const Ctx = createContext<{ audienceId: AudienceId; audience: Register; setAudienceId: (a: AudienceId) => void }>({
  audienceId: DEFAULT,
  audience: "plain",
  setAudienceId: () => {},
});

export function AudienceProvider({ children }: { children: ReactNode }) {
  const [id, setId] = useState<AudienceId>(DEFAULT);
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("audience") as AudienceId | null;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restoring a stored preference once
      if (saved && AUDIENCES.some((a) => a.id === saved)) setId(saved);
    } catch {
      /* storage blocked: keep the default */
    }
  }, []);
  const setAudienceId = (a: AudienceId) => {
    setId(a);
    try {
      window.localStorage.setItem("audience", a);
    } catch {
      /* storage blocked */
    }
  };
  return (
    <Ctx.Provider value={{ audienceId: id, audience: registerOf(id), setAudienceId }}>{children}</Ctx.Provider>
  );
}

/** `audience` is the register (plain, researcher, engineer); `audienceId` is the choice in the selector. */
export function useAudience() {
  return useContext(Ctx);
}

/** Wording per register. Every variant must say the same thing; only the register changes. */
export function pick<T>(audience: Register, v: Record<Register, T>): T {
  return v[audience];
}
