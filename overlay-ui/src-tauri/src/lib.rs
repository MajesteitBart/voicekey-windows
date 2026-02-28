use std::{
    net::UdpSocket,
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, PhysicalPosition, Position, State, WebviewWindow};

const UDP_ADDR: &str = "127.0.0.1:38485";
const TASKBAR_MARGIN_PX: i32 = 76;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, rename_all = "snake_case")]
struct OverlayState {
    connection: String,
    listening: String,
    processing: String,
    target: String,
    level: f64,
    visible: bool,
    message: Option<String>,
}

impl Default for OverlayState {
    fn default() -> Self {
        Self {
            connection: "checking".to_string(),
            listening: "ready".to_string(),
            processing: "idle".to_string(),
            target: "unknown".to_string(),
            level: 0.0,
            visible: false,
            message: None,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default, rename_all = "snake_case")]
struct OverlayPatch {
    connection: Option<String>,
    listening: Option<String>,
    processing: Option<String>,
    target: Option<String>,
    level: Option<f64>,
    visible: Option<bool>,
    message: Option<String>,
}

impl OverlayPatch {
    fn apply(self, state: &mut OverlayState) {
        if let Some(value) = self.connection {
            state.connection = value;
        }
        if let Some(value) = self.listening {
            state.listening = value;
        }
        if let Some(value) = self.processing {
            state.processing = value;
        }
        if let Some(value) = self.target {
            state.target = value;
        }
        if let Some(value) = self.level {
            state.level = value.clamp(0.0, 1.0);
        }
        if let Some(value) = self.visible {
            state.visible = value;
        }
        if let Some(value) = self.message {
            state.message = if value.trim().is_empty() {
                None
            } else {
                Some(value)
            };
        }
    }
}

#[derive(Default)]
struct SharedOverlayState {
    current: Mutex<OverlayState>,
}

fn emit_overlay_state(app: &AppHandle, state: &OverlayState) {
    let _ = app.emit("overlay://state", state);
}

fn lock_state(shared: &Arc<SharedOverlayState>) -> Result<std::sync::MutexGuard<'_, OverlayState>, String> {
    shared
        .current
        .lock()
        .map_err(|_| "overlay state lock poisoned".to_string())
}

#[tauri::command]
fn get_overlay_state(shared: State<'_, Arc<SharedOverlayState>>) -> Result<OverlayState, String> {
    Ok(lock_state(shared.inner())?.clone())
}

#[tauri::command]
fn set_overlay_state(
    next: OverlayState,
    app: AppHandle,
    shared: State<'_, Arc<SharedOverlayState>>,
) -> Result<(), String> {
    {
        let mut state = lock_state(shared.inner())?;
        *state = OverlayState {
            level: next.level.clamp(0.0, 1.0),
            ..next
        };
        emit_overlay_state(&app, &state);
    }
    Ok(())
}

fn start_udp_bridge(app: AppHandle, shared: Arc<SharedOverlayState>) {
    thread::spawn(move || {
        let socket = match UdpSocket::bind(UDP_ADDR) {
            Ok(socket) => socket,
            Err(error) => {
                log::error!("failed to bind UDP bridge at {}: {}", UDP_ADDR, error);
                return;
            }
        };
        let _ = socket.set_read_timeout(Some(Duration::from_millis(250)));
        log::info!("overlay UDP bridge listening on {}", UDP_ADDR);

        let mut buffer = [0_u8; 8192];
        loop {
            match socket.recv_from(&mut buffer) {
                Ok((count, _)) => {
                    let payload = match std::str::from_utf8(&buffer[..count]) {
                        Ok(text) => text,
                        Err(error) => {
                            log::warn!("invalid UTF-8 UDP payload: {}", error);
                            continue;
                        }
                    };
                    if let Ok(next) = serde_json::from_str::<OverlayState>(payload) {
                        if let Ok(mut state) = lock_state(&shared) {
                            *state = OverlayState {
                                level: next.level.clamp(0.0, 1.0),
                                ..next
                            };
                            emit_overlay_state(&app, &state);
                        }
                        continue;
                    }
                    if let Ok(patch) = serde_json::from_str::<OverlayPatch>(payload) {
                        if let Ok(mut state) = lock_state(&shared) {
                            patch.apply(&mut state);
                            emit_overlay_state(&app, &state);
                        }
                        continue;
                    }
                    log::warn!("ignored UDP payload (invalid JSON shape): {}", payload);
                }
                Err(error)
                    if error.kind() == std::io::ErrorKind::WouldBlock
                        || error.kind() == std::io::ErrorKind::TimedOut =>
                {
                    continue;
                }
                Err(error) => {
                    log::error!("overlay UDP bridge stopped: {}", error);
                    break;
                }
            }
        }
    });
}

fn position_overlay_window(window: &WebviewWindow) -> tauri::Result<()> {
    let monitor = match window.current_monitor()? {
        Some(current) => Some(current),
        None => window.primary_monitor()?,
    };
    if let Some(monitor) = monitor {
        let monitor_size = monitor.size();
        let window_size = window.outer_size()?;
        let margin = (TASKBAR_MARGIN_PX as f64 * monitor.scale_factor()) as i32;
        let x = ((monitor_size.width as i32 - window_size.width as i32) / 2).max(0);
        let y = (monitor_size.height as i32 - window_size.height as i32 - margin).max(0);
        window.set_position(Position::Physical(PhysicalPosition::new(x, y)))?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let shared = Arc::new(SharedOverlayState::default());
    let state_for_setup = shared.clone();

    tauri::Builder::default()
        .manage(shared)
        .invoke_handler(tauri::generate_handler![get_overlay_state, set_overlay_state])
        .setup(move |app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_ignore_cursor_events(true);
                let _ = position_overlay_window(&window);
            }

            if let Ok(initial) = lock_state(&state_for_setup) {
                let handle = app.handle().clone();
                emit_overlay_state(&handle, &initial);
            }

            start_udp_bridge(app.handle().clone(), state_for_setup.clone());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
