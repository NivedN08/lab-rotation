import { useCallback, useSyncExternalStore } from "react";
import { getRotation, subscribeEvents, subscribeJump, type RotationState } from "../api/client";

// The shared rotation state starts a session on its first reader. The app shell must not be that
// reader while the opening screen is up, or every page load would start a session before the
// visitor picks rotation, judge mode or the demo. So it reads the state only once `on` is true.

const IDLE: RotationState = getRotation();

export function useLateRotation(on: boolean): RotationState {
  const subscribe = useCallback(
    (changed: () => void) => {
      if (!on) return () => {};
      const offEvents = subscribeEvents(changed); // also starts the session (or follows the demo)
      const offJump = subscribeJump(changed);
      // The task, its clock and the results can change between events: look again every second.
      const timer = window.setInterval(changed, 1000);
      return () => {
        offEvents();
        offJump();
        clearInterval(timer);
      };
    },
    [on],
  );
  return useSyncExternalStore(subscribe, () => (on ? getRotation() : IDLE));
}
