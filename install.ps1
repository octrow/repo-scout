# repo-scout installer for Windows (PowerShell).
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/octrow/repo-scout/main/install.ps1 | iex"
# Options are environment variables, since `irm | iex` cannot pass arguments:
#   $env:REPO_SCOUT_VERSION = "0.1.0"   # a specific release instead of the latest one
#   $env:REPO_SCOUT_MAIN = "1"          # current main branch instead of a release
#   $env:REPO_SCOUT_NO_LAUNCH = "1"     # install only, do not offer to start the GUI
#   $env:REPO_SCOUT_UNINSTALL = "1"     # remove the app, keep your runs and index
# Re-running it updates. $env:REPO_SCOUT_SOURCE = <path or uv spec> installs from there instead (CI, local testing).
# "Continue": in Windows PowerShell 5.1 "Stop" turns any stderr line of a redirected native command
# (uv, gh) into a fatal error; native failures are checked through $LASTEXITCODE instead
$ErrorActionPreference = "Continue"

$Repo = "octrow/repo-scout"
$Python = "3.12"  # ponytail: pinned so onnxruntime/fastembed wheels exist; bump when they ship for newer Pythons

function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Note($m) { Write-Host "    $m" }
function Warn($m) { Write-Host "!! $m" -ForegroundColor Yellow }
function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
# installers update PATH in the registry, not in this session
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User") + ";$HOME\.local\bin"
}
$Interactive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected

Refresh-Path

if ($env:REPO_SCOUT_UNINSTALL -eq "1") {
  if (Have uv) { uv tool uninstall repo-scout }
  Say "repo-scout removed. Your runs and index stay in your user data folder."
  return
}

# 1. uv: installs Python and the app into an isolated environment, no system Python needed
if (-not (Have uv)) {
  Say "Installing uv, the Python package manager repo-scout runs on"
  Invoke-RestMethod https://astral.sh/uv/install.ps1 -ErrorAction Stop | Invoke-Expression
  Refresh-Path
  if (-not (Have uv)) { throw "uv was installed but is not on PATH. Open a new terminal and re-run this command." }
}

# 2. gh: every GitHub search goes through the official GitHub CLI
if (-not (Have gh)) {
  Say "Installing the GitHub CLI (gh)"
  Note "repo-scout searches GitHub through gh, which keeps your login in Windows Credential Manager."
  if (Have winget) {
    Note "It comes from winget; Windows may ask you to allow the install."
    winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
  }
  if (-not (Have gh)) {
    Warn "Could not install gh automatically."
    Note "Install it from https://cli.github.com/ (a single .msi installer),"
    Note "then re-run this command. Everything else is installed already."
  }
}

# 3. the app: a release wheel built and tested by CI, or the main branch
$Version = ""
if ($env:REPO_SCOUT_SOURCE) {
  $Spec = $env:REPO_SCOUT_SOURCE
} elseif ($env:REPO_SCOUT_MAIN -eq "1") {
  $Spec = "repo-scout @ https://github.com/$Repo/archive/refs/heads/main.tar.gz"
} else {
  $Version = "$env:REPO_SCOUT_VERSION".TrimStart("v")
  if (-not $Version) {
    try { $Version = (Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" -ErrorAction Stop).tag_name.TrimStart("v") }
    catch { throw "No release found (or GitHub is unreachable). Set `$env:REPO_SCOUT_MAIN = `"1`" and re-run." }
  }
  $Spec = "repo-scout @ https://github.com/$Repo/releases/download/v$Version/repo_scout-$Version-py3-none-any.whl"
}
Say "Installing repo-scout $Version"
uv tool install --reinstall --python $Python $Spec
if ($LASTEXITCODE -ne 0) { throw "uv tool install failed" }
uv tool update-shell *> $null
$Bin = Join-Path (uv tool dir --bin) "repo-scout.exe"

# 4. GitHub login, once
if (Have gh) {
  gh auth status *> $null
  if ($LASTEXITCODE -ne 0) {
    if ($Interactive) {
      Say "Log in to GitHub: a browser page opens, read-only access is enough"
      gh auth login --web --git-protocol https
      if ($LASTEXITCODE -ne 0) { Warn "Login skipped. Run 'gh auth login' before your first search." }
    } else {
      Warn "Not logged in to GitHub. Run 'gh auth login' before your first search."
    }
  }
}

# 5. download the embedding model now so the first search does not stall, then show what is ready
Say "Checking the setup"
& $Bin doctor --fix
if ($LASTEXITCODE -ne 0) { Warn "Fix the items marked with a cross above, then check again with: repo-scout doctor" }

Say "Installed. Start repo-scout any time with: repo-scout"
Note "(open a new terminal if the command is not found; full path: $Bin)"
if ($env:REPO_SCOUT_NO_LAUNCH -ne "1" -and $Interactive) {
  $answer = Read-Host "Start repo-scout now? [Y/n]"
  if ($answer -notmatch '^[nN]') {
    Say "Starting the GUI in your browser, press Ctrl+C here to stop it"
    & $Bin gui --open
  }
}
