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

const ID_WORDS = TRAPS.filter((t) => t.id !== "none").map((t) => t.id).join("|");
const ID_PATTERN = new RegExp(`\\b(${ID_WORDS})\\b`, "g");

/**
 * Replaces raw trap ids inside a sentence with their labels ("unit_mismatch" becomes "Unit mix-up"), for text the
 * backend wrote with ids in it. `none` is left alone, since it is also an ordinary word.
 */
export const labelTraps = (text: string): string => text.replace(ID_PATTERN, (id) => trapLabel(id));
