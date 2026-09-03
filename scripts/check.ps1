$ErrorActionPreference = "Stop"

function Assert-LastExitCode {
    param([Parameter(Mandatory = $true)][string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

pnpm format:check
Assert-LastExitCode "Prettier"
pnpm lint
Assert-LastExitCode "ESLint"
pnpm typecheck
Assert-LastExitCode "TypeScript and Cargo check"
pnpm test
Assert-LastExitCode "Unit tests"
pnpm e2e
Assert-LastExitCode "Playwright"
pnpm --filter @loredock/contracts build
Assert-LastExitCode "Contracts build"
pnpm --filter @loredock/ui build
Assert-LastExitCode "UI build"
pnpm --filter @loredock/web build
Assert-LastExitCode "Web build"

python -m uv run --directory core ruff format --check .
Assert-LastExitCode "Ruff format"
python -m uv run --directory core ruff check .
Assert-LastExitCode "Ruff lint"
python -m uv run --directory core pyright
Assert-LastExitCode "Pyright"
python -m uv run --directory core pytest
Assert-LastExitCode "Pytest"
python -m uv run --directory core loredock-eval
Assert-LastExitCode "Retrieval evaluation"

cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml --check
Assert-LastExitCode "rustfmt"
cargo clippy --manifest-path apps/desktop/src-tauri/Cargo.toml --all-targets -- -D warnings
Assert-LastExitCode "Clippy"
