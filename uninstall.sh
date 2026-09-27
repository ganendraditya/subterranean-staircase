#!/usr/bin/env bash
# Subtitle Translator V1 — Clean Uninstaller (macOS & Linux)
set -euo pipefail

if [ -z "${HOME:-}" ]; then
    echo "Error: HOME environment variable is not set." >&2
    exit 1
fi

APP_NAME="subtrans"
INSTALL_DIR="${HOME}/.local/share/subtitle-translator"
BIN_DIR="${HOME}/.local/bin"
LAUNCHER_PATH="${BIN_DIR}/${APP_NAME}"
CONFIG_BASE="${XDG_CONFIG_HOME:-${HOME}/.config}"
CACHE_BASE="${XDG_CACHE_HOME:-${HOME}/.cache}"
CONFIG_DIR="${CONFIG_BASE}/subtitle-translator"
CACHE_DIR="${CACHE_BASE}/subtitle-translator"

echo "=================================================="
echo "  Subterranean Staircase / Subtitle Translator"
echo "=================================================="

# Check for non-interactive flags (-y, -f, --yes, --force, --purge)
AUTO_CONFIRM=false
PURGE_DATA=false

for arg in "$@"; do
    case "${arg}" in
        -y|--yes|-f|--force) AUTO_CONFIRM=true ;;
        --purge|--all)
            PURGE_DATA=true
            AUTO_CONFIRM=true
            ;;
        uninstall) ;;
        *)
            echo "Warning: Unrecognized option '${arg}'" >&2
            ;;
    esac
done

if [ "${AUTO_CONFIRM}" != "true" ]; then
    if [ ! -t 0 ] && [ ! -e /dev/tty ]; then
        echo "Error: Non-interactive shell detected without -y/--force flag. Aborting." >&2
        exit 1
    fi
    echo ""
    read -r -p "Are you sure you want to uninstall Subterranean Staircase? [y/N] " CONFIRM </dev/tty || CONFIRM="n"
    case "${CONFIRM}" in
        [yY][eE][sS]|[yY]) ;;
        *)
            echo "Uninstall cancelled."
            exit 0
            ;;
    esac
fi

# 1. Remove binary launcher
if [ -f "${LAUNCHER_PATH}" ]; then
    echo "Removing launcher: ${LAUNCHER_PATH}..."
    rm -f "${LAUNCHER_PATH}" 2>/dev/null || true
fi
if [ -L "/usr/local/bin/${APP_NAME}" ]; then
    rm -f "/usr/local/bin/${APP_NAME}" 2>/dev/null || true
fi

# 2. Remove LaunchAgent (macOS only)
if [ "$(uname)" = "Darwin" ]; then
    LAUNCH_AGENT_PLIST="${HOME}/Library/LaunchAgents/com.subtitle-translator.subtrans.plist"
    if [ -f "${LAUNCH_AGENT_PLIST}" ]; then
        echo "Unloading and removing LaunchAgent..."
        launchctl unload "${LAUNCH_AGENT_PLIST}" 2>/dev/null || true
        rm -f "${LAUNCH_AGENT_PLIST}"
    fi
fi

# 3. Optional Config & Cache Clean
REMOVE_DATA="n"
if [ "${PURGE_DATA}" = "true" ]; then
    REMOVE_DATA="y"
elif [ "${AUTO_CONFIRM}" != "true" ]; then
    echo ""
    echo "💡 By default, your settings and cached translation database are preserved."
    read -r -p "Do you want to completely PURGE all translation caches and user configs? [y/N] " REMOVE_DATA </dev/tty || REMOVE_DATA="n"
fi

case "${REMOVE_DATA}" in
    [yY][eE][sS]|[yY])
        if [ -d "${CONFIG_DIR}" ]; then
            echo "Removing configuration: ${CONFIG_DIR}..."
            rm -rf "${CONFIG_DIR}"
        fi
        if [ -d "${CACHE_DIR}" ]; then
            echo "Removing cached models and database: ${CACHE_DIR}..."
            rm -rf "${CACHE_DIR}"
        fi
        ;;
    *)
        echo "Preserved user configs and caches (use --purge to remove)."
        ;;
esac

# 4. Remove installation directory (final step)
if [ -d "${INSTALL_DIR}" ]; then
    echo "Removing application files: ${INSTALL_DIR}..."
    cd "${HOME}" || true
    rm -rf "${INSTALL_DIR}"
fi

echo ""
echo "=================================================="
echo "✔ Subterranean Staircase was cleanly uninstalled."
echo "=================================================="

# If invoked from a temporary staging copy, clean up the temp file
if [ "$0" != "${INSTALL_DIR}/uninstall.sh" ] && [ -f "$0" ]; then
    rm -f "$0" 2>/dev/null || true
fi
