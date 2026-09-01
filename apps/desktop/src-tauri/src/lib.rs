//! LoreDock desktop process boundary.
//!
//! Phase 0 intentionally does not launch the Python sidecar yet. Sidecar lifecycle,
//! dynamic port allocation, and version handshakes are implemented in Phase 3 after
//! the Core process contract is stable.

pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("failed to run LoreDock desktop application");
}
