import { useSyncExternalStore } from "react";

const KEY = "lab-rotation.muted";
let muted = (() => {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
})();
const subs = new Set<() => void>();

export const voiceMute = {
  get: () => muted,
  set(next: boolean) {
    muted = next;
    try {
      localStorage.setItem(KEY, next ? "1" : "0");
    } catch {
      /* keep it in memory */
    }
    subs.forEach((f) => f());
  },
};

export const useMuted = (): boolean =>
  useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => muted,
  );
