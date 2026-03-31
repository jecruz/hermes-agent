#!/usr/bin/env bash
# =============================================================================
# hermes-switch.sh — Switch between stable and test hermes-agent installations
#
# Usage:
#   ./scripts/switch-hermes.sh test    # Activate test branch in venv
#   ./scripts/switch-hermes.sh stable  # Return to stable pip installation
#   ./scripts/switch-hermes.sh status  # Show which is active
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HOME}/.hermes"
VENV_PATH="${HOME}/.venvs/hermes-test"
BRANCH="perf/hermes-caching-layer"
REPO_URL="https://github.com/jecruz/hermes-agent.git"
PID_FILE="${HERMES_HOME}/gateway.pid"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[hermes-switch]${RESET}  $*"; }
success() { echo -e "${GREEN}[hermes-switch]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[hermes-switch]${RESET}  WARNING: $*"; }
error()   { echo -e "${RED}[hermes-switch]${RESET}  ERROR: $*"; exit 1; }

# ── Helpers ───────────────────────────────────────────────────────────────────
is_venv_active() {
    [[ "${VIRTUAL_ENV:-}" == "${VENV_PATH}" ]]
}

check_running_gateway() {
    if [[ -f "${PID_FILE}" ]]; then
        local pid
        pid=$(cat "${PID_FILE}" 2>/dev/null)
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            error "Gateway is already running (PID ${pid}).\n  Run 'kill ${pid}' or 'hermes --gateway --replace' first, then retry."
        fi
    fi
}

pip_install() {
    local extra="${1:-}"
    info "Installing hermes-agent@${BRANCH} into venv..."
    # Direct URL syntax: name[extras] @ URL
    pip install --quiet \
        "hermes-agent${extra} @ git+${REPO_URL}@${BRANCH}"
    success "Installed: ${BRANCH}"
}

# ── Commands ─────────────────────────────────────────────────────────────────
cmd_test() {
    check_running_gateway

    if is_venv_active; then
        info "Test venv already active: ${VIRTUAL_ENV}"
        return
    fi

    if [[ ! -d "${VENV_PATH}" ]]; then
        info "Creating venv at ${VENV_PATH}..."
        python3 -m venv "${VENV_PATH}"
    fi

    # Activate the venv and install the branch
    # shellcheck disable=SC1091
    source "${VENV_PATH}/bin/activate"

    pip install --quiet --upgrade pip
    pip_install "[dev]"

    # Verify installation
    local installed_branch
    installed_branch=$(pip show hermes-agent 2>/dev/null | grep -i "Version:" | awk '{print $2}')
    success "Switched to TEST branch!"
    info "Active venv: ${VIRTUAL_ENV}"
    info "Branch:       ${BRANCH}"
    info "Version:      ${installed_branch}"
    echo
    info "Run these commands to activate:"
    echo
    echo -e "  ${BOLD}source ${VENV_PATH}/bin/activate${RESET}"
    echo
    info "Or add this to your shell profile for quick access:"
    echo
    echo -e "  ${BOLD}alias hermes-test='source ${VENV_PATH}/bin/activate && hermes'$RESET"
    echo
}

cmd_stable() {
    check_running_gateway

    if is_venv_active; then
        deactivate 2>/dev/null || true
        success "Deactivated test venv."
    fi

    # Reinstall stable from PyPI on top of whatever python is currently active
    info "Installing stable hermes-agent from PyPI..."
    pip install --quiet --upgrade hermes-agent

    local installed_version
    installed_version=$(pip show hermes-agent 2>/dev/null | grep -i "Version:" | awk '{print $2}')
    success "Switched to STABLE!"
    info "Version: ${installed_version}"
}

cmd_status() {
    echo
    echo -e "${BOLD}hermes-agent installation status${RESET}"
    echo -e "─────────────────────────────────────────────"

    if is_venv_active; then
        local branch_info installed_version
        branch_info=$(pip show hermes-agent 2>/dev/null | grep -i "Location:" | awk '{print $2}')
        installed_version=$(pip show hermes-agent 2>/dev/null | grep -i "Version:" | awk '{print $2}')
        echo -e "  Mode:     ${BOLD}${GREEN}TEST${RESET}"
        echo -e "  Branch:   ${CYAN}${BRANCH}${RESET}"
        echo -e "  Version:  ${installed_version}"
        echo -e "  Path:     ${VIRTUAL_ENV}"
        echo -e "  Install:  editable — ${branch_info}"
    else
        local version source
        version=$(pip show hermes-agent 2>/dev/null | grep -i "Version:" | awk '{print $2}')
        source=$(pip show hermes-agent 2>/dev/null | grep -i "Location:" | awk '{print $2}')
        echo -e "  Mode:     ${BOLD}STABLE${RESET}"
        echo -e "  Version:  ${version}"
        echo -e "  Source:   ${source}"
    fi

    # Check if gateway config exists
    local config_path="${HOME}/.hermes/config.yaml"
    echo
    if [[ -f "${config_path}" ]]; then
        echo -e "  Config:   ${GREEN}found${RESET} — ${config_path}"
    else
        echo -e "  Config:   ${YELLOW}not found${RESET} — ${config_path}"
    fi

    echo
}

cmd_uninstall() {
    if is_venv_active; then
        deactivate 2>/dev/null || true
    fi
    info "Removing test venv at ${VENV_PATH}..."
    rm -rf "${VENV_PATH}"
    success "Test venv removed."
}

# ── Main ─────────────────────────────────────────────────────────────────────
CMD="${1:-}"

case "${CMD}" in
    test)
        cmd_test
        ;;
    stable|prod)
        cmd_stable
        ;;
    status|stat)
        cmd_status
        ;;
    uninstall|clean)
        cmd_uninstall
        ;;
    "")
        echo -e "${BOLD}hermes-switch${RESET} — switch between hermes-agent installations"
        echo
        echo "Usage: $0 <command>"
        echo
        echo "Commands:"
        echo "  test      Install & activate the test branch in a venv"
        echo "  stable    Switch back to the stable PyPI version"
        echo "  status    Show which version is currently active"
        echo "  uninstall Remove the test venv"
        echo
        echo "After running '$0 test', add to your shell profile for convenience:"
        echo "  alias hermes-test='source ${VENV_PATH}/bin/activate && hermes'"
        ;;
    *)
        error "Unknown command: ${CMD}"
        ;;
esac
