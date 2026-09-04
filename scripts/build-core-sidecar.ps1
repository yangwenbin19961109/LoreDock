$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$coreDirectory = Join-Path $repositoryRoot "core"
$uvCandidates = @(
    (Get-Command uv.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
    (Join-Path $env:USERPROFILE ".cherrystudio\bin\uv.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
$uvExecutable = $uvCandidates | Select-Object -First 1

if (-not $uvExecutable) {
    throw "uv.exe was not found. Install uv or add it to PATH before packaging Core."
}

& $uvExecutable run --directory $coreDirectory python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name loredock-core `
    --distpath (Join-Path $coreDirectory "dist") `
    --workpath (Join-Path $coreDirectory "build\pyinstaller") `
    --specpath (Join-Path $coreDirectory "build") `
    --collect-all sqlite_vec `
    --hidden-import onnxruntime `
    --hidden-import keyring.backends.Windows `
    (Join-Path $coreDirectory "src\loredock\__main__.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$sidecar = Join-Path $coreDirectory "dist\loredock-core\loredock-core.exe"
if (-not (Test-Path -LiteralPath $sidecar -PathType Leaf)) {
    throw "Expected sidecar was not created at $sidecar."
}

Write-Output $sidecar

# Keep the stdio console executable with its own runtime, inside the existing
# Tauri Core resource tree. Never use --windowed: MCP requires standard streams.
& $uvExecutable run --directory $coreDirectory python -m PyInstaller `
    --noconfirm --clean --onedir --name loredock-mcp `
    --distpath (Join-Path $coreDirectory "dist\loredock-core\bridge") `
    --workpath (Join-Path $coreDirectory "build\mcp-pyinstaller") `
    --specpath (Join-Path $coreDirectory "build") `
    --hidden-import keyring.backends.Windows `
    (Join-Path $coreDirectory "src\loredock\mcp\bridge.py")
if ($LASTEXITCODE -ne 0) {
    throw "MCP bridge packaging failed with exit code $LASTEXITCODE."
}
