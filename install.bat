@echo off
setlocal enabledelayedexpansion
:: ══════════════════════════════════════════════════════════════════════════════
:: 🟣 RALLY AGENT — Batch Installer for Windows (Fallback)
::
:: This is a simple fallback for systems where PowerShell is not available
:: or when running from cmd.exe directly.
::
:: Usage:
::   install.bat [/minimal] [/dev] [/uninstall]
::
:: One-liner (run in cmd):
::   curl -fsSL https://raw.githubusercontent.com/Atum246/rally-agent/main/install.bat -o install.bat && install.bat
:: ══════════════════════════════════════════════════════════════════════════════

set "RALLY_VERSION=1.0.0"
if "%RALLY_HOME%"=="" set "RALLY_HOME=%USERPROFILE%\.rally-agent"
set "REPO_URL=https://github.com/Atum246/rally-agent"
set "PYTHON_MIN=3.10"

:: ── Parse flags ──────────────────────────────────────────────────────────────
set "MINIMAL=false"
set "DEV=false"
set "UNINSTALL=false"
for %%a in (%*) do (
    if /i "%%a"=="/minimal" set "MINIMAL=true"
    if /i "%%a"=="/dev" set "DEV=true"
    if /i "%%a"=="/uninstall" set "UNINSTALL=true"
    if /i "%%a"=="/help" goto :show_help
    if /i "%%a"=="/?" goto :show_help
)

if "%UNINSTALL%"=="true" goto :uninstall

:: ── Banner ───────────────────────────────────────────────────────────────────
echo.
echo     ██████╗  █████╗ ██╗     ██╗     ██╗   ██╗
echo     ██╔══██╗██╔══██╗██║     ██║     ╚██╗ ██╔╝
echo     ██████╔╝███████║██║     ██║      ╚████╔╝
echo     ██╔══██╗██╔══██║██║     ██║       ╚██╔╝
echo     ██║  ██║██║  ██║███████╗███████╗   ██║
echo     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝
echo            █████╗  ██████╗ ███████╗███╗   ██╗████████╗
echo           ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
echo           ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
echo           ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
echo           ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
echo           ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
echo.
echo            v%RALLY_VERSION% - The OpenClaw Killer
echo            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

:: ── Step 1: Detect Platform ─────────────────────────────────────────────────
echo ━━━ Detecting Platform ━━━
echo    OS: Windows
for /f "tokens=4-5 delims=. " %%i in ('ver') do set "WIN_VER=%%i.%%j"
echo    Version: %WIN_VER%
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (set "ARCH=x64") else (set "ARCH=x86")
echo    Architecture: %ARCH%
echo [✓] Platform: Windows/%ARCH%
echo.

:: ── Step 2: Check Python ────────────────────────────────────────────────────
echo ━━━ Checking Python %PYTHON_MIN%+ ━━━
set "PYTHON="

:: Check various Python commands
for %%p in (python3.12 python3.11 python3.10 python3 python) do (
    where %%p >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('%%p --version 2^>^&1') do (
            set "PY_VER=%%v"
            set "PYTHON=%%p"
            goto :python_found
        )
    )
)
goto :python_not_found

:python_found
echo [✓] Python %PY_VER% (%PYTHON%)
goto :check_git

:python_not_found
echo [✗] Python %PYTHON_MIN%+ not found
echo [➤] Attempting to install Python via winget...

where winget >nul 2>&1
if %errorlevel% equ 0 (
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    if !errorlevel! equ 0 (
        :: Refresh PATH
        set "PATH=%LOCALAPPDATA%\Programs\Python\Python312\;%LOCALAPPDATA%\Programs\Python\Python312\Scripts\;%PATH%"
        set "PYTHON=python"
        echo [✓] Python installed via winget
        goto :check_git
    )
)

echo [✗] Could not install Python automatically.
echo     Please install Python 3.10+ from https://python.org
echo     Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1

:: ── Step 3: Check Git ───────────────────────────────────────────────────────
:check_git
echo.
echo ━━━ Checking Git ━━━
where git >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=3" %%v in ('git --version') do echo [✓] Git %%v
    goto :clone_repo
)

echo [!] Git not found, attempting install...
where winget >nul 2>&1
if %errorlevel% equ 0 (
    winget install Git.Git --silent --accept-package-agreements --accept-source-agreements
    set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
    if exist "%ProgramFiles%\Git\cmd\git.exe" (
        echo [✓] Git installed
        goto :clone_repo
    )
)
echo [!] Git not installed. You may need to install it manually from https://git-scm.com

:: ── Step 4: Clone/Update Repository ─────────────────────────────────────────
:clone_repo
echo.
echo ━━━ Getting Rally Agent Source ━━━
if not exist "%RALLY_HOME%" mkdir "%RALLY_HOME%"

:: Check if we're running from inside the repo
if exist "rally.py" if exist "requirements.txt" (
    echo [➤] Installing from local directory...
    for %%d in (core cli memory tools agents integrations marketplace security utils web voice) do (
        if exist "%%d" xcopy /E /I /Y /Q "%%d" "%RALLY_HOME%\%%d" >nul 2>&1
    )
    for %%f in (rally.py requirements.txt pyproject.toml setup.py README.md LICENSE .gitignore) do (
        if exist "%%f" copy /Y "%%f" "%RALLY_HOME%\" >nul 2>&1
    )
    echo [✓] Copied local source
    goto :setup_venv
)

if exist "%RALLY_HOME%\.git" (
    echo [➤] Updating existing installation...
    pushd "%RALLY_HOME%"
    git pull --ff-only >nul 2>&1
    popd
    echo [✓] Repository updated
) else (
    echo [➤] Cloning from %REPO_URL%...
    git clone --depth 1 "%REPO_URL%" "%RALLY_HOME%"
    if !errorlevel! neq 0 (
        echo [✗] Clone failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo [✓] Repository cloned
)

:: ── Step 5: Create Virtual Environment ──────────────────────────────────────
:setup_venv
echo.
echo ━━━ Setting Up Virtual Environment ━━━
if exist "%RALLY_HOME%\.venv\Scripts\python.exe" (
    echo [✓] Virtual environment already exists
    goto :install_deps
)

echo [➤] Creating virtual environment...
%PYTHON% -m venv "%RALLY_HOME%\.venv"
if not exist "%RALLY_HOME%\.venv\Scripts\python.exe" (
    echo [✗] Failed to create virtual environment
    pause
    exit /b 1
)
echo [✓] Virtual environment created

:: ── Step 6: Install Dependencies ────────────────────────────────────────────
:install_deps
echo.
echo ━━━ Installing Python Dependencies ━━━

set "VENV_PIP=%RALLY_HOME%\.venv\Scripts\pip.exe"
set "VENV_PY=%RALLY_HOME%\.venv\Scripts\python.exe"

echo [➤] Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip --quiet >nul 2>&1

if exist "%RALLY_HOME%\requirements.txt" (
    echo [➤] Installing requirements.txt...
    "%VENV_PIP%" install -r "%RALLY_HOME%\requirements.txt" --quiet
    if !errorlevel! equ 0 (
        echo [✓] Dependencies installed
    ) else (
        echo [!] Some dependencies may have failed
    )
)

if exist "%RALLY_HOME%\pyproject.toml" (
    echo [➤] Installing rally-agent package...
    "%VENV_PIP%" install -e "%RALLY_HOME%" --quiet >nul 2>&1
)

:: ── Step 7: Install Playwright (optional) ───────────────────────────────────
if "%MINIMAL%"=="true" goto :create_launcher

echo.
echo ━━━ Installing Playwright Browsers ━━━
set "VENV_PW=%RALLY_HOME%\.venv\Scripts\playwright.exe"
if exist "%VENV_PW%" (
    echo [➤] Installing Chromium...
    "%VENV_PW%" install chromium
    echo [✓] Playwright browsers installed
) else (
    "%VENV_PY%" -m playwright install chromium >nul 2>&1
    if !errorlevel! equ 0 (
        echo [✓] Playwright browsers installed
    ) else (
        echo [!] Playwright browser install skipped
    )
)

:: ── Step 8: Create CLI Launcher ─────────────────────────────────────────────
:create_launcher
echo.
echo ━━━ Creating CLI Launcher ━━━
set "BIN_DIR=%RALLY_HOME%\bin"
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

:: Create rally.cmd
(
    echo @echo off
    echo :: Rally Agent CLI Launcher
    echo call "%RALLY_HOME%\.venv\Scripts\activate.bat" ^>nul 2^>^&1
    echo python "%RALLY_HOME%\rally.py" %%*
) > "%BIN_DIR%\rally.cmd"

:: Add to user PATH
set "CURRENT_PATH="
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "CURRENT_PATH=%%b"
echo %CURRENT_PATH% | find /i "%BIN_DIR%" >nul
if errorlevel 1 (
    reg add "HKCU\Environment" /v Path /t REG_EXPAND_SZ /d "%CURRENT_PATH%;%BIN_DIR%" /f >nul 2>&1
    set "PATH=%PATH%;%BIN_DIR%"
    echo [✓] Added to PATH: %BIN_DIR%
)
echo [✓] Launcher: %BIN_DIR%\rally.cmd

:: ── Step 9: Generate Config ─────────────────────────────────────────────────
echo.
echo ━━━ Generating Configuration ━━━
set "CONFIG_DIR=%RALLY_HOME%\config"
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

if exist "%CONFIG_DIR%\rally.toml" (
    echo [!] Config already exists, skipping
    goto :verify
)

(
    echo # ═══════════════════════════════════════════════════════════════
    echo # RALLY AGENT - Configuration
    echo # ═══════════════════════════════════════════════════════════════
    echo.
    echo [agent]
    echo name = "Rally"
    echo version = "1.0.0"
    echo default_model = "auto"
    echo thinking = true
    echo max_context = 128000
    echo.
    echo [agent.auto_model]
    echo fallback_order = ["anthropic", "openai", "google", "ollama", "local"]
    echo.
    echo [cli]
    echo theme = "hacker_purple"
    echo animations = true
    echo banner = true
    echo compact = false
    echo syntax_highlight = true
    echo show_timestamps = true
    echo emoji = true
    echo.
    echo [memory]
    echo backend = "hybrid"
    echo vector_store = "local"
    echo max_entries = 10000
    echo auto_consolidate = true
    echo encryption = true
    echo.
    echo [security]
    echo confirm_dangerous = true
    echo audit_log = true
    echo max_file_ops = 100
    echo sandbox_exec = true
    echo blocked_commands = ["rm -rf /", "mkfs", "dd if="]
    echo.
    echo [tools]
    echo web_search = true
    echo file_ops = true
    echo exec = true
    echo browser = true
    echo code_exec = true
    echo.
    echo [agents]
    echo max_parallel = 5
    echo auto_delegate = true
    echo orchestrator = true
    echo.
    echo [integrations]
    echo # Set API keys here or use environment variables
    echo # OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, etc.
    echo.
    echo [marketplace]
    echo auto_update = false
    echo trusted_sources = ["rally-official", "community-verified"]
) > "%CONFIG_DIR%\rally.toml"

echo [✓] Configuration: %CONFIG_DIR%\rally.toml

:: ── Step 10: Verify Installation ────────────────────────────────────────────
:verify
echo.
echo ━━━ Verifying Installation ━━━
set "CHECKS=0"
set "PASSED=0"

set /a CHECKS+=1
if exist "%BIN_DIR%\rally.cmd" (
    echo [✓] rally command: available
    set /a PASSED+=1
) else (
    echo [✗] rally command: NOT found
)

set /a CHECKS+=1
if exist "%RALLY_HOME%\.venv\Scripts\python.exe" (
    echo [✓] Virtual environment: ready
    set /a PASSED+=1
) else (
    echo [✗] Virtual environment: NOT found
)

set /a CHECKS+=1
if exist "%CONFIG_DIR%\rally.toml" (
    echo [✓] Configuration: present
    set /a PASSED+=1
) else (
    echo [✗] Configuration: NOT found
)

set /a CHECKS+=1
if exist "%RALLY_HOME%\rally.py" (
    echo [✓] Core: rally.py present
    set /a PASSED+=1
) else (
    echo [✗] Core: rally.py NOT found
)

echo.
echo    %PASSED%/%CHECKS% checks passed

:: ── Done ────────────────────────────────────────────────────────────────────
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║  🟣 RALLY AGENT v%RALLY_VERSION% - Installation Complete!             ║
echo ╠════════════════════════════════════════════════════════════════╣
echo ║                                                              ║
echo ║  Quick start:                                                ║
echo ║    rally               Interactive mode                      ║
echo ║    rally chat          Start chatting                        ║
echo ║    rally status        Check system status                   ║
echo ║    rally --help        Show all commands                     ║
echo ║                                                              ║
echo ║  Add your API keys:                                          ║
echo ║    set OPENAI_API_KEY=sk-...                                 ║
echo ║    Or edit: %%USERPROFILE%%\.rally-agent\config\rally.toml       ║
echo ║                                                              ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo    💀 The OpenClaw Killer has been deployed. ⚡
echo    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo    Note: You may need to restart your terminal for PATH changes.
echo.
pause
exit /b 0

:: ── Uninstall ───────────────────────────────────────────────────────────────
:uninstall
echo ━━━ Uninstalling Rally Agent ━━━
if exist "%RALLY_HOME%" (
    rmdir /s /q "%RALLY_HOME%"
    echo [✓] Removed %RALLY_HOME%
)
:: Remove from PATH
set "CURRENT_PATH="
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "CURRENT_PATH=%%b"
set "NEW_PATH=!CURRENT_PATH:;%RALLY_HOME%\bin=!"
reg add "HKCU\Environment" /v Path /t REG_EXPAND_SZ /d "%NEW_PATH%" /f >nul 2>&1
echo [✓] Rally Agent uninstalled. So long! 💀
pause
exit /b 0

:: ── Help ────────────────────────────────────────────────────────────────────
:show_help
echo Rally Agent Installer for Windows
echo.
echo Usage: install.bat [/minimal] [/dev] [/uninstall] [/help]
echo.
echo   /minimal    Core only, skip browser/voice dependencies
echo   /dev        Include development dependencies
echo   /uninstall  Remove Rally Agent completely
echo   /help       Show this help
echo.
echo One-liner:
echo   curl -fsSL https://raw.githubusercontent.com/Atum246/rally-agent/main/install.bat -o install.bat ^&^& install.bat
echo.
exit /b 0
