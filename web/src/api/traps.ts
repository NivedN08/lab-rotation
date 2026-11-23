// The trap types a learner can name. One list, so the labels can be matched to the backend's later.

export const TRAPS = [
  "Duplicated rows",
  "Unit mix-up",
  "Misleading data dictionary",
  "Batch confounder",
  "Hidden column in a second table",
  "No trap (the data is clean)",
] as const;

export type Trap = (typeof TRAPS)[number];
