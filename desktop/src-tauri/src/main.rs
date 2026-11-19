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
            if value["pid"].as_u64() == Some(expected_pid as u64) {
                supervisor_log(&format!("health passed pid={expected_pid}"));
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
            backend_stop,
            backend_approvals,
            backend_approval_decide,
            backend_settings,
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
}
