import { useEffect, useRef, useState } from "react";
import type { Role } from "../data/types";
import { lookFor, personSprite, SPR_H, SPR_W } from "../world/people";

/** A person's portrait from the backend when there is one, otherwise their sprite scaled up with hard pixels. */
export function Avatar({ id, role, scale = 5, portrait }: { id: string; role: Role; scale?: number; portrait?: string | null }) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [portrait]);
  if (portrait && !broken) return <img className="photo" src={portrait} alt="" onError={() => setBroken(true)} />;
  return <Sprite id={id} role={role} scale={scale} />;
}

function Sprite({ id, role, scale }: { id: string; role: Role; scale: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext("2d")!;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.drawImage(personSprite(lookFor(id, role), 0, "stand", 0), 0, 0, SPR_W, SPR_H - 1, 0, 0, cv.width, cv.height);
  }, [id, role, scale]);
  return <canvas ref={ref} width={SPR_W * scale} height={(SPR_H - 1) * scale} aria-hidden="true" />;
}
