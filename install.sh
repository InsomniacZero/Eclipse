#!/usr/bin/env bash
# Eclipse Global Command Installer
# Installs 'eclipse' and 'nephis' CLI commands globally on Termux, Linux, and macOS.

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "⚡ Installing Eclipse / nephis CLI globally..."

chmod +x "$DIR/start.sh" "$DIR/nephis" "$DIR/c2a" 2>/dev/null || true

INSTALLED=0

# Termux environment
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ]; then
    ln -sf "$DIR/start.sh" "$PREFIX/bin/eclipse"
    ln -sf "$DIR/start.sh" "$PREFIX/bin/nephis"
    ln -sf "$DIR/start.sh" "$PREFIX/bin/c2a"
    chmod +x "$PREFIX/bin/eclipse" "$PREFIX/bin/nephis" "$PREFIX/bin/c2a"
    INSTALLED=1
fi

# Standard Linux/macOS user bin
if [ -d "$HOME/.local/bin" ]; then
    ln -sf "$DIR/start.sh" "$HOME/.local/bin/eclipse" 2>/dev/null || true
    ln -sf "$DIR/start.sh" "$HOME/.local/bin/nephis" 2>/dev/null || true
    ln -sf "$DIR/start.sh" "$HOME/.local/bin/c2a" 2>/dev/null || true
    chmod +x "$HOME/.local/bin/eclipse" "$HOME/.local/bin/nephis" "$HOME/.local/bin/c2a" 2>/dev/null || true
    INSTALLED=1
elif [ -w "/usr/local/bin" ]; then
    ln -sf "$DIR/start.sh" "/usr/local/bin/eclipse" 2>/dev/null || true
    ln -sf "$DIR/start.sh" "/usr/local/bin/nephis" 2>/dev/null || true
    ln -sf "$DIR/start.sh" "/usr/local/bin/c2a" 2>/dev/null || true
    chmod +x "/usr/local/bin/eclipse" "/usr/local/bin/nephis" "/usr/local/bin/c2a" 2>/dev/null || true
    INSTALLED=1
fi

# Add alias to ~/.bashrc for Termux as an extra guarantee
if [ -f "$HOME/.bashrc" ]; then
    if ! grep -q "alias eclipse=" "$HOME/.bashrc" 2>/dev/null; then
        echo "alias eclipse=\"$DIR/start.sh\"" >> "$HOME/.bashrc"
        echo "alias nephis=\"$DIR/start.sh\"" >> "$HOME/.bashrc"
    fi
fi

echo "============================================================"
echo "  [✓] Eclipse CLI (keywords: eclipse / nephis) successfully installed!"
echo "  You can now run directly from anywhere:"
echo "      eclipse            (starts Eclipse Gateway)"
echo "      nephis             (starts Eclipse Gateway)"
echo "      eclipse status"
echo "      eclipse limits"
echo "============================================================"
