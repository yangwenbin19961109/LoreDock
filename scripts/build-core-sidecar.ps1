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
    (Join-Path $coreDirectory "src\loredock\__main__.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$sidecar = Join-Path $coreDirectory "dist\loredock-core\loredock-core.exe"
if (-not (Test-Path -LiteralPath $sidecar -PathType Leaf)) {
    throw "Expected sidecar was not created at $sidecar."
}

Write-Output $sidecar
