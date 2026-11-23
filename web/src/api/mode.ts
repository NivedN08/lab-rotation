// How the app runs, in one place. No imports, so anything can read it at any time.

/**
 * Static replay mode, for the hosted live link: the app reads a recorded session from JSON files instead of calling /api.
 * Turn it on with a build setting: `VITE_STATIC=1`.
 */
export const isStatic = (): boolean => import.meta.env.VITE_STATIC === "1";

/** True while running under the Vite dev server (`npm run dev`), where sample data is the default. */
export const isDevServer = (): boolean => import.meta.env.DEV === true;
