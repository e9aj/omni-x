import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./styles.css";

class WorkspaceBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean; generation: number }
> {
  state = { failed: false, generation: 0 };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <main className="recovery-screen" role="alert">
          <p className="eyebrow">OMNI-X</p>
          <h1>The workspace could not be displayed</h1>
          <p>Return to the workspace and try again. Unsaved changes may need to be re-entered.</p>
          <button onClick={() => this.setState((state) => ({ failed: false, generation: state.generation + 1 }))}>
            Return to workspace
          </button>
        </main>
      );
    }
    return <React.Fragment key={this.state.generation}>{this.props.children}</React.Fragment>;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><WorkspaceBoundary><App /></WorkspaceBoundary></React.StrictMode>,
);
