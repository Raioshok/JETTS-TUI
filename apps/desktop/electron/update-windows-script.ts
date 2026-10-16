/**
 * update-windows-script.ts — pure generator for the Windows detached updater
 * script that allows users to update directly through the desktop app.
 *
 * Background:
 * On Windows, a running Electron app (`JettsTUI.exe`) and its backend (`python.exe`)
 * keep binary and `.pyd` files locked. During `jettstui update` + `desktop --build-only`,
 * the venv and desktop package cannot replace running executables.
 *
 * When the Tauri setup installer binary isn't present (e.g. source/git or CLI installs),
 * the desktop hands off to this detached PowerShell updater script. The desktop
 * stops its backend, writes the update-in-progress marker, spawns the script
 * detached, and exits cleanly. The script waits for the desktop process to exit,
 * executes `jettstui update`, and relaunches the updated desktop app.
 */

export interface WindowsUpdateScriptOptions {
  parentPid?: number
  updateRoot: string
  branch?: string
  execPath?: string
  execArgs?: string[]
  jettstuiHome: string
  markerPath?: string
}

/**
 * Escape a string for inclusion inside PowerShell double quotes (`"..."`).
 * In PowerShell double quotes, backtick (`) is the escape character, while
 * backslash (\) is treated literally. We escape `, $, and every character
 * PowerShell accepts as a double-quote delimiter — the typographic quotes
 * “ ” „ terminate a "..." string too, so leaving them bare would let a path
 * or relaunch argument break out of the string.
 */
export function psEscape(str: string): string {
  return String(str || '')
    .replace(/`/g, '``')
    .replace(/\$/g, '`$')
    .replace(/["“”„]/g, quote => `\`${quote}`)
}

/**
 * Generate a standalone PowerShell script that performs the update and relaunches
 * the desktop app once finished.
 */
export function buildWindowsUpdateScript(opts: WindowsUpdateScriptOptions): string {
  const {
    parentPid = 0,
    updateRoot,
    branch = 'main',
    execPath = '',
    execArgs = [],
    jettstuiHome,
    markerPath = ''
  } = opts

  const formattedArgs = execArgs.length > 0
    ? `@(${execArgs.map(arg => `"${psEscape(arg)}"`).join(', ')})`
    : '@()'

  return `param()
try { $host.UI.RawUI.WindowTitle = "JettsTUI Desktop Update" } catch {}
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "       Updating JettsTUI Desktop          " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$markerPath = "${psEscape(markerPath)}"
if ($markerPath) {
  # Claim the update-in-progress marker with this script's pid before waiting,
  # so a relaunched desktop parks instead of re-locking the venv mid-update.
  try {
    $startedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    [IO.File]::WriteAllText($markerPath, "$PID\`n$startedAt\`n")
  } catch {}
}

$parentPid = ${parentPid}
if ($parentPid -gt 0) {
  Write-Host "Waiting for JettsTUI to close..." -ForegroundColor Gray
  try {
    $proc = Get-Process -Id $parentPid -ErrorAction SilentlyContinue
    if ($proc) {
      $null = $proc.WaitForExit(30000)
    }
  } catch {}
  Start-Sleep -Milliseconds 1500
}

$env:JETTSTUI_HOME = "${psEscape(jettstuiHome)}"
$env:PYTHONUNBUFFERED = "1"

$updateRoot = "${psEscape(updateRoot)}"
$venvPython = Join-Path $updateRoot "venv\\Scripts\\python.exe"
$venvJettstui = Join-Path $updateRoot "venv\\Scripts\\jettstui.exe"
$branch = "${psEscape(branch)}"

Write-Host "Updating JettsTUI (branch: $branch)..." -ForegroundColor Yellow
$updateArgs = @("update", "--yes", "--force", "--branch", $branch)

if (Test-Path $venvJettstui) {
  & $venvJettstui @updateArgs
} elseif (Test-Path $venvPython) {
  & $venvPython -m jettstui.main @updateArgs
} else {
  jettstui @updateArgs
}

$exitCode = $LASTEXITCODE

if ($markerPath -and (Test-Path -LiteralPath $markerPath)) {
  Remove-Item -LiteralPath $markerPath -Force -ErrorAction SilentlyContinue
}
# This script is single-use; don't leave it behind in %TEMP%.
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue

$execPath = "${psEscape(execPath)}"
$execArgs = ${formattedArgs}

if ($exitCode -eq 0) {
  Write-Host ""
  Write-Host "Update completed successfully! Launching JettsTUI..." -ForegroundColor Green
  Start-Sleep -Milliseconds 1000
  if ($execPath -and (Test-Path $execPath) -and ($execPath -notmatch "electron\\.exe$")) {
    if ($execArgs.Count -gt 0) {
      Start-Process -FilePath $execPath -ArgumentList $execArgs
    } else {
      Start-Process -FilePath $execPath
    }
  } elseif (Test-Path $venvJettstui) {
    Start-Process -FilePath $venvJettstui -ArgumentList "desktop"
  } else {
    Start-Process -FilePath "jettstui" -ArgumentList "desktop"
  }
} else {
  Write-Host ""
  Write-Host "Update exited with code $exitCode." -ForegroundColor Red
  Write-Host "Press any key to close..." -ForegroundColor Gray
  try {
    $null = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
  } catch {
    Start-Sleep -Seconds 10
  }
}
`
}
