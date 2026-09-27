#!/usr/bin/env bash
# Subtitle Translator V1 — Single-line Terminal Installer (macOS & Linux)
set -euo pipefail

APP_NAME="subtrans"
INSTALL_DIR="${HOME}/.local/share/subtitle-translator"
BIN_DIR="${HOME}/.local/bin"
REPO_URL="https://github.com/ganendraditya/subtitle-translator.git"

echo "=================================================="
echo "  Subtitle Translator V1 — Installer"
echo "=================================================="

# 1. Check Python version
PYTHON_CMD=""
PY_VERSION=""
for cmd in python3 python; do
    if command -v "${cmd}" >/dev/null 2>&1; then
        ver=$("${cmd}" -c 'import sys; sys.exit(1) if sys.version_info < (3, 10) else print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
        if [ -n "${ver}" ]; then
            PYTHON_CMD="${cmd}"
            PY_VERSION="${ver}"
            break
        fi
    fi
done

if [ -z "${PYTHON_CMD}" ]; then
    echo "Error: Python 3.10 or higher is required but not found in PATH." >&2
    exit 1
fi
echo "✔ Found compatible Python ${PY_VERSION}"

# 2. Check Git
if ! command -v git >/dev/null 2>&1; then
    echo "Error: git is required but not found in PATH." >&2
    exit 1
fi

# 3. Clone or update repository into INSTALL_DIR
if [ -d "${INSTALL_DIR}/.git" ]; then
    echo "Updating existing installation in ${INSTALL_DIR}..."
    if ! git -C "${INSTALL_DIR}" pull --quiet 2>/dev/null; then
        echo "Git pull encountered issues. Resetting to remote state (stashing local changes)..."
        git -C "${INSTALL_DIR}" stash --quiet 2>/dev/null || true
        if ! git -C "${INSTALL_DIR}" fetch --quiet origin; then
            echo "Error: Failed to fetch repository from origin." >&2
            exit 1
        fi
        UPSTREAM="$(git -C "${INSTALL_DIR}" rev-parse --abbrev-ref @{upstream} 2>/dev/null || echo "")"
        if [ -z "${UPSTREAM}" ] || ! git -C "${INSTALL_DIR}" rev-parse --verify --quiet "${UPSTREAM}" >/dev/null 2>&1; then
            UPSTREAM="$(git -C "${INSTALL_DIR}" rev-parse --verify FETCH_HEAD 2>/dev/null || echo "HEAD")"
        fi
        git -C "${INSTALL_DIR}" reset --hard "${UPSTREAM}" --quiet
        echo "Note: Local modifications were stashed. You can inspect or restore them using: git -C \"${INSTALL_DIR}\" stash pop"
    fi
else
    if [ -d "${INSTALL_DIR}" ]; then
        if [ -n "$(ls -A "${INSTALL_DIR}" 2>/dev/null)" ]; then
            echo "Warning: Target directory ${INSTALL_DIR} exists and is not a valid git repository." >&2
            if [ ! -t 0 ]; then
                echo "Error: Non-interactive session detected and target directory is not empty. Aborting." >&2
                exit 1
            fi
            read -r -p "Overwrite and delete existing contents? [y/N] " CONFIRM || CONFIRM="n"
            case "${CONFIRM}" in
                [yY][eE][sS]|[yY]) rm -rf "${INSTALL_DIR}" ;;
                *) echo "Installation aborted." >&2; exit 1 ;;
            esac
        else
            rm -rf "${INSTALL_DIR}"
        fi
    fi
    echo "Cloning repository into ${INSTALL_DIR}..."
    if ! git clone --quiet --depth 1 "${REPO_URL}" "${INSTALL_DIR}"; then
        echo "Error: Failed to clone repository from ${REPO_URL}." >&2
        exit 1
    fi
fi

# 4. Setup dedicated virtual environment
VENV_DIR="${INSTALL_DIR}/.venv"
if [ ! -f "${VENV_DIR}/bin/python" ]; then
    echo "Creating virtual environment in ${VENV_DIR}..."
    rm -rf "${VENV_DIR}"
    if ! "${PYTHON_CMD}" -m venv "${VENV_DIR}"; then
        echo "Error: Failed to create virtual environment. If on Debian/Ubuntu, try installing 'python3-venv'." >&2
        exit 1
    fi
fi

echo "Installing/updating dependencies..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"

# 5. Create launcher wrapper script in ~/.local/bin/subtrans
mkdir -p "${BIN_DIR}"
LAUNCHER_PATH="${BIN_DIR}/${APP_NAME}"

cat << 'EOF' > "${LAUNCHER_PATH}"
#!/usr/bin/env bash
EOF
printf 'INSTALL_DIR=%q\n' "${INSTALL_DIR}" >> "${LAUNCHER_PATH}"
cat << 'EOF' >> "${LAUNCHER_PATH}"

if [ "${1:-}" = "uninstall" ]; then
    shift
    if [ ! -f "${INSTALL_DIR}/uninstall.sh" ]; then
        echo "Error: uninstall script not found at ${INSTALL_DIR}/uninstall.sh" >&2
        exit 1
    fi
    TMP_DIR="${TMPDIR:-/tmp}"
    TMP_UNINSTALL="$(umask 077 && mktemp "${TMP_DIR%/}/subtrans_uninstall.XXXXXX")" || exit 1
    cp "${INSTALL_DIR}/uninstall.sh" "${TMP_UNINSTALL}"
    chmod +x "${TMP_UNINSTALL}"
    exec "${TMP_UNINSTALL}" "$@"
fi

exec "${INSTALL_DIR}/.venv/bin/python" "${INSTALL_DIR}/run.py" "$@"
EOF

chmod +x "${LAUNCHER_PATH}"
echo "✔ Created launcher: ${LAUNCHER_PATH}"

# 6. Optional LaunchAgent (macOS only — auto-start subtrans at login)
LAUNCH_AGENT_PLIST=""
if [ "$(uname)" = "Darwin" ]; then
    LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
    LAUNCH_AGENT_PLIST="${LAUNCH_AGENTS_DIR}/com.subtitle-translator.subtrans.plist"
    INSTALL_AGENT=false

    if [ -f "${LAUNCH_AGENT_PLIST}" ]; then
        echo "✔ LaunchAgent already installed: ${LAUNCH_AGENT_PLIST}"
        launchctl load "${LAUNCH_AGENT_PLIST}" 2>/dev/null || true
        INSTALL_AGENT=false
    elif [ -t 0 ]; then
        echo ""
        read -r -p "Install LaunchAgent to auto-start subtrans at login? [y/N] " _LA_CONFIRM || _LA_CONFIRM="n"
        case "${_LA_CONFIRM}" in
            [yY][eE][sS]|[yY]) INSTALL_AGENT=true ;;
            *) INSTALL_AGENT=false ;;
        esac
    fi

    if [ "${INSTALL_AGENT}" = "true" ]; then
        mkdir -p "${LAUNCH_AGENTS_DIR}"
        cat > "${LAUNCH_AGENT_PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.subtitle-translator.subtrans</string>
    <key>ProgramArguments</key>
    <array>
        <string>${LAUNCHER_PATH}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>${HOME}/Library/Logs/subtrans.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/Library/Logs/subtrans.log</string>
</dict>
</plist>
PLIST
        launchctl load "${LAUNCH_AGENT_PLIST}" 2>/dev/null || true
        echo "✔ LaunchAgent installed — subtrans will auto-start at login."
        echo "  To disable: launchctl unload \"${LAUNCH_AGENT_PLIST}\""
    fi
fi

# 8. Check PATH
if command -v "${APP_NAME}" >/dev/null 2>&1; then
    :
else
    case ":${PATH}:" in
        *:"${BIN_DIR}":*|*:"~/.local/bin":*) ;;
        *)
            echo ""
            echo "Note: ${BIN_DIR} is not in your current PATH."
            echo "Add the following line to your shell profile (~/.zshrc or ~/.bashrc):"
            echo "  export PATH=\"\${HOME}/.local/bin:\${PATH}\""
            ;;
    esac
fi

echo ""
echo "=================================================="
echo "✔ Installation completed successfully!"
echo "Run 'subtrans' to launch Subtitle Translator."
echo "Run 'subtrans uninstall' to remove it."
echo "=================================================="
