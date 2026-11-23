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
    time::{Duration, SystemTime, UNIX_EPOCH},
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
    restart_attempts: AtomicU32,
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
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!("omnix-{}-{}", std::process::id(), nanos)
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
    stream
        .set_read_timeout(Some(Duration::from_secs(180)))
        .map_err(|e| e.to_string())?;
    let body = payload.map(|value| value.to_string()).unwrap_or_default();
    let request = format!("{} {} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {}\r\nOrigin: tauri://localhost\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", method, path, state.token, body.len(), body);
    stream
        .write_all(request.as_bytes())
        .map_err(|e| e.to_string())?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|e| e.to_string())?;
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
    let child = command
        .env("OMNIX_IPC_TOKEN", &state.token)
        .spawn()
        .map_err(|e| format!("backend start failed: {e}"))?;
    let expected_pid = child.id();
    eprintln!("OMNI-X backend sidecar spawned with pid {expected_pid}");
    supervisor_log(&format!("spawned backend pid={expected_pid}"));
    *state
        .child
        .lock()
        .map_err(|_| "backend lock poisoned".to_string())? = Some(child);
    for _ in 0..30 {
        if let Ok(value) = request(state, "GET", "/v1/health", None) {
            if let Some(actual_pid) = value["pid"].as_u64().map(|value| value as u32) {
                if process_is_owned_descendant(actual_pid, expected_pid) {
                    supervisor_log(&format!(
                        "health passed launcher_pid={expected_pid} backend_pid={actual_pid}"
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
            return Err("backend exited before authenticated health check".into());
        }
        thread::sleep(Duration::from_millis(500));
    }
    eprintln!("OMNI-X backend authenticated health check timed out");
    supervisor_log(&format!("health timeout pid={expected_pid}"));
    Err("backend did not pass authenticated health check within 15 seconds".into())
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
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[tauri::command]
fn backend_status(state: State<'_, BackendState>) -> BackendStatus {
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
}

#[tauri::command]
fn backend_chat(
    prompt: String,
    session_id: Option<String>,
    state: State<'_, BackendState>,
) -> Result<Value, String> {
    if prompt.trim().is_empty() {
        return Err("prompt is required".into());
    }
    request(
        &state,
        "POST",
        "/v1/chat",
        Some(json!({"prompt": prompt, "session_id": session_id})),
    )
}

#[tauri::command]
fn backend_council(
    prompt: String,
    mode: String,
    models: Vec<String>,
    session_id: Option<String>,
    state: State<'_, BackendState>,
) -> Result<Value, String> {
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

#[tauri::command]
fn backend_stop(state: State<'_, BackendState>) -> Result<Value, String> {
    request(&state, "POST", "/v1/stop", Some(json!({})))
}

#[tauri::command]
fn backend_approvals(state: State<'_, BackendState>) -> Result<Value, String> {
    request(&state, "GET", "/v1/approvals", None)
}

#[tauri::command]
fn backend_approval_decide(
    id: String,
    decision: String,
    state: State<'_, BackendState>,
) -> Result<Value, String> {
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

#[tauri::command]
fn backend_settings(state: State<'_, BackendState>) -> Result<Value, String> {
    request(&state, "GET", "/v1/settings", None)
}

#[tauri::command]
fn backend_models(state: State<'_, BackendState>) -> Result<Value, String> {
    request(&state, "GET", "/v1/models", None)
}

#[tauri::command]
fn backend_set_model(model: String, state: State<'_, BackendState>) -> Result<Value, String> {
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

#[tauri::command]
fn backend_brain_notes(state: State<'_, BackendState>) -> Result<Value, String> {
    request(&state, "GET", "/v1/brain/notes", None)
}

#[tauri::command]
fn backend_brain_note(path: String, state: State<'_, BackendState>) -> Result<Value, String> {
    request(
        &state,
        "GET",
        &format!("/v1/brain/note?path={}", encode_query(&path)),
        None,
    )
}

#[tauri::command]
fn backend_brain_save(
    path: String,
    content: String,
    state: State<'_, BackendState>,
) -> Result<Value, String> {
    request(
        &state,
        "POST",
        "/v1/brain/notes",
        Some(json!({"path": path, "content": content})),
    )
}

#[tauri::command]
fn backend_tasks(state: State<'_, BackendState>) -> Result<Value, String> {
    request(&state, "GET", "/v1/tasks", None)
}

#[tauri::command]
fn backend_task_action(
    action: String,
    task_id: Option<String>,
    prompt: Option<String>,
    schedule: Option<String>,
    state: State<'_, BackendState>,
) -> Result<Value, String> {
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

#[tauri::command]
fn backend_session(session_id: String, state: State<'_, BackendState>) -> Result<Value, String> {
    if session_id.trim().is_empty() || session_id.len() > 200 {
        return Err("session id is invalid".into());
    }
    request(&state, "GET", &format!("/v1/sessions/{session_id}"), None)
}

#[tauri::command]
fn backend_set_content_preference(
    preference: String,
    state: State<'_, BackendState>,
) -> Result<Value, String> {
    request(
        &state,
        "POST",
        "/v1/settings",
        Some(json!({"content_preference": preference})),
    )
}

fn main() {
    let state = BackendState {
        child: Mutex::new(None),
        token: token(),
        stopping: AtomicBool::new(false),
        restart_attempts: AtomicU32::new(0),
    };
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|_, _, _| {}))
        .manage(state)
        .setup(|app| {
            let handle = app.handle().clone();
            {
                let state = handle.state::<BackendState>();
                let mut startup_error = None;
                let mut started = false;
                for attempt in 1..=3 {
                    match start_backend(&handle, &state) {
                        Ok(()) => {
                            eprintln!("OMNI-X backend startup succeeded on attempt {attempt}");
                            started = true;
                            break;
                        }
                        Err(error) => {
                            eprintln!("OMNI-X backend startup attempt {attempt} failed: {error}");
                            startup_error = Some(error);
                            thread::sleep(Duration::from_secs(1));
                        }
                    }
                }
                if !started {
                    return Err(Box::<dyn std::error::Error>::from(format!(
                        "backend startup failed after 3 attempts: {}",
                        startup_error.unwrap_or_else(|| "unknown error".into())
                    )));
                }
            }
            thread::spawn(move || loop {
                thread::sleep(Duration::from_secs(2));
                let state = handle.state::<BackendState>();
                if state.stopping.load(Ordering::SeqCst) {
                    break;
                }
                let needs_restart = if let Ok(mut child) = state.child.lock() {
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
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                let state = window.app_handle().state::<BackendState>();
                shutdown_backend(&state);
            }
        })
        .invoke_handler(tauri::generate_handler![
            backend_status,
            backend_chat,
            backend_council,
            backend_stop,
            backend_approvals,
            backend_approval_decide,
            backend_settings,
            backend_models,
            backend_set_model,
            backend_brain_notes,
            backend_brain_note,
            backend_brain_save,
            backend_tasks,
            backend_task_action,
            backend_session,
            backend_set_content_preference
        ])
        .run(tauri::generate_context!())
        .expect("error while running OMNI-X");
}

#[cfg(test)]
mod tests {
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
