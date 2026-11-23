import { Component, lazy, Suspense, type ComponentType, type ReactNode } from "react";

/** What the side panel hands the Workspace session's component (web/src/workspace/index.tsx). */
export type WorkspaceProps = {
  /** Call with true when a task starts and false when it ends; the panel widens while it runs. */
  onTaskChange: (running: boolean) => void;
};

type WorkspaceModule = { default?: ComponentType<WorkspaceProps>; Workspace?: ComponentType<WorkspaceProps> };

// A glob, not an import: the floor still builds and runs before web/src/workspace/ exists.
const loaders = import.meta.glob<WorkspaceModule>("../workspace/index.tsx");
const load = loaders["../workspace/index.tsx"];
const Workspace = load
  ? lazy(() =>
      load().then((m) => {
        const C = m.default ?? m.Workspace;
        if (!C) throw new Error("web/src/workspace/index.tsx has no default or Workspace export.");
        return { default: C };
      }),
    )
  : null;

/** Keeps a crash inside the workspace from taking the lab floor down with it. */
class Guard extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: unknown) {
    return { error: String((e as Error)?.message ?? e) };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="side-body">
          <p className="empty">The workspace hit an error.</p>
          <p className="empty">{this.state.error}</p>
          <button className="btn" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function WorkspaceTab(props: WorkspaceProps) {
  if (!Workspace) {
    return (
      <div className="side-body">
        <p className="empty">The workspace is on its way.</p>
        <p className="empty">This tab mounts web/src/workspace/index.tsx as soon as it exists.</p>
      </div>
    );
  }
  return (
    <Guard>
      <Suspense fallback={<div className="side-body">Opening the workspace…</div>}>
        <Workspace {...props} />
      </Suspense>
    </Guard>
  );
}
