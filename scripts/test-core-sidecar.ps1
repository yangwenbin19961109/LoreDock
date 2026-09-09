param(
    [string]$SidecarPath = "core\dist\loredock-core\loredock-core.exe"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedSidecar = (Resolve-Path (Join-Path $repositoryRoot $SidecarPath)).Path
$fixturePath = (Resolve-Path (Join-Path $repositoryRoot "evals\fixtures\documents\faq.md")).Path
$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "loredock-sidecar-smoke-" + [guid]::NewGuid().ToString("N")
)
$resolvedTempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$resolvedSmokeRoot = [System.IO.Path]::GetFullPath($smokeRoot)
if (-not $resolvedSmokeRoot.StartsWith(
    $resolvedTempRoot,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Unsafe smoke-test directory."
}

New-Item -ItemType Directory -Path $resolvedSmokeRoot | Out-Null
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$smokePort = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()
$smokeToken = [guid]::NewGuid().ToString("N")
$env:LOREDOCK_HOST = "127.0.0.1"
$env:LOREDOCK_PORT = [string]$smokePort
$env:LOREDOCK_DATA_DIR = $resolvedSmokeRoot
$env:LOREDOCK_DESKTOP_TOKEN = $smokeToken
$sidecarProcess = Start-Process -FilePath $resolvedSidecar -WindowStyle Hidden -PassThru

try {
    $headers = @{ Authorization = "Bearer $smokeToken" }
    $health = $null
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        try {
            $health = Invoke-RestMethod `
                -Uri "http://127.0.0.1:$smokePort/api/v1/health" `
                -Headers $headers `
                -TimeoutSec 1
            break
        }
        catch {
            Start-Sleep -Milliseconds 100
        }
    }
    if (-not $health) {
        throw "Packaged Core did not become ready."
    }

    try {
        Invoke-WebRequest `
            -Uri "http://127.0.0.1:$smokePort/api/v1/health" `
            -UseBasicParsing `
            -TimeoutSec 2 `
            -ErrorAction Stop | Out-Null
        throw "Unauthenticated request unexpectedly succeeded."
    }
    catch {
        if ([int]$_.Exception.Response.StatusCode -ne 401) {
            throw
        }
    }

    $library = Invoke-RestMethod `
        -Method Post `
        -Uri "http://127.0.0.1:$smokePort/api/v1/libraries" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body '{"name":"Packaged Smoke"}'
    $uploadJson = & curl.exe `
        -sS `
        -H "Authorization: Bearer $smokeToken" `
        -F "file=@$fixturePath;type=text/markdown" `
        "http://127.0.0.1:$smokePort/api/v1/libraries/$($library.id)/sources"
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged source upload failed."
    }
    $upload = $uploadJson | ConvertFrom-Json
    $job = $upload.job
    for ($attempt = 0; $attempt -lt 100 -and $job.status -notin @("succeeded", "failed"); $attempt++) {
        Start-Sleep -Milliseconds 100
        $job = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$smokePort/api/v1/jobs/$($upload.job.id)" `
            -Headers $headers `
            -TimeoutSec 1
    }
    if ($job.status -ne "succeeded") {
        throw "Packaged source indexing did not succeed: $($job.status)"
    }
    $source = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$smokePort/api/v1/sources/$($upload.source.id)" `
        -Headers $headers `
        -TimeoutSec 1
    if ($source.status -ne "ready") {
        throw "Unexpected source status after indexing: $($source.status)"
    }

    Invoke-RestMethod `
        -Method Post `
        -Uri "http://127.0.0.1:$smokePort/api/v1/desktop/shutdown" `
        -Headers $headers | Out-Null
    Wait-Process -Id $sidecarProcess.Id -Timeout 10 -ErrorAction Stop
    $size = (Get-ChildItem (Split-Path $resolvedSidecar) -Recurse -File |
        Measure-Object Length -Sum).Sum
    [PSCustomObject]@{
        Ready = $health.status
        Port = $smokePort
        UnauthorizedStatus = 401
        ImportedStatus = $source.status
        Exited = $sidecarProcess.HasExited
        SizeMiB = [math]::Round($size / 1MB, 1)
    }
}
finally {
    if (-not $sidecarProcess.HasExited) {
        Stop-Process -Id $sidecarProcess.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $sidecarProcess.Id -Timeout 5 -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $resolvedSmokeRoot) {
        $cleanupError = $null
        for ($attempt = 0; $attempt -lt 10; $attempt++) {
            try {
                Remove-Item -LiteralPath $resolvedSmokeRoot -Recurse -Force
                $cleanupError = $null
                break
            }
            catch {
                $cleanupError = $_
                Start-Sleep -Milliseconds 250
            }
        }
        if ($cleanupError) {
            throw $cleanupError
        }
    }
}
