#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# 🟣 RALLY AGENT — Universal Installer
# Works on: Linux (all distros), macOS, WSL
# Architectures: x64, arm64
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/Atum246/rally-agent/main/install.sh | bash
#
# Flags:
#   --minimal   Install core only (no browser automation, no voice)
#   --dev       Install development dependencies too
#   --uninstall Remove Rally Agent completely
#   --help      Show this help
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

RALLY_VERSION="1.0.0"
RALLY_HOME="${RALLY_HOME:-$HOME/.rally-agent}"
REPO_URL="https://github.com/Atum246/rally-agent"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10
NODE_MIN_MAJOR=18

# ── Flags ─────────────────────────────────────────────────────────────────────
MINIMAL=false
DEV=false
UNINSTALL=false
for arg in "$@"; do
    case "$arg" in
        --minimal)   MINIMAL=true ;;
        --dev)       DEV=true ;;
        --uninstall) UNINSTALL=true ;;
        --help|-h)
            echo "Usage: install.sh [--minimal] [--dev] [--uninstall]"
            echo "  --minimal   Core only, skip browser/voice deps"
            echo "  --dev       Include development dependencies"
            echo "  --uninstall Remove Rally Agent completely"
            exit 0
            ;;
    esac
done

# ── Colors & Formatting ──────────────────────────────────────────────────────
if [ -t 1 ]; then
    PURPLE='\033[38;5;135m'
    BRIGHT='\033[38;5;141m'
    NEON='\033[38;5;201m'
    CYAN='\033[38;5;51m'
    GREEN='\033[38;5;46m'
    RED='\033[38;5;196m'
    YELLOW='\033[38;5;226m'
    GRAY='\033[38;5;245m'
    BOLD='\033[1m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    PURPLE='' BRIGHT='' NEON='' CYAN='' GREEN='' RED='' YELLOW='' GRAY='' BOLD='' DIM='' RESET=''
fi

# ── Logging ───────────────────────────────────────────────────────────────────
log()    { echo -e "${PURPLE}[➤]${RESET} $1"; }
ok()     { echo -e "${GREEN}[✓]${RESET} $1"; }
warn()   { echo -e "${YELLOW}[!]${RESET} $1"; }
err()    { echo -e "${RED}[✗]${RESET} $1"; }
step()   { echo -e "\n${BRIGHT}${BOLD}━━━ $1 ━━━${RESET}"; }
info()   { echo -e "${GRAY}    $1${RESET}"; }
fatal()  { err "$1"; exit 1; }

# ── Spinner ───────────────────────────────────────────────────────────────────
spinner() {
    local pid=$1 msg="${2:-Working...}"
    local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local i=0
    tput civis 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r${PURPLE}[%s]${RESET} %s   " "${frames[i]}" "$msg"
        i=$(( (i + 1) % ${#frames[@]} ))
        sleep 0.08
    done
    tput cnorm 2>/dev/null || true
    printf "\r\033[K"
}

# Run a command with spinner, capture output
run_with_spinner() {
    local msg="$1"; shift
    local logfile
    logfile=$(mktemp)
    "$@" > "$logfile" 2>&1 &
    local pid=$!
    spinner "$pid" "$msg"
    local rc=0
    wait "$pid" || rc=$?
    if [ $rc -ne 0 ]; then
        err "$msg — failed (exit $rc)"
        if [ -s "$logfile" ]; then
            echo -e "${GRAY}$(cat "$logfile" | tail -5)${RESET}"
        fi
        rm -f "$logfile"
        return $rc
    fi
    rm -f "$logfile"
    return 0
}

# ── Version Compare ──────────────────────────────────────────────────────────
version_gte() {
    # Returns 0 if $1 >= $2 (major.minor comparison)
    local v1_major v1_minor v2_major v2_minor
    v1_major=$(echo "$1" | cut -d. -f1)
    v1_minor=$(echo "$1" | cut -d. -f2)
    v2_major=$(echo "$2" | cut -d. -f1)
    v2_minor=$(echo "$2" | cut -d. -f2)
    if [ "$v1_major" -gt "$v2_major" ] 2>/dev/null; then return 0; fi
    if [ "$v1_major" -eq "$v2_major" ] 2>/dev/null && [ "$v1_minor" -ge "$v2_minor" ] 2>/dev/null; then return 0; fi
    return 1
}

# ── Uninstall ────────────────────────────────────────────────────────────────
do_uninstall() {
    step "🗑️  Uninstalling Rally Agent"
    [ -d "$RALLY_HOME" ] && rm -rf "$RALLY_HOME" && ok "Removed $RALLY_HOME"
    sudo rm -f /usr/local/bin/rally 2>/dev/null || true
    rm -f "$HOME/.local/bin/rally" 2>/dev/null || true
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        [ -f "$rc" ] && sed -i '/# ── Rally Agent/,/^$/d' "$rc" 2>/dev/null || true
    done
    ok "Rally Agent uninstalled. So long! 💀"
    exit 0
}
$UNINSTALL && do_uninstall

# ── Banner ───────────────────────────────────────────────────────────────────
show_banner() {
    echo -e "${PURPLE}"
    cat << 'BANNER'
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
BANNER
    echo -e "${NEON}${BOLD}           ⚡ v${RALLY_VERSION} — The OpenClaw Killer 💀${RESET}"
    echo -e "${GRAY}           ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    if $MINIMAL; then
        echo -e "${CYAN}           📦 Minimal install (core only)${RESET}"
    fi
    if $DEV; then
        echo -e "${CYAN}           🔧 Dev install (includes dev deps)${RESET}"
    fi
    echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  PLATFORM DETECTION
# ══════════════════════════════════════════════════════════════════════════════

detect_platform() {
    step "🔍 Detecting Platform"

    OS_RAW="$(uname -s)"
    ARCH_RAW="$(uname -m)"

    # Normalize OS
    case "$OS_RAW" in
        Linux*)   PLATFORM="linux" ;;
        Darwin*)  PLATFORM="macos" ;;
        MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
        *)        fatal "Unsupported OS: $OS_RAW. Use install.ps1 on Windows." ;;
    esac

    # Detect WSL
    IS_WSL=false
    if [ "$PLATFORM" = "linux" ] && grep -qiE "(microsoft|wsl)" /proc/version 2>/dev/null; then
        IS_WSL=true
        info "Running inside WSL"
    fi

    # Normalize architecture
    case "$ARCH_RAW" in
        x86_64|amd64)  ARCH="x64" ;;
        arm64|aarch64) ARCH="arm64" ;;
        armv7*)        ARCH="armv7" ;;
        *)             ARCH="$ARCH_RAW" ;;
    esac

    # Detect Linux distro family
    PKG_MANAGER="unknown"
    DISTRO="unknown"
    if [ "$PLATFORM" = "linux" ]; then
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            DISTRO="${ID:-unknown}"
        fi
        if command -v apt-get &>/dev/null; then
            PKG_MANAGER="apt"
        elif command -v dnf &>/dev/null; then
            PKG_MANAGER="dnf"
        elif command -v yum &>/dev/null; then
            PKG_MANAGER="yum"
        elif command -v pacman &>/dev/null; then
            PKG_MANAGER="pacman"
        elif command -v apk &>/dev/null; then
            PKG_MANAGER="apk"
        elif command -v zypper &>/dev/null; then
            PKG_MANAGER="zypper"
        fi
    elif [ "$PLATFORM" = "macos" ]; then
        PKG_MANAGER="brew"
        DISTRO="macos"
    fi

    info "OS: $PLATFORM | Distro: $DISTRO | Pkg: $PKG_MANAGER | Arch: $ARCH"
    ok "Platform: ${PLATFORM}/${ARCH} (${DISTRO})"
}

# ══════════════════════════════════════════════════════════════════════════════
#  DEPENDENCY INSTALLATION
# ══════════════════════════════════════════════════════════════════════════════

pkg_install() {
    # Install a package using the system package manager
    local pkg="$1"
    case "$PKG_MANAGER" in
        apt)    sudo apt-get install -y -qq "$pkg" ;;
        dnf)    sudo dnf install -y -q "$pkg" ;;
        yum)    sudo yum install -y -q "$pkg" ;;
        pacman) sudo pacman -S --noconfirm --needed "$pkg" ;;
        apk)    sudo apk add --no-cache "$pkg" ;;
        zypper) sudo zypper --non-interactive install "$pkg" ;;
        brew)   brew install "$pkg" ;;
        *)      return 1 ;;
    esac
}

pkg_update() {
    case "$PKG_MANAGER" in
        apt)    sudo apt-get update -qq ;;
        dnf|yum|pacman|apk|zypper|brew) ;;  # not needed or auto-handles
    esac
}

# ── Python ────────────────────────────────────────────────────────────────────
check_python() {
    step "🐍 Checking Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+"

    PYTHON=""
    PYTHON_VER=""

    # Search for suitable Python binaries in preference order
    for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            local full_ver
            full_ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
            if version_gte "$full_ver" "${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}"; then
                PYTHON="$cmd"
                PYTHON_VER="$full_ver"
                break
            fi
        fi
    done

    if [ -n "$PYTHON" ]; then
        ok "Python $($PYTHON --version 2>&1 | awk '{print $2}') ($PYTHON)"
        return 0
    fi

    err "Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ not found"
    log "Installing Python..."

    case "$PKG_MANAGER" in
        apt)
            pkg_update
            run_with_spinner "Installing python3 (apt)" pkg_install python3
            run_with_spinner "Installing python3-pip (apt)" pkg_install python3-pip
            run_with_spinner "Installing python3-venv (apt)" pkg_install python3-venv
            ;;
        dnf|yum)
            run_with_spinner "Installing python3 ($PKG_MANAGER)" pkg_install python3
            run_with_spinner "Installing python3-pip ($PKG_MANAGER)" pkg_install python3-pip
            ;;
        pacman)
            run_with_spinner "Installing python (pacman)" pkg_install python
            run_with_spinner "Installing python-pip (pacman)" pkg_install python-pip
            ;;
        apk)
            run_with_spinner "Installing python3 (apk)" pkg_install python3
            run_with_spinner "Installing py3-pip (apk)" pkg_install py3-pip
            ;;
        zypper)
            run_with_spinner "Installing python3 (zypper)" pkg_install python3
            run_with_spinner "Installing python3-pip (zypper)" pkg_install python3-pip
            ;;
        brew)
            run_with_spinner "Installing python@3.12 (brew)" brew install python@3.12
            ;;
        *)
            fatal "Cannot auto-install Python. Install Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ manually."
            ;;
    esac

    # Re-check
    PYTHON="python3"
    PYTHON_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || true

    if ! version_gte "$PYTHON_VER" "${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}"; then
        fatal "Python installation failed or version too old: $PYTHON_VER"
    fi
    ok "Python $($PYTHON --version 2>&1 | awk '{print $2}') ($PYTHON)"
}

# ── Node.js (optional) ───────────────────────────────────────────────────────
check_node() {
    step "📦 Checking Node.js (optional)"

    NODE=""
    for cmd in node nodejs; do
        if command -v "$cmd" &>/dev/null; then
            local major
            major=$("$cmd" --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)
            if [ "${major:-0}" -ge "$NODE_MIN_MAJOR" ] 2>/dev/null; then
                NODE="$cmd"
                break
            fi
        fi
    done

    if [ -n "$NODE" ]; then
        ok "Node.js $($NODE --version)"
        return 0
    fi

    warn "Node.js ${NODE_MIN_MAJOR}+ not found — installing..."
    case "$PKG_MANAGER" in
        apt)
            # Use NodeSource for up-to-date version
            if curl -fsSL https://deb.nodesource.com/setup_20.x 2>/dev/null | sudo bash - 2>/dev/null; then
                sudo apt-get install -y -qq nodejs 2>/dev/null || true
            fi
            ;;
        dnf|yum)
            curl -fsSL https://rpm.nodesource.com/setup_20.x 2>/dev/null | sudo bash - 2>/dev/null || true
            sudo $PKG_MANAGER install -y -q nodejs 2>/dev/null || true
            ;;
        pacman)   sudo pacman -S --noconfirm --needed nodejs npm 2>/dev/null || true ;;
        apk)      sudo apk add --no-cache nodejs npm 2>/dev/null || true ;;
        brew)     brew install node 2>/dev/null || true ;;
    esac

    NODE="node"
    if command -v "$NODE" &>/dev/null; then
        ok "Node.js $($NODE --version)"
    else
        warn "Node.js not installed — continuing without it (optional)"
    fi
}

# ── Git ───────────────────────────────────────────────────────────────────────
check_git() {
    step "📋 Checking Git"

    if command -v git &>/dev/null; then
        ok "Git $(git --version | awk '{print $3}')"
        return 0
    fi

    log "Installing Git..."
    case "$PKG_MANAGER" in
        apt)      pkg_update; run_with_spinner "Installing git (apt)" pkg_install git ;;
        dnf|yum)  run_with_spinner "Installing git ($PKG_MANAGER)" pkg_install git ;;
        pacman)   run_with_spinner "Installing git (pacman)" pkg_install git ;;
        apk)      run_with_spinner "Installing git (apk)" pkg_install git ;;
        zypper)   run_with_spinner "Installing git (zypper)" pkg_install git ;;
        brew)     run_with_spinner "Installing git (brew)" pkg_install git ;;
        *)        warn "Cannot auto-install Git. Install manually." ; return ;;
    esac

    command -v git &>/dev/null && ok "Git $(git --version | awk '{print $3}')" || warn "Git install may have failed"
}

# ══════════════════════════════════════════════════════════════════════════════
#  RALLY INSTALLATION
# ══════════════════════════════════════════════════════════════════════════════

clone_or_copy_repo() {
    step "📥 Getting Rally Agent Source"

    mkdir -p "$RALLY_HOME"

    # If we're running from inside the repo (piped from curl), clone it
    if [ -f "./rally.py" ] && [ -f "./requirements.txt" ]; then
        log "Installing from local directory..."
        cp -r ./{core,cli,memory,tools,agents,integrations,marketplace,security,utils,web,voice,memory} "$RALLY_HOME/" 2>/dev/null || true
        cp -r ./{rally.py,requirements.txt,pyproject.toml,setup.py,README.md,LICENSE,.gitignore} "$RALLY_HOME/" 2>/dev/null || true
        ok "Copied local source"
        return
    fi

    # Clone from GitHub
    if [ -d "$RALLY_HOME/.git" ]; then
        log "Updating existing installation..."
        (cd "$RALLY_HOME" && git pull --ff-only 2>/dev/null) || true
        ok "Repository updated"
    else
        log "Cloning from ${REPO_URL}..."
        run_with_spinner "Cloning repository" git clone --depth 1 "$REPO_URL" "$RALLY_HOME"
        ok "Repository cloned"
    fi
}

setup_venv() {
    step "🐍 Setting Up Virtual Environment"

    VENV_PATH="$RALLY_HOME/.venv"

    if [ -d "$VENV_PATH" ]; then
        log "Virtual environment already exists"
        # Verify it works
        if "$VENV_PATH/bin/python" -c "import sys" 2>/dev/null; then
            ok "Virtual environment is healthy"
            return
        else
            warn "Existing venv is broken, recreating..."
            rm -rf "$VENV_PATH"
        fi
    fi

    log "Creating virtual environment..."
    run_with_spinner "Creating venv at $VENV_PATH" "$PYTHON" -m venv "$VENV_PATH"

    if [ ! -f "$VENV_PATH/bin/activate" ]; then
        fatal "Failed to create virtual environment"
    fi

    ok "Virtual environment created"
}

install_pip_deps() {
    step "📦 Installing Python Dependencies"

    source "$RALLY_HOME/.venv/bin/activate"

    # Upgrade pip
    run_with_spinner "Upgrading pip" pip install --upgrade pip

    # Core requirements
    if [ -f "$RALLY_HOME/requirements.txt" ]; then
        run_with_spinner "Installing requirements.txt" pip install -r "$RALLY_HOME/requirements.txt"
    fi

    # Dev dependencies
    if $DEV && [ -f "$RALLY_HOME/requirements-dev.txt" ]; then
        run_with_spinner "Installing dev requirements" pip install -r "$RALLY_HOME/requirements-dev.txt"
    fi

    # Install the package itself in editable mode
    if [ -f "$RALLY_HOME/pyproject.toml" ] || [ -f "$RALLY_HOME/setup.py" ]; then
        local extras=""
        if ! $MINIMAL; then
            extras="[all]"
        fi
        run_with_spinner "Installing rally-agent${extras}" pip install -e "${RALLY_HOME}${extras}" 2>/dev/null || \
            run_with_spinner "Installing rally-agent (fallback)" pip install -e "$RALLY_HOME"
    fi

    deactivate 2>/dev/null || true
    ok "Python dependencies installed"
}

install_playwright() {
    $MINIMAL && return 0

    step "🌐 Installing Playwright Browsers"

    source "$RALLY_HOME/.venv/bin/activate"

    if command -v playwright &>/dev/null || "$RALLY_HOME/.venv/bin/python" -c "import playwright" 2>/dev/null; then
        run_with_spinner "Installing Chromium for Playwright" playwright install chromium
        run_with_spinner "Installing Playwright system deps" playwright install-deps chromium 2>/dev/null || true
        ok "Playwright browsers installed"
    else
        warn "Playwright not available, skipping browser install"
    fi

    deactivate 2>/dev/null || true
}

# ══════════════════════════════════════════════════════════════════════════════
#  CLI & SHELL SETUP
# ══════════════════════════════════════════════════════════════════════════════

create_launcher() {
    step "🚀 Creating CLI Launcher"

    # Create the rally launcher script
    cat > "$RALLY_HOME/rally" << 'LAUNCHER'
#!/usr/bin/env bash
# Rally Agent CLI Launcher
RALLY_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate virtual environment silently
if [ -f "$RALLY_HOME/.venv/bin/activate" ]; then
    source "$RALLY_HOME/.venv/bin/activate"
fi

# Run the main script
exec python3 "$RALLY_HOME/rally.py" "$@"
LAUNCHER

    chmod +x "$RALLY_HOME/rally"

    # Determine best bin directory
    local bin_dir=""
    if [ -w "/usr/local/bin" ] 2>/dev/null; then
        bin_dir="/usr/local/bin"
    elif [ -d "$HOME/.local/bin" ]; then
        bin_dir="$HOME/.local/bin"
    else
        mkdir -p "$HOME/.local/bin"
        bin_dir="$HOME/.local/bin"
    fi

    ln -sf "$RALLY_HOME/rally" "$bin_dir/rally"

    # Ensure the bin dir is in PATH for this session
    case ":$PATH:" in
        *":$bin_dir:"*) ;;
        *) export PATH="$bin_dir:$PATH" ;;
    esac

    ok "Launcher: $bin_dir/rally → $RALLY_HOME/rally"
}

generate_config() {
    step "⚙️  Generating Configuration"

    local config_dir="$RALLY_HOME/config"
    local config_file="$config_dir/rally.toml"
    mkdir -p "$config_dir"

    if [ -f "$config_file" ]; then
        warn "Config already exists at $config_file — not overwriting"
        return
    fi

    cat > "$config_file" << 'TOML'
# ═══════════════════════════════════════════════════════════════
# 🟣 RALLY AGENT — Configuration
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
TOML

    ok "Configuration: $config_file"
}

setup_shell_integration() {
    step "🐚 Shell Integration"

    # ── Bash ──
    if [ -f "$HOME/.bashrc" ]; then
        if ! grep -q "# rally-agent" "$HOME/.bashrc" 2>/dev/null; then
            cat >> "$HOME/.bashrc" << 'BASH_RC'

# rally-agent
export RALLY_HOME="$HOME/.rally-agent"
[ -d "$HOME/.local/bin" ] && export PATH="$HOME/.local/bin:$PATH"
alias r='rally'
alias rc='rally chat'
alias rs='rally status'
BASH_RC
            ok "Bash: added to ~/.bashrc"
        fi
    fi

    # ── Zsh ──
    if [ -f "$HOME/.zshrc" ]; then
        if ! grep -q "# rally-agent" "$HOME/.zshrc" 2>/dev/null; then
            cat >> "$HOME/.zshrc" << 'ZSH_RC'

# rally-agent
export RALLY_HOME="$HOME/.rally-agent"
[ -d "$HOME/.local/bin" ] && export PATH="$HOME/.local/bin:$PATH"
alias r='rally'
alias rc='rally chat'
alias rs='rally status'
# Tab completion
_rally_completions() {
    local commands="chat status config agents swarm memory rag tools skills browser sandbox voice plugins users metrics security web serve daemon version help"
    compadd $commands
}
compdef _rally_completions rally
ZSH_RC
            ok "Zsh: added to ~/.zshrc"
        fi
    fi

    # ── Fish ──
    local fish_dir="$HOME/.config/fish"
    if [ -d "$fish_dir" ]; then
        local fish_file="$fish_dir/conf.d/rally-agent.fish"
        if [ ! -f "$fish_file" ]; then
            mkdir -p "$fish_dir/conf.d"
            cat > "$fish_file" << 'FISH_RC'
# rally-agent
set -gx RALLY_HOME "$HOME/.rally-agent"
fish_add_path -gP "$HOME/.local/bin" 2>/dev/null
abbr -a r rally
abbr -a rc 'rally chat'
abbr -a rs 'rally status'
FISH_RC
            ok "Fish: added to $fish_file"
        fi
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
#  VERIFY
# ══════════════════════════════════════════════════════════════════════════════

verify_install() {
    step "✅ Verifying Installation"

    local checks=0 passed=0

    # rally command
    checks=$((checks + 1))
    if command -v rally &>/dev/null || [ -x "$RALLY_HOME/rally" ]; then
        ok "rally command: available"
        passed=$((passed + 1))
    else
        err "rally command: NOT found"
    fi

    # Virtual environment
    checks=$((checks + 1))
    if [ -f "$RALLY_HOME/.venv/bin/activate" ]; then
        ok "Virtual environment: ready"
        passed=$((passed + 1))
    else
        err "Virtual environment: NOT found"
    fi

    # Python in venv
    checks=$((checks + 1))
    if "$RALLY_HOME/.venv/bin/python" --version &>/dev/null; then
        ok "Python in venv: $("$RALLY_HOME/.venv/bin/python" --version 2>&1)"
        passed=$((passed + 1))
    else
        err "Python in venv: broken"
    fi

    # Configuration
    checks=$((checks + 1))
    if [ -f "$RALLY_HOME/config/rally.toml" ]; then
        ok "Configuration: present"
        passed=$((passed + 1))
    else
        err "Configuration: NOT found"
    fi

    # Core modules
    checks=$((checks + 1))
    if [ -f "$RALLY_HOME/rally.py" ]; then
        ok "Core: rally.py present"
        passed=$((passed + 1))
    else
        err "Core: rally.py NOT found"
    fi

    # pip packages
    checks=$((checks + 1))
    if "$RALLY_HOME/.venv/bin/python" -c "import rich; import httpx" 2>/dev/null; then
        ok "Core packages: installed (rich, httpx)"
        passed=$((passed + 1))
    else
        warn "Core packages: some may be missing"
    fi

    echo ""
    if [ "$passed" -eq "$checks" ]; then
        echo -e "${GREEN}${BOLD}    ✓ All ${passed}/${checks} checks passed!${RESET}"
    else
        echo -e "${YELLOW}${BOLD}    ${passed}/${checks} checks passed${RESET}"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
#  DONE
# ══════════════════════════════════════════════════════════════════════════════

show_done() {
    echo ""
    echo -e "${PURPLE}╔════════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${PURPLE}║${RESET}  ${NEON}${BOLD}🟣 RALLY AGENT v${RALLY_VERSION} — Installation Complete!${RESET}            ${PURPLE}║${RESET}"
    echo -e "${PURPLE}╠════════════════════════════════════════════════════════════════╣${RESET}"
    echo -e "${PURPLE}║${RESET}                                                              ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${CYAN}Quick start:${RESET}                                              ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}    ${BOLD}rally${RESET}                Interactive mode                    ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}    ${BOLD}rally chat${RESET}           Start chatting                      ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}    ${BOLD}rally status${RESET}         Check system status                 ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}    ${BOLD}rally --help${RESET}         Show all commands                   ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}                                                              ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${YELLOW}⚡ Add your API keys:${RESET}                                     ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}    ${GRAY}export OPENAI_API_KEY=sk-...${RESET}                            ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}    ${GRAY}Or edit: ~/.rally-agent/config/rally.toml${RESET}                ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}                                                              ${PURPLE}║${RESET}"
    echo -e "${PURPLE}╚════════════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "${NEON}${BOLD}    💀 The OpenClaw Killer has been deployed. ⚡${RESET}"
    echo -e "${PURPLE}    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
    echo -e "${DIM}    Tip: Run ${BOLD}rally${DIM} to get started, or source your shell:${RESET}"
    echo -e "${DIM}      source ~/.bashrc  # or ~/.zshrc${RESET}"
    echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

main() {
    show_banner
    detect_platform
    check_python
    check_node
    check_git
    clone_or_copy_repo
    setup_venv
    install_pip_deps
    install_playwright
    create_launcher
    generate_config
    setup_shell_integration
    verify_install
    show_done
}

main
