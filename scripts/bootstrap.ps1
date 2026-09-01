$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

Write-Host "Installing JavaScript dependencies..."
pnpm install
pnpm exec playwright install chromium

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    python -m pip install --user uv
}

Write-Host "Installing Python dependencies..."
python -m uv sync --directory core --all-groups

Write-Host "LoreDock development environment is ready."
