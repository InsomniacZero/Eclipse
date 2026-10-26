#!/usr/bin/env bash
# Eclipse Gateway Launcher

if command -v realpath >/dev/null 2>&1; then
    SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
    DIR="$(dirname "$SCRIPT_PATH")"
else
    DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
fi


# Auto-link 'eclipse' binary into PATH if in Termux
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ]; then
    ln -sf "$DIR/start.sh" "$PREFIX/bin/eclipse" 2>/dev/null || true
    chmod +x "$PREFIX/bin/eclipse" 2>/dev/null || true
    if [ -f "$HOME/.bashrc" ]; then
        if ! grep -q "alias eclipse=" "$HOME/.bashrc" 2>/dev/null; then
            echo "alias eclipse=\"$DIR/start.sh\"" >> "$HOME/.bashrc" 2>/dev/null || true
        fi
    fi
fi

# Auto-link into ~/.local/bin for standard Linux/macOS users
if [ -z "$PREFIX" ] && [ -d "$HOME/.local/bin" ]; then
    ln -sf "$DIR/start.sh" "$HOME/.local/bin/eclipse" 2>/dev/null || true
    chmod +x "$HOME/.local/bin/eclipse" 2>/dev/null || true
fi

# Phone / Termux Native ngrok setup (Android ARM64/ARM)
if [ -n "$PREFIX" ]; then
    # Verify existing ngrok actually runs without Exec format error
    NGROK_RUNNABLE=0
    if command -v ngrok >/dev/null 2>&1; then
        if ngrok version >/dev/null 2>&1; then
            NGROK_RUNNABLE=1
        else
            echo "  [⚠️] Detected broken or architecture-mismatched ngrok in Termux. Removing..."
            rm -f "$PREFIX/bin/ngrok" "$DIR/eclipse/bin/ngrok" 2>/dev/null || true
        fi
    fi

    if [ "$NGROK_RUNNABLE" -eq 0 ]; then
        echo "  [📱] Android/Termux detected: installing verified native ngrok binary..."
        (
            # Accurately detect userspace architecture (dpkg) rather than just kernel (uname -m)
            DPKG_ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
            NGROK_URL=""
            if [ "$DPKG_ARCH" = "aarch64" ] || [ "$DPKG_ARCH" = "arm64" ]; then
                NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz"
            elif [[ "$DPKG_ARCH" == arm* ]]; then
                NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz"
            elif [ "$DPKG_ARCH" = "x86_64" ] || [ "$DPKG_ARCH" = "amd64" ]; then
                NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz"
            else
                NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz"
            fi

            TMP_TGZ="/tmp/ngrok-termux-$$.tgz"
            if command -v curl >/dev/null 2>&1; then
                curl -sSL "$NGROK_URL" -o "$TMP_TGZ" 2>/dev/null
            elif command -v wget >/dev/null 2>&1; then
                wget -q "$NGROK_URL" -O "$TMP_TGZ" 2>/dev/null
            fi

            if [ -f "$TMP_TGZ" ]; then
                mkdir -p "$DIR/eclipse/bin"
                tar -xzf "$TMP_TGZ" -C "$DIR/eclipse/bin" ngrok 2>/dev/null || tar -xzf "$TMP_TGZ" -C "$DIR/eclipse/bin" 2>/dev/null
                rm -f "$TMP_TGZ"
                if [ -f "$DIR/eclipse/bin/ngrok" ]; then
                    chmod +x "$DIR/eclipse/bin/ngrok"
                    # Test if the binary executes without Exec format error
                    if ! "$DIR/eclipse/bin/ngrok" version >/dev/null 2>&1; then
                        echo "  [!] Primary binary incompatible with device. Falling back to alternative 32-bit ARM binary..."
                        ALT_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz"
                        if command -v curl >/dev/null 2>&1; then
                            curl -sSL "$ALT_URL" -o "/tmp/ngrok-alt.tgz" 2>/dev/null
                        elif command -v wget >/dev/null 2>&1; then
                            wget -q "$ALT_URL" -O "/tmp/ngrok-alt.tgz" 2>/dev/null
                        fi
                        if [ -f "/tmp/ngrok-alt.tgz" ]; then
                            tar -xzf "/tmp/ngrok-alt.tgz" -C "$DIR/eclipse/bin" ngrok 2>/dev/null
                            chmod +x "$DIR/eclipse/bin/ngrok"
                            rm -f "/tmp/ngrok-alt.tgz"
                        fi
                    fi

                    if "$DIR/eclipse/bin/ngrok" version >/dev/null 2>&1; then
                        [ -d "$PREFIX/bin" ] && cp -f "$DIR/eclipse/bin/ngrok" "$PREFIX/bin/ngrok" 2>/dev/null && chmod +x "$PREFIX/bin/ngrok" 2>/dev/null
                        echo "  [✓] Verified native ngrok successfully installed for Android!"
                    fi
                fi
            fi
        ) || true
    fi
fi

# Detect Python across Linux, macOS, Termux, and Windows (Git Bash/MSYS2/WSL)
PYTHON_BIN=""
if [ -x "$DIR/eclipse/.venv/bin/python3" ]; then
    PYTHON_BIN="$DIR/eclipse/.venv/bin/python3"
elif [ -x "$DIR/eclipse/.venv/Scripts/python.exe" ]; then
    PYTHON_BIN="$DIR/eclipse/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
elif command -v py >/dev/null 2>&1; then
    PYTHON_BIN="py"
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "============================================================"
    echo "  [ERROR] Python was not found on your system!"
    echo "  Please install Python 3.10+ from https://www.python.org"
    echo "  On Windows: Ensure 'Add python.exe to PATH' is checked."
    echo "============================================================"
    read -p "Press Enter to close..." _ 2>/dev/null || sleep 5
    exit 1
fi

# Prevent instant terminal window closure on crash/error (common on Windows Git Bash)
trap 'EXIT_CODE=$?; if [ $EXIT_CODE -ne 0 ]; then echo ""; echo "Eclipse exited with code $EXIT_CODE."; read -p "Press Enter to close..." _ 2>/dev/null || sleep 5; fi' EXIT

cd "$DIR/eclipse" || exit 1

# Check basic dependencies (starlette, uvicorn, httpx)
if ! "$PYTHON_BIN" -c "import starlette, uvicorn, httpx" 2>/dev/null; then
    # Homebrew and Debian/Ubuntu Pythons refuse global pip installs (PEP 668), so install into a
    # private virtualenv like start.bat does. Falls back to the plain interpreter if venv is unavailable.
    VENV_DIR="$DIR/eclipse/.venv"
    if [ ! -x "$VENV_DIR/bin/python3" ] && [ ! -x "$VENV_DIR/Scripts/python.exe" ]; then
        echo "  [*] Creating virtual environment in eclipse/.venv..."
        "$PYTHON_BIN" -m venv "$VENV_DIR" >/dev/null 2>&1 || rm -rf "$VENV_DIR"
    fi
    if [ -x "$VENV_DIR/bin/python3" ]; then
        PYTHON_BIN="$VENV_DIR/bin/python3"
    elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
        PYTHON_BIN="$VENV_DIR/Scripts/python.exe"
    fi

    echo "  [*] Installing required dependencies from requirements.txt..."
    "$PYTHON_BIN" -m pip install -r "$DIR/requirements.txt" || true
    if ! "$PYTHON_BIN" -c "import starlette, uvicorn, httpx" 2>/dev/null; then
        echo "  [ERROR] Could not install Eclipse's Python dependencies."
        echo "          Try manually: $PYTHON_BIN -m pip install -r \"$DIR/requirements.txt\""
        exit 1
    fi
fi

# --lan: listen on all interfaces so phones / other PCs can connect (they log in with the gateway key).
# --no-update: bypass automatic startup git pull.
# Default is this machine only.
ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--lan" ]; then
        export ECLIPSE_LAN=1
    elif [ "$arg" = "--no-update" ]; then
        export ECLIPSE_NO_UPDATE=1
    else
        ARGS+=("$arg")
    fi
done
set -- ${ARGS[@]+"${ARGS[@]}"}

kill_port_listeners() {
    for port in "$@"; do
        # 1. fuser sends SIGKILL directly to processes using the port socket
        if command -v fuser >/dev/null 2>&1; then
            fuser -k -9 "${port}/tcp" >/dev/null 2>&1 || true
        fi
        # 2. lsof filtered specifically to LISTEN sockets (avoids touching client connections)
        if command -v lsof >/dev/null 2>&1; then
            lsof -sTCP:LISTEN -iTCP:"${port}" -t 2>/dev/null | xargs -r kill -9 >/dev/null 2>&1 || true
        fi
        # 3. ss socket statistics parser for listening PIDs on Linux
        if command -v ss >/dev/null 2>&1; then
            ss -lptn "sport = :${port}" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | xargs -r kill -9 >/dev/null 2>&1 || true
        fi
    done
}

# Route CLI commands vs server launch
case "$1" in
    status|limits|accounts|login|autofetch|import|export|simulate|host|chat|model-audit|thinking|service|tunnel|claudecode|key|bench|update|upgrade|-h|--help)
        exec "$PYTHON_BIN" cli.py "$@"
        ;;
    restart|server|"")
        IS_RESTART=0
        if [ "$1" = "restart" ]; then
            IS_RESTART=1
            shift
        elif [ "$1" = "server" ]; then
            shift
        fi

        # Cleanly terminate any stale processes holding port 5000
        GATEWAY_PORT="${PORT:-5000}"
        if [ "$IS_RESTART" = "1" ]; then
            echo "  [🔄] Restarting Eclipse (clearing port $GATEWAY_PORT)..."
        fi
        kill_port_listeners "$GATEWAY_PORT"
        sleep 0.2

        "$PYTHON_BIN" server.py "$@"
        exit $?
        ;;
    *)
        kill_port_listeners "${PORT:-5000}"
        exec "$PYTHON_BIN" server.py "$@"
        ;;
esac

