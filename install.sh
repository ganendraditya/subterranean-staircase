#!/usr/bin/env bash
# Subtitle Translator V1 — Single-line Terminal Installer (macOS & Linux)
set -euo pipefail

APP_NAME="subtrans"
INSTALL_DIR="${HOME}/.local/share/subtitle-translator"
BIN_DIR="${HOME}/.local/bin"
REPO_URL="https://github.com/ganendraditya/subterranean-staircase.git"

echo "=================================================="
echo "  Subterranean Staircase / Subtitle Translator"
echo "=================================================="

# Determine OS and Architecture
OS_NAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH_RAW="$(uname -m)"
case "${ARCH_RAW}" in
    x86_64|amd64) ARCH="x86_64" ;;
    arm64|aarch64) ARCH="arm64" ;;
    *) ARCH="${ARCH_RAW}" ;;
esac

PREBUILT_INSTALLED=false

# Attempt Fast Prebuilt Release Download (Zero-Python requirement)
if command -v curl >/dev/null 2>&1 && command -v tar >/dev/null 2>&1; then
    ASSET_NAME="subtrans-${OS_NAME}-${ARCH}.tar.gz"
    RELEASE_URL="https://github.com/ganendraditya/subterranean-staircase/releases/latest/download/${ASSET_NAME}"

    if curl -s -f -I -L "${RELEASE_URL}" >/dev/null 2>&1; then
        echo "🚀 Found prebuilt standalone release for ${OS_NAME}-${ARCH}."
        echo "⬇ Downloading prebuilt package..."
        TMP_TAR="$(mktemp "${TMPDIR:-/tmp}/subtrans_dist.XXXXXX.tar.gz")"
        if curl -f -L --progress-bar "${RELEASE_URL}" -o "${TMP_TAR}"; then
            echo "📦 Extracting to ${INSTALL_DIR}..."
            mkdir -p "${INSTALL_DIR}"
            tar -xzf "${TMP_TAR}" -C "${INSTALL_DIR}" --strip-components=1
            rm -f "${TMP_TAR}"
            PREBUILT_INSTALLED=true
        fi
    fi
fi

if [ "${PREBUILT_INSTALLED}" != "true" ]; then
    # 1. Check Python version (requires Python 3.10 - 3.12 for ONNX/PyTorch compatibility)
    PYTHON_CMD=""
    PY_VERSION=""
    for cmd in python3.12 python3.11 python3.10 python3 python; do
        if command -v "${cmd}" >/dev/null 2>&1; then
            ver=$("${cmd}" -c 'import sys; sys.exit(1) if not (3, 10) <= sys.version_info < (3, 13) else print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
            if [ -n "${ver}" ]; then
                PYTHON_CMD="${cmd}"
                PY_VERSION="${ver}"
                break
            fi
        fi
    done

    if [ -z "${PYTHON_CMD}" ]; then
        echo "Error: Python 3.10, 3.11, or 3.12 is required (ONNX runtime and CTranslate2 do not yet support Python 3.13+)." >&2
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
    VENV_PY_VER=""
    if [ -f "${VENV_DIR}/bin/python" ]; then
        VENV_PY_VER=$("${VENV_DIR}/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
    fi

    if [ ! -f "${VENV_DIR}/bin/python" ] || [ "${VENV_PY_VER}" != "${PY_VERSION}" ]; then
        echo "Creating virtual environment with Python ${PY_VERSION} in ${VENV_DIR}..."
        rm -rf "${VENV_DIR}"
        if ! "${PYTHON_CMD}" -m venv "${VENV_DIR}"; then
            echo "Error: Failed to create virtual environment. If on Debian/Ubuntu, try installing 'python3-venv'." >&2
            exit 1
        fi
    fi

    echo ""
    echo "📦 Installing AI & GUI dependencies (RapidOCR, CTranslate2, PyQt6)..."
    echo "--------------------------------------------------"

    PIP_MIRROR_ARGS=()
    # If in Asia/Pacific region or experiencing PyPI throttling, use high-speed mirror
    if curl -s --connect-timeout 2 -I https://mirrors.aliyun.com/pypi/simple/ >/dev/null 2>&1; then
        echo "✔ Using high-speed Regional PyPI CDN mirror"
        PIP_MIRROR_ARGS=(-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com)
    fi

    "${VENV_DIR}/bin/pip" install "${PIP_MIRROR_ARGS[@]}" --upgrade pip >/dev/null 2>&1 || true

    # Install dependencies with full native pip progress bar
    "${VENV_DIR}/bin/pip" install "${PIP_MIRROR_ARGS[@]}" -r "${INSTALL_DIR}/requirements.txt"

    echo "--------------------------------------------------"
fi

# 5. Create launcher wrapper script and macOS App Bundle
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

# On macOS, register native .app bundle so Screen Recording permission is attributed to "Subterranean Staircase"
if [ "$(uname)" = "Darwin" ]; then
    MAC_APP_DIR="${HOME}/Applications/Subterranean Staircase.app"
    mkdir -p "${MAC_APP_DIR}/Contents/MacOS"
    mkdir -p "${MAC_APP_DIR}/Contents/Resources"

    cat > "${MAC_APP_DIR}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Subterranean Staircase</string>
    <key>CFBundleDisplayName</key>
    <string>Subterranean Staircase</string>
    <key>CFBundleIdentifier</key>
    <string>com.subtitle-translator.subtrans</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>subtrans</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSScreenCaptureUsageDescription</key>
    <string>Subterranean Staircase needs Screen Recording access to detect and translate on-screen subtitles in real time.</string>
</dict>
</plist>
PLIST

    # Put app bundle executable that delegates to virtualenv python
    cat << 'EOF' > "${MAC_APP_DIR}/Contents/MacOS/subtrans"
#!/usr/bin/env bash
EOF
    printf 'INSTALL_DIR=%q\n' "${INSTALL_DIR}" >> "${MAC_APP_DIR}/Contents/MacOS/subtrans"
    cat << 'EOF' >> "${MAC_APP_DIR}/Contents/MacOS/subtrans"
exec "${INSTALL_DIR}/.venv/bin/python" "${INSTALL_DIR}/run.py" "$@"
EOF
    chmod +x "${MAC_APP_DIR}/Contents/MacOS/subtrans"
    echo "✔ Created native macOS App Bundle: ${MAC_APP_DIR}"
fi

# 6. Configure LaunchAgent (macOS auto-start on login)
if [ "$(uname)" = "Darwin" ]; then
    LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
    LAUNCH_AGENT_PLIST="${LAUNCH_AGENTS_DIR}/com.subtitle-translator.subtrans.plist"
    mkdir -p "${LAUNCH_AGENTS_DIR}"

    APP_BIN_TARGET="${LAUNCHER_PATH}"
    if [ -f "${HOME}/Applications/Subterranean Staircase.app/Contents/MacOS/subtrans" ]; then
        APP_BIN_TARGET="${HOME}/Applications/Subterranean Staircase.app/Contents/MacOS/subtrans"
    fi

    cat > "${LAUNCH_AGENT_PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.subtitle-translator.subtrans</string>
    <key>ProgramArguments</key>
    <array>
        <string>${APP_BIN_TARGET}</string>
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
    echo "✔ Configured background service — subtrans will standby at login."
fi

# 8. Configure PATH automatically in user shell profile if missing
case ":${PATH}:" in
    *:"${BIN_DIR}":*|*:"~/.local/bin":*) ;;
    *)
        SHELL_RC=""
        if [ -n "${ZSH_VERSION:-}" ] || [ -f "${HOME}/.zshrc" ]; then
            SHELL_RC="${HOME}/.zshrc"
        elif [ -f "${HOME}/.bashrc" ]; then
            SHELL_RC="${HOME}/.bashrc"
        fi

        if [ -n "${SHELL_RC}" ]; then
            if ! grep -q 'export PATH=.*\.local/bin' "${SHELL_RC}" 2>/dev/null; then
                printf '\n# Added by Subterranean Staircase (subtrans)\nexport PATH="%s:${PATH}"\n' "${BIN_DIR}" >> "${SHELL_RC}"
                echo "✔ Automatically configured PATH in ${SHELL_RC}"
            fi
        fi
        ;;
esac

# 9. Create standard symlink in /usr/local/bin if writable (instantly available without reloading shell)
if [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    ln -sf "${LAUNCHER_PATH}" "/usr/local/bin/${APP_NAME}" 2>/dev/null || true
fi

echo ""
echo "=================================================="
echo "✔ Installation completed successfully!"
echo "Run 'subtrans' to launch Subtitle Translator."
echo "Run 'subtrans uninstall' to remove it."
echo "=================================================="

# Auto-launch app into background immediately after install if not already running
if ! pgrep -f "subtitle-translator/run.py" >/dev/null 2>&1; then
    nohup "${LAUNCHER_PATH}" >/dev/null 2>&1 &
fi
