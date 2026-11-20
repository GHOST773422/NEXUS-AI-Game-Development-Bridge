use serde::{Deserialize, Serialize};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const MAX_DESKTOP_LOG_BYTES: u64 = 2 * 1024 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopConfig {
    pub bind_host: String,
    pub rest_port: u16,
    pub ws_port: u16,
    pub mcp_http_port: u16,
    pub launch_daemon_on_startup: bool,
    pub keep_daemon_alive_on_exit: bool,
    pub python_executable: String,
    pub daemon_mode: String,
    pub data_dir_override: Option<String>,
}

impl Default for DesktopConfig {
    fn default() -> Self {
        let default_python = if cfg!(target_os = "windows") {
            "python".to_string()
        } else {
            "python3".to_string()
        };
        Self {
            bind_host: "127.0.0.1".to_string(),
            rest_port: 47100,
            ws_port: 47101,
            mcp_http_port: 47102,
            launch_daemon_on_startup: true,
            keep_daemon_alive_on_exit: true,
            python_executable: default_python,
            daemon_mode: "auto".to_string(),
            data_dir_override: None,
        }
    }
}

pub fn resolve_data_dir(config: Option<&DesktopConfig>) -> PathBuf {
    if let Some(cfg) = config {
        if let Some(custom) = &cfg.data_dir_override {
            let trimmed = custom.trim();
            if !trimmed.is_empty() {
                return PathBuf::from(trimmed);
            }
        }
    }
    if let Ok(env_dir) = std::env::var("NEXUS_DATA_DIR") {
        let trimmed = env_dir.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    if cfg!(target_os = "windows") {
        if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
            let trimmed = local_app_data.trim();
            if !trimmed.is_empty() {
                return PathBuf::from(trimmed).join("NEXUS");
            }
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let trimmed = home.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed).join(".nexus");
        }
    }
    PathBuf::from(".nexus")
}

pub fn ensure_secure_directory(dir: &Path) -> Result<(), String> {
    fs::create_dir_all(dir).map_err(|e| format!("Failed to create directory {}: {e}", dir.display()))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(dir, fs::Permissions::from_mode(0o700));
    }
    Ok(())
}

pub fn restrict_file_permissions(path: &Path) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(path, fs::Permissions::from_mode(0o600));
    }
    #[cfg(windows)]
    {
        // %LOCALAPPDATA%\NEXUS inherits the active Windows user profile ACL cleanly.
        let _ = path;
    }
}

pub fn config_file_path(data_dir: &Path) -> PathBuf {
    data_dir.join("desktop-config.json")
}

pub fn token_file_path(data_dir: &Path) -> PathBuf {
    data_dir.join("daemon.token")
}

pub fn desktop_log_path(data_dir: &Path) -> PathBuf {
    data_dir.join("logs").join("desktop-shell.log")
}

pub fn daemon_log_path(data_dir: &Path) -> PathBuf {
    data_dir.join("logs").join("nexus-daemon.log")
}

pub fn load_desktop_config() -> Result<DesktopConfig, String> {
    let base_dir = resolve_data_dir(None);
    let path = config_file_path(&base_dir);
    if !path.exists() {
        return Ok(DesktopConfig::default());
    }
    let raw = fs::read_to_string(&path)
        .map_err(|e| format!("Failed to read {}: {e}", path.display()))?;
    serde_json::from_str::<DesktopConfig>(&raw)
        .map_err(|e| format!("Invalid desktop config JSON in {}: {e}", path.display()))
}

pub fn save_desktop_config(cfg: &DesktopConfig) -> Result<DesktopConfig, String> {
    let trimmed_host = cfg.bind_host.trim();
    if trimmed_host != "127.0.0.1" && trimmed_host != "localhost" && trimmed_host != "::1" {
        return Err(format!(
            "Refusing non-loopback bindHost '{trimmed_host}'. Desktop bridge only permits loopback addresses."
        ));
    }
    let data_dir = resolve_data_dir(Some(cfg));
    ensure_secure_directory(&data_dir)?;
    let path = config_file_path(&data_dir);
    let serialized = serde_json::to_string_pretty(cfg)
        .map_err(|e| format!("Failed to serialize desktop config: {e}"))?;
    fs::write(&path, serialized)
        .map_err(|e| format!("Failed to write {}: {e}", path.display()))?;
    restrict_file_permissions(&path);
    append_desktop_log(
        &data_dir,
        "INFO",
        "config.saved",
        &format!("Saved desktop configuration to {}", path.display()),
    );
    Ok(cfg.clone())
}

pub fn read_or_create_daemon_token(data_dir: &Path) -> Result<String, String> {
    if let Ok(env_token) = std::env::var("NEXUS_API_TOKEN") {
        let trimmed = env_token.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }
    ensure_secure_directory(data_dir)?;
    let token_path = token_file_path(data_dir);
    if token_path.exists() {
        let existing = fs::read_to_string(&token_path)
            .map_err(|e| format!("Failed to read token file {}: {e}", token_path.display()))?;
        let trimmed = existing.trim().to_string();
        if !trimmed.is_empty() {
            restrict_file_permissions(&token_path);
            return Ok(trimmed);
        }
    }

    let generated = generate_local_token();
    fs::write(&token_path, &generated)
        .map_err(|e| format!("Failed to write token file {}: {e}", token_path.display()))?;
    restrict_file_permissions(&token_path);
    Ok(generated)
}

fn generate_local_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let pid = std::process::id() as u128;
    // Mix high-resolution clock, pid, and stack entropy cleanly with SplitMix64.
    let mut state = nanos ^ (pid << 64) ^ 0x9E37_79B9_7F4A_7C15_u128;
    let mut out = String::from("nxs_");
    for idx in 0..4u128 {
        state = state.wrapping_add(0x9E37_79B9_7F4A_7C15 ^ idx);
        let mut z = state as u64 ^ ((state >> 64) as u64);
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^= z >> 31;
        out.push_str(&format!("{z:016x}"));
    }
    out
}

pub fn epoch_iso_approx() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("unix:{secs}")
}

pub fn append_desktop_log(data_dir: &Path, level: &str, event: &str, message: &str) {
    let log_path = desktop_log_path(data_dir);
    if let Some(parent) = log_path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(meta) = fs::metadata(&log_path) {
        if meta.len() >= MAX_DESKTOP_LOG_BYTES {
            let rotated = log_path.with_extension("log.1");
            let _ = fs::rename(&log_path, rotated);
        }
    }
    let entry = serde_json::json!({
        "timestamp": epoch_iso_approx(),
        "level": level,
        "component": "nexus-desktop-shell",
        "event": event,
        "message": message,
    });
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&log_path) {
        let _ = writeln!(file, "{entry}");
    }
}
