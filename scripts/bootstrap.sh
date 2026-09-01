#!/usr/bin/env sh
set -eu

pnpm install
pnpm exec playwright install chromium

if ! python3 -m uv --version >/dev/null 2>&1; then
  python3 -m pip install --user uv
fi

python3 -m uv sync --directory core --all-groups
printf '%s\n' 'LoreDock development environment is ready.'
