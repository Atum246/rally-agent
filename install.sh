#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# 🟣 RALLY AGENT — Installer
# "The OpenClaw Killer" 💀
# ═══════════════════════════════════════════════════════════════

RALLY_VERSION="1.0.0"
RALLY_HOME="${RALLY_HOME:-$HOME/.rally-agent}"
RALLY_BIN="/usr/local/bin"
PYTHON_MIN="3.10"

# ── Colors ────────────────────────────────────────────────────
PURPLE='\033[38;5;135m'
BRIGHT_PURPLE='\033[38;5;141m'
DARK_PURPLE='\033[38;5;57m'
NEON='\033[38;5;201m'
CYAN='\033[38;5;51m'
GREEN='\033[38;5;46m'
RED='\033[38;5;196m'
YELLOW='\033[38;5;226m'
GRAY='\033[38;5;245m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

# ── Banner ────────────────────────────────────────────────────
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
    echo ""
}

# ── Logging ───────────────────────────────────────────────────
log()    { echo -e "${PURPLE}[➤]${RESET} $1"; }
ok()     { echo -e "${GREEN}[✓]${RESET} $1"; }
warn()   { echo -e "${YELLOW}[!]${RESET} $1"; }
err()    { echo -e "${RED}[✗]${RESET} $1"; }
step()   { echo -e "\n${BRIGHT_PURPLE}${BOLD}━━━ $1 ━━━${RESET}"; }
info()   { echo -e "${GRAY}    $1${RESET}"; }

# ── Spinner ───────────────────────────────────────────────────
spinner() {
    local pid=$1 msg="${2:-Working...}"
    local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local i=0
    tput civis 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null; do
        echo -ne "\r${PURPLE}[$(printf '%s' "${frames[i]}")]${RESET} ${msg}   "
        i=$(( (i + 1) % ${#frames[@]} ))
        sleep 0.08
    done
    tput cnorm 2>/dev/null || true
    echo -ne "\r"
}

# ── Platform Detection ────────────────────────────────────────
detect_platform() {
    step "🔍 Detecting Platform"
    OS="$(uname -s)"
    ARCH="$(uname -m)"
    info "OS: ${OS} | Arch: ${ARCH}"

    case "$OS" in
        Linux*)  PLATFORM="linux" ;;
        Darwin*) PLATFORM="macos" ;;
        *)       err "Unsupported OS: $OS"; exit 1 ;;
    esac

    case "$ARCH" in
        x86_64|amd64) ARCH_NORM="x64" ;;
        arm64|aarch64) ARCH_NORM="arm64" ;;
        *) ARCH_NORM="$ARCH" ;;
    esac
    ok "Platform: ${PLATFORM}/${ARCH_NORM}"
}

# ── Dependency Checks ─────────────────────────────────────────
check_python() {
    step "🐍 Checking Python"
    PYTHON=""
    for cmd in python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
            if python3 -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
                PYTHON="$cmd"
                break
            fi
        fi
    done

    if [ -z "$PYTHON" ]; then
        err "Python ${PYTHON_MIN}+ not found!"
        log "Installing Python..."
        case "$PLATFORM" in
            linux)
                if command -v apt-get &>/dev/null; then
                    sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv
                elif command -v dnf &>/dev/null; then
                    sudo dnf install -y python3 python3-pip
                elif command -v pacman &>/dev/null; then
                    sudo pacman -S --noconfirm python python-pip
                fi
                PYTHON="python3"
                ;;
            macos)
                if command -v brew &>/dev/null; then
                    brew install python@3.12
                    PYTHON="python3.12"
                else
                    err "Install Homebrew first: https://brew.sh"
                    exit 1
                fi
                ;;
        esac
    fi

    PY_VER=$($PYTHON --version 2>&1)
    ok "Python: ${PY_VER} ($PYTHON)"
}

check_node() {
    step "📦 Checking Node.js"
    NODE=""
    for cmd in node nodejs; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" --version 2>&1 | grep -oP '\d+')
            if [ "$ver" -ge 18 ] 2>/dev/null; then
                NODE="$cmd"
                break
            fi
        fi
    done

    if [ -z "$NODE" ]; then
        warn "Node.js 18+ not found, installing..."
        case "$PLATFORM" in
            linux)
                curl -fsSL https://deb.nodesource.com/setup_20.x 2>/dev/null | sudo bash - 2>/dev/null
                sudo apt-get install -y -qq nodejs 2>/dev/null || true
                ;;
            macos)
                brew install node 2>/dev/null || true
                ;;
        esac
        NODE="node"
    fi

    if command -v "$NODE" &>/dev/null; then
        ok "Node.js: $($NODE --version)"
    else
        warn "Node.js optional, continuing without it"
    fi
}

check_git() {
    step "📋 Checking Git"
    if ! command -v git &>/dev/null; then
        case "$PLATFORM" in
            linux)  sudo apt-get install -y -qq git 2>/dev/null || sudo dnf install -y git 2>/dev/null ;;
            macos)  xcode-select --install 2>/dev/null || true ;;
        esac
    fi
    ok "Git: $(git --version 2>/dev/null || echo 'installed')"
}

# ── Installation ──────────────────────────────────────────────
install_rally() {
    step "⚡ Installing Rally Agent"

    # Create directory structure
    log "Creating Rally home at ${RALLY_HOME}..."
    mkdir -p "$RALLY_HOME"/{core,cli,memory,tools,agents,integrations,marketplace,security,utils,config,skills,logs,data}

    # Copy project files
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    log "Copying files..."
    cp -r "$SCRIPT_DIR"/{core,cli,memory,tools,agents,integrations,marketplace,security,utils,config,skills,*.py,*.toml,*.txt,*.md} "$RALLY_HOME/" 2>/dev/null || true

    # Create virtual environment
    log "Creating virtual environment..."
    $PYTHON -m venv "$RALLY_HOME/.venv" &>/dev/null &
    spinner $! "Creating virtual environment..."
    ok "Virtual environment created"

    # Install dependencies
    log "Installing dependencies (this may take a minute)..."
    source "$RALLY_HOME/.venv/bin/activate"

    pip install --upgrade pip -q 2>/dev/null &
    spinner $! "Upgrading pip..."

    if [ -f "$RALLY_HOME/requirements.txt" ]; then
        pip install -r "$RALLY_HOME/requirements.txt" -q 2>/dev/null &
        spinner $! "Installing Python packages..."
    fi
    ok "Dependencies installed"

    deactivate
}

# ── Configuration ─────────────────────────────────────────────
setup_config() {
    step "🔧 Setting Up Configuration"

    CONFIG_FILE="$RALLY_HOME/config/rally.toml"

    if [ -f "$CONFIG_FILE" ]; then
        warn "Config already exists, skipping..."
        return
    fi

    cat > "$CONFIG_FILE" << 'TOML'
# ═══════════════════════════════════════════════════════════════
# 🟣 RALLY AGENT — Configuration
# ═══════════════════════════════════════════════════════════════

[agent]
name = "Rally"
version = "1.0.0"
default_model = "auto"
thinking = true
max_context = 128000

[agent.auto_model]
# Auto-selects best available model from configured providers
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
# Add your API keys here or use environment variables
# openai_key = "sk-..."
# anthropic_key = "sk-ant-..."
# google_key = "..."
# serpapi_key = "..."

[marketplace]
auto_update = false
trusted_sources = ["rally-official", "community-verified"]
TOML

    ok "Configuration created at ${CONFIG_FILE}"
}

# ── CLI Launcher ──────────────────────────────────────────────
create_launcher() {
    step "🚀 Creating CLI Launcher"

    cat > "$RALLY_HOME/rally" << 'LAUNCHER'
#!/usr/bin/env bash
# Rally Agent Launcher
RALLY_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$RALLY_HOME/.venv/bin/activate" 2>/dev/null
exec python3 "$RALLY_HOME/rally.py" "$@"
LAUNCHER

    chmod +x "$RALLY_HOME/rally"

    # Symlink to PATH
    if [ -d "$RALLY_BIN" ]; then
        sudo ln -sf "$RALLY_HOME/rally" "$RALLY_BIN/rally" 2>/dev/null || {
            mkdir -p "$HOME/.local/bin"
            ln -sf "$RALLY_HOME/rally" "$HOME/.local/bin/rally"
            export PATH="$HOME/.local/bin:$PATH"
        }
    fi

    ok "Launcher created: $(which rally 2>/dev/null || echo "$RALLY_HOME/rally")"
}

# ── Shell Integration ─────────────────────────────────────────
setup_shell() {
    step "🐚 Shell Integration"

    SHELL_RC=""
    case "$(basename "$SHELL")" in
        bash) SHELL_RC="$HOME/.bashrc" ;;
        zsh)  SHELL_RC="$HOME/.zshrc" ;;
        fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
    esac

    if [ -n "$SHELL_RC" ]; then
        if ! grep -q "rally-agent" "$SHELL_RC" 2>/dev/null; then
            cat >> "$SHELL_RC" << 'SHELL'

# ── Rally Agent ──────────────────────────────────────────
export RALLY_HOME="$HOME/.rally-agent"
[ -d "$HOME/.local/bin" ] && export PATH="$HOME/.local/bin:$PATH"
# Aliases
alias r='rally'
alias rally-chat='rally chat'
alias rally-status='rally status'
alias rally-agent='rally'
# Completions
if command -v rally &>/dev/null; then
    eval "$(rally completions 2>/dev/null || true)"
fi
SHELL
            ok "Shell integration added to ${SHELL_RC}"
        else
            info "Shell integration already configured"
        fi
    fi
}

# ── Verify Installation ──────────────────────────────────────
verify_install() {
    step "✅ Verifying Installation"

    local checks=0
    local passed=0

    # Check rally command
    checks=$((checks + 1))
    if [ -x "$RALLY_HOME/rally" ] || command -v rally &>/dev/null; then
        ok "rally command: available"
        passed=$((passed + 1))
    else
        err "rally command: NOT found"
    fi

    # Check venv
    checks=$((checks + 1))
    if [ -d "$RALLY_HOME/.venv" ]; then
        ok "Virtual environment: ready"
        passed=$((passed + 1))
    else
        err "Virtual environment: NOT found"
    fi

    # Check config
    checks=$((checks + 1))
    if [ -f "$RALLY_HOME/config/rally.toml" ]; then
        ok "Configuration: loaded"
        passed=$((passed + 1))
    else
        err "Configuration: NOT found"
    fi

    # Check core modules
    checks=$((checks + 1))
    if [ -f "$RALLY_HOME/core/__init__.py" ] || [ -f "$RALLY_HOME/core/agent.py" ]; then
        ok "Core modules: installed"
        passed=$((passed + 1))
    else
        err "Core modules: NOT found"
    fi

    echo ""
    if [ "$passed" -eq "$checks" ]; then
        echo -e "${GREEN}${BOLD}    All ${passed}/${checks} checks passed! ✨${RESET}"
    else
        echo -e "${YELLOW}${BOLD}    ${passed}/${checks} checks passed${RESET}"
    fi
}

# ── Final Message ─────────────────────────────────────────────
show_done() {
    echo ""
    echo -e "${PURPLE}╔══════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${PURPLE}║${RESET}  ${NEON}${BOLD}🟣 RALLY AGENT v${RALLY_VERSION} — Installation Complete!${RESET}          ${PURPLE}║${RESET}"
    echo -e "${PURPLE}╠══════════════════════════════════════════════════════════════╣${RESET}"
    echo -e "${PURPLE}║${RESET}                                                            ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${CYAN}Start:${RESET}   ${BOLD}rally${RESET}                                    ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${CYAN}Chat:${RESET}    ${BOLD}rally chat${RESET}                               ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${CYAN}Status:${RESET}  ${BOLD}rally status${RESET}                              ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${CYAN}Help:${RESET}    ${BOLD}rally --help${RESET}                              ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${CYAN}Config:${RESET}  ${BOLD}${RALLY_HOME}/config/rally.toml${RESET}  ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}                                                            ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${YELLOW}⚡ Add your API keys in the config or set env vars:${RESET}     ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${GRAY}   OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.${RESET}              ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}                                                            ${PURPLE}║${RESET}"
    echo -e "${PURPLE}║${RESET}  ${DIM}Source: ${RALLY_HOME}${RESET}$(printf '%*s' $((28 - ${#RALLY_HOME})) '')${PURPLE}║${RESET}"
    echo -e "${PURPLE}╚══════════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "${NEON}${BOLD}    💀 The OpenClaw Killer has been deployed. ⚡${RESET}"
    echo -e "${PURPLE}    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────
main() {
    show_banner
    detect_platform
    check_python
    check_node
    check_git
    install_rally
    setup_config
    create_launcher
    setup_shell
    verify_install
    show_done
}

main "$@"
