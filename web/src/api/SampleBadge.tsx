import { useDemo } from "./demo";

/** A small "Sample data" chip. Shows while the page is running on fake data (mock mode demo). Mount it once in the app. */
export function SampleBadge() {
  const demo = useDemo();
  if (demo.status === "off" || !demo.sample) return null;
  return (
    <div
      role="status"
      style={{
        position: "fixed",
        left: 14,
        bottom: 96,
        zIndex: 40,
        padding: "4px 10px",
        background: "var(--gold)",
        color: "var(--ink)",
        boxShadow: "0 0 0 2px var(--ink)",
        fontFamily: "var(--pixel)",
        fontSize: 13,
        fontWeight: 700,
      }}
    >
      Sample data
    </div>
  );
}
