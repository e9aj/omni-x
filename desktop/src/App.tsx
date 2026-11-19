import { FormEvent, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type BackendStatus = { connected: boolean; endpoint: string; version?: string; error?: string };
type ChatResult = { answer: string; session_id: string; mode: string; allow_paid: boolean };
type Message = { role: "user" | "assistant" | "error"; content: string };
const sections = ["Chat", "Agents", "Tasks", "Models", "Tools & Skills", "Memory", "Settings"];

export function App() {
  const [section, setSection] = useState("Chat");
  const [status, setStatus] = useState<BackendStatus>({ connected: false, endpoint: "loopback", error: "Checking backend" });
  const [prompt, setPrompt] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [running, setRunning] = useState(false);

  async function refreshStatus() {
    try { setStatus(await invoke<BackendStatus>("backend_status")); }
    catch (error) { setStatus({ connected: false, endpoint: "loopback", error: String(error) }); }
  }
  useEffect(() => { void refreshStatus(); const timer = window.setInterval(() => void refreshStatus(), 5000); return () => window.clearInterval(timer); }, []);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || running) return;
    setPrompt(""); setMessages((items) => [...items, { role: "user", content: text }]); setRunning(true);
    try {
      const result = await invoke<ChatResult>("backend_chat", { prompt: text, sessionId });
      setSessionId(result.session_id); setMessages((items) => [...items, { role: "assistant", content: result.answer }]);
    } catch (error) { setMessages((items) => [...items, { role: "error", content: String(error) }]); }
    finally { setRunning(false); void refreshStatus(); }
  }
  async function stop() { try { await invoke("backend_stop"); } catch (error) { setMessages((items) => [...items, { role: "error", content: String(error) }]); } }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">OX</span><span><strong>OMNI-X</strong><small>ONE AGENT. EVERY AI.</small></span></div>
      <nav>{sections.map((item) => <button className={section === item ? "nav-item active" : "nav-item"} onClick={() => setSection(item)} key={item}>{item}</button>)}</nav>
      <div className="sidebar-footer"><span className={status.connected ? "status-dot online" : "status-dot"} />{status.connected ? "Backend connected" : "Backend unavailable"}</div>
    </aside>
    <main className="workspace">
      <header><div><p className="eyebrow">WORKSPACE</p><h1>{section}</h1></div><div className="connection">{status.connected ? `OMNI-X ${status.version ?? "runtime"}` : status.error ?? "Offline"}</div></header>
      {section === "Chat" ? <section className="chat-panel"><div className="message-list">{messages.length === 0 && <div className="empty-chat"><p className="eyebrow">FREE MODE · SECURE LOCAL RUNTIME</p><h2>Ready when you are.</h2><p className="muted">Responses use the existing OMNI-X Python runtime, SQLite sessions, routing, tools and approval controls.</p></div>}{messages.map((message, index) => <article className={`message ${message.role}`} key={`${message.role}-${index}`}><span className="message-role">{message.role}</span><p>{message.content}</p></article>)}{running && <article className="message assistant"><span className="message-role">assistant</span><p>Working…</p></article>}</div><form className="composer" onSubmit={send}><input value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Ask OMNI-X anything…" disabled={!status.connected || running} /><button type={running ? "button" : "submit"} onClick={running ? stop : undefined}>{running ? "Stop" : "Send"}</button></form></section> : <section className="panel"><p className="eyebrow">PHASE 3 FOUNDATION</p><h2>{section}</h2><p className="muted">This workspace is connected to the unified OMNI-X backend. The section UI is being delivered incrementally without replacing the existing CLI runtime.</p></section>}
    </main>
  </div>;
}
