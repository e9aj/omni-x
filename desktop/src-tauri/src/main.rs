#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use serde_json::{json, Value};
use std::{io::{Read, Write}, net::{TcpStream, ToSocketAddrs}, process::{Child, Command}, sync::{atomic::{AtomicBool, Ordering}, Mutex}, thread, time::{Duration, SystemTime, UNIX_EPOCH}};
use tauri::{AppHandle, Manager, State, WindowEvent};

const PORT: u16 = 27451;

struct BackendState { child: Mutex<Option<Child>>, token: String, stopping: AtomicBool }

#[derive(Serialize)]
struct BackendStatus { connected: bool, endpoint: String, version: Option<String>, error: Option<String> }

fn token() -> String {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos();
    format!("omnix-{}-{}", std::process::id(), nanos)
}

fn request(state: &BackendState, method: &str, path: &str, payload: Option<Value>) -> Result<Value, String> {
    let mut stream = TcpStream::connect_timeout(&("127.0.0.1", PORT).to_socket_addrs().map_err(|e| e.to_string())?.next().ok_or("no loopback address")?, Duration::from_secs(2)).map_err(|e| e.to_string())?;
    stream.set_read_timeout(Some(Duration::from_secs(180))).map_err(|e| e.to_string())?;
    let body = payload.map(|value| value.to_string()).unwrap_or_default();
    let request = format!("{} {} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {}\r\nOrigin: tauri://localhost\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", method, path, state.token, body.len(), body);
    stream.write_all(request.as_bytes()).map_err(|e| e.to_string())?;
    let mut response = String::new(); stream.read_to_string(&mut response).map_err(|e| e.to_string())?;
    let status = response.lines().next().unwrap_or("");
    let json_body = response.split("\r\n\r\n").nth(1).unwrap_or("");
    let value: Value = serde_json::from_str(json_body).map_err(|e| e.to_string())?;
    if !status.contains(" 200 ") { return Err(value["error"].as_str().unwrap_or("backend request failed").to_string()); }
    Ok(value)
}

fn start_backend(app: &AppHandle, state: &BackendState) -> Result<(), String> {
    if state.stopping.load(Ordering::SeqCst) { return Err("backend is stopping".into()); }
    if state.child.lock().map_err(|_| "backend lock poisoned".to_string())?.as_ref().is_some() { return Ok(()); }
    if request(state, "GET", "/v1/health", None).is_ok() { return Ok(()); }
    if TcpStream::connect(("127.0.0.1", PORT)).is_ok() { return Err("loopback backend port is occupied by an unauthorised process".into()); }
    let bundled = app.path().resource_dir().map_err(|e| format!("backend resource path unavailable: {e}"))?.join("omnix-backend.exe");
    let mut command;
    if bundled.is_file() {
        command = Command::new(&bundled);
        command.args(["--port", &PORT.to_string()]);
        command.current_dir(app.path().resource_dir().map_err(|e| e.to_string())?);
    } else {
        let python = std::env::var("OMNIX_PYTHON").unwrap_or_else(|_| "python".into());
        command = Command::new(python);
        command.args(["-m", "omnix.desktop_server", "--port", &PORT.to_string()]);
        command.env("PYTHONPATH", std::env::var("OMNIX_PYTHONPATH").unwrap_or_else(|_| "../src".into()));
    }
    let child = command.env("OMNIX_IPC_TOKEN", &state.token).spawn().map_err(|e| format!("backend start failed: {e}"))?;
    *state.child.lock().map_err(|_| "backend lock poisoned".to_string())? = Some(child);
    for _ in 0..30 {
        if request(state, "GET", "/v1/health", None).is_ok() { return Ok(()); }
        let exited = state.child.lock().ok().and_then(|mut guard| guard.as_mut().map(|value| value.try_wait().ok().flatten().is_some())).unwrap_or(true);
        if exited { return Err("backend exited before authenticated health check".into()); }
        thread::sleep(Duration::from_millis(500));
    }
    Err("backend did not pass authenticated health check within 15 seconds".into())
}

fn shutdown_backend(state: &BackendState) {
    state.stopping.store(true, Ordering::SeqCst);
    let _ = request(state, "POST", "/v1/shutdown", Some(json!({})));
    if let Ok(mut guard) = state.child.lock() { if let Some(mut child) = guard.take() { for _ in 0..20 { if child.try_wait().ok().flatten().is_some() { return; } thread::sleep(Duration::from_millis(50)); } let _ = child.kill(); let _ = child.wait(); } }
}

#[tauri::command]
fn backend_status(state: State<'_, BackendState>) -> BackendStatus {
    match request(&state, "GET", "/v1/health", None) { Ok(value) => BackendStatus { connected: value["status"] == "ok", endpoint: format!("127.0.0.1:{PORT}"), version: value["version"].as_str().map(String::from), error: None }, Err(error) => BackendStatus { connected: false, endpoint: format!("127.0.0.1:{PORT}"), version: None, error: Some(error) } }
}

#[tauri::command]
fn backend_chat(prompt: String, session_id: Option<String>, state: State<'_, BackendState>) -> Result<Value, String> {
    if prompt.trim().is_empty() { return Err("prompt is required".into()); }
    request(&state, "POST", "/v1/chat", Some(json!({"prompt": prompt, "session_id": session_id})))
}

#[tauri::command]
fn backend_stop(state: State<'_, BackendState>) -> Result<Value, String> { request(&state, "POST", "/v1/stop", Some(json!({}))) }

#[tauri::command]
fn backend_approvals(state: State<'_, BackendState>) -> Result<Value, String> { request(&state, "GET", "/v1/approvals", None) }

#[tauri::command]
fn backend_approval_decide(id: String, decision: String, state: State<'_, BackendState>) -> Result<Value, String> {
    if decision != "approve" && decision != "reject" { return Err("invalid approval decision".into()); }
    request(&state, "POST", &format!("/v1/approvals/{id}"), Some(json!({"decision": decision})))
}

#[tauri::command]
fn backend_settings(state: State<'_, BackendState>) -> Result<Value, String> { request(&state, "GET", "/v1/settings", None) }

#[tauri::command]
fn backend_set_content_preference(preference: String, state: State<'_, BackendState>) -> Result<Value, String> {
    request(&state, "POST", "/v1/settings", Some(json!({"content_preference": preference})))
}

fn main() {
    let state = BackendState { child: Mutex::new(None), token: token(), stopping: AtomicBool::new(false) };
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|_, _, _| {}))
        .manage(state)
        .setup(|app| {
            let handle = app.handle().clone();
            { let state = handle.state::<BackendState>(); start_backend(&handle, &state).map_err(|error| Box::<dyn std::error::Error>::from(error))?; }
            thread::spawn(move || loop {
                thread::sleep(Duration::from_secs(2));
                let state = handle.state::<BackendState>();
                if state.stopping.load(Ordering::SeqCst) { break; }
                let exited = state.child.lock().ok().and_then(|mut child| child.as_mut().map(|value| value.try_wait().ok().flatten().is_some())).unwrap_or(false);
                if exited { if let Ok(mut child) = state.child.lock() { *child = None; } let _ = start_backend(&handle, &state); }
            });
            Ok(())
        })
        .on_window_event(|window, event| { if matches!(event, WindowEvent::CloseRequested { .. }) { let state = window.app_handle().state::<BackendState>(); shutdown_backend(&state); } })
        .invoke_handler(tauri::generate_handler![backend_status, backend_chat, backend_stop, backend_approvals, backend_approval_decide, backend_settings, backend_set_content_preference])
        .run(tauri::generate_context!())
        .expect("error while running OMNI-X");
}
