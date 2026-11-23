// Shapes the workspace reads. fakeData.ts fills them for now; Nived's contract/ replaces it later.

export type Cell = string | number | boolean | null;

export type Column = { name: string; type: "text" | "int" | "real" | "date" };

export type Table = {
  name: string;
  /** One line on what the table holds, shown under the tabs. */
  about: string;
  columns: Column[];
  rows: Cell[][];
};
