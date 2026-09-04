# ADR 0013: Bundle an independent MCP executable

- Status: Accepted
- Date: 2026-09-04

## Decision

Build a console-mode PyInstaller onedir `loredock-mcp` alongside Core, under
`core/bridge/loredock-mcp/`. The existing Tauri Core resource mapping includes
this subtree. Retain standard input/output for MCP; do not use windowed mode.
Frozen Core generates the absolute sibling executable path, never a Python
module command, and fails closed if that file is missing. Do not search PATH,
download a replacement, or read a user-supplied executable override.

Application service exports are lazy, and dispatch service annotations are
type-checking-only, so importing bridge contracts does not load ONNX or the
application service. A subprocess regression test enforces this boundary.

## Consequences

No system Python is required by the two built executables. Credentials remain
in the OS vault; configuration contains only executable/profile paths and a
connection ID. No database migration, MCP tool change or retrieval change.
Development module commands remain supported. Setup metadata reports
`runtime: packaged` for frozen Core; relocating the installation requires
regenerating the external Agent configuration.

The first Windows build uses separate runtimes for predictable isolation,
not shared DLL layout. Uncompressed bridge size is about 90.7 MiB; combined
Core resource tree is about 214.3 MiB on the validation machine. Deduplicating
runtimes, dependency notice assembly, signing, clean-machine installer tests,
and macOS/Linux packaging remain release work. No new dependency was added.

## Validation

The opt-in system smoke test consumes the actual setup API command and launches
the packaged bridge against packaged Core. Windows vault access, MCP discovery,
scope denial, Core failure, port-changing restart and revocation passed.
This is SDK client validation, not Codex/Cursor end-user acceptance.
