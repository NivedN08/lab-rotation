import type { Cell, Table } from "./types";

// Fake tables shaped like a small GeneBench-style dataset, with a few planted traps
// (duplicate sample rows, missing values, a unit mix-up) so the browser has something to show.

function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

const r = rng(7);
const pick = <T,>(xs: T[]) => xs[Math.floor(r() * xs.length)];
const round = (n: number, d = 2) => Math.round(n * 10 ** d) / 10 ** d;

const genes = ["BRCA1", "TP53", "EGFR", "MYC", "KRAS", "PTEN", "CDK2", "IL6", "TNF", "GAPDH", "ACTB", "VEGFA"];
const tissues = ["liver", "lung", "breast", "colon", "skin"];
const arms = ["control", "treated"];

const samples: Cell[][] = [];
for (let i = 1; i <= 120; i++) {
  samples.push([
    `S${String(i).padStart(3, "0")}`,
    pick(tissues),
    pick(arms),
    pick(["A", "B", "C"]),
    r() < 0.06 ? null : round(30 + r() * 50, 0),
    `2026-0${1 + Math.floor(r() * 9)}-${String(1 + Math.floor(r() * 27)).padStart(2, "0")}`,
  ]);
}
// planted trap: the same sample entered twice
samples.push([...samples[11]], [...samples[40]]);

const expression: Cell[][] = [];
let id = 1;
for (const s of samples.slice(0, 120)) {
  for (const g of genes.slice(0, 6)) {
    expression.push([id++, s[0], g, round(Math.exp(r() * 6), 2), s[3] === "C" ? "TPM" : "FPKM"]);
  }
}

const variants: Cell[][] = [];
for (let i = 1; i <= 80; i++) {
  variants.push([
    `V${String(i).padStart(3, "0")}`,
    pick(genes),
    `chr${1 + Math.floor(r() * 22)}`,
    Math.floor(r() * 1e8),
    pick(["missense", "synonymous", "nonsense", "intronic"]),
    round(r() * 0.5, 3),
  ]);
}

export const FAKE_TABLES: Table[] = [
  {
    name: "samples",
    about: "One row per sample: tissue, arm, batch, age and collection date.",
    columns: [
      { name: "sample_id", type: "text" },
      { name: "tissue", type: "text" },
      { name: "arm", type: "text" },
      { name: "batch", type: "text" },
      { name: "age", type: "int" },
      { name: "collected", type: "date" },
    ],
    rows: samples,
  },
  {
    name: "expression",
    about: "Expression level of each gene in each sample. Batch C reports TPM, the rest FPKM.",
    columns: [
      { name: "id", type: "int" },
      { name: "sample_id", type: "text" },
      { name: "gene", type: "text" },
      { name: "level", type: "real" },
      { name: "unit", type: "text" },
    ],
    rows: expression,
  },
  {
    name: "variants",
    about: "Variant calls per gene with allele frequency.",
    columns: [
      { name: "variant_id", type: "text" },
      { name: "gene", type: "text" },
      { name: "chrom", type: "text" },
      { name: "pos", type: "int" },
      { name: "effect", type: "text" },
      { name: "allele_freq", type: "real" },
    ],
    rows: variants,
  },
];

/** Stands in for the server call; swap for the contract loader later. */
export function loadTables(): Promise<Table[]> {
  return new Promise((res) => setTimeout(() => res(FAKE_TABLES), 150));
}
