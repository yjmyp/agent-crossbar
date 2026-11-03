use std::{
    fs::OpenOptions,
    io::Write,
    path::{Path, PathBuf},
    sync::OnceLock,
};

static PRODUCT_DATA_ROOT: OnceLock<Result<PathBuf, String>> = OnceLock::new();

pub fn webview_data_dir() -> Result<PathBuf, String> {
    Ok(product_data_root()?.join("WebView2"))
}

pub fn runtime_temp_dir() -> Result<PathBuf, String> {
    Ok(product_data_root()?.join("Runtime"))
}

pub fn log_dir() -> Result<PathBuf, String> {
    Ok(product_data_root()?.join("Logs"))
}

pub fn database_dir() -> Result<PathBuf, String> {
    Ok(product_data_root()?.join("Data"))
}

fn product_data_root() -> Result<PathBuf, String> {
    PRODUCT_DATA_ROOT
        .get_or_init(resolve_product_data_root)
        .clone()
}

fn resolve_product_data_root() -> Result<PathBuf, String> {
    let mut failures = Vec::new();

    if let Some(local_app_data) = std::env::var_os("LOCALAPPDATA").filter(|value| !value.is_empty())
    {
        let standard = PathBuf::from(local_app_data).join("AgentCrossbar");
        match ensure_writable(&standard) {
            Ok(()) => return Ok(standard),
            Err(error) => failures.push(format!("{}: {error}", standard.display())),
        }
    }

    let executable = std::env::current_exe()
        .map_err(|error| format!("Could not resolve the application executable: {error}"))?;
    let parent = executable
        .parent()
        .ok_or_else(|| "The application executable has no parent directory.".to_string())?;
    let local = parent.join("AgentCrossbarData");
    match ensure_writable(&local) {
        Ok(()) => Ok(local),
        Err(error) => {
            failures.push(format!("{}: {error}", local.display()));
            Err(format!(
                "No writable application data directory is available ({})",
                failures.join("; ")
            ))
        }
    }
}

fn ensure_writable(path: &Path) -> Result<(), String> {
    std::fs::create_dir_all(path)
        .map_err(|error| format!("could not create the directory: {error}"))?;
    let probe = path.join(format!(".write-test-{}", std::process::id()));
    let result = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(&probe)
        .and_then(|mut file| file.write_all(b"Agent Crossbar"))
        .map_err(|error| format!("could not write to the directory: {error}"));
    let _ = std::fs::remove_file(probe);
    result
}
