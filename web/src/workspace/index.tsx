import { useEffect, useState } from "react";
import { TableBrowser } from "./TableBrowser";
import { loadTables } from "./fakeData";
import type { Table } from "./types";
import "./workspace.css";

type Props = { onTaskChange?: (running: boolean) => void };

export default function Workspace(_props: Props) {
  const [tables, setTables] = useState<Table[] | null>(null);

  useEffect(() => {
    let live = true;
    loadTables().then((t) => live && setTables(t));
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="ws-root">
      <h2 className="ws-title">Tables</h2>
      {tables ? <TableBrowser tables={tables} /> : <p className="empty">Loading tables…</p>}
    </div>
  );
}

export { Workspace };
