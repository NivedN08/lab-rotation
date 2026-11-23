import { evidence, useEvidence } from "./evidence";

export function EvidenceTray() {
  const items = useEvidence();
  return (
    <section className="ws-tray box" aria-label="Evidence">
      <div className="ws-tray-head">
        <h2 className="ws-title">Evidence</h2>
        <span className="ws-count">{items.length}</span>
        {items.length > 0 && (
          <button className="btn quiet" onClick={evidence.clear}>
            Clear
          </button>
        )}
      </div>
      {items.length === 0 ? (
        <p className="empty">Click a row number, a column name or a cell in any table to cite it here.</p>
      ) : (
        <ul className="ws-cites">
          {items.map((e) => (
            <li key={e.key}>
              <span className={`chip ws-kind ${e.kind}`}>{e.kind}</span>
              <span className="ws-cite-text">
                {e.label}
                {e.sql && <code className="ws-cite-sql">{e.sql}</code>}
              </span>
              <button className="btn quiet icon" aria-label={`Remove: ${e.label}`} onClick={() => evidence.remove(e.key)}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
