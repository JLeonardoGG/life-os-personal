#!/bin/zsh
set -euo pipefail
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.lifeos.personal.plist" 2>/dev/null || true
pkill -f "uvicorn lifeos.main:app.*127.0.0.1.*8765" 2>/dev/null || true
echo "Life OS detenido."
