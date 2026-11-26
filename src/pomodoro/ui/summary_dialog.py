"""關閉前的今日專注總結對話框。"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from pomodoro.core.stats import DailyStats
from pomodoro.ui.style import build_stylesheet

__all__ = ["SummaryDialog", "format_focus_duration"]


def format_focus_duration(seconds: int) -> str:
    """把秒數格式化成中文可讀長度，例如 4510 -> 「1 小時 15 分鐘」。"""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours} 小時 {minutes} 分鐘"
    if minutes:
        return f"{minutes} 分鐘 {secs} 秒"
    return f"{secs} 秒"


class SummaryDialog(QDialog):
    """今日專注總結：日期、場次、總時長 + 確定離開 / 繼續專注。"""

    def __init__(self, stats: DailyStats, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("今日專注總結")
        self.setModal(True)
        self.setMinimumWidth(320)
        self.setStyleSheet(build_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(10)

        title = QLabel("今日專注總結", self)
        title.setObjectName("summaryTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        root.addWidget(title)

        self._date_label = QLabel(f"今日日期：{stats.date}", self)
        self._date_label.setObjectName("dateLabel")
        self._sessions_label = QLabel(f"今日專注次數：{stats.sessions} 次", self)
        self._sessions_label.setObjectName("sessionsLabel")
        self._duration_label = QLabel(
            f"今日專注總時長：{format_focus_duration(stats.focus_seconds)}",
            self,
        )
        self._duration_label.setObjectName("durationLabel")
        self._entertainment_label = QLabel(
            f"今日娛樂總時長：{format_focus_duration(stats.entertainment_seconds)}",
            self,
        )
        self._entertainment_label.setObjectName("entertainmentDurationLabel")
        for label in (
            self._date_label,
            self._sessions_label,
            self._duration_label,
            self._entertainment_label,
        ):
            label.setStyleSheet("font-size: 14px; color: #E8E8F0;")
            root.addWidget(label)

        buttons = QDialogButtonBox(self)
        self._leave_btn = buttons.addButton(
            "確定離開", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._leave_btn.setObjectName("primaryButton")
        self._stay_btn = buttons.addButton(
            "繼續專注", QDialogButtonBox.ButtonRole.RejectRole
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def showEvent(self, event: QShowEvent) -> None:
        """顯示時置中於螢幕正中央，不貼著迷你懸浮膠囊位置。"""
        super().showEvent(event)
        self._center_on_screen()
        QTimer.singleShot(0, self._center_on_screen)

    def _center_on_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            frame = self.frameGeometry()
            frame.moveCenter(avail.center())
            self.move(frame.topLeft())
