# LoreDock Core

LoreDock Core is the local application service shared by the desktop and server editions.
It owns application use cases and exposes versioned HTTP contracts. The desktop application
will package it as a sidecar, so end users do not need a system Python installation.

## Development

```powershell
uv sync --all-groups
uv run loredock-core
```

The service binds to `127.0.0.1:49321` by default. Override the port with
`LOREDOCK_PORT` when running multiple development instances.
