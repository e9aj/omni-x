import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type BackendStatus = { connected: boolean; endpoint: string; version?: string; error?: string };
const sections = ["Chat", "Agents", "Tasks", "Models", "Tools & Skills", "Memory", "Settings"];

export function App() {
  const [section, setSection] = useState("Chat");
  const [status, setStatus] = useState<BackendStatus>({ connected: false, endpoint: "loopback", error: "Checking backend" });

  async function refreshStatus() {
    try { setStatus(await invoke<BackendStatus>("backend_status")); }
    catch (error) { setStatus({ connected: false, endpoint: "loopback", error: String(error) }); }
  }

  useEffect(() => { void refreshStatus(); const timer = window.setInterval(() => void refreshStatus(), 5000); return () => window.clearInterval(timer); }, []);

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">OX</span><span><strong>OMNI-X</strong><small>ONE AGENT. EVERY AI.</small></span></div>
      <nav>{sections.map((item) => <button className={section === item ? "nav-item active" : "nav-item"} onClick={() => setSection(item)} key={item}>{item}</button>)}</nav>
      <div className="sidebar-footer"><span className={status.connected ? "status-dot online" : "status-dot"} />{status.connected ? "Backend connected" : "Backend unavailable"}</div>
    </aside>
    <main className="workspace">
      <header><div><p className="eyebrow">WORKSPACE</p><h1>{section}</h1></div><div className="connection">{status.connected ? `OMNI-X ${status.version ?? "runtime"}` : status.error ?? "Offline"}</div></header>
      <section className="panel">
        {section === "Chat" ? <><p className="eyebrow">FREE MODE · SECURE LOCAL RUNTIME</p><h2>Ready when you are.</h2><p className="muted">The desktop foundation is connected to the existing OMNI-X Python runtime. Chat and approval workflows will use the same SQLite sessions, routing and permissions as the CLI.</p><div className="composer"><span>Ask OMNI-X anything…</span><button disabled>Send</button></div></> : <><p className="eyebrow">PHASE 3 FOUNDATION</p><h2>{section}</h2><p className="muted">This workspace is connected to the unified OMNI-X backend. The section UI is being delivered incrementally without replacing the existing CLI runtime.</p></>}
      </section>
    </main>
  </div>;
}
