use crate::config_store::{
    append_desktop_log, daemon_log_path, desktop_log_path, epoch_iso_approx, load_desktop_config,
    read_or_create_daemon_token, resolve_data_dir, token_file_path, DesktopConfig,
};
use crate::version::{APP_VERSION, MIN_PYTHON_VERSION, PROTOCOL_VERSION};
use serde::Serialize;
use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "PascalCase")]
pub enum LaunchMode {
    None,
    ExternalIndependent,
    BundledSidecar,
    PythonModule,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BridgeProbeResult {
    pub endpoint: String,
    pub status: String,
    pub http_status: Option<u16>,
    pub latency_ms: Option<u64>,
    pub message: String,
    pub checked_at: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DaemonLifecycleStatus {
    pub running: bool,
    pub supervised_by_shell: bool,
    pub launch_mode: LaunchMode,
    pub pid: Option<u32>,
    pub endpoint: String,
    pub daemon_version: Option<String>,
    pub data_dir: String,
    pub sidecar_path: Option<String>,
    pub keep_alive_on_exit: bool,
    pub last_started_at: Option<String>,
    pub last_error: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopDiagnosticsReport {
    pub app_version: String,
    pub protocol_version: String,
    pub os: String,
    pub arch: String,
    pub data_dir: String,
    pub token_configured: bool,
    pub desktop_log_path: String,
    pub desktop_log_bytes: u64,
    pub daemon_log_path: String,
    pub daemon_log_bytes: u64,
    pub python_check: String,
    pub sidecar_detected: bool,
    pub sidecar_path: Option<String>,
    pub lifecycle: DaemonLifecycleStatus,
    pub daemon_health: Option<serde_json::Value>,
    pub daemon_diagnostics: Option<serde_json::Value>,
    pub bundled_adapters: BundledAdapterStatus,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BundledAdapterStatus {
    pub unity_staged: bool,
    pub unity_path: String,
    pub godot_staged: bool,
    pub godot_path: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AdapterInstallGuide {
    pub engine: String,
    pub display_name: String,
    pub resource_path: String,
    pub staged_present: bool,
    pub min_engine_version: String,
    pub default_endpoint: String,
    pub steps: Vec<String>,
}

pub struct DaemonSupervisor {
    child: Option<Child>,
    launch_mode: LaunchMode,
    last_started_at: Option<String>,
    last_error: Option<String>,
    resource_dir: Option<PathBuf>,
}

impl DaemonSupervisor {
    pub fn new(resource_dir: Option<PathBuf>) -> Self {
        Self {
            child: None,
            launch_mode: LaunchMode::None,
            last_started_at: None,
            last_error: None,
            resource_dir,
        }
    }

    pub fn set_resource_dir(&mut self, resource_dir: Option<PathBuf>) {
        self.resource_dir = resource_dir;
    }

    fn refresh_child_liveness(&mut self) {
        if let Some(child) = self.child.as_mut() {
            match child.try_wait() {
                Ok(Some(_status)) => {
                    self.child = None;
                    if self.launch_mode != LaunchMode::ExternalIndependent {
                        self.launch_mode = LaunchMode::None;
                    }
                }
                Ok(None) => {}
                Err(err) => {
                    self.last_error = Some(format!("Failed polling child daemon status: {err}"));
                }
            }
        }
    }

    fn find_sidecar_binary() -> Option<PathBuf> {
        let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
        let target_triple = format!("{}-{}", std::env::consts::ARCH, target_os_triple());
        let candidates = if cfg!(target_os = "windows") {
            vec![
                exe_dir.join("nexus-daemon.exe"),
                exe_dir.join(format!("nexus-daemon-{target_triple}.exe")),
                exe_dir.join("binaries").join("nexus-daemon.exe"),
                exe_dir
                    .join("binaries")
                    .join(format!("nexus-daemon-{target_triple}.exe")),
            ]
        } else {
            vec![
                exe_dir.join("nexus-daemon"),
                exe_dir.join(format!("nexus-daemon-{target_triple}")),
                exe_dir.join("binaries").join("nexus-daemon"),
                exe_dir
                    .join("binaries")
                    .join(format!("nexus-daemon-{target_triple}")),
            ]
        };
        candidates.into_iter().find(|path| path.is_file())
    }

    fn resolve_adapter_root(&self) -> PathBuf {
        if let Some(res_dir) = &self.resource_dir {
            let staged = res_dir.join("resources").join("adapters");
            if staged.exists() {
                return staged;
            }
            let direct = res_dir.join("adapters");
            if direct.exists() {
                return direct;
            }
        }
        if let Ok(cwd) = std::env::current_dir() {
            let dev_staged = cwd.join("apps/desktop/src-tauri/resources/adapters");
            if dev_staged.exists() {
                return dev_staged;
            }
            let repo_adapters = cwd.join("adapters");
            if repo_adapters.exists() {
                return repo_adapters;
            }
        }
        PathBuf::from("adapters")
    }

    pub fn probe_health(&mut self, endpoint: &str) -> BridgeProbeResult {
        let (host, port) = parse_host_port(endpoint, "127.0.0.1", 47100);
        let url = format!("http://{host}:{port}/health");
        let started = Instant::now();
        match http_loopback_request(&host, port, "GET", "/health", None, None, Duration::from_millis(1800)) {
            Ok((status_code, body)) => {
                let elapsed = started.elapsed().as_millis() as u64;
                if status_code >= 200 && status_code < 300 {
                    let parsed = serde_json::from_str::<serde_json::Value>(&body).ok();
                    let service = parsed
                        .as_ref()
                        .and_then(|v| v.get("service"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("nexus-python-daemon");
                    let pid = parsed
                        .as_ref()
                        .and_then(|v| v.get("pid"))
                        .and_then(|v| v.as_u64())
                        .map(|p| p.to_string())
                        .unwrap_or_else(|| "N/A".to_string());
                    BridgeProbeResult {
                        endpoint: url,
                        status: "Connected".to_string(),
                        http_status: Some(status_code),
                        latency_ms: Some(elapsed),
                        message: format!("Daemon responded ({service} · PID {pid})."),
                        checked_at: epoch_iso_approx(),
                    }
                } else {
                    BridgeProbeResult {
                        endpoint: url,
                        status: "Failed".to_string(),
                        http_status: Some(status_code),
                        latency_ms: Some(elapsed),
                        message: format!("Daemon returned HTTP {status_code} on /health."),
                        checked_at: epoch_iso_approx(),
                    }
                }
            }
            Err(err) => BridgeProbeResult {
                endpoint: url,
                status: "Disconnected".to_string(),
                http_status: None,
                latency_ms: Some(started.elapsed().as_millis() as u64),
                message: format!("Local NEXUS daemon not reachable on loopback ({err})."),
                checked_at: epoch_iso_approx(),
            },
        }
    }

    pub fn start_background_daemon(&mut self, cfg: &DesktopConfig) -> DaemonLifecycleStatus {
        self.refresh_child_liveness();
        let data_dir = resolve_data_dir(Some(cfg));
        let token = match read_or_create_daemon_token(&data_dir) {
            Ok(tok) => tok,
            Err(err) => {
                self.last_error = Some(err);
                return self.lifecycle_status(cfg);
            }
        };

        if let Ok((200, _)) = http_loopback_request(
            &cfg.bind_host,
            cfg.rest_port,
            "GET",
            "/health",
            None,
            None,
            Duration::from_millis(600),
        ) {
            if self.child.is_none() {
                self.launch_mode = LaunchMode::ExternalIndependent;
            }
            self.last_error = None;
            append_desktop_log(
                &data_dir,
                "INFO",
                "daemon.attached",
                "Attached to already-running local NEXUS daemon.",
            );
            return self.lifecycle_status(cfg);
        }

        let log_file = daemon_log_path(&data_dir);
        let sidecar = Self::find_sidecar_binary();
        let prefer_python = cfg.daemon_mode == "python-service";

        let spawn_result = if !prefer_python {
            if let Some(sidecar_bin) = &sidecar {
                self.launch_mode = LaunchMode::BundledSidecar;
                spawn_sidecar(sidecar_bin, cfg, &data_dir, &log_file, &token)
            } else {
                self.launch_mode = LaunchMode::PythonModule;
                spawn_python_module(cfg, &data_dir, &log_file, &token)
            }
        } else {
            self.launch_mode = LaunchMode::PythonModule;
            spawn_python_module(cfg, &data_dir, &log_file, &token)
        };

        match spawn_result {
            Ok(child) => {
                let pid = child.id();
                self.child = Some(child);
                self.last_started_at = Some(epoch_iso_approx());
                self.last_error = None;
                append_desktop_log(
                    &data_dir,
                    "INFO",
                    "daemon.spawned",
                    &format!("Spawned NEXUS background daemon (PID {pid})."),
                );

                // Wait briefly for loopback listener readiness without freezing long.
                let deadline = Instant::now() + Duration::from_millis(4000);
                while Instant::now() < deadline {
                    if let Ok((200, _)) = http_loopback_request(
                        &cfg.bind_host,
                        cfg.rest_port,
                        "GET",
                        "/health",
                        None,
                        None,
                        Duration::from_millis(350),
                    ) {
                        break;
                    }
                    thread::sleep(Duration::from_millis(120));
                }
            }
            Err(err) => {
                self.launch_mode = LaunchMode::None;
                self.last_error = Some(err.clone());
                append_desktop_log(&data_dir, "ERROR", "daemon.spawn_failed", &err);
            }
        }

        self.lifecycle_status(cfg)
    }

    pub fn stop_background_daemon(&mut self, cfg: &DesktopConfig, force_external: bool) -> DaemonLifecycleStatus {
        self.refresh_child_liveness();
        let data_dir = resolve_data_dir(Some(cfg));

        if self.child.is_none() && !force_external {
            return self.lifecycle_status(cfg);
        }

        if let Ok(token) = read_or_create_daemon_token(&data_dir) {
            let _ = http_loopback_request(
                &cfg.bind_host,
                cfg.rest_port,
                "POST",
                "/api/v1/daemon/shutdown",
                Some(&token),
                Some("{}"),
                Duration::from_millis(1200),
            );
        }

        if let Some(mut child) = self.child.take() {
            let deadline = Instant::now() + Duration::from_millis(2500);
            let mut exited = false;
            while Instant::now() < deadline {
                if matches!(child.try_wait(), Ok(Some(_))) {
                    exited = true;
                    break;
                }
                thread::sleep(Duration::from_millis(100));
            }
            if !exited {
                let _ = child.kill();
                let _ = child.wait();
            }
        }

        self.launch_mode = LaunchMode::None;
        append_desktop_log(&data_dir, "INFO", "daemon.stopped", "Background daemon stopped.");
        self.lifecycle_status(cfg)
    }

    pub fn shutdown_on_app_exit(&mut self, cfg: &DesktopConfig) {
        let data_dir = resolve_data_dir(Some(cfg));
        if cfg.keep_daemon_alive_on_exit || self.launch_mode == LaunchMode::ExternalIndependent {
            append_desktop_log(
                &data_dir,
                "INFO",
                "app.exit.keep_daemon",
                "Desktop UI exiting while leaving background daemon running independently.",
            );
            return;
        }
        let _ = self.stop_background_daemon(cfg, false);
    }

    pub fn lifecycle_status(&mut self, cfg: &DesktopConfig) -> DaemonLifecycleStatus {
        self.refresh_child_liveness();
        let data_dir = resolve_data_dir(Some(cfg));
        let health_json = http_loopback_request(
            &cfg.bind_host,
            cfg.rest_port,
            "GET",
            "/health",
            None,
            None,
            Duration::from_millis(600),
        )
        .ok()
        .and_then(|(code, body)| {
            if code == 200 {
                serde_json::from_str::<serde_json::Value>(&body).ok()
            } else {
                None
            }
        });

        let running = health_json.is_some();
        let pid = self
            .child
            .as_ref()
            .map(|c| c.id())
            .or_else(|| {
                health_json
                    .as_ref()
                    .and_then(|v| v.get("pid"))
                    .and_then(|p| p.as_u64())
                    .map(|p| p as u32)
            });
        let daemon_version = health_json
            .as_ref()
            .and_then(|v| v.get("version"))
            .and_then(|s| s.as_str())
            .map(|s| s.to_string());

        let effective_mode = if self.child.is_some() {
            self.launch_mode.clone()
        } else if running {
            LaunchMode::ExternalIndependent
        } else {
            LaunchMode::None
        };

        DaemonLifecycleStatus {
            running,
            supervised_by_shell: self.child.is_some(),
            launch_mode: effective_mode,
            pid,
            endpoint: format!("http://{}:{}", cfg.bind_host, cfg.rest_port),
            daemon_version,
            data_dir: data_dir.display().to_string(),
            sidecar_path: Self::find_sidecar_binary().map(|p| p.display().to_string()),
            keep_alive_on_exit: cfg.keep_daemon_alive_on_exit,
            last_started_at: self.last_started_at.clone(),
            last_error: self.last_error.clone(),
        }
    }

    pub fn collect_diagnostics(&mut self, cfg: &DesktopConfig) -> DesktopDiagnosticsReport {
        let data_dir = resolve_data_dir(Some(cfg));
        let token = read_or_create_daemon_token(&data_dir).ok();
        let desktop_log = desktop_log_path(&data_dir);
        let daemon_log = daemon_log_path(&data_dir);

        let daemon_health = http_loopback_request(
            &cfg.bind_host,
            cfg.rest_port,
            "GET",
            "/health",
            None,
            None,
            Duration::from_millis(800),
        )
        .ok()
        .and_then(|(c, b)| if c == 200 { serde_json::from_str(&b).ok() } else { None });

        let daemon_diagnostics = token.as_deref().and_then(|tok| {
            http_loopback_request(
                &cfg.bind_host,
                cfg.rest_port,
                "GET",
                "/api/v1/diagnostics",
                Some(tok),
                None,
                Duration::from_millis(1200),
            )
            .ok()
            .and_then(|(c, b)| if c == 200 { serde_json::from_str(&b).ok() } else { None })
        });

        let python_check = check_python_version(&cfg.python_executable);
        let sidecar = Self::find_sidecar_binary();
        let adapter_root = self.resolve_adapter_root();
        let unity_path = adapter_root.join("unity");
        let godot_path = adapter_root.join("godot").join("addons").join("nexus_bridge");

        DesktopDiagnosticsReport {
            app_version: APP_VERSION.to_string(),
            protocol_version: PROTOCOL_VERSION.to_string(),
            os: std::env::consts::OS.to_string(),
            arch: std::env::consts::ARCH.to_string(),
            data_dir: data_dir.display().to_string(),
            token_configured: token_file_path(&data_dir).exists(),
            desktop_log_path: desktop_log.display().to_string(),
            desktop_log_bytes: fs::metadata(&desktop_log).map(|m| m.len()).unwrap_or(0),
            daemon_log_path: daemon_log.display().to_string(),
            daemon_log_bytes: fs::metadata(&daemon_log).map(|m| m.len()).unwrap_or(0),
            python_check,
            sidecar_detected: sidecar.is_some(),
            sidecar_path: sidecar.map(|p| p.display().to_string()),
            lifecycle: self.lifecycle_status(cfg),
            daemon_health,
            daemon_diagnostics,
            bundled_adapters: BundledAdapterStatus {
                unity_staged: unity_path.join("nexus-adapter.manifest.json").is_file(),
                unity_path: unity_path.display().to_string(),
                godot_staged: godot_path.join("plugin.cfg").is_file(),
                godot_path: godot_path.display().to_string(),
            },
        }
    }

    pub fn get_adapter_install_instructions(&self, cfg: &DesktopConfig) -> Vec<AdapterInstallGuide> {
        let adapter_root = self.resolve_adapter_root();
        let unity_dir = adapter_root.join("unity");
        let godot_dir = adapter_root.join("godot").join("addons").join("nexus_bridge");
        let data_dir = resolve_data_dir(Some(cfg));
        let token_hint = token_file_path(&data_dir).display().to_string();
        let rest_endpoint = format!("http://{}:{}", cfg.bind_host, cfg.rest_port);
        let ws_endpoint = format!("ws://{}:{}/events", cfg.bind_host, cfg.ws_port);

        vec![
            AdapterInstallGuide {
                engine: "unity".to_string(),
                display_name: "Unity Editor 2022.3 LTS+ (UPM Local Package)".to_string(),
                resource_path: unity_dir.display().to_string(),
                staged_present: unity_dir.join("package.json").is_file(),
                min_engine_version: "2022.3 LTS / Unity 6".to_string(),
                default_endpoint: rest_endpoint.clone(),
                steps: vec![
                    "Open your Unity project in Unity Editor on Windows.".to_string(),
                    "Navigate to Window > Package Manager > + > Add package from disk...".to_string(),
                    format!("Select {}\\package.json.", unity_dir.display()),
                    "Open Window > NEXUS Bridge and confirm the daemon endpoint and local token.".to_string(),
                    format!("Token file: {token_hint} (also settable via NEXUS_API_TOKEN)."),
                ],
            },
            AdapterInstallGuide {
                engine: "godot".to_string(),
                display_name: "Godot Engine 4.2+ (EditorPlugin Addon)".to_string(),
                resource_path: godot_dir.display().to_string(),
                staged_present: godot_dir.join("plugin.cfg").is_file(),
                min_engine_version: "4.2+".to_string(),
                default_endpoint: ws_endpoint,
                steps: vec![
                    format!("Copy {} into <YourGodotProject>/addons/nexus_bridge/.", godot_dir.display()),
                    "Open your Godot 4 project and open Project > Project Settings > Plugins.".to_string(),
                    "Enable the NEXUS Bridge EditorPlugin.".to_string(),
                    format!("Verify connection to {rest_endpoint} (token loaded automatically from {token_hint})."),
                ],
            },
        ]
    }
}

fn target_os_triple() -> &'static str {
    if cfg!(target_os = "windows") {
        "pc-windows-msvc"
    } else if cfg!(target_os = "macos") {
        "apple-darwin"
    } else {
        "unknown-linux-gnu"
    }
}

fn spawn_sidecar(
    sidecar_bin: &Path,
    cfg: &DesktopConfig,
    data_dir: &Path,
    log_file: &Path,
    token: &str,
) -> Result<Child, String> {
    let mut cmd = Command::new(sidecar_bin);
    cmd.args([
        "--serve",
        "--data-dir",
        &data_dir.display().to_string(),
        "--bind-host",
        &cfg.bind_host,
        "--rest-port",
        &cfg.rest_port.to_string(),
        "--log-file",
        &log_file.display().to_string(),
    ]);
    configure_daemon_env(&mut cmd, cfg, data_dir, log_file, token);
    cmd.spawn()
        .map_err(|e| format!("Failed spawning sidecar {}: {e}", sidecar_bin.display()))
}

fn spawn_python_module(
    cfg: &DesktopConfig,
    data_dir: &Path,
    log_file: &Path,
    token: &str,
) -> Result<Child, String> {
    let mut cmd = Command::new(&cfg.python_executable);
    cmd.args([
        "-m",
        "core.nexus_core",
        "--serve",
        "--data-dir",
        &data_dir.display().to_string(),
        "--bind-host",
        &cfg.bind_host,
        "--rest-port",
        &cfg.rest_port.to_string(),
        "--log-file",
        &log_file.display().to_string(),
    ]);
    configure_daemon_env(&mut cmd, cfg, data_dir, log_file, token);
    cmd.spawn()
        .map_err(|e| format!("Failed starting '{}' (-m core.nexus_core): {e}", cfg.python_executable))
}

fn configure_daemon_env(
    cmd: &mut Command,
    cfg: &DesktopConfig,
    data_dir: &Path,
    log_file: &Path,
    token: &str,
) {
    cmd.env("NEXUS_DATA_DIR", data_dir)
        .env("NEXUS_SQLITE_PATH", data_dir.join("nexus.db"))
        .env("NEXUS_BIND_HOST", &cfg.bind_host)
        .env("NEXUS_REST_PORT", cfg.rest_port.to_string())
        .env("NEXUS_WS_PORT", cfg.ws_port.to_string())
        .env("NEXUS_MCP_PORT", cfg.mcp_http_port.to_string())
        .env("NEXUS_LOG_FILE", log_file)
        .env("NEXUS_API_TOKEN", token)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
}

fn check_python_version(python_exe: &str) -> String {
    let mut cmd = Command::new(python_exe);
    cmd.arg("--version");
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    match cmd.output() {
        Ok(out) => {
            let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
            let err_text = String::from_utf8_lossy(&out.stderr).trim().to_string();
            let version_line = if text.is_empty() { err_text } else { text };
            if version_line.is_empty() {
                format!("Available (target >= {MIN_PYTHON_VERSION})")
            } else {
                version_line
            }
        }
        Err(e) => format!("Not detected ({e}); sidecar binary recommended"),
    }
}

pub fn parse_host_port(endpoint: &str, default_host: &str, default_port: u16) -> (String, u16) {
    let stripped = endpoint
        .trim()
        .trim_start_matches("http://")
        .trim_start_matches("https://");
    let authority = stripped.split('/').next().unwrap_or("");
    if let Some(rest) = authority.strip_prefix('[') {
        if let Some((host_inner, after_bracket)) = rest.split_once(']') {
            let clean_host = if host_inner.is_empty() {
                default_host
            } else {
                host_inner
            };
            let port = after_bracket
                .strip_prefix(':')
                .and_then(|p| p.parse::<u16>().ok())
                .unwrap_or(default_port);
            return (clean_host.to_string(), port);
        }
    }
    if authority == "::1" {
        return ("::1".to_string(), default_port);
    }
    if let Some((h, p)) = authority.rsplit_once(':') {
        let host = if h.is_empty() { default_host } else { h };
        let port = p.parse::<u16>().unwrap_or(default_port);
        return (host.to_string(), port);
    }
    if !authority.is_empty() {
        return (authority.to_string(), default_port);
    }
    (default_host.to_string(), default_port)
}

pub fn http_loopback_request(
    host: &str,
    port: u16,
    method: &str,
    path: &str,
    bearer_token: Option<&str>,
    body: Option<&str>,
    timeout: Duration,
) -> Result<(u16, String), String> {
    let clean_host = host.trim().trim_start_matches('[').trim_end_matches(']');
    if clean_host != "127.0.0.1" && clean_host != "localhost" && clean_host != "::1" {
        return Err(format!("Loopback policy rejected host '{host}'."));
    }
    let addr_str = if clean_host == "localhost" {
        format!("127.0.0.1:{port}")
    } else if clean_host == "::1" {
        format!("[::1]:{port}")
    } else {
        format!("{clean_host}:{port}")
    };
    let addr: SocketAddr = addr_str
        .parse()
        .map_err(|e| format!("Invalid socket address {addr_str}: {e}"))?;
    let mut stream =
        TcpStream::connect_timeout(&addr, timeout).map_err(|e| format!("connect error: {e}"))?;
    let _ = stream.set_read_timeout(Some(timeout));
    let _ = stream.set_write_timeout(Some(timeout));

    let payload = body.unwrap_or("");
    let host_header = if clean_host == "::1" {
        format!("[::1]:{port}")
    } else {
        format!("{clean_host}:{port}")
    };
    let mut req = format!(
        "{method} {path} HTTP/1.1\r\nHost: {host_header}\r\nAccept: application/json\r\nConnection: close\r\n"
    );
    if let Some(tok) = bearer_token {
        req.push_str(&format!("Authorization: Bearer {tok}\r\n"));
    }
    if !payload.is_empty() {
        req.push_str("Content-Type: application/json\r\n");
        req.push_str(&format!("Content-Length: {}\r\n", payload.len()));
    }
    req.push_str("\r\n");
    if !payload.is_empty() {
        req.push_str(payload);
    }

    stream
        .write_all(req.as_bytes())
        .map_err(|e| format!("write error: {e}"))?;

    let mut raw = Vec::new();
    stream
        .read_to_end(&mut raw)
        .map_err(|e| format!("read error: {e}"))?;
    let text = String::from_utf8_lossy(&raw).to_string();
    let (head, resp_body) = text
        .split_once("\r\n\r\n")
        .unwrap_or((text.as_str(), ""));
    let status_line = head.lines().next().unwrap_or("");
    let status_code = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|s| s.parse::<u16>().ok())
        .ok_or_else(|| format!("Malformed HTTP response status: {status_line}"))?;

    Ok((status_code, resp_body.to_string()))
}
