mod credentials;
mod logging;
mod paths;
mod sidecar;

use serde::Serialize;
use sidecar::{ServiceState, app_ready};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppConnection {
    base_url: String,
    token: String,
}

#[tauri::command]
fn get_provider_credential() -> Result<credentials::ProviderCredentialSummary, String> {
    credentials::summary()
}

#[tauri::command]
fn save_provider_credential(
    input: credentials::ProviderCredentialInput,
) -> Result<credentials::ProviderCredentialSummary, String> {
    credentials::save(input)
}

#[tauri::command]
fn delete_provider_credential() -> Result<(), String> {
    credentials::delete()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let log_dir = paths::log_dir().map_err(std::io::Error::other)?;
            logging::init(&log_dir.join("agent-crossbar.log")).map_err(|error| {
                std::io::Error::other(format!("failed to initialize logging: {error}"))
            })?;

            let webview_data = paths::webview_data_dir().map_err(std::io::Error::other)?;
            std::fs::create_dir_all(&webview_data).map_err(|error| {
                std::io::Error::other(format!(
                    "failed to create WebView2 directory {}: {error}",
                    webview_data.display()
                ))
            })?;
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Agent Crossbar")
                .inner_size(1360.0, 860.0)
                .min_inner_size(1120.0, 700.0)
                .center()
                .resizable(true)
                .fullscreen(false)
                .data_directory(webview_data)
                .build()
                .map_err(|error| {
                    std::io::Error::other(format!("failed to create the main window: {error}"))
                })?;

            let state = ServiceState::start(app.handle()).map_err(|error| {
                std::io::Error::other(format!("failed to start the local service: {error}"))
            })?;
            app.manage(state);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            app_ready,
            get_provider_credential,
            save_provider_credential,
            delete_provider_credential
        ])
        .build(tauri::generate_context!())
        .expect("error while building Agent Crossbar");

    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            if let Some(state) = app_handle.try_state::<ServiceState>() {
                state.stop();
            }
        }
    });
}
