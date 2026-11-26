#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APP_DIR/pomodoro-mini.desktop"

mkdir -p "$APP_DIR"
chmod +x "$SCRIPT_DIR/launch-pomodoro.sh"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Pomodoro Mini
Name[zh_TW]=迷你番茄鐘
Comment=Bongo Cat style floating Pomodoro desktop timer
Comment[zh_TW]=常駐桌面迷你懸浮番茄鐘
Exec=$SCRIPT_DIR/launch-pomodoro.sh
Icon=$SCRIPT_DIR/assets/pomodoro.svg
Terminal=false
Categories=Utility;Clock;
StartupNotify=false
EOF

chmod 644 "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "已註冊至應用程式清單: $DESKTOP_FILE"
