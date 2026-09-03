//! LoreDock desktop process boundary and Core sidecar lifecycle.

use serde::{Deserialize, Serialize};
use std::{
    env, fs,
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        Arc, Mutex,
        mpsc::{self, Receiver, RecvTimeoutError, Sender},
    },
    thread,
    time::{Duration, Instant},
};
use tauri::{Manager, RunEvent, State, WindowEvent};
use uuid::Uuid;

const CORE_START_TIMEOUT: Duration = Duration::from_secs(15);
const CORE_STOP_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_AUTOMATIC_RESTARTS: u8 = 3;

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

#[derive(Clone, Copy, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
enum CorePhase {
    Starting,
    Ready,
    Recovering,
    Failed,
    Stopped,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct CoreStatus {
    state: CorePhase,
    error_code: Option<String>,
    message: Option<String>,
    restart_count: u8,
}

struct RuntimeSnapshot {
    status: CoreStatus,
    connection: Option<CoreConnection>,
}

enum SupervisorCommand {
    Restart,
    Shutdown,
}

struct CoreState {
    snapshot: Arc<Mutex<RuntimeSnapshot>>,
    commands: Sender<SupervisorCommand>,
    supervisor: Mutex<Option<thread::JoinHandle<()>>>,
}

#[tauri::command]
fn core_connection(state: State<'_, CoreState>) -> Result<CoreConnection, String> {
    let snapshot = state
        .snapshot
        .lock()
        .map_err(|_| "无法读取 Core 运行状态。".to_string())?;
    if snapshot.status.state == CorePhase::Ready {
        snapshot
            .connection
            .clone()
            .ok_or_else(|| "Core 连接信息尚未就绪。".to_string())
    } else {
        Err(snapshot
            .status
            .message
            .clone()
            .unwrap_or_else(|| "Core 尚未就绪。".to_string()))
    }
}

#[tauri::command]
fn core_status(state: State<'_, CoreState>) -> Result<CoreStatus, String> {
    state
        .snapshot
        .lock()
        .map(|snapshot| snapshot.status.clone())
        .map_err(|_| "无法读取 Core 运行状态。".to_string())
}

#[tauri::command]
fn restart_core(state: State<'_, CoreState>) -> Result<(), String> {
    state
        .commands
        .send(SupervisorCommand::Restart)
        .map_err(|_| "Core 监督器已经停止。".to_string())
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

fn update_snapshot(
    snapshot: &Arc<Mutex<RuntimeSnapshot>>,
    state: CorePhase,
    connection: Option<CoreConnection>,
    error: Option<(&str, String)>,
    restart_count: u8,
) {
    if let Ok(mut current) = snapshot.lock() {
        current.status = CoreStatus {
            state,
            error_code: error.as_ref().map(|(code, _)| (*code).to_string()),
            message: error.map(|(_, message)| message),
            restart_count,
        };
        current.connection = connection;
    }
}

fn stop_child(child: &mut Child, connection: &CoreConnection) {
    {
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

fn wait_for_command(
    receiver: &Receiver<SupervisorCommand>,
    delay: Duration,
) -> Option<SupervisorCommand> {
    match receiver.recv_timeout(delay) {
        Ok(command) => Some(command),
        Err(RecvTimeoutError::Timeout) => None,
        Err(RecvTimeoutError::Disconnected) => Some(SupervisorCommand::Shutdown),
    }
}

fn recovery_delay(restart_count: u8) -> Option<Duration> {
    if restart_count == 0 || restart_count > MAX_AUTOMATIC_RESTARTS {
        return None;
    }
    Some(Duration::from_millis(500 * (1_u64 << (restart_count - 1))))
}

fn supervise_core(
    resource_dir: PathBuf,
    data_dir: PathBuf,
    snapshot: Arc<Mutex<RuntimeSnapshot>>,
    receiver: Receiver<SupervisorCommand>,
) {
    let mut restart_count = 0_u8;
    let mut phase = CorePhase::Starting;
    loop {
        update_snapshot(&snapshot, phase, None, None, restart_count);
        let started = start_core(&resource_dir, &data_dir);
        let (connection, mut child) = match started {
            Ok(runtime) => runtime,
            Err(message) => {
                if restart_count >= MAX_AUTOMATIC_RESTARTS {
                    update_snapshot(
                        &snapshot,
                        CorePhase::Failed,
                        None,
                        Some(("core_start_failed", message)),
                        restart_count,
                    );
                    match receiver.recv() {
                        Ok(SupervisorCommand::Restart) => {
                            restart_count = 0;
                            phase = CorePhase::Starting;
                        }
                        Ok(SupervisorCommand::Shutdown) | Err(_) => {
                            update_snapshot(
                                &snapshot,
                                CorePhase::Stopped,
                                None,
                                None,
                                restart_count,
                            );
                            return;
                        }
                    }
                    continue;
                }
                restart_count += 1;
                phase = CorePhase::Recovering;
                update_snapshot(
                    &snapshot,
                    phase,
                    None,
                    Some(("core_start_failed", message)),
                    restart_count,
                );
                let delay = recovery_delay(restart_count).unwrap_or_default();
                match wait_for_command(&receiver, delay) {
                    Some(SupervisorCommand::Shutdown) => {
                        update_snapshot(&snapshot, CorePhase::Stopped, None, None, restart_count);
                        return;
                    }
                    Some(SupervisorCommand::Restart) => {
                        restart_count = 0;
                        phase = CorePhase::Starting;
                    }
                    None => {}
                }
                continue;
            }
        };

        update_snapshot(
            &snapshot,
            CorePhase::Ready,
            Some(connection.clone()),
            None,
            restart_count,
        );
        loop {
            match wait_for_command(&receiver, Duration::from_millis(250)) {
                Some(SupervisorCommand::Shutdown) => {
                    stop_child(&mut child, &connection);
                    update_snapshot(&snapshot, CorePhase::Stopped, None, None, restart_count);
                    return;
                }
                Some(SupervisorCommand::Restart) => {
                    stop_child(&mut child, &connection);
                    restart_count = 0;
                    phase = CorePhase::Starting;
                    break;
                }
                None => match child.try_wait() {
                    Ok(Some(status)) => {
                        restart_count += 1;
                        if restart_count > MAX_AUTOMATIC_RESTARTS {
                            update_snapshot(
                                &snapshot,
                                CorePhase::Failed,
                                None,
                                Some((
                                    "core_restart_exhausted",
                                    format!("Core 反复异常退出，最后状态为 {status}。"),
                                )),
                                MAX_AUTOMATIC_RESTARTS,
                            );
                            restart_count = MAX_AUTOMATIC_RESTARTS;
                            phase = CorePhase::Failed;
                        } else {
                            update_snapshot(
                                &snapshot,
                                CorePhase::Recovering,
                                None,
                                Some((
                                    "core_exited_unexpectedly",
                                    format!("Core 意外退出（{status}），正在恢复。"),
                                )),
                                restart_count,
                            );
                            phase = CorePhase::Recovering;
                            let delay = recovery_delay(restart_count).unwrap_or_default();
                            match wait_for_command(&receiver, delay) {
                                Some(SupervisorCommand::Shutdown) => {
                                    update_snapshot(
                                        &snapshot,
                                        CorePhase::Stopped,
                                        None,
                                        None,
                                        restart_count,
                                    );
                                    return;
                                }
                                Some(SupervisorCommand::Restart) => {
                                    restart_count = 0;
                                    phase = CorePhase::Starting;
                                }
                                None => {}
                            }
                        }
                        break;
                    }
                    Ok(None) => {}
                    Err(error) => {
                        update_snapshot(
                            &snapshot,
                            CorePhase::Failed,
                            None,
                            Some(("core_process_check_failed", error.to_string())),
                            restart_count,
                        );
                        phase = CorePhase::Failed;
                        break;
                    }
                },
            }
        }

        if phase == CorePhase::Failed {
            match receiver.recv() {
                Ok(SupervisorCommand::Restart) => {
                    restart_count = 0;
                    phase = CorePhase::Starting;
                }
                Ok(SupervisorCommand::Shutdown) | Err(_) => {
                    update_snapshot(&snapshot, CorePhase::Stopped, None, None, restart_count);
                    return;
                }
            }
        }
    }
}

fn stop_core(state: &CoreState) {
    let _ = state.commands.send(SupervisorCommand::Shutdown);
    if let Ok(mut supervisor) = state.supervisor.lock()
        && let Some(handle) = supervisor.take()
    {
        let _ = handle.join();
    }
}

pub fn run() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            core_connection,
            core_status,
            restart_core
        ])
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                stop_core(&window.state::<CoreState>());
                window.app_handle().exit(0);
            }
        })
        .setup(|app| {
            let resource_dir = app.path().resource_dir()?;
            let data_dir = app.path().app_data_dir()?;
            let snapshot = Arc::new(Mutex::new(RuntimeSnapshot {
                status: CoreStatus {
                    state: CorePhase::Starting,
                    error_code: None,
                    message: None,
                    restart_count: 0,
                },
                connection: None,
            }));
            let (sender, receiver) = mpsc::channel();
            let supervisor_snapshot = Arc::clone(&snapshot);
            let supervisor = thread::Builder::new()
                .name("loredock-core-supervisor".into())
                .spawn(move || {
                    supervise_core(resource_dir, data_dir, supervisor_snapshot, receiver);
                })?;
            app.manage(CoreState {
                snapshot,
                commands: sender,
                supervisor: Mutex::new(Some(supervisor)),
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
    use super::{
        CoreConnection, CorePhase, CoreStatus, RuntimeSnapshot, recovery_delay,
        reserve_loopback_port, update_snapshot,
    };
    use std::net::TcpListener;
    use std::sync::{Arc, Mutex};
    use std::time::Duration;

    #[test]
    fn reserves_an_available_loopback_port() {
        let port = reserve_loopback_port().expect("port should be available");
        let listener = TcpListener::bind(("127.0.0.1", port));
        assert!(listener.is_ok());
    }

    #[test]
    fn recovery_policy_is_bounded_and_uses_exponential_backoff() {
        assert_eq!(recovery_delay(0), None);
        assert_eq!(recovery_delay(1), Some(Duration::from_millis(500)));
        assert_eq!(recovery_delay(2), Some(Duration::from_secs(1)));
        assert_eq!(recovery_delay(3), Some(Duration::from_secs(2)));
        assert_eq!(recovery_delay(4), None);
    }

    #[test]
    fn failure_status_clears_secret_connection_details() {
        let snapshot = Arc::new(Mutex::new(RuntimeSnapshot {
            status: CoreStatus {
                state: CorePhase::Ready,
                error_code: None,
                message: None,
                restart_count: 0,
            },
            connection: Some(CoreConnection {
                base_url: "http://127.0.0.1:12345".into(),
                token: "secret-token".into(),
                api_version: "v1".into(),
            }),
        }));
        update_snapshot(
            &snapshot,
            CorePhase::Failed,
            None,
            Some(("core_restart_exhausted", "Core failed".into())),
            3,
        );
        let snapshot = snapshot.lock().expect("snapshot should be readable");
        assert!(snapshot.connection.is_none());
        let serialized = serde_json::to_string(&snapshot.status).expect("status should serialize");
        assert!(!serialized.contains("secret-token"));
        assert!(serialized.contains("core_restart_exhausted"));
    }
}
