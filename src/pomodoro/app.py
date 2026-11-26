"""Pomodoro 桌面入口：啟動 QApplication、載入設定、開懸浮視窗、進事件迴圈。"""

from __future__ import annotations

import os
import signal
import sys

from PySide6.QtWidgets import QApplication

from pomodoro.config import ConfigManager
from pomodoro.ui.floating_widget import FloatingWidget

__all__ = ["build_widget", "main"]


def build_widget(config_manager: ConfigManager | None = None) -> FloatingWidget:
    """建立並掛好懸浮視窗（測試與 main 共用）。"""
    manager = config_manager or ConfigManager()
    return FloatingWidget(config_manager=manager)


def main() -> int:
    """應用程式進入點（``pomodoro`` 指令）。"""
    os.environ.setdefault("NO_AT_BRIDGE", "1")
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("pomodoro-mini")
    app.setOrganizationName("pomodoro-mini")
    app.setQuitOnLastWindowClosed(False)

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    widget = build_widget()
    widget.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
