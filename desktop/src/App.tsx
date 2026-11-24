import { FormEvent, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type BackendStatus = {
  connected: boolean;
  endpoint: string;
  version?: string;
  error?: string;
};
type ChatResult = {
  answer: string;
  session_id: string;
  mode: string;
  allow_paid: boolean;
  provider?: string;
  model?: string;
  usage?: Array<{
    provider: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
  }>;
};
type Message = { role: "user" | "assistant" | "error"; content: string };
type Approval = { id: string; action: string; expires_at: number };
type CouncilResult = {
  answer: string;
  session_id: string;
  mode: string;
  candidates: Array<{
    provider: string;
    model: string;
    score: number;
    latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    error?: string | null;
  }>;
};
type ModelInfo = {
  id: string;
  owned_by: string;
  free: boolean;
  context_length?: number;
  capabilities: Record<string, boolean>;
};
type BrainNote = { path: string; size: number; updated: number };
type TaskItem = {
  id: string;
  prompt: string;
  state: string;
  result?: string | null;
  error?: string | null;
  parent_job_id?: string | null;
  created: number;
  updated: number;
};
type SkillItem = {
  name: string;
  path: string;
  source: string;
  description: string;
  permissions: string[];
  credentials: string[];
  dependencies: string[];
  enabled: boolean;
  installed: boolean;
};
type IntegrationItem = {
  name: string;
  kind: string;
  interface: string;
  credentials: string[];
  permissions: string[];
  dependencies: string[];
  endpoints: string[];
  installed: boolean;
  enabled: boolean;
  revoked: boolean;
  configured: boolean;
  version: string;
  health: { healthy: boolean; status?: string; error?: string };
};
type BrainGraph = {
  nodes: Array<{ path: string }>;
  edges: Array<{ source: string; target: string }>;
};
type BrainCanvas = {
  nodes: Array<{ id: string; path: string; x: number; y: number }>;
  edges: Array<{ source: string; target: string }>;
  viewport: { x: number; y: number; zoom: number };
};
type MemorySuggestion = {
  id: string;
  memory_key: string;
  memory_value: string;
  source: string;
  state: string;
};
type VoiceCapabilities = {
  local_stt: boolean;
  local_tts: boolean;
  audio_devices: boolean;
  wake_word: boolean;
  remote_upload: boolean;
};
type WorkflowNode = {
  id: string;
  action: string;
  x: number;
  y: number;
  depends_on: string[];
};
type WorkflowItem = {
  id: string;
  name: string;
  definition: { nodes: WorkflowNode[] };
};
const sections = [
  "Chat",
  "Council",
  "Agents",
  "Tasks",
  "Models",
  "Tools & Skills",
  "Integrations",
  "Voice",
  "Workflows",
  "Memory",
  "Settings",
];

export function App() {
  const [section, setSection] = useState("Chat");
  const [status, setStatus] = useState<BackendStatus>({
    connected: false,
    endpoint: "loopback",
    error: "Checking backend",
  });
  const [prompt, setPrompt] = useState("");
  const [sessionId, setSessionId] = useState<string>(
    () => localStorage.getItem("omnix-session-id") ?? "",
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [running, setRunning] = useState(false);
  const [usage, setUsage] = useState<string>();
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [contentPreference, setContentPreference] = useState("creative");
  const [model, setModel] = useState("auto/best-free");
  const [councilMode, setCouncilMode] = useState("standard");
  const [councilModels, setCouncilModels] = useState("");
  const [councilPrompt, setCouncilPrompt] = useState("");
  const [councilResult, setCouncilResult] = useState<CouncilResult>();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string>();
  const [notes, setNotes] = useState<BrainNote[]>([]);
  const [selectedNote, setSelectedNote] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [newNotePath, setNewNotePath] = useState("note.md");
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [taskPrompt, setTaskPrompt] = useState("");
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationItem[]>([]);
  const [brainGraph, setBrainGraph] = useState<BrainGraph>({
    nodes: [],
    edges: [],
  });
  const [brainQuery, setBrainQuery] = useState("");
  const [brainResults, setBrainResults] = useState<
    Array<{ path: string; snippet: string }>
  >([]);
  const [brainCanvas, setBrainCanvas] = useState<BrainCanvas>({
    nodes: [],
    edges: [],
    viewport: { x: 0, y: 0, zoom: 1 },
  });
  const [memorySuggestions, setMemorySuggestions] = useState<MemorySuggestion[]>([]);
  const [canvasSelected, setCanvasSelected] = useState<string>();
  const [canvasZoom, setCanvasZoom] = useState(1);
  const [canvasPan, setCanvasPan] = useState({ x: 0, y: 0 });
  const [documentPath, setDocumentPath] = useState("");
  const [documentResult, setDocumentResult] = useState<string>();
  const [ocrEnabled, setOcrEnabled] = useState(false);
  const [voiceCapabilities, setVoiceCapabilities] =
    useState<VoiceCapabilities>();
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [workflowName, setWorkflowName] = useState("My workflow");
  const [workflowNodes, setWorkflowNodes] = useState<WorkflowNode[]>([
    { id: "step-1", action: "agent", x: 40, y: 40, depends_on: [] },
  ]);

  async function refreshStatus() {
    try {
      setStatus(await invoke<BackendStatus>("backend_status"));
    } catch (error) {
      setStatus({
        connected: false,
        endpoint: "loopback",
        error: String(error),
      });
    }
  }
  useEffect(() => {
    void refreshStatus();
    const timer = window.setInterval(() => void refreshStatus(), 5000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!sessionId) return;
    void invoke<{ messages: Array<{ role: string; content: string }> }>(
      "backend_session",
      { sessionId },
    )
      .then((result) =>
        setMessages(
          result.messages.filter((item): item is Message =>
            ["user", "assistant", "error"].includes(item.role),
          ) as Message[],
        ),
      )
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    async function refresh() {
      try {
        const result = await invoke<{ approvals: Approval[] }>(
          "backend_approvals",
        );
        setApprovals(result.approvals);
      } catch {
        /* backend status displays the connection error */
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    void invoke<{ content_preference: string; model: string }>(
      "backend_settings",
    )
      .then((result) => {
        setContentPreference(result.content_preference);
        setModel(result.model);
      })
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    if (section !== "Models") return;
    void invoke<{ models: ModelInfo[]; error?: string }>("backend_models")
      .then((result) => {
        setModels(result.models);
        setModelsError(result.error);
      })
      .catch((error) => setModelsError(String(error)));
  }, [section]);
  useEffect(() => {
    if (section !== "Memory") return;
    void Promise.all([
      invoke<{ notes: BrainNote[] }>("backend_brain_notes"),
      invoke<BrainGraph>("backend_brain_graph"),
      invoke<BrainCanvas>("backend_brain_canvas"),
      invoke<{ suggestions: MemorySuggestion[] }>("backend_memory_suggestions"),
    ])
      .then(([noteResult, graphResult, canvas, suggestions]) => {
        setNotes(noteResult.notes);
        setBrainGraph(graphResult);
        setBrainCanvas(canvas);
        setMemorySuggestions(suggestions.suggestions.filter((item) => item.state === "pending"));
      })
      .catch((error) => setModelsError(String(error)));
  }, [section]);
  useEffect(() => {
    if (section !== "Tasks" && section !== "Agents") return;
    void invoke<{ tasks: TaskItem[] }>("backend_tasks")
      .then((result) => setTasks(result.tasks))
      .catch((error) => setModelsError(String(error)));
  }, [section]);
  useEffect(() => {
    if (section !== "Tools & Skills") return;
    void invoke<{ skills: SkillItem[] }>("backend_skills")
      .then((result) => setSkills(result.skills))
      .catch((error) => setModelsError(String(error)));
  }, [section]);
  useEffect(() => {
    if (section !== "Integrations") return;
    void invoke<{ integrations: IntegrationItem[] }>("backend_integrations")
      .then((result) => setIntegrations(result.integrations))
      .catch((error) => setModelsError(String(error)));
  }, [section]);
  useEffect(() => {
    if (section !== "Voice") return;
    void invoke<{ capabilities: VoiceCapabilities }>(
      "backend_voice_capabilities",
    )
      .then((result) => setVoiceCapabilities(result.capabilities))
      .catch((error) => setModelsError(String(error)));
  }, [section]);
  useEffect(() => {
    if (section !== "Workflows") return;
    void invoke<{ workflows: WorkflowItem[] }>("backend_workflows")
      .then((result) => setWorkflows(result.workflows))
      .catch((error) => setModelsError(String(error)));
  }, [section]);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || running) return;
    setPrompt("");
    setMessages((items) => [...items, { role: "user", content: text }]);
    setRunning(true);
    try {
      const result = await invoke<ChatResult>("backend_chat", {
        prompt: text,
        sessionId,
      });
      setSessionId(result.session_id);
      localStorage.setItem("omnix-session-id", result.session_id);
      setModel(result.model ?? model);
      setUsage(
        result.usage
          ?.map(
            (item) =>
              `${item.provider}/${item.model}: ${item.input_tokens + item.output_tokens} tokens`,
          )
          .join(" · "),
      );
      setMessages((items) => [
        ...items,
        { role: "assistant", content: result.answer },
      ]);
    } catch (error) {
      setMessages((items) => [
        ...items,
        { role: "error", content: String(error) },
      ]);
    } finally {
      setRunning(false);
      void refreshStatus();
    }
  }
  async function stop() {
    try {
      await invoke("backend_stop");
    } catch (error) {
      setMessages((items) => [
        ...items,
        { role: "error", content: String(error) },
      ]);
    }
  }
  async function decide(id: string, decision: "approve" | "reject") {
    try {
      await invoke("backend_approval_decide", { id, decision });
      setApprovals((items) => items.filter((item) => item.id !== id));
    } catch (error) {
      setMessages((items) => [
        ...items,
        { role: "error", content: String(error) },
      ]);
    }
  }
  async function changeContentPreference(value: string) {
    setContentPreference(value);
    try {
      await invoke("backend_set_content_preference", { preference: value });
    } catch (error) {
      setMessages((items) => [
        ...items,
        { role: "error", content: String(error) },
      ]);
    }
  }
  async function runCouncil(event: FormEvent) {
    event.preventDefault();
    const text = councilPrompt.trim();
    if (!text || running) return;
    setRunning(true);
    setCouncilResult(undefined);
    try {
      const result = await invoke<CouncilResult>("backend_council", {
        prompt: text,
        mode: councilMode,
        models: councilModels
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean)
          .slice(0, 5),
        sessionId,
      });
      setCouncilResult(result);
      setSessionId(result.session_id);
      localStorage.setItem("omnix-session-id", result.session_id);
    } catch (error) {
      setMessages((items) => [
        ...items,
        { role: "error", content: String(error) },
      ]);
    } finally {
      setRunning(false);
    }
  }
  async function openNote(path: string) {
    try {
      const result = await invoke<{ content: string }>("backend_brain_note", {
        path,
      });
      setSelectedNote(path);
      setNoteContent(result.content);
    } catch (error) {
      setModelsError(String(error));
    }
  }
  async function saveNote() {
    if (!selectedNote) return;
    try {
      await invoke("backend_brain_save", {
        path: selectedNote,
        content: noteContent,
      });
    } catch (error) {
      setModelsError(String(error));
    }
  }
  async function createNote() {
    const path = newNotePath.trim();
    if (!path) return;
    try {
      await invoke("backend_brain_save", { path, content: "# New note\n" });
      setSelectedNote(path);
      setNoteContent("# New note\n");
      setNotes((items) => [
        ...items.filter((item) => item.path !== path),
        { path, size: 12, updated: Date.now() / 1000 },
      ]);
    } catch (error) {
      setModelsError(String(error));
    }
  }
  async function saveCanvas() {
    try {
      await invoke("backend_brain_save_canvas", { canvas: brainCanvas });
    } catch (error) {
      setModelsError(String(error));
    }
  }
  async function decideMemory(id: string, state: "approved" | "rejected" | "deleted", key?: string, value?: string) {
    try {
      await invoke("backend_memory_decide", { id, state, key: key ?? null, value: value ?? null });
      setMemorySuggestions((items) => items.filter((item) => item.id !== id));
    } catch (error) {
      setModelsError(String(error));
    }
  }
  function connectCanvasNode(path: string) {
    if (!canvasSelected) {
      setCanvasSelected(path);
      return;
    }
    if (canvasSelected !== path) {
      setBrainCanvas((canvas) => ({
        ...canvas,
        edges: [...canvas.edges.filter((edge) => !(edge.source === canvasSelected && edge.target === path)), { source: canvasSelected, target: path }],
      }));
    }
    setCanvasSelected(undefined);
  }
  function moveCanvas(dx: number, dy: number) { setCanvasPan((value) => ({ x: value.x + dx, y: value.y + dy })); }
  async function inspectDocument() {
    if (!documentPath.trim()) return;
    try {
      const result = await invoke<{ text: string }>("backend_brain_document", { path: documentPath.trim(), allowOcr: ocrEnabled });
      setDocumentResult(result.text.slice(0, 4000));
    } catch (error) { setModelsError(String(error)); }
  }
  function addCanvasNote(path: string) {
    setBrainCanvas((canvas) => ({
      ...canvas,
      nodes: [
        ...canvas.nodes.filter((item) => item.path !== path),
        {
          id: `canvas-${Date.now()}`,
          path,
          x: 30 + (canvas.nodes.length % 4) * 180,
          y: 30 + Math.floor(canvas.nodes.length / 4) * 100,
        },
      ],
    }));
  }
  async function enqueueTask(event: FormEvent) {
    event.preventDefault();
    const promptText = taskPrompt.trim();
    if (!promptText) return;
    try {
      await invoke("backend_task_action", {
        action: "enqueue",
        prompt: promptText,
        taskId: null,
        schedule: null,
      });
      setTaskPrompt("");
      const result = await invoke<{ tasks: TaskItem[] }>("backend_tasks");
      setTasks(result.tasks);
    } catch (error) {
      setModelsError(String(error));
    }
  }
  async function cancelTask(id: string) {
    try {
      await invoke("backend_task_action", {
        action: "cancel",
        taskId: id,
        prompt: null,
        schedule: null,
      });
      setTasks((items) =>
        items.map((item) =>
          item.id === id ? { ...item, state: "cancelled" } : item,
        ),
      );
    } catch (error) {
      setModelsError(String(error));
    }
  }
  async function setSkill(name: string, action: "enable" | "disable") {
    try {
      const result = await invoke<{ skill: SkillItem }>(
        "backend_skill_action",
        { name, action },
      );
      setSkills((items) =>
        items.map((item) => (item.name === name ? result.skill : item)),
      );
    } catch (error) {
      setModelsError(String(error));
    }
  }
  async function setIntegration(
    name: string,
    action: "install" | "enable" | "disable" | "revoke",
  ) {
    try {
      const result = await invoke<{ integration: IntegrationItem }>(
        "backend_integration_action",
        { name, action },
      );
      setIntegrations((items) =>
        items.map((item) => (item.name === name ? result.integration : item)),
      );
    } catch (error) {
      setModelsError(String(error));
    }
  }
  async function searchBrain(event: FormEvent) {
    event.preventDefault();
    if (!brainQuery.trim()) return;
    try {
      const result = await invoke<{
        results: Array<{ path: string; snippet: string }>;
      }>("backend_brain_semantic_search", { query: brainQuery });
      setBrainResults(result.results);
    } catch (error) {
      setModelsError(String(error));
    }
  }
  async function saveWorkflow() {
    try {
      const result = await invoke<{ workflow_id: string }>(
        "backend_workflow_save",
        { name: workflowName, definition: { nodes: workflowNodes }, id: null },
      );
      setWorkflows((items) => [
        {
          id: result.workflow_id,
          name: workflowName,
          definition: { nodes: workflowNodes },
        },
        ...items.filter((item) => item.id !== result.workflow_id),
      ]);
    } catch (error) {
      setModelsError(String(error));
    }
  }
  function addWorkflowNode() {
    setWorkflowNodes((items) => [
      ...items,
      {
        id: `step-${items.length + 1}`,
        action: "agent",
        x: 40 + (items.length % 3) * 180,
        y: 40 + Math.floor(items.length / 3) * 110,
        depends_on: items.length ? [items[items.length - 1].id] : [],
      },
    ]);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">OX</span>
          <span>
            <strong>OMNI-X</strong>
            <small>ONE AGENT. EVERY AI.</small>
          </span>
        </div>
        <nav>
          {sections.map((item) => (
            <button
              className={section === item ? "nav-item active" : "nav-item"}
              onClick={() => setSection(item)}
              key={item}
            >
              {item}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span
            className={status.connected ? "status-dot online" : "status-dot"}
          />
          {status.connected ? "Backend connected" : "Backend unavailable"}
        </div>
      </aside>
      <main className="workspace">
        <header>
          <div>
            <p className="eyebrow">WORKSPACE</p>
            <h1>{section}</h1>
          </div>
          <div className="connection">
            {status.connected
              ? `OMNI-X ${status.version ?? "runtime"}`
              : (status.error ?? "Offline")}
          </div>
        </header>
        {section === "Chat" ? (
          <section className="chat-panel">
            <div className="message-list">
              {messages.length === 0 && (
                <div className="empty-chat">
                  <p className="eyebrow">FREE MODE · SECURE LOCAL RUNTIME</p>
                  <h2>Ready when you are.</h2>
                  <p className="muted">
                    Responses use the existing OMNI-X Python runtime, SQLite
                    sessions, routing, tools and approval controls.
                  </p>
                </div>
              )}
              {messages.map((message, index) => (
                <article
                  className={`message ${message.role}`}
                  key={`${message.role}-${index}`}
                >
                  <span className="message-role">{message.role}</span>
                  <p>{message.content}</p>
                </article>
              ))}
              {running && (
                <article className="message assistant">
                  <span className="message-role">assistant</span>
                  <p>Working…</p>
                </article>
              )}
            </div>
            <form className="composer" onSubmit={send}>
              <input
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="Ask OMNI-X anything…"
                disabled={!status.connected || running}
              />
              <button
                type={running ? "button" : "submit"}
                onClick={running ? stop : undefined}
              >
                {running ? "Stop" : "Send"}
              </button>
            </form>
            {usage && (
              <p className="muted usage">
                {usage} · FREE mode · {model}
              </p>
            )}
          </section>
        ) : section === "Council" ? (
          <section className="panel">
            <p className="eyebrow">FREE-FIRST · BOUNDED INFERENCE</p>
            <h2>Ask the Council</h2>
            <p className="muted">
              Standard uses one model by default. Council uses three, Advanced
              five, and Research requires an explicit model group. The backend
              keeps provider credentials, FREE mode and spending policy
              authoritative.
            </p>
            <form className="council-form" onSubmit={runCouncil}>
              <label>
                Mode{" "}
                <select
                  value={councilMode}
                  onChange={(event) => setCouncilMode(event.target.value)}
                >
                  <option value="standard">Standard · 1 model</option>
                  <option value="council">Council · 3 models</option>
                  <option value="advanced">Advanced · 5 models</option>
                  <option value="research">Research · configured group</option>
                </select>
              </label>
              <label>
                Model group{" "}
                <input
                  value={councilModels}
                  onChange={(event) => setCouncilModels(event.target.value)}
                  placeholder="Optional comma-separated model IDs"
                />
              </label>
              <textarea
                value={councilPrompt}
                onChange={(event) => setCouncilPrompt(event.target.value)}
                placeholder="What should the Council compare?"
                rows={5}
              />
              <button
                type="submit"
                disabled={!status.connected || running || !councilPrompt.trim()}
              >
                {running ? "Working…" : "Run Council"}
              </button>
            </form>
            {councilResult && (
              <div className="council-result">
                <h3>{councilResult.answer}</h3>
                {councilResult.candidates.map((candidate) => (
                  <article
                    className="candidate"
                    key={`${candidate.provider}/${candidate.model}`}
                  >
                    <strong>
                      {candidate.provider}/{candidate.model}
                    </strong>
                    <span>
                      score {candidate.score.toFixed(1)} ·{" "}
                      {Math.round(candidate.latency_ms)}ms ·{" "}
                      {candidate.input_tokens + candidate.output_tokens} tokens
                    </span>
                    {candidate.error && <small>{candidate.error}</small>}
                  </article>
                ))}
              </div>
            )}
          </section>
        ) : section === "Models" ? (
          <section className="panel">
            <p className="eyebrow">OMNIROUTE · FREE MODE</p>
            <h2>Available models</h2>
            <p className="muted">
              Discovery reports what the configured gateway currently exposes. A
              model is selectable only when the backend verifies it as free.
            </p>
            {modelsError && (
              <p className="muted">Discovery error: {modelsError}</p>
            )}
            {models.length === 0 && !modelsError && (
              <p className="muted">
                No catalogue loaded yet. Refresh this section to query
                OmniRoute.
              </p>
            )}
            {models.map((item) => (
              <article className="candidate" key={item.id}>
                <strong>{item.id}</strong>
                <span>
                  {item.owned_by} · {item.free ? "FREE" : "paid/unverified"} ·
                  context {item.context_length ?? "unknown"}
                </span>
                {item.free && (
                  <button
                    onClick={() =>
                      void invoke("backend_set_model", { model: item.id })
                        .then(() => setModel(item.id))
                        .catch((error) => setModelsError(String(error)))
                    }
                  >
                    {model === item.id ? "Selected" : "Select"}
                  </button>
                )}
              </article>
            ))}
          </section>
        ) : section === "Voice" ? (
          <section className="panel">
            <p className="eyebrow">LOCAL-FIRST VOICE</p>
            <h2>Voice</h2>
            <p className="muted">
              OMNI-X only uses locally installed engines after explicit
              microphone or audio-output permission. No remote audio upload is
              enabled.
            </p>
            {voiceCapabilities ? (
              <div className="note-list">
                {Object.entries(voiceCapabilities).map(([name, available]) => (
                  <article className="candidate" key={name}>
                    <strong>{name.replaceAll("_", " ")}</strong>
                    <span>{available ? "available" : "unavailable"}</span>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">Checking local capabilities…</p>
            )}
            <p className="muted">
              Push-to-talk, wake-word support and live dictation remain
              unavailable until a reviewed local engine and audio device are
              present.
            </p>
          </section>
        ) : section === "Workflows" ? (
          <section className="panel">
            <p className="eyebrow">TASKSERVICE · PERSISTENT DEFINITION</p>
            <h2>Workflow builder</h2>
            <p className="muted">
              Drag-ready workflow nodes are stored in SQLite. Execution remains
              behind TaskService policy and is not claimed live here.
            </p>
            <label>
              Workflow name{" "}
              <input
                value={workflowName}
                onChange={(event) => setWorkflowName(event.target.value)}
              />
            </label>
            <div className="workflow-canvas">
              {workflowNodes.map((node) => (
                <article
                  className="candidate workflow-node"
                  draggable
                  key={node.id}
                  style={{ left: node.x, top: node.y }}
                  onDragEnd={(event) => {
                    const rect =
                      event.currentTarget.parentElement?.getBoundingClientRect();
                    if (rect)
                      setWorkflowNodes((items) =>
                        items.map((item) =>
                          item.id === node.id
                            ? {
                                ...item,
                                x: Math.max(0, event.clientX - rect.left - 60),
                                y: Math.max(0, event.clientY - rect.top - 30),
                              }
                            : item,
                        ),
                      );
                  }}
                >
                  <strong>{node.id}</strong>
                  <select
                    value={node.action}
                    onChange={(event) =>
                      setWorkflowNodes((items) =>
                        items.map((item) =>
                          item.id === node.id
                            ? { ...item, action: event.target.value }
                            : item,
                        ),
                      )
                    }
                  >
                    <option value="agent">Agent</option>
                    <option value="integration">Integration</option>
                    <option value="approval">Approval</option>
                  </select>
                </article>
              ))}
            </div>
            <button onClick={addWorkflowNode}>Add step</button>
            <button onClick={() => void saveWorkflow()}>Save workflow</button>
            <h3>Saved workflows</h3>
            {workflows.map((workflow) => (
              <article className="candidate" key={workflow.id}>
                <strong>{workflow.name}</strong>
                <span>{workflow.definition.nodes.length} steps</span>
              </article>
            ))}
          </section>
        ) : section === "Memory" ? (
          <section className="panel">
            <p className="eyebrow">LOCAL-FIRST MARKDOWN VAULT</p>
            <h2>Brain notes</h2>
            <form className="council-form" onSubmit={searchBrain}>
              <input
                value={brainQuery}
                onChange={(event) => setBrainQuery(event.target.value)}
                placeholder="Search the Brain vault"
              />
              <button type="submit">Search</button>
            </form>
            {brainResults.map((result) => (
              <article className="candidate" key={result.path}>
                <strong>{result.path}</strong>
                <small>{result.snippet}</small>
              </article>
            ))}
            <p className="muted">
              Knowledge graph: {brainGraph.nodes.length} notes ·{" "}
              {brainGraph.edges.length} links. Local semantic search is active;
              neural embeddings and OCR are optional local engines.
            </p>
            <h3>Memory suggestions</h3>
            {memorySuggestions.length === 0 ? (
              <p className="muted">No pending suggestions. Suggestions always require approval.</p>
            ) : memorySuggestions.map((suggestion) => (
              <article className="candidate" key={suggestion.id}>
                <strong>{suggestion.memory_key}</strong>
                <input defaultValue={suggestion.memory_value} aria-label={`Edit ${suggestion.memory_key}`} onBlur={(event) => void decideMemory(suggestion.id, "approved", suggestion.memory_key, event.target.value)} />
                <div><button onClick={() => void decideMemory(suggestion.id, "approved")}>Approve</button><button onClick={() => void decideMemory(suggestion.id, "rejected")}>Reject</button><button onClick={() => void decideMemory(suggestion.id, "deleted")}>Delete</button></div>
              </article>
            ))}
            <label>
              New note path{" "}
              <input
                value={newNotePath}
                onChange={(event) => setNewNotePath(event.target.value)}
              />
            </label>
            <button onClick={() => void createNote()}>Create note</button>
            <div className="note-list">
              {notes.length === 0 ? (
                <p className="muted">
                  No Markdown notes yet. Create one in the Brain vault to begin.
                </p>
              ) : (
                notes.map((note) => (
                  <span key={note.path}><button className="note-link" onClick={() => void openNote(note.path)}>{note.path}</button><button onClick={() => addCanvasNote(note.path)}>Add to canvas</button></span>
                ))
              )}
            </div>
            <h3>Infinite canvas</h3>
            <div className="workflow-canvas" style={{ transform: `translate(${canvasPan.x}px, ${canvasPan.y}px) scale(${canvasZoom})`, transformOrigin: "top left" }}>
              <svg className="canvas-links" aria-hidden="true">{brainCanvas.edges.map((edge) => { const source = brainCanvas.nodes.find((node) => node.path === edge.source); const target = brainCanvas.nodes.find((node) => node.path === edge.target); return source && target ? <line key={`${edge.source}-${edge.target}`} x1={source.x + 60} y1={source.y + 30} x2={target.x + 60} y2={target.y + 30} /> : null; })}</svg>
              {brainCanvas.nodes.map((node) => <article className={`candidate workflow-node${canvasSelected === node.path ? " active" : ""}`} draggable key={node.id} style={{ left: node.x, top: node.y }} onClick={() => connectCanvasNode(node.path)} onDragEnd={(event) => { const rect = event.currentTarget.parentElement?.getBoundingClientRect(); if (rect) setBrainCanvas((canvas) => ({ ...canvas, nodes: canvas.nodes.map((item) => item.id === node.id ? { ...item, x: Math.max(0, (event.clientX - rect.left - canvasPan.x) / canvasZoom - 60), y: Math.max(0, (event.clientY - rect.top - canvasPan.y) / canvasZoom - 30) } : item) })); }}><strong>{node.path}</strong></article>)}
            </div>
            <p className="muted">Click two notes to connect them. Drag cards to reposition. Use pan controls to navigate the canvas.</p>
            <button onClick={() => setCanvasZoom((value) => Math.min(2, value + 0.1))}>Zoom in</button><button onClick={() => setCanvasZoom((value) => Math.max(0.5, value - 0.1))}>Zoom out</button><button onClick={() => moveCanvas(-80, 0)}>Pan left</button><button onClick={() => moveCanvas(80, 0)}>Pan right</button><button onClick={() => moveCanvas(0, -80)}>Pan up</button><button onClick={() => moveCanvas(0, 80)}>Pan down</button><button onClick={() => void saveCanvas()}>Save layout</button>
            <h3>Document import and OCR</h3><p className="muted">Documents are read locally from the backend workspace. OCR is opt-in and requires reviewed local OCR engines.</p><input value={documentPath} onChange={(event) => setDocumentPath(event.target.value)} placeholder="relative/path/to/document.pdf" /><label><input type="checkbox" checked={ocrEnabled} onChange={(event) => setOcrEnabled(event.target.checked)} /> Enable local OCR</label><button onClick={() => void inspectDocument()}>Inspect document</button>{documentResult && <pre className="document-preview">{documentResult}</pre>}
            {selectedNote && (
              <>
                <input value={selectedNote} readOnly />
                <textarea
                  value={noteContent}
                  onChange={(event) => setNoteContent(event.target.value)}
                  rows={14}
                />
                <button onClick={() => void saveNote()}>Save note</button>
              </>
            )}
          </section>
        ) : section === "Tasks" || section === "Agents" ? (
          <section className="panel">
            <p className="eyebrow">TASKSERVICE · DURABLE SQLITE QUEUE</p>
            <h2>{section}</h2>
            <p className="muted">
              {section === "Agents"
                ? "Agent activity is shown from the unified TaskService queue. Hermes remains opt-in and inherits the stored policy."
                : "Queue and cancel background work without creating a second scheduler."}
            </p>
            {section === "Tasks" && (
              <form className="council-form" onSubmit={enqueueTask}>
                <input
                  value={taskPrompt}
                  onChange={(event) => setTaskPrompt(event.target.value)}
                  placeholder="Describe a background task"
                />
                <button
                  type="submit"
                  disabled={!status.connected || !taskPrompt.trim()}
                >
                  Queue task
                </button>
              </form>
            )}
            <div className="note-list">
              {tasks.length === 0 ? (
                <p className="muted">No tasks have been queued.</p>
              ) : (
                tasks.map((task) => (
                  <article className="candidate" key={task.id}>
                    <strong>{task.state}</strong>
                    <span>{task.prompt}</span>
                    {task.state === "queued" || task.state === "running" ? (
                      <button onClick={() => void cancelTask(task.id)}>
                        Cancel
                      </button>
                    ) : (
                      <small>{task.result || task.error || "completed"}</small>
                    )}
                  </article>
                ))
              )}
            </div>
          </section>
        ) : section === "Tools & Skills" ? (
          <section className="panel">
            <p className="eyebrow">
              BACKEND-ENFORCED APPROVALS · REVIEWED SKILLS
            </p>
            <h2>Tools & Skills</h2>
            <h3>Pending approvals</h3>
            {approvals.length === 0 ? (
              <p className="muted">No pending requests.</p>
            ) : (
              approvals.map((approval) => (
                <article className="approval" key={approval.id}>
                  <p>{approval.action}</p>
                  <small>
                    Expires{" "}
                    {new Date(approval.expires_at * 1000).toLocaleTimeString()}
                  </small>
                  <div>
                    <button onClick={() => void decide(approval.id, "approve")}>
                      Approve
                    </button>
                    <button onClick={() => void decide(approval.id, "reject")}>
                      Reject
                    </button>
                  </div>
                </article>
              ))
            )}
            <h3>Skills catalogue</h3>
            <p className="muted">
              Skills are disabled by default. Installation remains an explicit
              reviewed backend operation; this screen only changes enablement.
            </p>
            {skills.length === 0 ? (
              <p className="muted">
                No reviewed skills are installed or discoverable.
              </p>
            ) : (
              skills.map((skill) => (
                <article className="candidate" key={skill.name}>
                  <strong>{skill.name}</strong>
                  <span>
                    {skill.source} ·{" "}
                    {skill.installed ? "installed" : "discovered"} ·{" "}
                    {skill.permissions.length
                      ? `permissions: ${skill.permissions.join(", ")}`
                      : "no declared permissions"}
                  </span>
                  <small>{skill.description || "No description"}</small>
                  <button
                    onClick={() =>
                      void setSkill(
                        skill.name,
                        skill.enabled ? "disable" : "enable",
                      )
                    }
                  >
                    {skill.enabled ? "Disable" : "Enable"}
                  </button>
                </article>
              ))
            )}
          </section>
        ) : section === "Integrations" ? (
          <section className="panel">
            <p className="eyebrow">
              DISABLED BY DEFAULT · EXPLICIT AUTHORISATION
            </p>
            <h2>Integrations</h2>
            <p className="muted">
              The catalogue is metadata-only until you explicitly install and
              enable an integration. OMNI-X never connects to external services
              or exposes credentials from this screen.
            </p>
            {integrations.length === 0 ? (
              <p className="muted">No catalogue entries available.</p>
            ) : (
              integrations.map((item) => (
                <article className="candidate" key={item.name}>
                  <strong>{item.name}</strong>
                  <span>
                    {item.kind} · {item.interface} ·{" "}
                    {item.health.status ||
                      (item.health.healthy ? "healthy" : "unhealthy")}
                  </span>
                  <small>
                    {item.credentials.length
                      ? `Credentials: ${item.credentials.join(", ")}`
                      : "No credentials declared"}{" "}
                    ·{" "}
                    {item.permissions.length
                      ? `Permissions: ${item.permissions.join(", ")}`
                      : "No permissions declared"}
                  </small>
                  <div>
                    {!item.installed && (
                      <button
                        onClick={() =>
                          void setIntegration(item.name, "install")
                        }
                      >
                        Record install
                      </button>
                    )}
                    {item.installed && !item.enabled && !item.revoked && (
                      <button
                        onClick={() => void setIntegration(item.name, "enable")}
                      >
                        Enable
                      </button>
                    )}
                    {item.enabled && (
                      <button
                        onClick={() =>
                          void setIntegration(item.name, "disable")
                        }
                      >
                        Disable
                      </button>
                    )}
                    {!item.revoked && (
                      <button
                        onClick={() => void setIntegration(item.name, "revoke")}
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                </article>
              ))
            )}
          </section>
        ) : section === "Settings" ? (
          <section className="panel">
            <p className="eyebrow">CONTENT PREFERENCES</p>
            <h2>OMNI-X preferences</h2>
            <label>
              Content style{" "}
              <select
                value={contentPreference}
                onChange={(event) =>
                  void changeContentPreference(event.target.value)
                }
              >
                <option value="standard">Standard</option>
                <option value="creative">Creative</option>
                <option value="open">Open</option>
              </select>
            </label>
            <p className="muted">
              Creative is the default. This affects OMNI-X prompting only and
              never changes terminal, browser, filesystem or provider
              permissions.
            </p>
            <p className="muted">
              Provider: OmniRoute · Model: {model} · FREE mode
            </p>
          </section>
        ) : (
          <section className="panel">
            <p className="eyebrow">PHASE 3 FOUNDATION</p>
            <h2>{section}</h2>
            <p className="muted">
              This workspace is connected to the unified OMNI-X backend. The
              section UI is being delivered incrementally without replacing the
              existing CLI runtime.
            </p>
          </section>
        )}
      </main>
    </div>
  );
}
