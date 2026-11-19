import { FormEvent, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type BackendStatus = { connected: boolean; endpoint: string; version?: string; error?: string };
type ChatResult = { answer: string; session_id: string; mode: string; allow_paid: boolean; provider?: string; model?: string; usage?: Array<{ provider: string; model: string; input_tokens: number; output_tokens: number }> };
type Message = { role: "user" | "assistant" | "error"; content: string };
type Approval = { id: string; action: string; expires_at: number };
const sections = ["Chat", "Agents", "Tasks", "Models", "Tools & Skills", "Memory", "Settings"];

export function App() {
  const [section, setSection] = useState("Chat");
  const [status, setStatus] = useState<BackendStatus>({ connected: false, endpoint: "loopback", error: "Checking backend" });
  const [prompt, setPrompt] = useState("");
  const [sessionId, setSessionId] = useState<string>(() => localStorage.getItem("omnix-session-id") ?? "");
  const [messages, setMessages] = useState<Message[]>([]);
  const [running, setRunning] = useState(false);
  const [usage, setUsage] = useState<string>();
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [contentPreference, setContentPreference] = useState("creative");
  const [model, setModel] = useState("auto/best-free");

  async function refreshStatus() {
    try { setStatus(await invoke<BackendStatus>("backend_status")); }
    catch (error) { setStatus({ connected: false, endpoint: "loopback", error: String(error) }); }
  }
  useEffect(() => { void refreshStatus(); const timer = window.setInterval(() => void refreshStatus(), 5000); return () => window.clearInterval(timer); }, []);
  useEffect(() => { if (!sessionId) return; void invoke<{ messages: Array<{ role: string; content: string }> }>("backend_session", { sessionId }).then((result) => setMessages(result.messages.filter((item): item is Message => ["user", "assistant", "error"].includes(item.role)) as Message[])).catch(() => undefined); }, []);
  useEffect(() => { async function refresh() { try { const result = await invoke<{ approvals: Approval[] }>("backend_approvals"); setApprovals(result.approvals); } catch { /* backend status displays the connection error */ } } void refresh(); const timer = window.setInterval(() => void refresh(), 1000); return () => window.clearInterval(timer); }, []);
  useEffect(() => { void invoke<{ content_preference: string; model: string }>("backend_settings").then((result) => { setContentPreference(result.content_preference); setModel(result.model); }).catch(() => undefined); }, []);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || running) return;
    setPrompt(""); setMessages((items) => [...items, { role: "user", content: text }]); setRunning(true);
    try {
      const result = await invoke<ChatResult>("backend_chat", { prompt: text, sessionId });
      setSessionId(result.session_id); localStorage.setItem("omnix-session-id", result.session_id); setModel(result.model ?? model); setUsage(result.usage?.map((item) => `${item.provider}/${item.model}: ${item.input_tokens + item.output_tokens} tokens`).join(" · ")); setMessages((items) => [...items, { role: "assistant", content: result.answer }]);
    } catch (error) { setMessages((items) => [...items, { role: "error", content: String(error) }]); }
    finally { setRunning(false); void refreshStatus(); }
  }
  async function stop() { try { await invoke("backend_stop"); } catch (error) { setMessages((items) => [...items, { role: "error", content: String(error) }]); } }
  async function decide(id: string, decision: "approve" | "reject") { try { await invoke("backend_approval_decide", { id, decision }); setApprovals((items) => items.filter((item) => item.id !== id)); } catch (error) { setMessages((items) => [...items, { role: "error", content: String(error) }]); } }
  async function changeContentPreference(value: string) { setContentPreference(value); try { await invoke("backend_set_content_preference", { preference: value }); } catch (error) { setMessages((items) => [...items, { role: "error", content: String(error) }]); } }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">OX</span><span><strong>OMNI-X</strong><small>ONE AGENT. EVERY AI.</small></span></div>
      <nav>{sections.map((item) => <button className={section === item ? "nav-item active" : "nav-item"} onClick={() => setSection(item)} key={item}>{item}</button>)}</nav>
      <div className="sidebar-footer"><span className={status.connected ? "status-dot online" : "status-dot"} />{status.connected ? "Backend connected" : "Backend unavailable"}</div>
    </aside>
    <main className="workspace">
      <header><div><p className="eyebrow">WORKSPACE</p><h1>{section}</h1></div><div className="connection">{status.connected ? `OMNI-X ${status.version ?? "runtime"}` : status.error ?? "Offline"}</div></header>
      {section === "Chat" ? <section className="chat-panel"><div className="message-list">{messages.length === 0 && <div className="empty-chat"><p className="eyebrow">FREE MODE · SECURE LOCAL RUNTIME</p><h2>Ready when you are.</h2><p className="muted">Responses use the existing OMNI-X Python runtime, SQLite sessions, routing, tools and approval controls.</p></div>}{messages.map((message, index) => <article className={`message ${message.role}`} key={`${message.role}-${index}`}><span className="message-role">{message.role}</span><p>{message.content}</p></article>)}{running && <article className="message assistant"><span className="message-role">assistant</span><p>Working…</p></article>}</div><form className="composer" onSubmit={send}><input value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Ask OMNI-X anything…" disabled={!status.connected || running} /><button type={running ? "button" : "submit"} onClick={running ? stop : undefined}>{running ? "Stop" : "Send"}</button></form>{usage && <p className="muted usage">{usage} · FREE mode · {model}</p>}</section> : section === "Tools & Skills" ? <section className="panel"><p className="eyebrow">BACKEND-ENFORCED APPROVALS</p><h2>Pending approvals</h2>{approvals.length === 0 ? <p className="muted">No pending requests.</p> : approvals.map((approval) => <article className="approval" key={approval.id}><p>{approval.action}</p><small>Expires {new Date(approval.expires_at * 1000).toLocaleTimeString()}</small><div><button onClick={() => void decide(approval.id, "approve")}>Approve</button><button onClick={() => void decide(approval.id, "reject")}>Reject</button></div></article>)}</section> : section === "Settings" ? <section className="panel"><p className="eyebrow">CONTENT PREFERENCES</p><h2>OMNI-X preferences</h2><label>Content style <select value={contentPreference} onChange={(event) => void changeContentPreference(event.target.value)}><option value="standard">Standard</option><option value="creative">Creative</option><option value="open">Open</option></select></label><p className="muted">Creative is the default. This affects OMNI-X prompting only and never changes terminal, browser, filesystem or provider permissions.</p><p className="muted">Provider: OmniRoute · Model: {model} · FREE mode</p></section> : <section className="panel"><p className="eyebrow">PHASE 3 FOUNDATION</p><h2>{section}</h2><p className="muted">This workspace is connected to the unified OMNI-X backend. The section UI is being delivered incrementally without replacing the existing CLI runtime.</p></section>}
    </main>
  </div>;
}
