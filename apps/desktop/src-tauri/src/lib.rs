//! LoreDock desktop process boundary and Core sidecar lifecycle.

use serde::{Deserialize, Serialize};
use std::{
    env, fs,
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tauri::{Manager, RunEvent, State, WindowEvent};
use uuid::Uuid;

const CORE_START_TIMEOUT: Duration = Duration::from_secs(15);
const CORE_STOP_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct CoreConnection {
    base_url: String,
    token: String,
    api_version: String,
}

#[derive(Deserialize)]
struct VersionResponse {
    api_version: String,
}

struct CoreState {
    connection: Result<CoreConnection, String>,
    child: Mutex<Option<Child>>,
}

#[tauri::command]
fn core_connection(state: State<'_, CoreState>) -> Result<CoreConnection, String> {
    state.connection.clone()
}

fn reserve_loopback_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|error| format!("无法分配 Core 本地端口：{error}"))?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| format!("无法读取 Core 本地端口：{error}"))
}

fn core_command(resource_dir: &Path) -> Result<Command, String> {
    if let Some(executable) = env::var_os("LOREDOCK_CORE_EXECUTABLE") {
        return Ok(Command::new(executable));
    }

    let packaged = resource_dir.join(if cfg!(windows) {
        "core/loredock-core.exe"
    } else {
        "core/loredock-core"
    });
    if packaged.is_file() {
        return Ok(Command::new(packaged));
    }

    if cfg!(debug_assertions) {
        let core_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../core");
        let python = core_dir.join(if cfg!(windows) {
            ".venv/Scripts/python.exe"
        } else {
            ".venv/bin/python"
        });
        if python.is_file() {
            let mut command = Command::new(python);
            command.arg("-m").arg("loredock").current_dir(core_dir);
            return Ok(command);
        }
    }

    Err("未找到 LoreDock Core sidecar。请重新安装应用或配置 LOREDOCK_CORE_EXECUTABLE。".into())
}

fn send_request(port: u16, token: &str, method: &str, path: &str) -> Result<String, String> {
    let mut stream = TcpStream::connect(("127.0.0.1", port)).map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .map_err(|error| error.to_string())?;
    write!(
        stream,
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
    )
    .map_err(|error| error.to_string())?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| error.to_string())?;
    let (head, body) = response
        .split_once("\r\n\r\n")
        .ok_or_else(|| "Core 返回了无效的 HTTP 响应。".to_string())?;
    if !head.starts_with("HTTP/1.1 200") && !head.starts_with("HTTP/1.1 202") {
        return Err(format!(
            "Core 请求失败：{}",
            head.lines().next().unwrap_or(head)
        ));
    }
    Ok(body.to_string())
}

fn start_core(resource_dir: &Path, data_dir: &Path) -> Result<(CoreConnection, Child), String> {
    fs::create_dir_all(data_dir).map_err(|error| format!("无法创建 LoreDock 数据目录：{error}"))?;
    let port = reserve_loopback_port()?;
    let token = Uuid::new_v4().simple().to_string();
    let mut command = core_command(resource_dir)?;
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let mut child = command
        .env("LOREDOCK_HOST", "127.0.0.1")
        .env("LOREDOCK_PORT", port.to_string())
        .env("LOREDOCK_DATA_DIR", data_dir)
        .env("LOREDOCK_DESKTOP_TOKEN", &token)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("无法启动 LoreDock Core：{error}"))?;

    let started = Instant::now();
    loop {
        if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
            return Err(format!("LoreDock Core 启动时退出：{status}"));
        }
        if let Ok(body) = send_request(port, &token, "GET", "/api/v1/version") {
            let version: VersionResponse = serde_json::from_str(&body)
                .map_err(|error| format!("无法解析 Core 版本响应：{error}"))?;
            if version.api_version != "v1" {
                let _ = child.kill();
                return Err(format!("桌面端不支持 Core API {}。", version.api_version));
            }
            return Ok((
                CoreConnection {
                    base_url: format!("http://127.0.0.1:{port}"),
                    token,
                    api_version: version.api_version,
                },
                child,
            ));
        }
        if started.elapsed() >= CORE_START_TIMEOUT {
            let _ = child.kill();
            return Err("LoreDock Core 在 15 秒内没有就绪。".into());
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn stop_core(state: &CoreState) {
    let Ok(mut guard) = state.child.lock() else {
        return;
    };
    let Some(mut child) = guard.take() else {
        return;
    };
    if let Ok(connection) = &state.connection {
        let port = connection
            .base_url
            .rsplit_once(':')
            .and_then(|(_, value)| value.parse::<u16>().ok());
        if let Some(port) = port {
            let _ = send_request(port, &connection.token, "POST", "/api/v1/desktop/shutdown");
        }
    }
    let started = Instant::now();
    while started.elapsed() < CORE_STOP_TIMEOUT {
        match child.try_wait() {
            Ok(Some(_)) => return,
            Ok(None) => thread::sleep(Duration::from_millis(50)),
            Err(_) => break,
        }
    }
    let _ = child.kill();
    let _ = child.wait();
}

pub fn run() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![core_connection])
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                stop_core(&window.state::<CoreState>());
                window.app_handle().exit(0);
            }
        })
        .setup(|app| {
            let resource_dir = app.path().resource_dir()?;
            let data_dir = app.path().app_data_dir()?;
            let (connection, child) = match start_core(&resource_dir, &data_dir) {
                Ok((connection, child)) => (Ok(connection), Some(child)),
                Err(error) => (Err(error), None),
            };
            app.manage(CoreState {
                connection,
                child: Mutex::new(child),
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build LoreDock desktop application");

    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit) {
            stop_core(&handle.state::<CoreState>());
        }
    });
}

#[cfg(test)]
mod tests {
    use super::reserve_loopback_port;
    use std::net::TcpListener;

    #[test]
    fn reserves_an_available_loopback_port() {
        let port = reserve_loopback_port().expect("port should be available");
        let listener = TcpListener::bind(("127.0.0.1", port));
        assert!(listener.is_ok());
    }
}
