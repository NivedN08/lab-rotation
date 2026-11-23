import { Component, type ReactNode } from "react";

/** Keeps one panel's error from taking the floor down: the panel just steps aside. */
export class Safe extends Component<{ children: ReactNode; name: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    console.error(`${this.props.name} hit an error and was hidden:`, error);
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}
