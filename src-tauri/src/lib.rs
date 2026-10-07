use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemInfo {
    pub app_name: String,
    pub version: String,
    pub architecture: String,
    pub status: String,
}

#[tauri::command]
fn get_system_info() -> SystemInfo {
    SystemInfo {
        app_name: "Subterranean Staircase".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        architecture: std::env::consts::ARCH.to_string(),
        status: "Core Online".to_string(),
    }
}

#[tauri::command]
fn ping(message: String) -> String {
    format!(
        "Pong from Rust core! Received: '{}' on architecture: {}",
        message,
        std::env::consts::ARCH
    )
}

pub fn run() -> Result<(), Box<dyn std::error::Error>> {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![get_system_info, ping])
        .run(tauri::generate_context!())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_system_info_metadata() {
        let info = get_system_info();
        assert_eq!(info.app_name, "Subterranean Staircase");
        assert_eq!(info.version, env!("CARGO_PKG_VERSION"));
        assert_eq!(info.status, "Core Online");
        assert!(!info.architecture.is_empty());
    }

    #[test]
    fn test_ping_response() {
        let reply = ping("Hello Tauri".to_string());
        assert!(reply.contains("Pong from Rust core!"));
        assert!(reply.contains("Hello Tauri"));
    }
}

