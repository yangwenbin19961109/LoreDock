param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("msi", "nsis")]
    [string]$InstallerType,
    [Parameter(Mandatory = $true)]
    [string]$CurrentInstaller,
    [string]$PreviousInstaller,
    [switch]$AcknowledgeDisposableMachine
)

$ErrorActionPreference = "Stop"

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "Windows installer acceptance can only run on Windows."
}
if (-not $AcknowledgeDisposableMachine) {
    throw "Run only on a disposable clean Windows VM and pass -AcknowledgeDisposableMachine."
}

function Resolve-InstallerPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "Installer does not exist: $resolved"
    }
    return $resolved
}

function Get-LoreDockUninstallEntry {
    $roots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $entries = foreach ($root in $roots) {
        Get-ItemProperty $root -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -eq "LoreDock" }
    }
    return $entries | Select-Object -First 1
}

function Invoke-Installer {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][ValidateSet("msi", "nsis")][string]$Type
    )
    if ($Type -eq "msi") {
        $process = Start-Process msiexec.exe -ArgumentList @("/i", $Path, "/qn", "/norestart") -Wait -PassThru
    }
    else {
        $process = Start-Process -FilePath $Path -ArgumentList "/S" -Wait -PassThru
    }
    if ($process.ExitCode -ne 0) {
        throw "Installer failed with exit code $($process.ExitCode): $Path"
    }
}

function Get-LoreDockExecutable {
    $entry = Get-LoreDockUninstallEntry
    if (-not $entry) {
        throw "LoreDock uninstall registration was not found."
    }
    $candidates = @()
    if ($entry.InstallLocation) {
        $candidates += Join-Path $entry.InstallLocation "LoreDock.exe"
    }
    if ($entry.DisplayIcon) {
        $candidates += ($entry.DisplayIcon -replace ',\d+$', '').Trim('"')
    }
    $candidates += @(
        (Join-Path $env:LOCALAPPDATA "LoreDock\LoreDock.exe"),
        (Join-Path $env:ProgramFiles "LoreDock\LoreDock.exe")
    )
    $executable = $candidates | Where-Object {
        $_ -and (Test-Path -LiteralPath $_ -PathType Leaf)
    } | Select-Object -First 1
    if (-not $executable) {
        throw "Installed LoreDock executable was not found."
    }
    return $executable
}

function Stop-LoreDock {
    Get-Process -Name "LoreDock", "loredock-core" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

function Invoke-LoreDockSmoke {
    $executable = Get-LoreDockExecutable
    $process = Start-Process -FilePath $executable -PassThru
    Start-Sleep -Seconds 5
    if ($process.HasExited) {
        throw "LoreDock exited before the startup smoke check completed."
    }
    Stop-LoreDock
    return $executable
}

function Uninstall-LoreDock {
    param([Parameter(Mandatory = $true)][ValidateSet("msi", "nsis")][string]$Type)
    $entry = Get-LoreDockUninstallEntry
    if (-not $entry) {
        throw "LoreDock uninstall registration was not found."
    }
    if ($Type -eq "msi") {
        if ($entry.PSChildName -notmatch '^\{[0-9A-Fa-f-]+\}$') {
            throw "Unexpected MSI product identifier: $($entry.PSChildName)"
        }
        $process = Start-Process msiexec.exe -ArgumentList @(
            "/x", $entry.PSChildName, "/qn", "/norestart"
        ) -Wait -PassThru
    }
    else {
        $command = if ($entry.QuietUninstallString) {
            $entry.QuietUninstallString
        } else {
            $entry.UninstallString
        }
        if ($command -notmatch '^\s*"([^"]+\.exe)"(?:\s.*)?$') {
            throw "Unexpected NSIS uninstall command; refusing to execute it."
        }
        $uninstaller = $Matches[1]
        if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) {
            throw "NSIS uninstaller does not exist: $uninstaller"
        }
        $process = Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -PassThru
    }
    if ($process.ExitCode -ne 0) {
        throw "Uninstall failed with exit code $($process.ExitCode)."
    }
}

$currentPath = Resolve-InstallerPath $CurrentInstaller
$previousPath = if ($PreviousInstaller) { Resolve-InstallerPath $PreviousInstaller } else { $null }
$dataDirectory = Join-Path $env:APPDATA "app.loredock.desktop"
$markerPath = Join-Path $dataDirectory "installer-acceptance-marker.txt"

if (Get-LoreDockUninstallEntry) {
    throw "LoreDock is already installed. Start from a clean disposable VM."
}
if (Test-Path -LiteralPath $dataDirectory) {
    throw "LoreDock data already exists at $dataDirectory. Start from a clean VM or preserve it manually."
}

$installPath = if ($previousPath) { $previousPath } else { $currentPath }
Invoke-Installer -Path $installPath -Type $InstallerType
$initialExecutable = Invoke-LoreDockSmoke

New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
[guid]::NewGuid().ToString("N") | Set-Content -LiteralPath $markerPath -Encoding ascii
$markerHash = (Get-FileHash -LiteralPath $markerPath -Algorithm SHA256).Hash

if ($previousPath) {
    Invoke-Installer -Path $currentPath -Type $InstallerType
    $upgradedExecutable = Invoke-LoreDockSmoke
    if ((Get-FileHash -LiteralPath $markerPath -Algorithm SHA256).Hash -ne $markerHash) {
        throw "User data marker changed during upgrade."
    }
}
else {
    $upgradedExecutable = $null
}

Uninstall-LoreDock -Type $InstallerType
Start-Sleep -Seconds 2
if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
    throw "User data was removed during uninstall."
}
if (Get-Process -Name "LoreDock", "loredock-core" -ErrorAction SilentlyContinue) {
    throw "LoreDock processes remain after uninstall."
}

[PSCustomObject]@{
    InstallerType = $InstallerType
    CurrentInstaller = $currentPath
    PreviousInstaller = $previousPath
    InitialExecutable = $initialExecutable
    UpgradedExecutable = $upgradedExecutable
    DataPreserved = $true
    OrphanProcesses = 0
    MarkerPath = $markerPath
}
