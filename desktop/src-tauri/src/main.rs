#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use serde_json::{json, Value};
use std::{
    fs::OpenOptions,
    io::{Read, Write},
    net::{TcpStream, ToSocketAddrs},
    process::{Child, Command},
    sync::{
        atomic::{AtomicBool, AtomicU32, Ordering},
        Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Manager, State, WindowEvent};

const PORT: u16 = 27451;

fn supervisor_log(message: &str) {
    if let Ok(mut file) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(std::env::temp_dir().join("omnix-desktop-supervisor.log"))
    {
        use std::io::Write as _;
        let _ = writeln!(file, "{message}");
    }
}

struct BackendState {
    child: Mutex<Option<Child>>,
    token: String,
    stopping: AtomicBool,
    starting: AtomicBool,
    restart_attempts: AtomicU32,
    launched_at: Instant,
}

struct StartupGuard<'a>(&'a AtomicBool);

impl Drop for StartupGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

#[derive(Serialize)]
struct BackendStatus {
    connected: bool,
    endpoint: String,
    version: Option<String>,
    error: Option<String>,
}

fn token() -> String {
    if let Ok(value) = std::env::var("OMNIX_IPC_TOKEN") {
        if !value.trim().is_empty() {
            return value;
        }
    }
    random_token().expect("operating-system randomness is unavailable")
}

fn random_token() -> Result<String, getrandom::Error> {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes)?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn read_bounded_response(reader: impl Read, limit: u64) -> Result<String, String> {
    let mut bytes = Vec::new();
    reader
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| error.to_string())?;
    if bytes.len() as u64 > limit {
        return Err("backend response exceeds the desktop size limit".into());
    }
    String::from_utf8(bytes).map_err(|_| "backend response is not valid UTF-8".into())
}

fn request(
    state: &BackendState,
    method: &str,
    path: &str,
    payload: Option<Value>,
) -> Result<Value, String> {
    let mut stream = TcpStream::connect_timeout(
        &("127.0.0.1", PORT)
            .to_socket_addrs()
            .map_err(|e| e.to_string())?
            .next()
            .ok_or("no loopback address")?,
        Duration::from_secs(2),
    )
    .map_err(|e| e.to_string())?;
    let quick_request = matches!(
        path,
        "/v1/health" | "/v1/approvals" | "/v1/stop" | "/v1/shutdown"
    ) || path.starts_with("/v1/chat/stream?")
        || path.starts_with("/v1/sessions/");
    stream
        .set_read_timeout(Some(Duration::from_secs(if quick_request {
            5
        } else {
            180
        })))
        .map_err(|e| e.to_string())?;
    let body = payload.map(|value| value.to_string()).unwrap_or_default();
    let request = format!("{} {} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {}\r\nOrigin: tauri://localhost\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", method, path, state.token, body.len(), body);
    stream
        .write_all(request.as_bytes())
        .map_err(|e| e.to_string())?;
    let response = read_bounded_response(stream, 32_000_000)?;
    let status = response.lines().next().unwrap_or("");
    let json_body = response.split("\r\n\r\n").nth(1).unwrap_or("");
    let value: Value = serde_json::from_str(json_body).map_err(|e| e.to_string())?;
    if !status.contains(" 200 ") {
        return Err(value["error"]
            .as_str()
            .unwrap_or("backend request failed")
            .to_string());
    }
    Ok(value)
}

fn encode_query(value: &str) -> String {
    value
        .bytes()
        .map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'/' => {
                (byte as char).to_string()
            }
            _ => format!("%{byte:02X}"),
        })
        .collect()
}

fn terminate_authenticated_orphan(pid: u32) -> Result<(), String> {
    if pid == std::process::id() {
        return Err("refusing to terminate the desktop process".into());
    }
    #[cfg(windows)]
    {
        let status = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .status()
            .map_err(|error| format!("failed to terminate owned backend {pid}: {error}"))?;
        if status.success() {
            return Ok(());
        }
        return Err(format!("taskkill failed for owned backend {pid}: {status}"));
    }
    #[cfg(not(windows))]
    {
        let _ = pid;
        Err("orphan backend recovery is only supported on Windows".into())
    }
}

#[cfg(windows)]
fn process_parent_pid(pid: u32) -> Option<u32> {
    use std::mem::{size_of, zeroed};
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W,
        TH32CS_SNAPPROCESS,
    };
    unsafe {
        let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if snapshot == INVALID_HANDLE_VALUE {
            return None;
        }
        let mut entry: PROCESSENTRY32W = zeroed();
        entry.dwSize = size_of::<PROCESSENTRY32W>() as u32;
        let mut found = None;
        if Process32FirstW(snapshot, &mut entry) != 0 {
            loop {
                if entry.th32ProcessID == pid {
                    found = Some(entry.th32ParentProcessID);
                    break;
                }
                if Process32NextW(snapshot, &mut entry) == 0 {
                    break;
                }
            }
        }
        CloseHandle(snapshot);
        found
    }
}

fn pid_is_in_ancestry<F>(pid: u32, launcher_pid: u32, mut parent_of: F) -> bool
where
    F: FnMut(u32) -> Option<u32>,
{
    if pid == launcher_pid {
        return true;
    }
    let mut current = pid;
    for _ in 0..32 {
        let Some(parent) = parent_of(current) else {
            return false;
        };
        if parent == launcher_pid {
            return true;
        }
        if parent == 0 || parent == current {
            return false;
        }
        current = parent;
    }
    false
}

#[cfg(windows)]
fn process_is_owned_descendant(pid: u32, launcher_pid: u32) -> bool {
    pid_is_in_ancestry(pid, launcher_pid, process_parent_pid)
}

#[cfg(not(windows))]
fn process_is_owned_descendant(pid: u32, launcher_pid: u32) -> bool {
    pid == launcher_pid
}

fn start_backend(app: &AppHandle, state: &BackendState) -> Result<(), String> {
    if state.stopping.load(Ordering::SeqCst) {
        return Err("backend is stopping".into());
    }
    if state
        .starting
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return Err("backend startup already in progress".into());
    }
    let _startup_guard = StartupGuard(&state.starting);
    if state
        .child
        .lock()
        .map_err(|_| "backend lock poisoned".to_string())?
        .as_ref()
        .is_some()
    {
        return Ok(());
    }
    if let Ok(value) = request(state, "GET", "/v1/health", None) {
        if let Some(pid) = value["pid"].as_u64().map(|value| value as u32) {
            supervisor_log(&format!(
                "authenticated orphan detected pid={pid}; terminating exact PID"
            ));
            terminate_authenticated_orphan(pid)?;
            for _ in 0..20 {
                if request(state, "GET", "/v1/health", None).is_err() {
                    break;
                }
                thread::sleep(Duration::from_millis(100));
            }
        } else {
            return Err("authenticated backend is reachable without a verifiable PID".into());
        }
    }
    if TcpStream::connect(("127.0.0.1", PORT)).is_ok() {
        return Err("loopback backend port is occupied by an unauthorised process".into());
    }
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("backend resource path unavailable: {e}"))?;
    let bundled = [
        resource_dir.join("omnix-backend.exe"),
        resource_dir.join("omnix-backend-x86_64-pc-windows-msvc.exe"),
        resource_dir.join("binaries").join("omnix-backend.exe"),
        resource_dir
            .join("binaries")
            .join("omnix-backend-x86_64-pc-windows-msvc.exe"),
    ]
    .into_iter()
    .find(|path| path.is_file());
    eprintln!(
        "OMNI-X backend sidecar discovery: {}",
        bundled
            .as_ref()
            .map(|path| path.display().to_string())
            .unwrap_or_else(|| "not found".into())
    );
    let mut command;
    if let Some(bundled) = bundled.as_ref() {
        command = Command::new(bundled);
        command.args(["--port", &PORT.to_string()]);
        command.current_dir(&resource_dir);
    } else {
        if !cfg!(debug_assertions) && std::env::var_os("OMNIX_PYTHON").is_none() {
            return Err(format!(
                "managed backend sidecar not found under {}",
                resource_dir.display()
            ));
        }
        let python = std::env::var("OMNIX_PYTHON").unwrap_or_else(|_| "python".into());
        command = Command::new(python);
        command.args(["-m", "omnix.desktop_server", "--port", &PORT.to_string()]);
        command.env(
            "PYTHONPATH",
            std::env::var("OMNIX_PYTHONPATH").unwrap_or_else(|_| "../src".into()),
        );
    }
    // Publish the child under the same lock used by shutdown. Otherwise a
    // close racing with spawn can observe no child and leave a new orphan.
    let mut child_guard = state
        .child
        .lock()
        .map_err(|_| "backend lock poisoned".to_string())?;
    if state.stopping.load(Ordering::SeqCst) {
        return Err("backend is stopping".into());
    }
    let child = command
        .env("OMNIX_IPC_TOKEN", &state.token)
        .spawn()
        .map_err(|e| format!("backend start failed: {e}"))?;
    let expected_pid = child.id();
    eprintln!("OMNI-X backend sidecar spawned with pid {expected_pid}");
    supervisor_log(&format!(
        "spawned backend pid={expected_pid} elapsed_ms={}",
        state.launched_at.elapsed().as_millis()
    ));
    *child_guard = Some(child);
    drop(child_guard);
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        if let Ok(value) = request(state, "GET", "/v1/health", None) {
            if let Some(actual_pid) = value["pid"].as_u64().map(|value| value as u32) {
                if process_is_owned_descendant(actual_pid, expected_pid) {
                    supervisor_log(&format!(
                        "health passed launcher_pid={expected_pid} backend_pid={actual_pid} elapsed_ms={}",
                        state.launched_at.elapsed().as_millis()
                    ));
                    return Ok(());
                }
            }
            if value["pid"].as_u64() == Some(expected_pid as u64) {
                return Ok(());
            }
            supervisor_log(&format!(
                "health returned unexpected pid expected={expected_pid} actual={}",
                value["pid"]
            ));
        }
        let exit_status = state.child.lock().ok().and_then(|mut guard| {
            guard
                .as_mut()
                .and_then(|value| value.try_wait().ok().flatten())
        });
        if let Some(status) = exit_status {
            eprintln!("OMNI-X backend sidecar exited before health check with status {status}");
            supervisor_log(&format!(
                "backend pid={expected_pid} exited before health: {status}"
            ));
            discard_child(state);
            return Err("backend exited before authenticated health check".into());
        }
        thread::sleep(Duration::from_millis(250));
    }
    eprintln!("OMNI-X backend authenticated health check timed out");
    supervisor_log(&format!("health timeout pid={expected_pid}"));
    discard_child(state);
    Err("backend did not pass authenticated health check within the startup limit".into())
}

fn stop_owned_child(child: &mut Child) {
    if matches!(child.try_wait(), Ok(None)) {
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            let _ = Command::new("taskkill")
                .args(["/PID", &child.id().to_string(), "/T", "/F"])
                .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
                .status();
        }
    }
    // Child::kill uses the owned process handle, including if status probing failed.
    let _ = child.kill();
    let _ = child.wait();
}

fn discard_child(state: &BackendState) {
    if let Ok(mut guard) = state.child.lock() {
        if let Some(mut child) = guard.take() {
            stop_owned_child(&mut child);
        }
    }
}

fn shutdown_backend(state: &BackendState) {
    state.stopping.store(true, Ordering::SeqCst);
    supervisor_log("shutdown requested");
    let _ = request(state, "POST", "/v1/shutdown", Some(json!({})));
    if let Ok(mut guard) = state.child.lock() {
        if let Some(mut child) = guard.take() {
            for _ in 0..20 {
                if child.try_wait().ok().flatten().is_some() {
                    return;
                }
                thread::sleep(Duration::from_millis(50));
            }
            stop_owned_child(&mut child);
        }
    }
}

#[tauri::command]
fn frontend_ready(state: State<'_, BackendState>) {
    supervisor_log(&format!(
        "frontend animation frame elapsed_ms={}",
        state.launched_at.elapsed().as_millis()
    ));
}

#[tauri::command]
async fn backend_status(app: AppHandle) -> Result<BackendStatus, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<BackendState>();
        match request(&state, "GET", "/v1/health", None) {
            Ok(value) => BackendStatus {
                connected: value["status"] == "ok",
                endpoint: format!("127.0.0.1:{PORT}"),
                version: value["version"].as_str().map(String::from),
                error: None,
            },
            Err(error) => BackendStatus {
                connected: false,
                endpoint: format!("127.0.0.1:{PORT}"),
                version: None,
                error: Some(error),
            },
        }
    })
    .await
    .map_err(|_| "Status worker stopped unexpectedly".to_string())
}

#[tauri::command]
async fn backend_chat(
    prompt: String,
    session_id: Option<String>,
    stream_id: String,
    app: AppHandle,
) -> Result<Value, String> {
    if prompt.trim().is_empty() {
        return Err("prompt is required".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<BackendState>();
        request(
            &state,
            "POST",
            "/v1/chat",
            Some(json!({"prompt": prompt, "session_id": session_id, "stream_id": stream_id})),
        )
    })
    .await
    .map_err(|_| "Chat worker stopped unexpectedly".to_string())?
}

#[tauri::command]
async fn backend_chat_stream(stream_id: String, app: AppHandle) -> Result<Value, String> {
    if stream_id.is_empty()
        || stream_id.len() > 80
        || !stream_id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
    {
        return Err("invalid stream identifier".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<BackendState>();
        request(
            &state,
            "GET",
            &format!("/v1/chat/stream?id={stream_id}"),
            None,
        )
    })
    .await
    .map_err(|_| "Stream worker stopped unexpectedly".to_string())?
}

macro_rules! blocking_backend_command {
    ($name:ident ($($arg:ident: $kind:ty),* $(,)?) $state:ident $body:block) => {
        #[tauri::command]
        async fn $name($($arg: $kind,)* app: AppHandle) -> Result<Value, String> {
            tauri::async_runtime::spawn_blocking(move || {
                let $state = app.state::<BackendState>();
                $body
            })
            .await
            .map_err(|_| "Backend worker stopped unexpectedly".to_string())?
        }
    };
}

blocking_backend_command! {
    backend_council(
        prompt: String,
        mode: String,
        models: Vec<String>,
        session_id: Option<String>,
    ) state {
        if prompt.trim().is_empty() || models.len() > 5 {
            return Err("invalid Council request".into());
        }
        request(
            &state,
            "POST",
            "/v1/council",
            Some(json!({
                "prompt": prompt, "mode": mode, "models": models, "session_id": session_id
            })),
        )
    }
}

#[tauri::command]
async fn backend_stop(app: AppHandle) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<BackendState>();
        request(&state, "POST", "/v1/stop", Some(json!({})))
    })
    .await
    .map_err(|_| "Stop worker stopped unexpectedly".to_string())?
}

#[tauri::command]
async fn backend_approvals(app: AppHandle) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<BackendState>();
        request(&state, "GET", "/v1/approvals", None)
    })
    .await
    .map_err(|_| "Approval worker stopped unexpectedly".to_string())?
}

blocking_backend_command! {
    backend_approval_decide(
        id: String,
        decision: String,
    ) state {
        if decision != "approve" && decision != "reject" {
            return Err("invalid approval decision".into());
        }
        request(
            &state,
            "POST",
            &format!("/v1/approvals/{id}"),
            Some(json!({"decision": decision})),
        )
    }
}

blocking_backend_command! {
    backend_settings() state {
        request(&state, "GET", "/v1/settings", None)
    }
}

blocking_backend_command! {
    backend_models() state {
        request(&state, "GET", "/v1/models", None)
    }
}

blocking_backend_command! {
    backend_set_model(
        model: String,
    ) state {
        if model.trim().is_empty() || model.len() > 200 {
            return Err("model is invalid".into());
        }
        request(
            &state,
            "POST",
            "/v1/settings",
            Some(json!({"model": model})),
        )
    }
}

blocking_backend_command! {
    backend_brain_notes() state {
        request(&state, "GET", "/v1/brain/notes", None)
    }
}

blocking_backend_command! {
    backend_brain_graph() state {
        request(&state, "GET", "/v1/brain/graph", None)
    }
}

blocking_backend_command! {
    backend_brain_canvas() state {
        request(&state, "GET", "/v1/brain/canvas", None)
    }
}

blocking_backend_command! {
    backend_brain_save_canvas(
        canvas: Value,
    ) state {
        if !canvas.is_object() {
            return Err("canvas payload is invalid".into());
        }
        request(&state, "POST", "/v1/brain/canvas", Some(canvas))
    }
}

blocking_backend_command! {
    backend_memory_suggestions() state {
        request(&state, "GET", "/v1/memory/suggestions", None)
    }
}

blocking_backend_command! {
    backend_memory_decide(
        id: String,
        state: String,
        key: Option<String>,
        value: Option<String>,
    ) backend {
        if id.trim().is_empty()
            || id.len() > 100
            || !["approved", "rejected", "deleted"].contains(&state.as_str())
        {
            return Err("memory decision is invalid".into());
        }
        request(
            &backend,
            "POST",
            &format!("/v1/memory/suggestions/{id}"),
            Some(json!({"state": state, "key": key, "value": value})),
        )
    }
}

blocking_backend_command! {
    backend_brain_search(
        query: String,
    ) state {
        if query.trim().is_empty() || query.len() > 200 {
            return Err("search query is invalid".into());
        }
        request(
            &state,
            "GET",
            &format!("/v1/brain/search?q={}", encode_query(&query)),
            None,
        )
    }
}

blocking_backend_command! {
    backend_brain_semantic_search(
        query: String,
    ) state {
        if query.trim().is_empty() || query.len() > 200 {
            return Err("search query is invalid".into());
        }
        request(
            &state,
            "GET",
            &format!("/v1/brain/semantic-search?q={}", encode_query(&query)),
            None,
        )
    }
}

blocking_backend_command! {
    backend_brain_inspect(
        path: String,
    ) state {
        request(
            &state,
            "GET",
            &format!("/v1/brain/note/inspect?path={}", encode_query(&path)),
            None,
        )
    }
}

blocking_backend_command! {
    backend_brain_note(
        path: String,
    ) state {
        request(
            &state,
            "GET",
            &format!("/v1/brain/note?path={}", encode_query(&path)),
            None,
        )
    }
}

blocking_backend_command! {
    backend_brain_save(
        path: String,
        content: String,
    ) state {
        request(
            &state,
            "POST",
            "/v1/brain/notes",
            Some(json!({"path": path, "content": content})),
        )
    }
}

blocking_backend_command! {
    backend_brain_attachments() state {
        request(&state, "GET", "/v1/brain/attachments", None)
    }
}

blocking_backend_command! {
    backend_brain_history(
        path: String,
    ) state {
        request(
            &state,
            "GET",
            &format!("/v1/brain/history?path={}", encode_query(&path)),
            None,
        )
    }
}

blocking_backend_command! {
    backend_brain_from_session(
        session_id: String,
        path: String,
    ) state {
        request(
            &state,
            "POST",
            "/v1/brain/from-session",
            Some(json!({"session_id": session_id, "path": path})),
        )
    }
}

blocking_backend_command! {
    backend_brain_document(
        path: String,
        allow_ocr: bool,
    ) state {
        request(
            &state,
            "GET",
            &format!(
                "/v1/brain/document?path={}&ocr={}",
                encode_query(&path),
                if allow_ocr { 1 } else { 0 }
            ),
            None,
        )
    }
}

blocking_backend_command! {
    backend_tasks() state {
        request(&state, "GET", "/v1/tasks", None)
    }
}

blocking_backend_command! {
    backend_task_action(
        action: String,
        task_id: Option<String>,
        prompt: Option<String>,
        schedule: Option<String>,
    ) state {
        if action == "cancel" {
            let id = task_id.ok_or("task id is required")?;
            return request(
                &state,
                "POST",
                &format!("/v1/tasks/{id}"),
                Some(json!({"action": "cancel"})),
            );
        }
        request(
            &state,
            "POST",
            "/v1/tasks",
            Some(json!({"action": action, "prompt": prompt, "schedule": schedule})),
        )
    }
}

blocking_backend_command! {
    backend_skills() state {
        request(&state, "GET", "/v1/skills", None)
    }
}

blocking_backend_command! {
    backend_skill_action(
        name: String,
        action: String,
    ) state {
        if name.trim().is_empty()
            || name.len() > 120
            || !matches!(action.as_str(), "enable" | "disable")
        {
            return Err("skill action is invalid".into());
        }
        request(
            &state,
            "POST",
            &format!("/v1/skills/{}", encode_query(&name)),
            Some(json!({"action": action})),
        )
    }
}

blocking_backend_command! {
    backend_integrations() state {
        request(&state, "GET", "/v1/integrations", None)
    }
}

blocking_backend_command! {
    backend_voice_capabilities() state {
        request(&state, "GET", "/v1/voice/capabilities", None)
    }
}

blocking_backend_command! {
    backend_voice_devices() state {
        request(&state, "GET", "/v1/voice/devices", None)
    }
}

blocking_backend_command! {
    backend_voice_transcribe(
        path: String,
        model: String,
    ) state {
        request(
            &state,
            "POST",
            "/v1/voice/transcribe",
            Some(json!({"path": path, "model": model})),
        )
    }
}

blocking_backend_command! {
    backend_voice_record(
        path: String,
        duration_seconds: f64,
        device: Option<i32>,
    ) state {
        request(
            &state,
            "POST",
            "/v1/voice/record",
            Some(json!({"path": path, "duration_seconds": duration_seconds, "device": device})),
        )
    }
}

blocking_backend_command! {
    backend_voice_speak(
        text: String,
        output_path: Option<String>,
    ) state {
        request(
            &state,
            "POST",
            "/v1/voice/speak",
            Some(json!({"text": text, "output_path": output_path})),
        )
    }
}

blocking_backend_command! {
    backend_workflows() state {
        request(&state, "GET", "/v1/workflows", None)
    }
}

blocking_backend_command! {
    backend_workflow_save(
        name: String,
        definition: Value,
        id: Option<String>,
    ) state {
        if name.trim().is_empty() || name.len() > 200 || !definition.is_object() {
            return Err("workflow definition is invalid".into());
        }
        request(
            &state,
            "POST",
            "/v1/workflows",
            Some(json!({"name": name, "definition": definition, "id": id})),
        )
    }
}

blocking_backend_command! {
    backend_workflow_run(
        id: String,
    ) state {
        if id.trim().is_empty() || id.len() > 100 {
            return Err("workflow id is invalid".into());
        }
        request(
            &state,
            "POST",
            &format!("/v1/workflows/{id}/run"),
            Some(json!({})),
        )
    }
}

blocking_backend_command! {
    backend_workflow_cancel(
        run_id: String,
    ) state {
        if run_id.trim().is_empty() || run_id.len() > 100 {
            return Err("workflow run id is invalid".into());
        }
        request(
            &state,
            "POST",
            &format!("/v1/workflow-runs/{run_id}/cancel"),
            Some(json!({})),
        )
    }
}

blocking_backend_command! {
    backend_workflow_schedule(
        id: String,
        schedule: String,
    ) state {
        if id.trim().is_empty() || id.len() > 100 || schedule.trim().is_empty() || schedule.len() > 200
        {
            return Err("workflow schedule is invalid".into());
        }
        request(
            &state,
            "POST",
            &format!("/v1/workflows/{id}/schedule"),
            Some(json!({"schedule": schedule})),
        )
    }
}

blocking_backend_command! {
    backend_workflow_runs(
        id: String,
    ) state {
        if id.trim().is_empty() || id.len() > 100 {
            return Err("workflow id is invalid".into());
        }
        request(&state, "GET", &format!("/v1/workflows/{id}/runs"), None)
    }
}

blocking_backend_command! {
    backend_integration_action(
        name: String,
        action: String,
    ) state {
        if name.trim().is_empty()
            || name.len() > 120
            || !matches!(action.as_str(), "install" | "enable" | "disable" | "revoke")
        {
            return Err("integration action is invalid".into());
        }
        request(
            &state,
            "POST",
            &format!("/v1/integrations/{}", encode_query(&name)),
            Some(json!({"action": action})),
        )
    }
}

#[tauri::command]
async fn backend_session(session_id: String, app: AppHandle) -> Result<Value, String> {
    if session_id.trim().is_empty() || session_id.len() > 200 {
        return Err("session id is invalid".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<BackendState>();
        request(&state, "GET", &format!("/v1/sessions/{session_id}"), None)
    })
    .await
    .map_err(|_| "Session worker stopped unexpectedly".to_string())?
}

blocking_backend_command! {
    backend_set_content_preference(
        preference: String,
    ) state {
        request(
            &state,
            "POST",
            "/v1/settings",
            Some(json!({"content_preference": preference})),
        )
    }
}

fn main() {
    let state = BackendState {
        child: Mutex::new(None),
        token: token(),
        stopping: AtomicBool::new(false),
        starting: AtomicBool::new(false),
        restart_attempts: AtomicU32::new(0),
        launched_at: Instant::now(),
    };
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|_, _, _| {}))
        .manage(state)
        .setup(|app| {
            let handle = app.handle().clone();
            // Render the shell immediately. Backend readiness is supervised in
            // the background so a slow database/provider cannot prevent the
            // recovery UI from opening.
            let startup_handle = handle.clone();
            thread::spawn(move || {
                for attempt in 1..=3 {
                    let state = startup_handle.state::<BackendState>();
                    match start_backend(&startup_handle, &state) {
                        Ok(()) => {
                            eprintln!("OMNI-X backend startup succeeded on attempt {attempt}");
                            return;
                        }
                        Err(error) => {
                            eprintln!("OMNI-X backend startup attempt {attempt} failed: {error}");
                            supervisor_log(&format!("startup attempt={attempt} failed: {error}"));
                            thread::sleep(Duration::from_millis(500));
                        }
                    }
                }
                supervisor_log(
                    "backend startup exhausted bounded attempts; desktop remains available",
                );
            });
            thread::spawn(move || loop {
                thread::sleep(Duration::from_secs(2));
                let state = handle.state::<BackendState>();
                if state.stopping.load(Ordering::SeqCst) {
                    break;
                }
                let needs_restart = if state.starting.load(Ordering::SeqCst) {
                    false
                } else if let Ok(mut child) = state.child.lock() {
                    match child.as_mut() {
                        Some(value) => match value.try_wait() {
                            Ok(Some(_)) => {
                                supervisor_log("owned backend exited; scheduling recovery");
                                *child = None;
                                true
                            }
                            Ok(None) => false,
                            Err(_) => {
                                supervisor_log("owned backend wait failed; scheduling recovery");
                                *child = None;
                                true
                            }
                        },
                        None => true,
                    }
                } else {
                    false
                };
                if needs_restart {
                    let attempt = state.restart_attempts.fetch_add(1, Ordering::SeqCst) + 1;
                    if attempt <= 3 {
                        eprintln!("OMNI-X backend recovery attempt {attempt}/3");
                        supervisor_log(&format!("recovery attempt={attempt}"));
                        match start_backend(&handle, &state) {
                            Ok(()) => {
                                state.restart_attempts.store(0, Ordering::SeqCst);
                                eprintln!("OMNI-X backend recovery succeeded");
                                supervisor_log("recovery succeeded");
                            }
                            Err(error) => {
                                eprintln!(
                                    "OMNI-X backend recovery attempt {attempt} failed: {error}"
                                );
                                supervisor_log(&format!(
                                    "recovery failed attempt={attempt}: {error}"
                                ));
                            }
                        }
                    } else {
                        eprintln!("OMNI-X backend recovery stopped after 3 failed attempts");
                        supervisor_log("recovery stopped after 3 attempts");
                    }
                }
            });
            // Start the backend while WebView2 initialises, using the same
            // configured window and capabilities as automatic creation.
            let window_result = tauri::WebviewWindowBuilder::from_config(
                app.handle(),
                &app.config().app.windows[0],
            )
            .and_then(|builder| builder.build());
            if let Err(error) = window_result {
                shutdown_backend(&app.state::<BackendState>());
                return Err(error.into());
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Shutdown can wait on a stalled backend. Keep that work off
                // the window thread so Windows can continue processing it.
                api.prevent_close();
                let handle = window.app_handle().clone();
                let first_close = !handle
                    .state::<BackendState>()
                    .stopping
                    .swap(true, Ordering::SeqCst);
                if first_close {
                    thread::spawn(move || {
                        shutdown_backend(&handle.state::<BackendState>());
                        handle.exit(0);
                    });
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            frontend_ready,
            backend_status,
            backend_chat,
            backend_chat_stream,
            backend_council,
            backend_stop,
            backend_approvals,
            backend_approval_decide,
            backend_settings,
            backend_models,
            backend_set_model,
            backend_brain_notes,
            backend_brain_graph,
            backend_brain_canvas,
            backend_brain_save_canvas,
            backend_memory_suggestions,
            backend_memory_decide,
            backend_brain_search,
            backend_brain_semantic_search,
            backend_brain_inspect,
            backend_brain_note,
            backend_brain_save,
            backend_brain_attachments,
            backend_brain_history,
            backend_brain_from_session,
            backend_brain_document,
            backend_tasks,
            backend_task_action,
            backend_skills,
            backend_skill_action,
            backend_integrations,
            backend_voice_capabilities,
            backend_voice_devices,
            backend_voice_transcribe,
            backend_voice_record,
            backend_voice_speak,
            backend_workflows,
            backend_workflow_save,
            backend_workflow_run,
            backend_workflow_cancel,
            backend_workflow_schedule,
            backend_workflow_runs,
            backend_integration_action,
            backend_session,
            backend_set_content_preference
        ])
        .run(tauri::generate_context!())
        .expect("error while running OMNI-X");
}

#[cfg(test)]
mod tests {
    use super::{pid_is_in_ancestry, random_token, terminate_authenticated_orphan};

    #[test]
    fn backend_response_read_is_bounded_and_validates_utf8() {
        assert_eq!(
            super::read_bounded_response(&b"hello"[..], 5).unwrap(),
            "hello"
        );
        assert!(super::read_bounded_response(&b"too long"[..], 3)
            .unwrap_err()
            .contains("size limit"));
        assert!(super::read_bounded_response(&b"\xff"[..], 3)
            .unwrap_err()
            .contains("UTF-8"));
    }

    #[test]
    fn generated_ipc_tokens_are_distinct_and_well_formed() {
        let first = random_token().expect("OS randomness");
        let second = random_token().expect("OS randomness");
        assert_eq!(first.len(), 64);
        assert!(first.bytes().all(|byte| byte.is_ascii_hexdigit()));
        assert_ne!(first, second);
    }

    fn should_restart(child_present: bool, child_exited: bool, stopping: bool) -> bool {
        !stopping && (!child_present || child_exited)
    }

    #[test]
    fn supervisor_starts_when_no_child_exists() {
        assert!(should_restart(false, false, false));
    }

    #[test]
    fn supervisor_restarts_after_unexpected_exit() {
        assert!(should_restart(true, true, false));
    }

    #[test]
    fn supervisor_does_not_restart_live_child_or_during_shutdown() {
        assert!(!should_restart(true, false, false));
        assert!(!should_restart(false, true, true));
    }

    #[test]
    fn orphan_cleanup_never_targets_desktop_process() {
        assert!(terminate_authenticated_orphan(std::process::id()).is_err());
    }

    #[cfg(windows)]
    #[test]
    fn owned_child_cleanup_stops_the_spawned_process() {
        use std::os::windows::process::CommandExt;
        use std::process::Command;
        let mut child = Command::new("powershell.exe")
            .args([
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Start-Sleep -Seconds 30",
            ])
            .creation_flags(0x0800_0000)
            .spawn()
            .expect("start owned test process");
        super::stop_owned_child(&mut child);
        assert!(child.try_wait().expect("check owned child").is_some());
    }

    #[test]
    fn packaged_backend_descendant_is_owned_but_unrelated_pid_is_not() {
        let parent = |pid| match pid {
            300 => Some(200),
            200 => Some(100),
            900 => Some(800),
            _ => None,
        };
        assert!(pid_is_in_ancestry(300, 100, parent));
        assert!(!pid_is_in_ancestry(900, 100, parent));
    }
}
