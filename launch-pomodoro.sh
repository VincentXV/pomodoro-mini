#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

UV_BIN=""
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
  UV_BIN="$HOME/.local/bin/uv"
else
  echo "uv executable not found in PATH or \$HOME/.local/bin/uv" >&2
  exit 1
fi

export NO_AT_BRIDGE=1

# 若系統已安裝 libxcb-cursor0 且有 X11/XWayland DISPLAY，優先走 xcb 以完整支援位置記憶與置頂
if [ -z "${QT_QPA_PLATFORM:-}" ] && [ -n "${DISPLAY:-}" ]; then
  if [ -e /usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0 ] \
    || [ -e /lib/x86_64-linux-gnu/libxcb-cursor.so.0 ] \
    || /sbin/ldconfig -p 2>/dev/null | grep -q "libxcb-cursor" \
    || /usr/sbin/ldconfig -p 2>/dev/null | grep -q "libxcb-cursor"; then
    export QT_QPA_PLATFORM=xcb
  fi
fi

if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
  exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/pomodoro/app.py"
fi

exec "$UV_BIN" run --directory "$SCRIPT_DIR" python3 src/pomodoro/app.py
