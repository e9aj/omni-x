import { FormEvent, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import logo from "./assets/website-logo-256.png";

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
type WorkflowRun = { id: string; state: string; error?: string | null; result?: Record<string, string> | null; created: number; finished?: number | null };
const navigation = [
  { label: "WORKSPACE", items: ["Chat", "Council", "Agents", "Tasks", "Workflows", "Memory"] },
  { label: "CONFIGURE", items: ["Models", "Tools & Skills", "Integrations", "Voice", "Settings"] },
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
  const runningRef = useRef(false);
  const [stopping, setStopping] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamStatus, setStreamStatus] = useState("");
  const [booting, setBooting] = useState(true);
  const [usage, setUsage] = useState<string>();
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [contentPreference, setContentPreference] = useState("creative");
  const [model, setModel] = useState("auto/best-free");
  const [provider, setProvider] = useState("");
  const [routingMode, setRoutingMode] = useState("");
  const [councilMode, setCouncilMode] = useState("standard");
  const [councilModels, setCouncilModels] = useState("");
  const [councilPrompt, setCouncilPrompt] = useState("");
  const [councilResult, setCouncilResult] = useState<CouncilResult>();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string>();
  const [modelsRefresh, setModelsRefresh] = useState(0);
  const [modelsLoading, setModelsLoading] = useState(false);
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
  const [memoryEdits, setMemoryEdits] = useState<Record<string, string>>({});
  const [canvasSelected, setCanvasSelected] = useState<string>();
  const [canvasZoom, setCanvasZoom] = useState(1);
  const [canvasPan, setCanvasPan] = useState({ x: 0, y: 0 });
  const [documentPath, setDocumentPath] = useState("");
  const [documentResult, setDocumentResult] = useState<string>();
  const [ocrEnabled, setOcrEnabled] = useState(false);
  const [voiceCapabilities, setVoiceCapabilities] =
    useState<VoiceCapabilities>();
  const [voicePath, setVoicePath] = useState("");
  const [voiceModel, setVoiceModel] = useState("");
  const [voiceText, setVoiceText] = useState("");
  const [voiceDevices, setVoiceDevices] = useState<string[]>([]);
  const [voiceNotePath, setVoiceNotePath] = useState("voice-notes/recording.wav");
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [workflowName, setWorkflowName] = useState("My workflow");
  const [workflowNodes, setWorkflowNodes] = useState<WorkflowNode[]>([
    { id: "step-1", action: "agent", x: 40, y: 40, depends_on: [] },
  ]);
  const [workflowRuns, setWorkflowRuns] = useState<Record<string, WorkflowRun[]>>({});

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
    // Let the branded first frame paint, then expose the workspace while the
    // backend starts or recovers. Readiness remains visible in the status UI.
    const frame = window.requestAnimationFrame(() => {
      setBooting(false);
      void invoke("frontend_ready").catch(() => undefined);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);
  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const refresh = async () => {
      await refreshStatus();
      if (!stopped) timer = window.setTimeout(refresh, 5000);
    };
    void refresh();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, []);
  useEffect(() => {
    if (!sessionId || !status.connected || running) return;
    let current = true;
    void invoke<{ messages: Array<{ role: string; content: string }> }>(
      "backend_session",
      { sessionId },
    )
      .then((result) => {
        if (current && !runningRef.current) setMessages(
          result.messages.filter((item): item is Message =>
            ["user", "assistant", "error"].includes(item.role),
          ) as Message[],
        );
      })
      .catch(() => undefined);
    return () => { current = false; };
  }, [sessionId, status.connected]);
  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    async function refresh() {
      try {
        const result = await invoke<{ approvals: Approval[] }>(
          "backend_approvals",
        );
        setApprovals(result.approvals);
      } catch {
        /* backend status displays the connection error */
      }
      if (!stopped) timer = window.setTimeout(refresh, 1000);
    }
    void refresh();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, []);
  useEffect(() => {
    if (!status.connected) return;
    void invoke<{ content_preference: string; model: string; provider: string; mode: string }>(
      "backend_settings",
    )
      .then((result) => {
        setContentPreference(result.content_preference);
        setModel(result.model);
        setProvider(result.provider);
        setRoutingMode(result.mode);
      })
      .catch(() => undefined);
  }, [status.connected]);
  useEffect(() => { setModelsError(undefined); }, [section]);
  useEffect(() => {
    if (section !== "Models" || !status.connected) return;
    let current = true;
    setModelsLoading(true);
    void invoke<{ models: ModelInfo[]; error?: string }>("backend_models")
      .then((result) => {
        if (!current) return;
        setModels(result.models);
        setModelsError(result.error);
      })
      .catch((error) => { if (current) setModelsError(String(error)); })
      .finally(() => { if (current) setModelsLoading(false); });
    return () => { current = false; };
  }, [section, status.connected, modelsRefresh]);
  useEffect(() => {
    if (section !== "Memory" || !status.connected) return;
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
  }, [section, status.connected]);
  useEffect(() => {
    if ((section !== "Tasks" && section !== "Agents") || !status.connected) return;
    void invoke<{ tasks: TaskItem[] }>("backend_tasks")
      .then((result) => setTasks(result.tasks))
      .catch((error) => setModelsError(String(error)));
  }, [section, status.connected]);
  useEffect(() => {
    if (section !== "Tools & Skills" || !status.connected) return;
    void invoke<{ skills: SkillItem[] }>("backend_skills")
      .then((result) => setSkills(result.skills))
      .catch((error) => setModelsError(String(error)));
  }, [section, status.connected]);
  useEffect(() => {
    if (section !== "Integrations" || !status.connected) return;
    void invoke<{ integrations: IntegrationItem[] }>("backend_integrations")
      .then((result) => setIntegrations(result.integrations))
      .catch((error) => setModelsError(String(error)));
  }, [section, status.connected]);
  useEffect(() => {
    if (section !== "Voice" || !status.connected) return;
    void invoke<{ capabilities: VoiceCapabilities }>(
      "backend_voice_capabilities",
    )
      .then((result) => setVoiceCapabilities(result.capabilities))
      .catch((error) => setModelsError(String(error)));
  }, [section, status.connected]);
  useEffect(() => {
    if (section !== "Workflows" || !status.connected) return;
    void invoke<{ workflows: WorkflowItem[] }>("backend_workflows")
      .then((result) => setWorkflows(result.workflows))
      .catch((error) => setModelsError(String(error)));
  }, [section, status.connected]);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || running) return;
    setPrompt("");
    setMessages((items) => [...items, { role: "user", content: text }]);
    runningRef.current = true;
    setRunning(true);
    setStreamText("");
    setStreamStatus("Starting");
    const streamId = crypto.randomUUID();
    let polling = true;
    const poll = async () => {
      while (polling) {
        try {
          const result = await invoke<{ text: string; status: string }>("backend_chat_stream", { streamId });
          if (polling) { setStreamText(result.text); if (result.status) setStreamStatus(result.status); }
        } catch { /* The chat request reports connection errors. */ }
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
    };
    void poll();
    try {
      const result = await invoke<ChatResult>("backend_chat", {
        prompt: text,
        sessionId,
        streamId,
      });
      setSessionId(result.session_id);
      localStorage.setItem("omnix-session-id", result.session_id);
      setModel(result.model ?? model);
      setProvider(result.provider ?? provider);
      setRoutingMode(result.mode);
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
      polling = false;
      setStreamText("");
      setStreamStatus("");
      setStopping(false);
      runningRef.current = false;
      setRunning(false);
      void refreshStatus();
    }
  }
  async function stop() {
    setStopping(true);
    try {
      await invoke("backend_stop");
    } catch (error) {
      setStopping(false);
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
    runningRef.current = true;
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
      runningRef.current = false;
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
  async function transcribeVoice() {
    try { const result = await invoke<{ text: string }>("backend_voice_transcribe", { path: voicePath, model: voiceModel }); setVoiceText(result.text); }
    catch (error) { setModelsError(String(error)); }
  }
  async function speakVoice() {
    try { await invoke("backend_voice_speak", { text: voiceText, outputPath: null }); }
    catch (error) { setModelsError(String(error)); }
  }
  async function listVoiceDevices() {
    try { const result = await invoke<{ devices: Array<{ name: string }> }>("backend_voice_devices"); setVoiceDevices(result.devices.map((item) => item.name)); }
    catch (error) { setModelsError(String(error)); }
  }
  async function recordVoiceNote() {
    try { await invoke("backend_voice_record", { path: voiceNotePath, durationSeconds: 5, device: null }); setVoicePath(voiceNotePath); }
    catch (error) { setModelsError(String(error)); }
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
  async function runWorkflow(id: string) {
    try { await invoke("backend_workflow_run", { id }); const result = await invoke<{ runs: WorkflowRun[] }>("backend_workflow_runs", { id }); setWorkflowRuns((items) => ({ ...items, [id]: result.runs })); }
    catch (error) { setModelsError(String(error)); }
  }
  async function cancelWorkflow(runId: string, workflowId: string) {
    try { await invoke("backend_workflow_cancel", { runId }); await loadWorkflowRuns(workflowId); }
    catch (error) { setModelsError(String(error)); }
  }
  async function scheduleWorkflow(id: string) {
    try { const schedule = window.prompt("Schedule (for example: every 1h)", "every 1h"); if (schedule) await invoke("backend_workflow_schedule", { id, schedule }); }
    catch (error) { setModelsError(String(error)); }
  }
  async function loadWorkflowRuns(id: string) {
    try { const result = await invoke<{ runs: WorkflowRun[] }>("backend_workflow_runs", { id }); setWorkflowRuns((items) => ({ ...items, [id]: result.runs })); }
    catch (error) { setModelsError(String(error)); }
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
      {booting && (
        <div className="boot-screen" role="status" aria-live="polite">
          <img src={logo} alt="OMNI-X" />
          <strong>OMNI-X</strong>
          <span>Starting local runtime</span>
        </div>
      )}
      <aside className="sidebar">
        <div className="brand">
          <img className="brand-mark" src={logo} alt="OMNI-X" />
          <span>
            <strong>OMNI-X</strong>
            <small>ONE AGENT. EVERY AI.</small>
          </span>
        </div>
        <nav>
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <p className="nav-label">{group.label}</p>
              {group.items.map((item) => (
                <button
                  className={section === item ? "nav-item active" : "nav-item"}
                  onClick={() => setSection(item)}
                  aria-current={section === item ? "page" : undefined}
                  key={item}
                >
                  {item}
                </button>
              ))}
            </div>
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
          <div className="connection" title={status.connected ? undefined : "The local runtime is unavailable; OMNI-X will retry."} role="status">
            {status.connected
              ? `OMNI-X ${status.version ?? "runtime"}`
              : "Local runtime unavailable · retrying"}
          </div>
        </header>
        {!status.connected && section !== "Chat" && (
          <p className="offline-notice" role="status">
            The local runtime is unavailable. Data in this view may be incomplete until it reconnects.
          </p>
        )}
        {modelsError && section !== "Models" && (
          <p className="error-notice" role="alert">{modelsError}</p>
        )}
        {section === "Chat" ? (
          <section className="chat-panel">
            <div className="message-list">
              {messages.length === 0 && (
                <div className="empty-chat">
                  <p className="eyebrow">YOUR LOCAL AGENT WORKSPACE</p>
                  <h2>What shall we work on?</h2>
                  <p className="muted">
                    Bring an idea, a question or a task. OMNI-X will keep you
                    in control as the work takes shape.
                  </p>
                  <div className="quick-links" aria-label="Explore your workspace">
                    <button type="button" onClick={() => setSection("Tasks")}>
                      <strong>Tasks <span aria-hidden="true">↗</span></strong>
                      <small>Queue work for later</small>
                    </button>
                    <button type="button" onClick={() => setSection("Workflows")}>
                      <strong>Workflows <span aria-hidden="true">↗</span></strong>
                      <small>Arrange repeatable steps</small>
                    </button>
                    <button type="button" onClick={() => setSection("Memory")}>
                      <strong>Memory <span aria-hidden="true">↗</span></strong>
                      <small>Explore your local notes</small>
                    </button>
                  </div>
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
                  <span className="message-role">assistant · {stopping ? "stopping" : (streamStatus || "working")}</span>
                  <p>{stopping ? "Stopping the current task…" : (streamText || "Working…")}</p>
                </article>
              )}
            </div>
            <form className="composer" onSubmit={send}>
              <input
                aria-label="Message OMNI-X"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="Ask OMNI-X anything…"
                disabled={!status.connected || running}
              />
              <button
                type={running ? "button" : "submit"}
                onClick={running ? stop : undefined}
                disabled={stopping}
              >
                {stopping ? "Stopping…" : running ? "Stop" : "Send"}
              </button>
            </form>
            {usage && (
              <p className="muted usage">
                {usage} · {routingMode} mode · {model}
              </p>
            )}
          </section>
        ) : section === "Council" ? (
          <section className="panel">
            <p className="eyebrow">FREE-FIRST · BOUNDED INFERENCE</p>
            <h2>Ask the Council</h2>
            <p className="muted">
              Standard uses one model by default. Council uses three, Advanced
              five, and Research requires an explicit model group. Your
              provider, FREE mode and spending settings apply to every answer.
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
                aria-label="Council prompt"
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
            <p className="eyebrow">MODEL DISCOVERY</p>
            <h2>Available models</h2>
            <p className="muted">
              Discovery reports what the configured gateway currently exposes. A
              model is selectable only when the backend verifies it as free.
            </p>
            <button disabled={!status.connected || modelsLoading} onClick={() => setModelsRefresh((value) => value + 1)}>Refresh models</button>
            {modelsError && (
              <p className="muted">Discovery error: {modelsError}</p>
            )}
            {models.length === 0 && !modelsError && (
              <p className="muted">
                {!status.connected ? "Connect the local runtime to load models." : modelsLoading ? "Loading models…" : "No models returned. Check your gateway and refresh."}
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
                    disabled={!status.connected}
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
              <p className="muted">{status.connected ? "Checking local capabilities…" : "Connect the local runtime to check voice capabilities."}</p>
            )}
            <h3>Offline dictation</h3>
            <p className="muted">Choose a workspace-relative WAV fixture and an existing local Whisper model directory. No weights are downloaded.</p>
            <label>WAV file path<input value={voicePath} onChange={(event) => setVoicePath(event.target.value)} placeholder="fixtures/voice.wav" /></label>
            <label>Local Whisper model directory<input value={voiceModel} onChange={(event) => setVoiceModel(event.target.value)} placeholder="C:/local/whisper-model" /></label>
            <button disabled={!status.connected} onClick={() => void transcribeVoice()}>Transcribe locally</button>
            <label>Transcription or text to speak<textarea value={voiceText} onChange={(event) => setVoiceText(event.target.value)} rows={4} /></label>
            <button disabled={!status.connected} onClick={() => void speakVoice()}>Speak locally</button><label>Voice note path<input value={voiceNotePath} onChange={(event) => setVoiceNotePath(event.target.value)} /></label><button disabled={!status.connected} onClick={() => void recordVoiceNote()}>Record a 5-second note</button><button disabled={!status.connected} onClick={() => void listVoiceDevices()}>List input devices (approval required)</button>
            {voiceDevices.map((device) => <small key={device}>{device}</small>)}
            <p className="muted">Recording and speech require approved local audio components. Wake-word activation is unavailable.</p>
          </section>
        ) : section === "Workflows" ? (
          <section className="panel">
            <p className="eyebrow">REPEATABLE WORK</p>
            <h2>Workflow builder</h2>
            <p className="muted">
              Arrange steps, then save, run or schedule your workflow. Actions
              remain subject to your permissions and approvals.
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
                  tabIndex={0}
                  aria-label={`${node.id}, use arrow keys to move`}
                  key={node.id}
                  style={{ left: node.x, top: node.y }}
                  onKeyDown={(event) => {
                    if (event.target !== event.currentTarget) return;
                    const delta: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
                    const move = delta[event.key];
                    if (!move) return;
                    event.preventDefault();
                    setWorkflowNodes((items) => items.map((item) => item.id === node.id ? { ...item, x: Math.max(0, item.x + move[0]), y: Math.max(0, item.y + move[1]) } : item));
                  }}
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
                    aria-label={`Action for ${node.id}`}
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
            <p className="muted">Drag a step, or focus it and use the arrow keys to move it.</p>
            <button onClick={addWorkflowNode}>Add step</button>
            <button disabled={!status.connected} onClick={() => void saveWorkflow()}>Save workflow</button>
            <h3>Saved workflows</h3>
            {workflows.map((workflow) => (
              <article className="candidate" key={workflow.id}>
                <strong>{workflow.name}</strong>
                <span>{workflow.definition.nodes.length} steps</span>
                <button disabled={!status.connected} onClick={() => void runWorkflow(workflow.id)}>Run workflow</button><button disabled={!status.connected} onClick={() => void scheduleWorkflow(workflow.id)}>Schedule</button><button disabled={!status.connected} onClick={() => void loadWorkflowRuns(workflow.id)}>Refresh history</button>
                {(workflowRuns[workflow.id] ?? []).map((run) => <span key={run.id}><small>{run.state}{run.error ? ` · ${run.error}` : ""}</small>{run.state === "running" && <button disabled={!status.connected} onClick={() => void cancelWorkflow(run.id, workflow.id)}>Stop</button>}</span>)}
              </article>
            ))}
          </section>
        ) : section === "Memory" ? (
          <section className="panel">
            <p className="eyebrow">LOCAL-FIRST MARKDOWN VAULT</p>
            <h2>Brain notes</h2>
            <form className="council-form" onSubmit={searchBrain}>
              <input
                aria-label="Search the Brain vault"
                value={brainQuery}
                onChange={(event) => setBrainQuery(event.target.value)}
                placeholder="Search the Brain vault"
              />
              <button type="submit" disabled={!status.connected}>Search</button>
            </form>
            {brainResults.map((result) => (
              <article className="candidate" key={result.path}>
                <strong>{result.path}</strong>
                <small>{result.snippet}</small>
              </article>
            ))}
            <p className="muted">
              {status.connected ? `Knowledge graph: ${brainGraph.nodes.length} notes · ${brainGraph.edges.length} links. Local semantic search is active; neural embeddings and OCR are optional local engines.` : "Connect the local runtime to load the knowledge graph."}
            </p>
            <h3>Memory suggestions</h3>
            {memorySuggestions.length === 0 ? (
              <p className="muted">{status.connected ? "No pending suggestions. Suggestions always require approval." : "Connect the local runtime to load memory suggestions."}</p>
            ) : memorySuggestions.map((suggestion) => (
              <article className="candidate" key={suggestion.id}>
                <strong>{suggestion.memory_key}</strong>
                <input value={memoryEdits[suggestion.id] ?? suggestion.memory_value} aria-label={`Edit ${suggestion.memory_key}`} onChange={(event) => setMemoryEdits((items) => ({ ...items, [suggestion.id]: event.target.value }))} />
                <div><button disabled={!status.connected} onClick={() => void decideMemory(suggestion.id, "approved", suggestion.memory_key, memoryEdits[suggestion.id] ?? suggestion.memory_value)}>Approve</button><button disabled={!status.connected} onClick={() => void decideMemory(suggestion.id, "rejected")}>Reject</button><button disabled={!status.connected} onClick={() => void decideMemory(suggestion.id, "deleted")}>Delete</button></div>
              </article>
            ))}
            <label>
              New note path{" "}
              <input
                value={newNotePath}
                onChange={(event) => setNewNotePath(event.target.value)}
              />
            </label>
            <button disabled={!status.connected} onClick={() => void createNote()}>Create note</button>
            <div className="note-list">
              {notes.length === 0 ? (
                <p className="muted">
                  {status.connected ? "No Markdown notes yet. Create one in the Brain vault to begin." : "Connect the local runtime to load Brain notes."}
                </p>
              ) : (
                notes.map((note) => (
                  <span key={note.path}><button className="note-link" disabled={!status.connected} onClick={() => void openNote(note.path)}>{note.path}</button><button onClick={() => addCanvasNote(note.path)}>Add to canvas</button></span>
                ))
              )}
            </div>
            <h3>Infinite canvas</h3>
            <div className="workflow-canvas" style={{ transform: `translate(${canvasPan.x}px, ${canvasPan.y}px) scale(${canvasZoom})`, transformOrigin: "top left" }}>
              <svg className="canvas-links" aria-hidden="true">{brainCanvas.edges.map((edge) => { const source = brainCanvas.nodes.find((node) => node.path === edge.source); const target = brainCanvas.nodes.find((node) => node.path === edge.target); return source && target ? <line key={`${edge.source}-${edge.target}`} x1={source.x + 60} y1={source.y + 30} x2={target.x + 60} y2={target.y + 30} /> : null; })}</svg>
              {brainCanvas.nodes.map((node) => <article className={`candidate workflow-node${canvasSelected === node.path ? " active" : ""}`} draggable role="button" tabIndex={0} aria-label={`${node.path}, press Enter to connect or use arrow keys to move`} key={node.id} style={{ left: node.x, top: node.y }} onClick={() => connectCanvasNode(node.path)} onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") { event.preventDefault(); connectCanvasNode(node.path); return; }
                const delta: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
                const move = delta[event.key];
                if (!move) return;
                event.preventDefault();
                setBrainCanvas((canvas) => ({ ...canvas, nodes: canvas.nodes.map((item) => item.id === node.id ? { ...item, x: Math.max(0, item.x + move[0]), y: Math.max(0, item.y + move[1]) } : item) }));
              }} onDragEnd={(event) => { const rect = event.currentTarget.parentElement?.getBoundingClientRect(); if (rect) setBrainCanvas((canvas) => ({ ...canvas, nodes: canvas.nodes.map((item) => item.id === node.id ? { ...item, x: Math.max(0, (event.clientX - rect.left) / canvasZoom - 60), y: Math.max(0, (event.clientY - rect.top) / canvasZoom - 30) } : item) })); }}><strong>{node.path}</strong></article>)}
            </div>
            <p className="muted">Select two notes to connect them. Drag cards or use arrow keys to move them; use the pan controls to navigate.</p>
            <button onClick={() => setCanvasZoom((value) => Math.min(2, value + 0.1))}>Zoom in</button><button onClick={() => setCanvasZoom((value) => Math.max(0.5, value - 0.1))}>Zoom out</button><button onClick={() => moveCanvas(-80, 0)}>Pan left</button><button onClick={() => moveCanvas(80, 0)}>Pan right</button><button onClick={() => moveCanvas(0, -80)}>Pan up</button><button onClick={() => moveCanvas(0, 80)}>Pan down</button><button disabled={!status.connected} onClick={() => void saveCanvas()}>Save layout</button>
            <h3>Document import and OCR</h3><p className="muted">Documents are read locally from the backend workspace. OCR is opt-in and requires reviewed local OCR engines.</p><label>Document path<input value={documentPath} onChange={(event) => setDocumentPath(event.target.value)} placeholder="relative/path/to/document.pdf" /></label><label><input type="checkbox" checked={ocrEnabled} onChange={(event) => setOcrEnabled(event.target.checked)} /> Enable local OCR</label><button disabled={!status.connected} onClick={() => void inspectDocument()}>Inspect document</button>{documentResult && <pre className="document-preview">{documentResult}</pre>}
            {selectedNote && (
              <>
                <input value={selectedNote} aria-label="Selected note path" readOnly />
                <textarea
                  value={noteContent}
                  aria-label="Note content"
                  onChange={(event) => setNoteContent(event.target.value)}
                  rows={14}
                />
                <button disabled={!status.connected} onClick={() => void saveNote()}>Save note</button>
              </>
            )}
          </section>
        ) : section === "Tasks" || section === "Agents" ? (
          <section className="panel">
            <p className="eyebrow">BACKGROUND WORK</p>
            <h2>{section}</h2>
            <p className="muted">
              {section === "Agents"
                ? "Review agent activity and delegated work from the shared task queue."
                : "Queue and cancel background work."}
            </p>
            {section === "Tasks" && (
              <form className="council-form" onSubmit={enqueueTask}>
                <input
                  aria-label="Background task"
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
                <p className="muted">{status.connected ? "No tasks have been queued." : "Connect the local runtime to load tasks."}</p>
              ) : (
                tasks.map((task) => (
                  <article className="candidate" key={task.id}>
                    <strong>{task.state}</strong>
                    <span>{task.prompt}</span>
                    {task.state === "queued" || task.state === "running" ? (
                      <button disabled={!status.connected} onClick={() => void cancelTask(task.id)}>
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
              APPROVALS · REVIEWED SKILLS
            </p>
            <h2>Tools & Skills</h2>
            <h3>Pending approvals</h3>
            {approvals.length === 0 ? (
              <p className="muted">{status.connected ? "No pending requests." : "Connect the local runtime to load approvals."}</p>
            ) : (
              approvals.map((approval) => (
                <article className="approval" key={approval.id}>
                  <p>{approval.action}</p>
                  <small>
                    Expires{" "}
                    {new Date(approval.expires_at * 1000).toLocaleTimeString()}
                  </small>
                  <div>
                    <button disabled={!status.connected} onClick={() => void decide(approval.id, "approve")}>
                      Approve
                    </button>
                    <button disabled={!status.connected} onClick={() => void decide(approval.id, "reject")}>
                      Reject
                    </button>
                  </div>
                </article>
              ))
            )}
            <h3>Skills catalogue</h3>
            <p className="muted">
              Skills are disabled by default. Review and install skills before
              enabling them here.
            </p>
            {skills.length === 0 ? (
              <p className="muted">
                {status.connected ? "No reviewed skills are installed or discoverable." : "Connect the local runtime to load skills."}
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
                    disabled={!status.connected}
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
              Integrations are disabled by default. Review and enable each one
              explicitly; this screen does not connect services or reveal credentials.
            </p>
            {integrations.length === 0 ? (
              <p className="muted">{status.connected ? "No catalogue entries available." : "Connect the local runtime to load integrations."}</p>
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
                        disabled={!status.connected}
                        onClick={() =>
                          void setIntegration(item.name, "install")
                        }
                      >
                        Record install
                      </button>
                    )}
                    {item.installed && !item.enabled && !item.revoked && (
                      <button
                        disabled={!status.connected}
                        onClick={() => void setIntegration(item.name, "enable")}
                      >
                        Enable
                      </button>
                    )}
                    {item.enabled && (
                      <button
                        disabled={!status.connected}
                        onClick={() =>
                          void setIntegration(item.name, "disable")
                        }
                      >
                        Disable
                      </button>
                    )}
                    {!item.revoked && (
                      <button
                        disabled={!status.connected}
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
                disabled={!status.connected}
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
              {status.connected && provider ? `Provider: ${provider} · Model: ${model} · ${routingMode} mode` : "Provider details are unavailable."}
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
