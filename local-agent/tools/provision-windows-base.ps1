<#
.SYNOPSIS
    Provision the native Windows PlatformIO Base Environment for the CompilerIO Local Agent (M2.4).

.DESCRIPTION
    Explicit, repeatable, host-native provisioning of <workspace>\runtime\platformio-data with the
    pinned esp32dev / Arduino stack used by the validated Linux baseline (ccbcc91):

        PlatformIO Core                        6.1.19
        platformio/espressif32 (platform)      7.0.1
        espressif/toolchain-xtensa-esp32       8.4.0+2021r2-patch5   (windows_amd64 build)
        platformio/framework-arduinoespressif32 3.20017.241212+sha.dcc1105b
        platformio/tool-esptoolpy              2.41100.0
        platformio/tool-scons                  4.40801.0
        platformio/tool-mkspiffs               2.230.0
        platformio/tool-mklittlefs             1.203.210628
        platformio/tool-mkfatfs                2.0.1

    Rules:
      * Never copies or reuses a Linux Base: aborts if any installed package targets another OS.
      * Never upgrades: every package is installed by exact version; a different installed version aborts.
      * Downloads go to a temporary cache outside the Base.
      * Validates the result and writes evidence to <workspace>\runtime\windows-base-provision.json.
      * Nothing is installed unless requested: the Local Agent venv must already exist, unless
        -CreateVenv is passed explicitly.

.PARAMETER WorkspaceRoot
    CompilerIO checkout root. Defaults to two levels above this script.

.PARAMETER CreateVenv
    Explicitly create local-agent\venv with Python 3.12 (py launcher) and install pinned Python packages.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File local-agent\tools\provision-windows-base.ps1
    powershell -ExecutionPolicy Bypass -File local-agent\tools\provision-windows-base.ps1 -CreateVenv
#>
[CmdletBinding()]
param(
    [string]$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [switch]$CreateVenv
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$PioVersion = '6.1.19'
$PythonPins = @('platformio==6.1.19', 'fastapi==0.141.1', 'uvicorn==0.40.0')
# Installed in this order; the platform last with --skip-dependencies so no unpinned package is pulled in.
$Packages = @(
    @{ Kind = 'tool';     Spec = 'espressif/toolchain-xtensa-esp32@8.4.0+2021r2-patch5';            Dir = 'packages\toolchain-xtensa-esp32';       Version = '8.4.0+2021r2-patch5';        Native = $true  }
    @{ Kind = 'tool';     Spec = 'platformio/framework-arduinoespressif32@3.20017.241212+sha.dcc1105b'; Dir = 'packages\framework-arduinoespressif32'; Version = '3.20017.241212+sha.dcc1105b'; Native = $false }
    @{ Kind = 'tool';     Spec = 'platformio/tool-esptoolpy@2.41100.0';                            Dir = 'packages\tool-esptoolpy';               Version = '2.41100.0';                  Native = $false }
    @{ Kind = 'tool';     Spec = 'platformio/tool-scons@4.40801.0';                                Dir = 'packages\tool-scons';                   Version = '4.40801.0';                  Native = $false }
    @{ Kind = 'tool';     Spec = 'platformio/tool-mkspiffs@2.230.0';                               Dir = 'packages\tool-mkspiffs';                Version = '2.230.0';                    Native = $true  }
    @{ Kind = 'tool';     Spec = 'platformio/tool-mklittlefs@1.203.210628';                        Dir = 'packages\tool-mklittlefs';              Version = '1.203.210628';               Native = $true  }
    @{ Kind = 'tool';     Spec = 'platformio/tool-mkfatfs@2.0.1';                                  Dir = 'packages\tool-mkfatfs';                 Version = '2.0.1';                      Native = $true  }
    @{ Kind = 'platform'; Spec = 'platformio/espressif32@7.0.1';                                   Dir = 'platforms\espressif32';                 Version = '7.0.1';                      Native = $false }
)
# Same markers the Local Agent checks in EnvironmentManager.MARKERS.
$Markers = @(
    'platforms\espressif32\platform.json',
    'packages\framework-arduinoespressif32',
    'packages\tool-esptoolpy',
    'packages\tool-scons',
    'packages\toolchain-xtensa-esp32',
    'packages\tool-esptoolpy\esptool.py'
)

function Fail([string]$Message) {
    Write-Host "PROVISIONING FAILED: $Message" -ForegroundColor Red
    exit 1
}

function Read-PackageMeta([string]$Path) {
    $file = if (Test-Path (Join-Path $Path 'platform.json')) { Join-Path $Path 'platform.json' } else { Join-Path $Path 'package.json' }
    if (-not (Test-Path $file)) { return $null }
    return Get-Content -Raw -Encoding UTF8 $file | ConvertFrom-Json
}

function Get-Systems($Meta) {
    if ($null -eq $Meta -or -not ($Meta.PSObject.Properties.Name -contains 'system')) { return @('*') }
    return @($Meta.system)
}

# --- 1. Host checks (no silent substitution) -------------------------------------------
if ($env:OS -ne 'Windows_NT') { Fail 'This script must run on a native Windows host.' }
if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { Fail "Unsupported architecture '$($env:PROCESSOR_ARCHITECTURE)'; windows_amd64 is required." }

$Base = Join-Path $WorkspaceRoot 'runtime\platformio-data'
$Venv = Join-Path $WorkspaceRoot 'local-agent\venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
Write-Host "Workspace : $WorkspaceRoot"
Write-Host "Base      : $Base"

if (-not (Test-Path $Py)) {
    if (-not $CreateVenv) {
        Fail "Local Agent venv not found at $Venv. Re-run with -CreateVenv to create it explicitly."
    }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $launcher) { Fail 'Python launcher "py" not found; install Python 3.12 (64-bit) first.' }
    & py -3.12 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the venv with "py -3.12". Python 3.12 is required.' }
    & $Py -m pip install --disable-pip-version-check @PythonPins
    if ($LASTEXITCODE -ne 0) { Fail 'pip install of pinned Python packages failed.' }
}

$pyVersion = (& $Py -c 'import sys; print("%d.%d" % sys.version_info[:2])').Trim()
if ([version]$pyVersion -lt [version]'3.12') { Fail "Local Agent venv Python is $pyVersion; 3.12 or newer is required." }
$pioReported = & $Py -m platformio --version 2>$null
if ($LASTEXITCODE -ne 0 -or $pioReported -notmatch [regex]::Escape($PioVersion)) {
    Fail "PlatformIO Core $PioVersion is required in the venv (found: '$pioReported'). Install it with: $Py -m pip install platformio==$PioVersion"
}
Write-Host "Python    : $pyVersion ($Py)"
Write-Host "PlatformIO: $pioReported"

# --- 2. Refuse a foreign (e.g. copied Linux) Base and version drift ----------------------
if (Test-Path $Base) {
    foreach ($pkg in $Packages) {
        $path = Join-Path $Base $pkg.Dir
        if (-not (Test-Path $path)) { continue }
        $meta = Read-PackageMeta $path
        $systems = Get-Systems $meta
        if ($pkg.Native -and -not ($systems -contains 'windows_amd64')) {
            Fail "$($pkg.Dir) is not a native Windows build (system: $($systems -join ', ')). Do not reuse another host's Base; use a fresh runtime\platformio-data."
        }
        if ($null -ne $meta -and $meta.version -ne $pkg.Version) {
            Fail "$($pkg.Dir) is version $($meta.version), expected $($pkg.Version). Refusing to upgrade/downgrade an existing Base."
        }
    }
}

# --- 3. Install exact pins into the Base (downloads cached outside the Base) -----------
New-Item -ItemType Directory -Force -Path $Base | Out-Null
$Cache = Join-Path ([System.IO.Path]::GetTempPath()) ("compilerio-pio-cache-" + [guid]::NewGuid().ToString('N'))
$env:PLATFORMIO_CORE_DIR = $Base
$env:PLATFORMIO_CACHE_DIR = $Cache
$env:PLATFORMIO_SETTING_ENABLE_TELEMETRY = 'No'
$env:PYTHONUTF8 = '1'
try {
    foreach ($pkg in $Packages) {
        $flag = if ($pkg.Kind -eq 'platform') { '-p' } else { '-t' }
        $extra = if ($pkg.Kind -eq 'platform') { @('--skip-dependencies') } else { @() }
        Write-Host "Installing $($pkg.Spec) ..."
        & $Py -m platformio pkg install -g $flag $pkg.Spec @extra
        if ($LASTEXITCODE -ne 0) { Fail "Installation of $($pkg.Spec) failed." }
    }
}
finally {
    Remove-Item Env:PLATFORMIO_CORE_DIR, Env:PLATFORMIO_CACHE_DIR -ErrorAction SilentlyContinue
    if (Test-Path $Cache) { Remove-Item -Recurse -Force $Cache }
}

# --- 4. Validate the resulting Base ------------------------------------------------------
$errors = @()
foreach ($marker in $Markers) {
    if (-not (Test-Path (Join-Path $Base $marker))) { $errors += "missing marker $marker" }
}
$evidencePackages = @()
foreach ($pkg in $Packages) {
    $meta = Read-PackageMeta (Join-Path $Base $pkg.Dir)
    if ($null -eq $meta) { $errors += "missing metadata for $($pkg.Dir)"; continue }
    $systems = Get-Systems $meta
    if ($meta.version -ne $pkg.Version) { $errors += "$($pkg.Dir) version $($meta.version) != $($pkg.Version)" }
    if ($pkg.Native -and -not ($systems -contains 'windows_amd64')) { $errors += "$($pkg.Dir) is not windows_amd64 (system: $($systems -join ', '))" }
    $evidencePackages += [ordered]@{ dir = $pkg.Dir; spec = $pkg.Spec; version = $meta.version; system = $systems }
}
$expectedDirs = $Packages | ForEach-Object { $_.Dir }
foreach ($root in @('packages', 'platforms')) {
    Get-ChildItem -Directory (Join-Path $Base $root) | ForEach-Object {
        $rel = "$root\$($_.Name)"
        if ($expectedDirs -notcontains $rel) { $errors += "unexpected package $rel (not pinned)" }
    }
}
if ($errors.Count -gt 0) { Fail ("Base validation failed:`n  " + ($errors -join "`n  ")) }

# Content-free listing fingerprint (relative path + size), recorded as provisioning evidence.
$files = Get-ChildItem -Recurse -File -Force $Base | Sort-Object FullName
$listing = ($files | ForEach-Object { "{0}`t{1}" -f $_.FullName.Substring($Base.Length).TrimStart('\'), $_.Length }) -join "`n"
$sha = [System.Security.Cryptography.SHA256]::Create()
$fingerprint = -join ($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($listing)) | ForEach-Object { $_.ToString('x2') })

$evidence = [ordered]@{
    provisioned_at   = (Get-Date).ToString('o')
    host             = [ordered]@{ os = [System.Environment]::OSVersion.VersionString; arch = $env:PROCESSOR_ARCHITECTURE; computer = $env:COMPUTERNAME }
    python           = $pyVersion
    platformio       = "$pioReported"
    base_environment = $Base
    packages         = $evidencePackages
    file_count       = $files.Count
    listing_sha256   = $fingerprint
}
$evidencePath = Join-Path $WorkspaceRoot 'runtime\windows-base-provision.json'
$evidence | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $evidencePath

Write-Host ''
Write-Host 'PROVISIONING OK: Windows Base Environment complete and pinned.' -ForegroundColor Green
Write-Host "Evidence  : $evidencePath"
Write-Host "Files     : $($files.Count), listing SHA-256 $fingerprint"
Write-Host 'Next: start the agent (Personal mode) and POST /environment/prepare to validate an isolated esp32dev build.'
exit 0
