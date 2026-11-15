"use client";
// The audience selector changes wording and which panels open first. Never numbers, never caveats.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Audience = "researcher" | "engineer" | "student";

// The audiences named in the challenge brief as recorded in the team's notes (CLAUDE.md).
export const AUDIENCES: { id: Audience; label: string; lead: string }[] = [
  { id: "researcher", label: "Researcher", lead: "Model validation and NASA sources first." },
  { id: "engineer", label: "Engineer", lead: "Habitat numbers and the nearest real tests first." },
  { id: "student", label: "Student", lead: "Plain-words explanations first." },
];

const Ctx = createContext<{ audience: Audience; setAudience: (a: Audience) => void }>({
  audience: "engineer",
  setAudience: () => {},
});

export function AudienceProvider({ children }: { children: ReactNode }) {
  const [audience, setAudienceState] = useState<Audience>("engineer");
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("audience") as Audience | null;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restoring a stored preference once
      if (saved && AUDIENCES.some((a) => a.id === saved)) setAudienceState(saved);
    } catch {
      /* storage blocked: keep the default */
    }
  }, []);
  const setAudience = (a: Audience) => {
    setAudienceState(a);
    try {
      window.localStorage.setItem("audience", a);
    } catch {
      /* storage blocked */
    }
  };
  return <Ctx.Provider value={{ audience, setAudience }}>{children}</Ctx.Provider>;
}

export function useAudience() {
  return useContext(Ctx);
}

/** Wording per audience. Every variant must say the same thing; only the register changes. */
export function pick<T>(audience: Audience, v: Record<Audience, T>): T {
  return v[audience];
}
