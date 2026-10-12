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
  Say "repo-scout is removed."
  Note "Your runs and index stay in your user folder."
  return
}

# 1. uv: installs Python and the app into an isolated environment, no system Python needed
if (-not (Have uv)) {
  Say "Installing uv (it installs Python and repo-scout)"
  Invoke-RestMethod https://astral.sh/uv/install.ps1 -ErrorAction Stop | Invoke-Expression
  Refresh-Path
  if (-not (Have uv)) { throw "uv is installed, but this terminal does not see it. Open a new terminal and run this command again." }
}

# 2. gh: every GitHub search goes through the official GitHub CLI
if (-not (Have gh)) {
  Say "Installing the GitHub CLI (gh)"
  Note "repo-scout searches GitHub through gh."
  if (Have winget) {
    Note "winget installs it. Windows may ask you to allow the install."
    winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
  }
  if (-not (Have gh)) {
    Warn "Could not install gh."
    Note "Everything else will be installed."
    Note "Install gh from https://cli.github.com/, then run this command again."
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
    catch { throw "No release found, or GitHub is not reachable. To install the main branch, set `$env:REPO_SCOUT_MAIN = `"1`" and run this command again." }
  }
  $Spec = "repo-scout @ https://github.com/$Repo/releases/download/v$Version/repo_scout-$Version-py3-none-any.whl"
}
Say "Installing repo-scout $Version"
uv tool install --reinstall --python $Python $Spec
if ($LASTEXITCODE -ne 0) { throw "uv could not install repo-scout. See the uv output above." }
uv tool update-shell *> $null
$Bin = Join-Path (uv tool dir --bin) "repo-scout.exe"

# 4. GitHub login, once
if (Have gh) {
  gh auth status *> $null
  if ($LASTEXITCODE -ne 0) {
    if ($Interactive) {
      Say "Log in to GitHub in the browser page that opens. Read-only access is enough."
      gh auth login --web --git-protocol https
      if ($LASTEXITCODE -ne 0) { Warn "Not logged in. Before your first search, run: gh auth login" }
    } else {
      Warn "Not logged in to GitHub. Before your first search, run: gh auth login"
    }
  }
}

# 5. download the embedding model now so the first search does not stall, then show what is ready
Say "Checking the setup"
& $Bin doctor --fix
if ($LASTEXITCODE -ne 0) { Warn "Fix the items marked with a cross above, then check again: repo-scout doctor" }

# 6. advanced mode (optional): asked once, skipped when a key is already saved
$EnvFile = if ($env:REPO_SCOUT_ENV) { $env:REPO_SCOUT_ENV } else { "$HOME\.config\repo-scout\.env" }
$HasKey = (Test-Path $EnvFile) -and (Select-String -Path $EnvFile -Pattern '^(LLM_API_KEY|OMNIROUTE_API_KEY|TYPESAFE_API_KEY)=' -Quiet)
if ($Interactive -and -not $HasKey) {
  Note "repo-scout works without external models. This is basic mode."
  Note "Advanced mode adds two extras, each with its own key:"
  Note "- LLM draft: a model writes search queries from your request in any language."
  Note "  Free: OmniRoute (https://github.com/diegosouzapw/OmniRoute) or a local Ollama."
  Note "- Fit: Jev by TypeSafe rates how well each top result fits your task."
  Note "  Key: https://console.typesafe.ai/keys"
  Note "You can set this up later: repo-scout config"
  $answer = Read-Host "Set up advanced mode now? [y/N]"
  if ($answer -match '^[yY]') {
    & $Bin config
    if ($LASTEXITCODE -ne 0) { Warn "Settings are not saved. To set them up later, run: repo-scout config" }
  }
}

Say "repo-scout is installed. To start it, run: repo-scout"
Note "Command not found? Open a new terminal or run: $Bin"
if ($env:REPO_SCOUT_NO_LAUNCH -ne "1" -and $Interactive) {
  $answer = Read-Host "Start repo-scout now? [Y/n]"
  if ($answer -notmatch '^[nN]') {
    Say "Opening repo-scout in your browser. To stop it, press Ctrl+C here."
    & $Bin gui --open
  }
}
