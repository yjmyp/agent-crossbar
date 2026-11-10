use std::{
    path::Path,
    sync::{Arc, Mutex},
    time::Duration,
};

#[cfg(debug_assertions)]
use std::path::PathBuf;

use serde::Deserialize;
use tauri::{AppHandle, State};
use tauri_plugin_shell::{
    ShellExt,
    process::{CommandChild, CommandEvent},
};
use tokio::sync::watch;
use uuid::Uuid;

use crate::{AppConnection, credentials, paths};

#[derive(Clone, Debug, Default)]
pub struct ServiceSnapshot {
    connection: Option<AppConnection>,
    error: Option<String>,
}

pub struct ServiceState {
    snapshot_tx: watch::Sender<ServiceSnapshot>,
    child: Arc<Mutex<Option<CommandChild>>>,
}

impl ServiceState {
    pub fn start(app: &AppHandle) -> Result<Self, Box<dyn std::error::Error>> {
        let database = paths::database_dir()
            .map_err(std::io::Error::other)?
            .join("crossbar.db");
        if let Some(parent) = database.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let token = Uuid::new_v4().simple().to_string();
        let (snapshot_tx, _) = watch::channel(ServiceSnapshot::default());
        let child_slot = Arc::new(Mutex::new(None));
        let task_tx = snapshot_tx.clone();
        let task_child = Arc::clone(&child_slot);
        let app_handle = app.clone();
        let launch_token = token.clone();

        tauri::async_runtime::spawn(async move {
            if let Err(error) = supervise(
                &app_handle,
                &database,
                &launch_token,
                task_tx.clone(),
                task_child,
            )
            .await
            {
                task_tx.send_replace(ServiceSnapshot {
                    connection: None,
                    error: Some(error),
                });
            }
        });

        Ok(Self {
            snapshot_tx,
            child: child_slot,
        })
    }

    pub fn stop(&self) {
        if let Ok(mut slot) = self.child.lock() {
            if let Some(child) = slot.take() {
                let _ = child.kill();
            }
        }
    }
}

async fn supervise(
    app: &AppHandle,
    database: &Path,
    token: &str,
    snapshot_tx: watch::Sender<ServiceSnapshot>,
    child_slot: Arc<Mutex<Option<CommandChild>>>,
) -> Result<(), String> {
    let command = sidecar_command(app, database, token)?;
    let (mut events, child) = command
        .spawn()
        .map_err(|error| format!("Could not launch the local service: {error}"))?;

    if let Ok(mut slot) = child_slot.lock() {
        *slot = Some(child);
    }

    let mut ready = false;
    while let Some(event) = events.recv().await {
        match event {
            CommandEvent::Stdout(bytes) => {
                let line = String::from_utf8_lossy(&bytes).trim().to_string();
                if let Ok(handshake) = serde_json::from_str::<Handshake>(&line) {
                    if handshake.event == "ready"
                        && handshake.host == "127.0.0.1"
                        && handshake.port > 0
                    {
                        ready = true;
                        snapshot_tx.send_replace(ServiceSnapshot {
                            connection: Some(AppConnection {
                                base_url: format!("http://127.0.0.1:{}", handshake.port),
                                token: token.to_string(),
                            }),
                            error: None,
                        });
                    }
                }
            }
            CommandEvent::Stderr(bytes) => {
                let line = String::from_utf8_lossy(&bytes).trim().to_string();
                if !line.is_empty() {
                    log::info!("sidecar: {line}");
                }
            }
            CommandEvent::Terminated(payload) => {
                if let Ok(mut slot) = child_slot.lock() {
                    slot.take();
                }
                if !ready {
                    return Err(format!(
                        "The local service stopped before it was ready (code: {:?}).",
                        payload.code
                    ));
                }
                snapshot_tx.send_replace(ServiceSnapshot {
                    connection: None,
                    error: Some("The local service stopped unexpectedly.".to_string()),
                });
                return Ok(());
            }
            CommandEvent::Error(error) => {
                return Err(format!("The local service failed: {error}"));
            }
            _ => {}
        }
    }

    Err("The local service output channel closed unexpectedly.".to_string())
}

fn sidecar_command(
    app: &AppHandle,
    database: &Path,
    token: &str,
) -> Result<tauri_plugin_shell::process::Command, String> {
    let arguments = vec![
        "--database".to_string(),
        database.to_string_lossy().to_string(),
        "--token".to_string(),
        token.to_string(),
        "--port".to_string(),
        "0".to_string(),
        "--parent-pid".to_string(),
        std::process::id().to_string(),
    ];
    let runtime_temp = paths::runtime_temp_dir()?;
    std::fs::create_dir_all(&runtime_temp)
        .map_err(|error| format!("Could not prepare the local runtime directory: {error}"))?;
    let runtime_temp = runtime_temp.to_string_lossy().to_string();
    let mut provider_environment =
        provider_environment_for_launch(credentials::sidecar_environment());
    provider_environment.extend(provider_environment_for_launch(
        credentials::embedding_sidecar_environment(),
    ));
    provider_environment.extend(worker_inbound_environment(
        std::env::var("AGENT_CROSSBAR_WORKER_INBOUND_TOKEN").ok(),
    )?);

    #[cfg(debug_assertions)]
    {
        let project_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .ok_or_else(|| "Could not resolve the development project directory.".to_string())?
            .to_path_buf();
        let python = project_root
            .join(".venv")
            .join("Scripts")
            .join("python.exe");
        if !python.is_file() {
            return Err(format!(
                "The development Python environment is missing. Run `uv sync` and try again ({}).",
                python.display()
            ));
        }
        let mut command = app
            .shell()
            .command(python.to_string_lossy().to_string())
            .args(["-m", "agent_crossbar.sidecar"])
            .args(arguments)
            .env("TEMP", runtime_temp.clone())
            .env("TMP", runtime_temp);
        for (name, value) in provider_environment {
            command = command.env(name, value);
        }
        return Ok(command.current_dir(project_root));
    }

    #[cfg(not(debug_assertions))]
    {
        let _ = database;
        let mut command = app
            .shell()
            .sidecar("agent-crossbar-sidecar")
            .map_err(|error| format!("Could not resolve the packaged local service: {error}"))?
            .args(arguments)
            .env("TEMP", runtime_temp.clone())
            .env("TMP", runtime_temp);
        for (name, value) in provider_environment {
            command = command.env(name, value);
        }
        Ok(command)
    }
}

fn provider_environment_for_launch(
    environment: Result<Vec<(String, String)>, String>,
) -> Vec<(String, String)> {
    match environment {
        Ok(environment) => environment,
        Err(error) => {
            log::warn!("Stored model connection is unavailable; starting in offline mode: {error}");
            Vec::new()
        }
    }
}

fn worker_inbound_environment(configured: Option<String>) -> Result<Vec<(String, String)>, String> {
    let Some(value) = configured else {
        return Ok(Vec::new());
    };
    let token = value.trim();
    if token.is_empty() {
        return Ok(Vec::new());
    }
    if token.chars().count() < 32 {
        return Err(
            "AGENT_CROSSBAR_WORKER_INBOUND_TOKEN must contain at least 32 characters.".to_string(),
        );
    }
    Ok(vec![(
        "AGENT_CROSSBAR_WORKER_INBOUND_TOKEN".to_string(),
        token.to_string(),
    )])
}

#[tauri::command]
pub async fn app_ready(state: State<'_, ServiceState>) -> Result<AppConnection, String> {
    let mut receiver = state.snapshot_tx.subscribe();

    loop {
        let snapshot = receiver.borrow().clone();
        if let Some(connection) = snapshot.connection {
            return Ok(connection);
        }
        if let Some(error) = snapshot.error {
            return Err(error);
        }

        tokio::time::timeout(Duration::from_secs(20), receiver.changed())
            .await
            .map_err(|_| "The local service did not become ready within 20 seconds.".to_string())?
            .map_err(|_| "The local service startup channel closed.".to_string())?;
    }
}

#[derive(Debug, Deserialize)]
struct Handshake {
    event: String,
    host: String,
    port: u16,
}

#[cfg(test)]
mod tests {
    use super::{provider_environment_for_launch, worker_inbound_environment};

    #[test]
    fn sidecar_launch_uses_valid_stored_provider_environment() {
        let environment = provider_environment_for_launch(Ok(vec![(
            "AGENT_CROSSBAR_OPENAI_MODEL".to_string(),
            "model-a".to_string(),
        )]));

        assert_eq!(
            environment,
            vec![(
                "AGENT_CROSSBAR_OPENAI_MODEL".to_string(),
                "model-a".to_string()
            )]
        );
    }

    #[test]
    fn sidecar_launch_keeps_offline_mode_when_stored_credentials_are_invalid() {
        let environment =
            provider_environment_for_launch(Err("stored connection is invalid".to_string()));

        assert!(environment.is_empty());
    }

    #[test]
    fn sidecar_launch_forwards_a_configured_worker_inbound_token_through_environment() {
        let environment = worker_inbound_environment(Some("w".repeat(40))).unwrap();

        assert_eq!(
            environment,
            vec![(
                "AGENT_CROSSBAR_WORKER_INBOUND_TOKEN".to_string(),
                "w".repeat(40),
            )]
        );
    }

    #[test]
    fn sidecar_launch_never_fabricates_a_missing_worker_inbound_token() {
        assert!(worker_inbound_environment(None).unwrap().is_empty());
        assert!(
            worker_inbound_environment(Some("   ".to_string()))
                .unwrap()
                .is_empty()
        );
    }

    #[test]
    fn sidecar_launch_rejects_a_short_worker_inbound_token_without_echoing_it() {
        let error = worker_inbound_environment(Some("too-short".to_string())).unwrap_err();

        assert!(error.contains("32"));
        assert!(!error.contains("too-short"));
    }
}
