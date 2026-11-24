import { useEffect, useRef, useState } from "react";
import { isStatic } from "../api/client";
import { SummitScene } from "../world/summit";

type Props = { onEnter: () => void; onJudge: () => void; onDemo: () => void; ready: boolean; status: string; live: boolean; leaving: boolean };

export function Landing({ onEnter, onJudge, onDemo, ready, status, live, leaving }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const sceneRef = useRef<SummitScene | null>(null);
  const [origin, setOrigin] = useState({ x: 68, y: 40 });
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scene = new SummitScene(ref.current!, reduced);
    sceneRef.current = scene;
    setOrigin({ x: scene.anchor.x * 100, y: scene.anchor.y * 100 });
    return () => scene.destroy();
  }, []);
  return (
    <div className={`landing ${leaving ? "leaving" : ""}`} style={{ ["--ox" as string]: `${origin.x}%`, ["--oy" as string]: `${origin.y}%` }}>
      <canvas ref={ref} aria-hidden="true" />
      <div className="hero">
        <h1 className="wordmark">
          Lab
          <br />
          Rotation
        </h1>
        <p>Your first week as a data analyst. A panel of AI scientists hands you a dataset that may hide a trap, watches how you work, and grades you against a real answer key.</p>
        {isStatic() ? (
          // The hosted replay has no live backend: the demo is the one way in.
          <button className="btn gold cta" onClick={onDemo} disabled={!ready} autoFocus>
            Watch the demo
          </button>
        ) : (
          <>
            <button className="btn gold cta" onClick={onJudge} disabled={!ready} autoFocus title="One task, four minutes, then the full debrief">
              Judge mode
            </button>
            <button className="btn cta" onClick={onEnter} disabled={!ready} style={{ marginLeft: 10 }} title="Three tasks, each a little harder">
              Start your rotation
            </button>
            <button className="btn cta" onClick={onDemo} disabled={!ready} style={{ marginLeft: 10 }}>
              Watch the demo
            </button>
            <p style={{ margin: "12px 0 0", fontSize: 15 }}>New here? Try Judge mode.</p>
          </>
        )}
        <div className="now">
          {live && <span className="live-dot" aria-hidden="true" />}
          {status}
        </div>
      </div>
    </div>
  );
}
