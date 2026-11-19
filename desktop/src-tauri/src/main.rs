#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::{io::{Read, Write}, net::TcpStream, process::{Child, Command}, sync::Mutex, time::{SystemTime, UNIX_EPOCH}};
use tauri::{Manager, State};

const PORT: u16 = 27451;

struct BackendState { child: Mutex<Option<Child>>, token: String }

#[derive(Serialize)]
struct BackendStatus { connected: bool, endpoint: String, version: Option<String>, error: Option<String> }

fn token() -> String {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos();
    format!("omnix-{}-{}", std::process::id(), nanos)
}

fn start_backend(state: &BackendState) -> Result<(), String> {
    if TcpStream::connect(("127.0.0.1", PORT)).is_ok() { return Ok(()); }
    let python = std::env::var("OMNIX_PYTHON").unwrap_or_else(|_| "python".into());
    let python_path = std::env::var("OMNIX_PYTHONPATH").unwrap_or_else(|_| "../src".into());
    let child = Command::new(python).args(["-m", "omnix.desktop_server", "--port", &PORT.to_string()]).env("OMNIX_IPC_TOKEN", &state.token).env("PYTHONPATH", python_path).spawn().map_err(|e| format!("backend start failed: {e}"))?;
    *state.child.lock().map_err(|_| "backend lock poisoned".to_string())? = Some(child);
    Ok(())
}

#[tauri::command]
fn backend_status(state: State<'_, BackendState>) -> BackendStatus {
    let mut stream = match TcpStream::connect(("127.0.0.1", PORT)) { Ok(value) => value, Err(error) => return BackendStatus { connected: false, endpoint: "127.0.0.1:27451".into(), version: None, error: Some(error.to_string()) } };
    let request = format!("GET /v1/health HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n", state.token);
    if let Err(error) = stream.write_all(request.as_bytes()) { return BackendStatus { connected: false, endpoint: "127.0.0.1:27451".into(), version: None, error: Some(error.to_string()) }; }
    let mut response = String::new(); let _ = stream.read_to_string(&mut response);
    let body = response.split("\r\n\r\n").nth(1).unwrap_or("");
    match serde_json::from_str::<serde_json::Value>(body) { Ok(json) => BackendStatus { connected: json["status"] == "ok", endpoint: "127.0.0.1:27451".into(), version: json["version"].as_str().map(String::from), error: None }, Err(error) => BackendStatus { connected: false, endpoint: "127.0.0.1:27451".into(), version: None, error: Some(error.to_string()) } }
}

fn main() {
    let state = BackendState { child: Mutex::new(None), token: token() };
    tauri::Builder::default().manage(state).setup(|app| { let state = app.state::<BackendState>(); start_backend(&state).map_err(|error| Box::<dyn std::error::Error>::from(error))?; Ok(()) }).invoke_handler(tauri::generate_handler![backend_status]).run(tauri::generate_context!()).expect("error while running OMNI-X");
}
