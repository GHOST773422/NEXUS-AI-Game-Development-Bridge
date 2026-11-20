use serde::Serialize;

pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const PROTOCOL_VERSION: &str = "2026.1.0-stage10";
pub const MIN_PYTHON_VERSION: &str = "3.12";
pub const TAURI_SHELL_NAME: &str = "tauri-2";

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ApplicationVersionInfo {
    pub app_version: &'static str,
    pub protocol_version: &'static str,
    pub min_python_version: &'static str,
    pub shell: &'static str,
    pub os: &'static str,
    pub arch: &'static str,
    pub offline_capable: bool,
    pub requires_ai_studio: bool,
    pub supported_installers: [&'static str; 2],
}

pub fn get_version_info() -> ApplicationVersionInfo {
    ApplicationVersionInfo {
        app_version: APP_VERSION,
        protocol_version: PROTOCOL_VERSION,
        min_python_version: MIN_PYTHON_VERSION,
        shell: TAURI_SHELL_NAME,
        os: std::env::consts::OS,
        arch: std::env::consts::ARCH,
        offline_capable: true,
        requires_ai_studio: false,
        supported_installers: ["nsis", "msi"],
    }
}
