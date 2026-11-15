// Shapes of the files in public/data/ written by src/export_web.py.

export type GridPoint = { x: number; mean: number; lower: number; upper: number; in_range: boolean; warnings: string[] };

export type LabSlice = {
  atm: "moon" | "iss";
  fuel: string;
  dil: "CO2" | "He";
  d0: number;
  pressure_mmhg: number;
  o2_base: number;
  tested: [number, number];
  d0_tested: [number, number];
  grid: { d_ext_over_d0: GridPoint[]; burning_rate_k: GridPoint[] };
  nearest: { test: number; distance: number }[][];
  crossing: { upper: number | null; mean: number | null; lower: number | null };
  sentence: string;
  points_key: string;
};

export type SlicePoint = {
  test: number; id: string; x: number; dil: "CO2" | "He" | "none"; ratio: number | null; k: number | null;
  d0: number | null; date: string; end: string;
};

export type FlexTest = {
  test: number; id: string; date: string; fuel: string; p_mmhg: number | null; o2: number; co2: number; he: number;
  d0: number | null; k: number | null; ratio: number | null; end: string; flag: string;
};

export type LabGrid = {
  threshold: number;
  fractions: number[];
  d0_mm: number[];
  fuels: string[];
  diluents: ("CO2" | "He")[];
  atmospheres: Record<"moon" | "iss", { label: string; o2_base: number; pressure_mmhg: number }>;
  slices: LabSlice[];
  points: Record<string, SlicePoint[]>;
  tests: Record<string, FlexTest>;
  limits: string[];
  note: string;
};

export type UnifiedRow = {
  id: string; inv: string; test: string; fuel: string; o2: number | null; basis: string; p: number | null;
  notTest: boolean; row: number;
};

export type Unified = {
  total_rows: number;
  rows_per_investigation: Record<string, number>;
  moon: { o2: number; p_kpa: number };
  rows: UnifiedRow[];
};

export async function getJSON<T>(name: string): Promise<T> {
  const r = await fetch(`/data/${name}`);
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  return (await r.json()) as T;
}
