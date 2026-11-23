// The trap types a learner can name. The answer form sends the `id`; the `label` is display only.
// Mastery uses the same ids in its `trap` field, including `none`.

export const TRAPS = [
  { id: "duplicate_rows", label: "Duplicated rows" },
  { id: "unit_mismatch", label: "Unit mix-up" },
  { id: "dictionary_flip", label: "Misleading data dictionary" },
  { id: "confounder", label: "Batch confounder" },
  { id: "hidden_variable", label: "Hidden column in a second table" },
  { id: "none", label: "No trap (the data is clean)" },
] as const;

export type TrapId = (typeof TRAPS)[number]["id"];

export const trapLabel = (id: string): string => TRAPS.find((t) => t.id === id)?.label ?? id;
