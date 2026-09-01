#!/usr/bin/env sh
set -eu

pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm e2e
pnpm --filter @loredock/contracts build
pnpm --filter @loredock/ui build
pnpm --filter @loredock/web build

python3 -m uv run --directory core ruff format --check .
python3 -m uv run --directory core ruff check .
python3 -m uv run --directory core pyright
python3 -m uv run --directory core pytest
python3 -m uv run --directory core loredock-eval

cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml --check
cargo clippy --manifest-path apps/desktop/src-tauri/Cargo.toml --all-targets -- -D warnings
