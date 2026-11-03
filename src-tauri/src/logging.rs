use std::{
    fs::{self, File, OpenOptions},
    io::{self, Write},
    path::Path,
    sync::Mutex,
    time::{SystemTime, UNIX_EPOCH},
};

const MAX_LOG_SIZE: u64 = 2_000_000;

struct FileLogger {
    file: Mutex<File>,
}

impl log::Log for FileLogger {
    fn enabled(&self, metadata: &log::Metadata<'_>) -> bool {
        metadata.level() <= log::Level::Info
    }

    fn log(&self, record: &log::Record<'_>) {
        if !self.enabled(record.metadata()) {
            return;
        }

        let elapsed = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default();
        let message = format!(
            "{}.{:03} {:<5} {}: {}\n",
            elapsed.as_secs(),
            elapsed.subsec_millis(),
            record.level(),
            record.target(),
            record.args()
        );

        if let Ok(mut file) = self.file.lock() {
            let _ = file.write_all(message.as_bytes());
            let _ = file.flush();
        }
    }

    fn flush(&self) {
        if let Ok(mut file) = self.file.lock() {
            let _ = file.flush();
        }
    }
}

pub fn init(path: &Path) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    if fs::metadata(path).is_ok_and(|metadata| metadata.len() >= MAX_LOG_SIZE) {
        let previous = path.with_extension("previous.log");
        let _ = fs::remove_file(&previous);
        let _ = fs::rename(path, previous);
    }

    let file = OpenOptions::new().create(true).append(true).open(path)?;
    let logger = Box::new(FileLogger {
        file: Mutex::new(file),
    });
    log::set_boxed_logger(logger).map_err(io::Error::other)?;
    log::set_max_level(log::LevelFilter::Info);
    Ok(())
}
