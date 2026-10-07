<#
.SYNOPSIS
Sets up a cloned JettsTUI repository on native Windows.

.DESCRIPTION
Installs uv when needed, creates or updates the local venv, installs JettsTUI,
adds its command to the user PATH, provisions Node.js, syncs bundled skills,
and starts the provider/model wizard.

.PARAMETER SkipSetup
Install the checkout without launching the provider/model wizard.

.PARAMETER Recreate
Delete and rebuild the checkout's venv. The default safely reuses it.

.PARAMETER SkipNode
Skip Node.js provisioning when only the basic Python CLI is needed.

.EXAMPLE
.\setup-jetts-tui.ps1

.EXAMPLE
.\setup-jetts-tui.ps1 -SkipSetup
#>

[CmdletBinding()]
param(
    [switch]$SkipSetup,
    [switch]$Recreate,
    [switch]$SkipNode
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PreferredVenv = Join-Path $RepoRoot ".venv"
$LegacyVenv = Join-Path $RepoRoot "venv"
$VenvDir = if (Test-Path -LiteralPath (Join-Path $PreferredVenv "Scripts\python.exe") -PathType Leaf) {
    $PreferredVenv
} elseif (Test-Path -LiteralPath (Join-Path $LegacyVenv "Scripts\python.exe") -PathType Leaf) {
    $LegacyVenv
} else {
    $PreferredVenv
}
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvScripts = Join-Path $VenvDir "Scripts"
$PythonVersion = "3.11"

function Write-Step([string]$Message) {
    Write-Host "-> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "OK $Message" -ForegroundColor Green
}

function Find-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "jettstui\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "jettstui\bin\uv.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

function Add-UserPath([string]$Directory) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @($userPath -split ";" | Where-Object { $_ })
    $alreadyPresent = $entries | Where-Object {
        $_.TrimEnd("\") -ieq $Directory.TrimEnd("\")
    }
    if (-not $alreadyPresent) {
        $nextPath = if ($userPath) { "$Directory;$userPath" } else { $Directory }
        [Environment]::SetEnvironmentVariable("Path", $nextPath, "User")
        Write-Ok "Added the local JettsTUI command to your user PATH"
    } else {
        Write-Ok "The local JettsTUI command is already on your user PATH"
    }
    if (($env:Path -split ";") -notcontains $Directory) {
        $env:Path = "$Directory;$env:Path"
    }
}

Push-Location $RepoRoot
try {
    Write-Host ""
    Write-Host "JettsTUI local checkout setup" -ForegroundColor Yellow
    Write-Host "Repository: $RepoRoot"
    Write-Host ""

    $uv = Find-Uv
    if (-not $uv) {
        Write-Step "Installing uv"
        $installer = Join-Path ([System.IO.Path]::GetTempPath()) "jettstui-uv-install.ps1"
        Invoke-WebRequest "https://astral.sh/uv/install.ps1" -OutFile $installer -UseBasicParsing
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
            if ($LASTEXITCODE -ne 0) { throw "uv installer failed with exit code $LASTEXITCODE" }
        } finally {
            Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
        }
        $uv = Find-Uv
        if (-not $uv) {
            throw "uv installed but uv.exe was not found. Open a new PowerShell window and retry."
        }
    }
    Write-Ok "uv found: $uv"

    if ($Recreate -and (Test-Path -LiteralPath $VenvDir)) {
        Write-Step "Recreating the local virtual environment"
        Remove-Item -LiteralPath $VenvDir -Recurse -Force
    }

    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        Write-Step "Creating venv with Python $PythonVersion"
        Invoke-Checked $uv "python" "install" $PythonVersion
        Invoke-Checked $uv "venv" $VenvDir "--python" $PythonVersion
    } else {
        Write-Ok "Reusing existing venv (pass -Recreate to rebuild)"
    }

    Write-Step "Installing JettsTUI and its Python dependencies"
    $previousProjectEnvironment = $env:UV_PROJECT_ENVIRONMENT
    $env:UV_PROJECT_ENVIRONMENT = $VenvDir
    try {
        & $uv sync --extra all --locked
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Lockfile sync failed; retrying with a fresh dependency resolve."
            Invoke-Checked $uv "pip" "install" "--python" $VenvPython "-e" ".[all]"
        }
    } finally {
        $env:UV_PROJECT_ENVIRONMENT = $previousProjectEnvironment
    }

    if (-not (Test-Path -LiteralPath ".env") -and (Test-Path -LiteralPath ".env.example")) {
        Copy-Item -LiteralPath ".env.example" -Destination ".env"
        Write-Ok "Created .env from .env.example"
    }

    Add-UserPath $VenvScripts

    if (-not $SkipNode) {
        Write-Step "Checking Node.js for the TUI and browser tools"
        # install.ps1's ensure protocol exits deliberately, so isolate it in a
        # child PowerShell process instead of terminating this setup script.
        & powershell.exe -NoProfile -ExecutionPolicy Bypass `
            -File (Join-Path $RepoRoot "scripts\install.ps1") `
            -Ensure "node" `
            -NonInteractive `
            -InstallDir $RepoRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Node.js setup failed with exit code $LASTEXITCODE"
        }
    }

    Write-Step "Syncing bundled skills"
    Invoke-Checked $VenvPython (Join-Path $RepoRoot "tools\skills_sync.py")

    Write-Host ""
    Write-Ok "Setup complete"
    Write-Host "  Command: $VenvScripts\jettstui.exe"
    Write-Host "  Diagnose: jetts-tui doctor"
    Write-Host ""

    if (-not $SkipSetup) {
        Write-Step "Starting the provider and model setup wizard"
        Invoke-Checked $VenvPython "-m" "jettstui.main" "setup"
    } else {
        Write-Host "Finish configuration later with: jetts-tui setup"
    }
} finally {
    Pop-Location
}
