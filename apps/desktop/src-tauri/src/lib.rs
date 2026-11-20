mod config_store;
mod daemon_manager;
mod version;

use config_store::{
    load_desktop_config, read_or_create_daemon_token, resolve_data_dir, save_desktop_config,
    DesktopConfig,
};
use daemon_manager::{
    AdapterInstallGuide, BridgeProbeResult, DaemonLifecycleStatus, DaemonSupervisor,
    DesktopDiagnosticsReport,
};
use serde::Serialize;
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{Manager, RunEvent, State};
use version::{get_version_info, ApplicationVersionInfo};

type SharedSupervisor = Arc<Mutex<DaemonSupervisor>>;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopRuntimeInfo {
    pub os: &'static str,
    pub arch: &'static str,
    pub shell: &'static str,
    pub app_version: &'static str,
    pub daemon_supervised: bool,
}

#[tauri::command]
fn get_desktop_runtime_info(supervisor: State<'_, SharedSupervisor>) -> DesktopRuntimeInfo {
    let supervised = supervisor
        .lock()
        .map(|mut s| {
            let cfg = load_desktop_config().unwrap_or_default();
            s.lifecycle_status(&cfg).supervised_by_shell
        })
        .unwrap_or(false);

    DesktopRuntimeInfo {
        os: std::env::consts::OS,
        arch: std::env::consts::ARCH,
        shell: "tauri-2",
        app_version: version::APP_VERSION,
        daemon_supervised: supervised,
    }
}

#[tauri::command]
fn get_application_version_info() -> ApplicationVersionInfo {
    get_version_info()
}

#[tauri::command]
fn probe_daemon_health(
    endpoint: String,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<BridgeProbeResult, String> {
    let mut guard = supervisor
        .lock()
        .map_err(|_| "Daemon supervisor mutex poisoned.".to_string())?;
    Ok(guard.probe_health(&endpoint))
}

#[tauri::command]
fn start_background_daemon(
    supervisor: State<'_, SharedSupervisor>,
) -> Result<DaemonLifecycleStatus, String> {
    let cfg = load_desktop_config().unwrap_or_default();
    let mut guard = supervisor
        .lock()
        .map_err(|_| "Daemon supervisor mutex poisoned.".to_string())?;
    Ok(guard.start_background_daemon(&cfg))
}

#[tauri::command]
fn stop_background_daemon(
    force_external: Option<bool>,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<DaemonLifecycleStatus, String> {
    let cfg = load_desktop_config().unwrap_or_default();
    let mut guard = supervisor
        .lock()
        .map_err(|_| "Daemon supervisor mutex poisoned.".to_string())?;
    Ok(guard.stop_background_daemon(&cfg, force_external.unwrap_or(false)))
}

#[tauri::command]
fn restart_background_daemon(
    supervisor: State<'_, SharedSupervisor>,
) -> Result<DaemonLifecycleStatus, String> {
    let cfg = load_desktop_config().unwrap_or_default();
    let mut guard = supervisor
        .lock()
        .map_err(|_| "Daemon supervisor mutex poisoned.".to_string())?;
    let _ = guard.stop_background_daemon(&cfg, false);
    Ok(guard.start_background_daemon(&cfg))
}

#[tauri::command]
fn get_daemon_lifecycle_status(
    supervisor: State<'_, SharedSupervisor>,
) -> Result<DaemonLifecycleStatus, String> {
    let cfg = load_desktop_config().unwrap_or_default();
    let mut guard = supervisor
        .lock()
        .map_err(|_| "Daemon supervisor mutex poisoned.".to_string())?;
    Ok(guard.lifecycle_status(&cfg))
}

#[tauri::command]
fn get_daemon_auth_token() -> Result<String, String> {
    let cfg = load_desktop_config().unwrap_or_default();
    let data_dir = resolve_data_dir(Some(&cfg));
    read_or_create_daemon_token(&data_dir)
}

#[tauri::command]
fn load_desktop_configuration() -> Result<DesktopConfig, String> {
    load_desktop_config()
}

#[tauri::command]
fn save_desktop_configuration(config: DesktopConfig) -> Result<DesktopConfig, String> {
    save_desktop_config(&config)
}

#[tauri::command]
fn collect_desktop_diagnostics(
    supervisor: State<'_, SharedSupervisor>,
) -> Result<DesktopDiagnosticsReport, String> {
    let cfg = load_desktop_config().unwrap_or_default();
    let mut guard = supervisor
        .lock()
        .map_err(|_| "Daemon supervisor mutex poisoned.".to_string())?;
    Ok(guard.collect_diagnostics(&cfg))
}

#[tauri::command]
fn get_adapter_install_instructions(
    supervisor: State<'_, SharedSupervisor>,
) -> Result<Vec<AdapterInstallGuide>, String> {
    let cfg = load_desktop_config().unwrap_or_default();
    let guard = supervisor
        .lock()
        .map_err(|_| "Daemon supervisor mutex poisoned.".to_string())?;
    Ok(guard.get_adapter_install_instructions(&cfg))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let supervisor: SharedSupervisor = Arc::new(Mutex::new(DaemonSupervisor::new(None)));
    let setup_supervisor = Arc::clone(&supervisor);
    let exit_supervisor = Arc::clone(&supervisor);

    let app = tauri::Builder::default()
        .manage(supervisor)
        .setup(move |app| {
            let resource_dir = app.path().resource_dir().ok();
            if let Ok(mut guard) = setup_supervisor.lock() {
                guard.set_resource_dir(resource_dir);
            }

            let cfg = load_desktop_config().unwrap_or_default();
            if cfg.launch_daemon_on_startup {
                let bg_supervisor = Arc::clone(&setup_supervisor);
                thread::spawn(move || {
                    if let Ok(mut guard) = bg_supervisor.lock() {
                        let _ = guard.start_background_daemon(&cfg);
                    }
                });
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_desktop_runtime_info,
            get_application_version_info,
            probe_daemon_health,
            start_background_daemon,
            stop_background_daemon,
            restart_background_daemon,
            get_daemon_lifecycle_status,
            get_daemon_auth_token,
            load_desktop_configuration,
            save_desktop_configuration,
            collect_desktop_diagnostics,
            get_adapter_install_instructions,
        ])
        .build(tauri::generate_context!())
        .expect("error while building NEXUS desktop shell");

    app.run(move |_app_handle, event| {
        if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
            if let Ok(mut guard) = exit_supervisor.lock() {
                let cfg = load_desktop_config().unwrap_or_default();
                guard.shutdown_on_app_exit(&cfg);
            }
        }
    });
}
