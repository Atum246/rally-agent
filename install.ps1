# ═══════════════════════════════════════════════════════════════════════════════
# 🟣 RALLY AGENT — PowerShell Installer for Windows
#
# One-liner:
#   irm https://raw.githubusercontent.com/Atum246/rally-agent/main/install.ps1 | iex
#
# Or download and run:
#   .\install.ps1 [-Minimal] [-Dev] [-Uninstall]
# ═══════════════════════════════════════════════════════════════════════════════

param(
    [switch]$Minimal,
    [switch]$Dev,
    [switch]$Uninstall,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# ── Configuration ────────────────────────────────────────────────────────────
$RALLY_VERSION = "1.0.0"
$RALLY_HOME = if ($env:RALLY_HOME) { $env:RALLY_HOME } else { Join-Path $env:USERPROFILE ".rally-agent" }
$REPO_URL = "https://github.com/Atum246/rally-agent"
$PYTHON_MIN = [version]"3.10.0"

# ── Help ─────────────────────────────────────────────────────────────────────
if ($Help) {
    Write-Host "Rally Agent Installer for Windows"
    Write-Host ""
    Write-Host "Usage: .\install.ps1 [-Minimal] [-Dev] [-Uninstall] [-Help]"
    Write-Host ""
    Write-Host "  -Minimal    Core only, skip browser/voice dependencies"
    Write-Host "  -Dev        Include development dependencies"
    Write-Host "  -Uninstall  Remove Rally Agent completely"
    Write-Host "  -Help       Show this help"
    Write-Host ""
    Write-Host "One-liner: irm $REPO_URL/raw/main/install.ps1 | iex"
    exit 0
}

# ── Colors ───────────────────────────────────────────────────────────────────
$script:HasAnsi = $Host.UI.RawUI -and $env:WT_SESSION  # Windows Terminal or modern PS

function Write-Purple($t)  { Write-Host $t -ForegroundColor Magenta }
function Write-Green($t)   { Write-Host $t -ForegroundColor Green }
function Write-Red($t)     { Write-Host $t -ForegroundColor Red }
function Write-Yellow($t)  { Write-Host $t -ForegroundColor Yellow }
function Write-Cyan($t)    { Write-Host $t -ForegroundColor Cyan }
function Write-Gray($t)    { Write-Host $t -ForegroundColor DarkGray }

function Log($msg)    { Write-Host "[➤] $msg" -ForegroundColor Magenta }
function Ok($msg)     { Write-Host "[✓] $msg" -ForegroundColor Green }
function Warn($msg)   { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Err($msg)    { Write-Host "[✗] $msg" -ForegroundColor Red }
function Step($msg)   { Write-Host ""; Write-Host "━━━ $msg ━━━" -ForegroundColor Magenta -FontStyle Bold }
function Info($msg)   { Write-Host "    $msg" -ForegroundColor DarkGray }
function Fatal($msg)  { Err $msg; exit 1 }

# ── Banner ───────────────────────────────────────────────────────────────────
function Show-Banner {
    Write-Host ""
    Write-Purple @"
    ██████╗  █████╗ ██╗     ██╗     ██╗   ██╗
    ██╔══██╗██╔══██╗██║     ██║     ╚██╗ ██╔╝
    ██████╔╝███████║██║     ██║      ╚████╔╝
    ██╔══██╗██╔══██║██║     ██║       ╚██╔╝
    ██║  ██║██║  ██║███████╗███████╗   ██║
    ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝
           █████╗  ██████╗ ███████╗███╗   ██╗████████╗
          ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
          ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
          ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
          ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
          ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
"@
    Write-Host "           " -NoNewline; Write-Host "⚡ v$RALLY_VERSION — The OpenClaw Killer 💀" -ForegroundColor Yellow -FontStyle Bold
    Write-Host "           ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
    if ($Minimal) { Write-Host "           📦 Minimal install (core only)" -ForegroundColor Cyan }
    if ($Dev)     { Write-Host "           🔧 Dev install (includes dev deps)" -ForegroundColor Cyan }
    Write-Host ""
}

# ── Uninstall ────────────────────────────────────────────────────────────────
function Invoke-Uninstall {
    Step "🗑️  Uninstalling Rally Agent"
    if (Test-Path $RALLY_HOME) {
        Remove-Item -Recurse -Force $RALLY_HOME
        Ok "Removed $RALLY_HOME"
    }
    # Remove launcher
    $launcherPath = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\rally.cmd"
    if (Test-Path $launcherPath) { Remove-Item -Force $launcherPath; Ok "Removed launcher" }
    # Remove from PATH
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $rallyBin = Join-Path $RALLY_HOME "bin"
    if ($userPath -like "*$rallyBin*") {
        $newPath = ($userPath -split ";" | Where-Object { $_ -ne $rallyBin }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Ok "Removed from PATH"
    }
    Ok "Rally Agent uninstalled. So long! 💀"
    exit 0
}

if ($Uninstall) { Invoke-Uninstall }

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

function Test-CommandExists($cmd) {
    $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue)
}

function Get-PythonVersion($pythonExe) {
    try {
        $ver = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        return [version]$ver
    } catch {
        return $null
    }
}

function Find-Python {
    $candidates = @("python3.12", "python3.11", "python3.10", "python3", "python")
    foreach ($cmd in $candidates) {
        if (Test-CommandExists $cmd) {
            $ver = Get-PythonVersion $cmd
            if ($ver -and $ver -ge $PYTHON_MIN) {
                return $cmd
            }
        }
    }
    # Try the Python Launcher for Windows
    if (Test-CommandExists "py") {
        foreach ($ver in @("3.12", "3.11", "3.10", "3")) {
            try {
                $result = & py "-$ver" -c "import sys; print(sys.version)" 2>$null
                if ($result) { return "py -$ver" }
            } catch {}
        }
    }
    return $null
}

function Add-ToPath($dir) {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$dir*") {
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$dir", "User")
        $env:Path = "$env:Path;$dir"
        Info "Added to PATH: $dir"
    }
}

# ══════════════════════════════════════════════════════════════════════════════
#  PLATFORM DETECTION
# ══════════════════════════════════════════════════════════════════════════════

function Detect-Platform {
    Step "🔍 Detecting Platform"
    $os = (Get-CimInstance Win32_OperatingSystem)
    $script:WindowsVersion = $os.Version
    $script:WindowsCaption = $os.Caption
    $script:Architecture = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
    Info "OS: $WindowsCaption"
    Info "Version: $WindowsVersion | Arch: $Architecture"
    Ok "Platform: Windows/$Architecture"
}

# ══════════════════════════════════════════════════════════════════════════════
#  DEPENDENCY CHECKS
# ══════════════════════════════════════════════════════════════════════════════

function Check-Python {
    Step "🐍 Checking Python 3.10+"

    $script:PythonCmd = Find-Python

    if ($script:PythonCmd) {
        $ver = Get-PythonVersion ($PythonCmd -split " ")[0]
        Ok "Python $ver ($PythonCmd)"
        return
    }

    Err "Python 3.10+ not found"
    Log "Installing Python..."

    # Try winget
    if (Test-CommandExists "winget") {
        Log "Using winget to install Python..."
        & winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements 2>$null
        if ($LASTEXITCODE -eq 0) {
            # Refresh PATH
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
            Start-Sleep -Seconds 2
        }
    }

    # Fallback: direct download
    if (-not (Find-Python)) {
        Warn "winget install may have failed. Trying direct download..."
        $arch = if ($Architecture -eq "x64") { "amd64" } else { "win32" }
        $url = "https://www.python.org/ftp/python/3.12.4/python-3.12.4-$arch.exe"
        $installer = Join-Path $env:TEMP "python-installer.exe"
        Log "Downloading Python from $url..."
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
        Log "Running installer (this may take a moment)..."
        Start-Process -FilePath $installer -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1" -Wait
        Remove-Item -Force $installer -ErrorAction SilentlyContinue
        # Refresh PATH
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        Start-Sleep -Seconds 2
    }

    $script:PythonCmd = Find-Python
    if (-not $script:PythonCmd) {
        Fatal "Python installation failed. Please install Python 3.10+ manually from https://python.org"
    }
    $ver = Get-PythonVersion ($PythonCmd -split " ")[0]
    Ok "Python $ver ($PythonCmd)"
}

function Check-Git {
    Step "📋 Checking Git"

    if (Test-CommandExists "git") {
        $ver = (git --version) -replace "git version ", ""
        Ok "Git $ver"
        return
    }

    Log "Installing Git..."

    if (Test-CommandExists "winget") {
        & winget install Git.Git --silent --accept-package-agreements --accept-source-agreements 2>$null
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    } else {
        # Direct download
        $url = "https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe"
        $installer = Join-Path $env:TEMP "git-installer.exe"
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
        Start-Process -FilePath $installer -ArgumentList "/VERYSILENT", "/NORESTART" -Wait
        Remove-Item -Force $installer -ErrorAction SilentlyContinue
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    }

    if (Test-CommandExists "git") {
        Ok "Git $(git --version)"
    } else {
        Warn "Git installation may have failed — continuing"
    }
}

# ══════════════════════════════════════════════════════════════════════════════
#  INSTALL RALLY
# ══════════════════════════════════════════════════════════════════════════════

function Get-RallySource {
    Step "📥 Getting Rally Agent Source"

    if (-not (Test-Path $RALLY_HOME)) {
        New-Item -ItemType Directory -Path $RALLY_HOME -Force | Out-Null
    }

    # Check if running from inside the repo
    if ((Test-Path "rally.py") -and (Test-Path "requirements.txt")) {
        Log "Installing from local directory..."
        $items = @("core", "cli", "memory", "tools", "agents", "integrations",
                    "marketplace", "security", "utils", "web", "voice",
                    "rally.py", "requirements.txt", "pyproject.toml", "setup.py",
                    "README.md", "LICENSE", ".gitignore")
        foreach ($item in $items) {
            if (Test-Path $item) {
                Copy-Item -Path $item -Destination $RALLY_HOME -Recurse -Force
            }
        }
        Ok "Copied local source"
        return
    }

    # Clone from GitHub
    $gitDir = Join-Path $RALLY_HOME ".git"
    if (Test-Path $gitDir) {
        Log "Updating existing installation..."
        Push-Location $RALLY_HOME
        & git pull --ff-only 2>$null
        Pop-Location
        Ok "Repository updated"
    } else {
        Log "Cloning from $REPO_URL..."
        & git clone --depth 1 $REPO_URL $RALLY_HOME
        Ok "Repository cloned"
    }
}

function Setup-Venv {
    Step "🐍 Setting Up Virtual Environment"

    $venvPath = Join-Path $RALLY_HOME ".venv"

    if (Test-Path (Join-Path $venvPath "Scripts\activate.ps1")) {
        # Verify it works
        $pyExe = Join-Path $venvPath "Scripts\python.exe"
        if (Test-Path $pyExe) {
            Ok "Virtual environment already exists and is healthy"
            return
        }
        Warn "Existing venv is broken, recreating..."
        Remove-Item -Recurse -Force $venvPath
    }

    Log "Creating virtual environment..."
    $pyCmd = ($PythonCmd -split " ")[0]
    & $pyCmd -m venv $venvPath
    if (-not (Test-Path (Join-Path $venvPath "Scripts\activate.ps1"))) {
        Fatal "Failed to create virtual environment"
    }
    Ok "Virtual environment created"
}

function Install-Deps {
    Step "📦 Installing Python Dependencies"

    $venvPath = Join-Path $RALLY_HOME ".venv"
    $pip = Join-Path $venvPath "Scripts\pip.exe"
    $pyExe = Join-Path $venvPath "Scripts\python.exe"

    # Upgrade pip
    Log "Upgrading pip..."
    & $pyExe -m pip install --upgrade pip --quiet 2>$null

    # Core requirements
    $reqFile = Join-Path $RALLY_HOME "requirements.txt"
    if (Test-Path $reqFile) {
        Log "Installing requirements.txt..."
        & $pip install -r $reqFile --quiet
    }

    # Dev deps
    if ($Dev) {
        $devReq = Join-Path $RALLY_HOME "requirements-dev.txt"
        if (Test-Path $devReq) {
            Log "Installing dev requirements..."
            & $pip install -r $devReq --quiet
        }
    }

    # Install package itself
    $pyprojectFile = Join-Path $RALLY_HOME "pyproject.toml"
    if (Test-Path $pyprojectFile) {
        Log "Installing rally-agent package..."
        if ($Minimal) {
            & $pip install -e $RALLY_HOME --quiet 2>$null
        } else {
            & $pip install -e "$RALLY_HOME[all]" --quiet 2>$null
            if ($LASTEXITCODE -ne 0) {
                & $pip install -e $RALLY_HOME --quiet 2>$null
            }
        }
    }

    Ok "Python dependencies installed"
}

function Install-Playwright {
    if ($Minimal) { return }

    Step "🌐 Installing Playwright Browsers"

    $venvPath = Join-Path $RALLY_HOME ".venv"
    $playwright = Join-Path $venvPath "Scripts\playwright.exe"

    if (Test-Path $playwright) {
        Log "Installing Chromium..."
        & $playwright install chromium
        Ok "Playwright browsers installed"
    } else {
        # Try via python module
        $pyExe = Join-Path $venvPath "Scripts\python.exe"
        if (Test-Path $pyExe) {
            Log "Installing Chromium via python..."
            & $pyExe -m playwright install chromium 2>$null
            if ($LASTEXITCODE -eq 0) {
                Ok "Playwright browsers installed"
            } else {
                Warn "Playwright browser install failed — you can retry later with: playwright install chromium"
            }
        } else {
            Warn "Playwright not available, skipping browser install"
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════════
#  CLI & SHELL SETUP
# ══════════════════════════════════════════════════════════════════════════════

function Create-Launcher {
    Step "🚀 Creating CLI Launcher"

    $binDir = Join-Path $RALLY_HOME "bin"
    if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir -Force | Out-Null }

    # Create rally.cmd launcher
    $cmdContent = @"
@echo off
:: Rally Agent CLI Launcher
set "RALLY_HOME=$RALLY_HOME"
call "%RALLY_HOME%\.venv\Scripts\activate.bat" >nul 2>&1
python "%RALLY_HOME%\rally.py" %*
"@
    Set-Content -Path (Join-Path $binDir "rally.cmd") -Value $cmdContent -Encoding ASCII

    # Create rally.ps1 launcher for PowerShell
    $ps1Content = @"
#!/usr/bin/env pwsh
# Rally Agent CLI Launcher
`$RALLY_HOME = "$RALLY_HOME"
& "`$RALLY_HOME\.venv\Scripts\Activate.ps1" 2>`$null
& python "`$RALLY_HOME\rally.py" @args
"@
    Set-Content -Path (Join-Path $binDir "rally.ps1") -Value $ps1Content -Encoding UTF8

    # Add to PATH
    Add-ToPath $binDir

    # Create a simple rally.exe shim using a batch file in WindowsApps or user PATH
    $shimDir = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"
    if (-not (Test-Path $shimDir)) { $shimDir = $binDir }

    $shimContent = @"
@echo off
"%RALLY_HOME%\.venv\Scripts\python.exe" "%RALLY_HOME%\rally.py" %*
"@
    Set-Content -Path (Join-Path $shimDir "rally.cmd") -Value $shimContent -Encoding ASCII -ErrorAction SilentlyContinue
    Add-ToPath $shimDir

    Ok "Launcher created in $binDir"
}

function Set-Config {
    Step "⚙️  Generating Configuration"

    $configDir = Join-Path $RALLY_HOME "config"
    if (-not (Test-Path $configDir)) { New-Item -ItemType Directory -Path $configDir -Force | Out-Null }
    $configFile = Join-Path $configDir "rally.toml"

    if (Test-Path $configFile) {
        Warn "Config already exists at $configFile — not overwriting"
        return
    }

    $configContent = @"
# ═══════════════════════════════════════════════════════════════
# RALLY AGENT — Configuration
# Edit this file to customise your Rally Agent experience.
# ═══════════════════════════════════════════════════════════════

[agent]
name = "Rally"
version = "1.0.0"
default_model = "auto"
thinking = true
max_context = 128000

[agent.auto_model]
fallback_order = ["anthropic", "openai", "google", "ollama", "local"]

[cli]
theme = "hacker_purple"
animations = true
banner = true
compact = false
syntax_highlight = true
show_timestamps = true
emoji = true

[memory]
backend = "hybrid"
vector_store = "local"
max_entries = 10000
auto_consolidate = true
encryption = true

[security]
confirm_dangerous = true
audit_log = true
max_file_ops = 100
sandbox_exec = true
blocked_commands = ["rm -rf /", "mkfs", "dd if="]

[tools]
web_search = true
file_ops = true
exec = true
browser = true
code_exec = true

[agents]
max_parallel = 5
auto_delegate = true
orchestrator = true

[integrations]
# Set API keys here or use environment variables:
#   OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, etc.

[marketplace]
auto_update = false
trusted_sources = ["rally-official", "community-verified"]
"@
    Set-Content -Path $configFile -Value $configContent -Encoding UTF8
    Ok "Configuration: $configFile"
}

function Setup-ShellIntegration {
    Step "🐚 PowerShell Profile Integration"

    $profilePath = $PROFILE.CurrentUserAllHosts
    $profileDir = Split-Path $profilePath

    if (-not (Test-Path $profileDir)) {
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    }

    $marker = "# rally-agent"
    if ((Test-Path $profilePath) -and (Get-Content $profilePath -Raw) -match [regex]::Escape($marker)) {
        Info "Shell integration already configured"
        return
    }

    $profileContent = @"

$marker
`$env:RALLY_HOME = "$RALLY_HOME"
`$env:Path += ";$(Join-Path $RALLY_HOME 'bin')"
function r { rally @args }
function rc { rally chat @args }
function rs { rally status @args }
"@

    if (Test-Path $profilePath) {
        Add-Content -Path $profilePath -Value $profileContent
    } else {
        Set-Content -Path $profilePath -Value $profileContent -Encoding UTF8
    }

    Ok "PowerShell profile updated: $profilePath"
    Info "Run '. `$PROFILE' or restart PowerShell to activate"
}

# ══════════════════════════════════════════════════════════════════════════════
#  VERIFY
# ══════════════════════════════════════════════════════════════════════════════

function Test-Installation {
    Step "✅ Verifying Installation"

    $checks = 0; $passed = 0

    # rally command
    $checks++
    $rallyCmd = Join-Path $RALLY_HOME "bin\rally.cmd"
    if ((Test-Path $rallyCmd) -or (Test-CommandExists "rally")) {
        Ok "rally command: available"; $passed++
    } else {
        Err "rally command: NOT found"
    }

    # Virtual environment
    $checks++
    $venvPy = Join-Path $RALLY_HOME ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        Ok "Virtual environment: ready"; $passed++
    } else {
        Err "Virtual environment: NOT found"
    }

    # Python in venv
    $checks++
    if ((Test-Path $venvPy) -and (& $venvPy --version 2>$null)) {
        $ver = & $venvPy --version 2>&1
        Ok "Python in venv: $ver"; $passed++
    } else {
        Err "Python in venv: broken"
    }

    # Configuration
    $checks++
    $configFile = Join-Path $RALLY_HOME "config\rally.toml"
    if (Test-Path $configFile) {
        Ok "Configuration: present"; $passed++
    } else {
        Err "Configuration: NOT found"
    }

    # Core modules
    $checks++
    if (Test-Path (Join-Path $RALLY_HOME "rally.py")) {
        Ok "Core: rally.py present"; $passed++
    } else {
        Err "Core: rally.py NOT found"
    }

    # pip packages
    $checks++
    $venvPip = Join-Path $RALLY_HOME ".venv\Scripts\pip.exe"
    if (Test-Path $venvPip) {
        try {
            & $venvPy -c "import rich; import httpx" 2>$null
            Ok "Core packages: installed (rich, httpx)"; $passed++
        } catch {
            Warn "Core packages: some may be missing"
        }
    } else {
        Warn "Core packages: pip not found"
    }

    Write-Host ""
    if ($passed -eq $checks) {
        Write-Host "    ✓ All $passed/$checks checks passed!" -ForegroundColor Green -FontStyle Bold
    } else {
        Write-Host "    $passed/$checks checks passed" -ForegroundColor Yellow -FontStyle Bold
    }
}

# ══════════════════════════════════════════════════════════════════════════════
#  DONE
# ══════════════════════════════════════════════════════════════════════════════

function Show-Done {
    Write-Host ""
    Write-Purple "╔════════════════════════════════════════════════════════════════╗"
    Write-Purple "║" -NoNewline; Write-Host "  " -NoNewline; Write-Host "🟣 RALLY AGENT v$RALLY_VERSION — Installation Complete!" -ForegroundColor Yellow -FontStyle Bold -NoNewline; Write-Host "            " -NoNewline; Write-Purple "║"
    Write-Purple "╠════════════════════════════════════════════════════════════════╣"
    Write-Purple "║                                                              ║"
    Write-Purple "║" -NoNewline; Write-Host "  Quick start:                                                " -NoNewline; Write-Purple "║"
    Write-Purple "║" -NoNewline; Write-Host "    rally               Interactive mode                      " -NoNewline; Write-Purple "║"
    Write-Purple "║" -NoNewline; Write-Host "    rally chat          Start chatting                        " -NoNewline; Write-Purple "║"
    Write-Purple "║" -NoNewline; Write-Host "    rally status        Check system status                   " -NoNewline; Write-Purple "║"
    Write-Purple "║" -NoNewline; Write-Host "    rally --help        Show all commands                     " -NoNewline; Write-Purple "║"
    Write-Purple "║                                                              ║"
    Write-Purple "║" -NoNewline; Write-Host "  Add your API keys:                                          " -NoNewline; Write-Purple "║"
    Write-Purple "║" -NoNewline; Write-Host "    `$env:OPENAI_API_KEY = 'sk-...'                            " -NoNewline; Write-Purple "║"
    Write-Purple "║" -NoNewline; Write-Host "    Or edit: ~/.rally-agent/config/rally.toml                  " -NoNewline; Write-Purple "║"
    Write-Purple "║                                                              ║"
    Write-Purple "╚════════════════════════════════════════════════════════════════╝"
    Write-Host ""
    Write-Host "    💀 The OpenClaw Killer has been deployed. ⚡" -ForegroundColor Yellow -FontStyle Bold
    Write-Host "    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "    Tip: Run " -ForegroundColor DarkGray -NoNewline; Write-Host "rally" -FontStyle Bold -NoNewline; Write-Host " to get started!" -ForegroundColor DarkGray
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

function Main {
    Show-Banner
    Detect-Platform
    Check-Python
    Check-Git
    Get-RallySource
    Setup-Venv
    Install-Deps
    Install-Playwright
    Create-Launcher
    Set-Config
    Setup-ShellIntegration
    Test-Installation
    Show-Done
}

Main
