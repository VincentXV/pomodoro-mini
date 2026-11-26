"""Bongo Cat 風格迷你懸浮膠囊計時器（無邊框、可拖曳、右鍵選單）。"""

from __future__ import annotations

import math
import shutil
import subprocess
from dataclasses import asdict

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QEnterEvent,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)

from pomodoro.config import AppConfig, ConfigManager
from pomodoro.core.sound import SoundManager
from pomodoro.core.state_machine import PomodoroStateMachine, TimerMode, TimerState
from pomodoro.core.stats import StatsManager
from pomodoro.ui.settings_dialog import SettingsDialog
from pomodoro.ui.style import accent_color, build_stylesheet
from pomodoro.ui.summary_dialog import SummaryDialog

__all__ = [
    "CAPSULE_HEIGHT",
    "FloatingWidget",
    "POLL_INTERVAL_MS",
    "TOP_TAB_HEIGHT",
    "WIDGET_HEIGHT",
    "WIDGET_WIDTH",
]

WIDGET_WIDTH = 244
TOP_TAB_HEIGHT = 20  # 正上方模式切換小方格標籤的高度
CAPSULE_HEIGHT = 64  # 橢圓膠囊本體高度（維持原本 244x64）
WIDGET_HEIGHT = TOP_TAB_HEIGHT + CAPSULE_HEIGHT  # 84
POLL_INTERVAL_MS = 100
PROGRESS_HEIGHT = 4
MODE_TAB_WIDTH = 76

_PHASE_DONE_MESSAGES: dict[TimerMode, tuple[str, str]] = {
    TimerMode.WORK: ("專注結束", "這一輪完成了，休息一下吧"),
    TimerMode.SHORT_BREAK: ("短休結束", "回到專注節奏"),
    TimerMode.LONG_BREAK: ("長休結束", "精神補滿，繼續下一輪"),
    TimerMode.GAME: ("遊戲時間到", "起身走動一下，讓眼睛休息吧"),
}


class _BreathingDot(QWidget):
    """左側模式呼吸指示燈：執行中呼吸、暫停慢閃、閒置恆亮。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._color = QColor("#FF6B6B")
        self._active = False
        self._paused = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def set_state(self, active: bool, paused: bool) -> None:
        self._active = active
        self._paused = paused

    def _advance(self) -> None:
        speed = 0.16 if self._active else 0.07
        self._phase += speed
        if self._phase > 6.283185307179586:
            self._phase -= 6.283185307179586
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._active:
            wave = 0.5 + 0.5 * math.sin(self._phase)
            alpha = int(90 + 165 * wave)
        elif self._paused:
            wave = 0.5 + 0.5 * math.sin(self._phase)
            alpha = int(50 + 120 * wave)
        else:
            alpha = 130
        color = QColor(self._color)
        color.setAlpha(alpha)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(1, 1, 8, 8)
        painter.end()


class FloatingWidget(QWidget):
    """244x84 懸浮膠囊：頂部模式小方格 + 倒數顯示 + 控制按鈕 + 底部進度條 + 右鍵選單。"""

    def __init__(
        self,
        config_manager: ConfigManager | None = None,
        parent: QWidget | None = None,
        stats_manager: StatsManager | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_manager = config_manager or ConfigManager()
        config = self._config_manager.load()
        self._machine = PomodoroStateMachine(config)
        self._sound = SoundManager()
        self._stats = stats_manager or StatsManager()
        self._user_quit = False
        self._drag_offset: QPoint | None = None
        self._buttons_visible = False
        self._current_accent = ""
        self._opacity = config.window_opacity / 100.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Pomodoro")
        self.setFixedSize(WIDGET_WIDTH, WIDGET_HEIGHT)

        self._build_ui()
        self.setStyleSheet(build_stylesheet())
        self._apply_window_config()

        if config.window_x is not None and config.window_y is not None:
            self.move(self._clamp_to_available_geometry(QPoint(config.window_x, config.window_y)))

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

        self._refresh()

    # ------------------------------------------------------------------ #
    # UI 組裝
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        # 頂部留 TOP_TAB_HEIGHT 給模式小方格；底部留白給進度條
        layout.setContentsMargins(12, TOP_TAB_HEIGHT + 6, 8, 8)
        layout.setSpacing(6)

        # 頂部正中央的模式切換小方格（不進 layout，絕對定位在膠囊上方）
        self._mode_tab_btn = QPushButton("專注", self)
        self._mode_tab_btn.setObjectName("modeTabButton")
        self._mode_tab_btn.setFixedSize(MODE_TAB_WIDTH, TOP_TAB_HEIGHT)
        self._mode_tab_btn.move((WIDGET_WIDTH - MODE_TAB_WIDTH) // 2, 0)
        self._mode_tab_btn.clicked.connect(self.toggle_game_mode)

        self._dot = _BreathingDot(self)
        layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._time_label = QLabel("25:00", self)
        self._time_label.setObjectName("timeLabel")
        self._time_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        font = QFont()
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setBold(True)
        self._time_label.setFont(font)
        layout.addWidget(self._time_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._cycle_label = QLabel("0/4", self)
        self._cycle_label.setObjectName("cycleLabel")
        self._cycle_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._cycle_label, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

        # 固定寬度容器：按鈕藏起來時也不會讓左側文字跳位
        # （不可設 WA_TransparentForMouseEvents，否則子按鈕會收不到點擊）
        btn_box = QWidget(self)
        btn_box.setFixedSize(96, 24)
        btn_layout = QHBoxLayout(btn_box)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(2)

        self._play_btn = self._make_button("▶", "開始 / 暫停")
        self._skip_btn = self._make_button("⏭", "跳到下一階段")
        self._settings_btn = self._make_button("⚙", "偏好設定")
        self._close_btn = self._make_button("✕", "離開")
        self._play_btn.clicked.connect(self.toggle_start_pause)
        self._skip_btn.clicked.connect(self.skip_phase)
        self._settings_btn.clicked.connect(self.open_settings)
        self._close_btn.clicked.connect(self.quit_app)
        for button in (self._play_btn, self._skip_btn, self._settings_btn, self._close_btn):
            btn_layout.addWidget(button)

        layout.addWidget(btn_box, 0, Qt.AlignmentFlag.AlignVCenter)
        self._set_buttons_visible(False)

    def _make_button(self, text: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setFixedWidth(22)
        button.setFixedHeight(22)
        button.hide()  # 預設低調藏起，滑鼠懸停才現身
        return button

    # ------------------------------------------------------------------ #
    # 操作
    # ------------------------------------------------------------------ #
    def toggle_start_pause(self) -> None:
        """開始 / 暫停切換。"""
        self._machine.start_or_pause()
        self._refresh()

    def toggle_game_mode(self) -> None:
        """專注 ⇄ 遊戲模式切換；兩組計時上下文由狀態機各自保存。"""
        self._machine.toggle_game_mode()
        self._refresh()

    def reset_phase(self) -> None:
        """重設目前階段；WORK / GAME 走過 >= 1 秒先把秒數記進統計（不加次數）。"""
        self._flush_partial_work()
        self._flush_partial_game()
        self._machine.reset()
        self._refresh()

    def skip_phase(self) -> None:
        """跳到下一階段；WORK / GAME 中途跳過只累加秒數、不加場次。"""
        self._flush_partial_work()
        self._flush_partial_game()
        self._machine.advance_phase()
        self._refresh()

    def open_settings(self) -> None:
        """開啟偏好設定；確定後存檔並套用。"""
        initial_mode = "game" if self._machine.mode is TimerMode.GAME else "focus"
        dialog = SettingsDialog(self._machine.config, self, initial_mode=initial_mode)
        if dialog.exec():
            self.apply_config(dialog.config())

    def apply_config(self, config: AppConfig) -> None:
        """存檔、套用新設定與外觀（透明度 / 置頂）。"""
        config.window_x = self.x()
        config.window_y = self.y()
        self._config_manager.save(config)
        self._machine.update_config(config)
        self._apply_window_config()
        self._refresh()

    def _apply_window_config(self) -> None:
        config = self._machine.config
        self._opacity = config.window_opacity / 100.0
        if not QApplication.platformName().startswith("wayland"):
            self.setWindowOpacity(self._opacity)
        current_on_top = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if current_on_top != config.always_on_top:
            was_visible = self.isVisible()
            if was_visible:
                self.hide()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, config.always_on_top)
            if was_visible:
                self.show()
                self.raise_()
        self.update()

    def _save_window_position(self) -> None:
        """儲存目前視窗座標；Wayland 不提供全域座標時不覆蓋既有設定。"""
        if QApplication.platformName().startswith("wayland"):
            return
        config = self._machine.config
        config.window_x = self.x()
        config.window_y = self.y()
        self._config_manager.save(config)

    def quit_app(self) -> None:
        """使用者按離開：走 closeEvent 彈今日總結，確定後才存位置並離開。"""
        self._user_quit = True
        self.close()

    # ------------------------------------------------------------------ #
    # 每日專注統計
    # ------------------------------------------------------------------ #
    def _work_elapsed_seconds(self) -> float:
        """目前 WORK 階段已走秒數（非進行中回 0）。"""
        if self._machine.mode is not TimerMode.WORK:
            return 0.0
        if self._machine.state not in (TimerState.RUNNING, TimerState.PAUSED):
            return 0.0
        duration = float(self._machine.config.work_minutes) * 60.0
        return max(0.0, duration - self._machine.timer.remaining_seconds())

    def _flush_partial_work(self) -> int:
        """WORK 中途累計已走秒數（>= 1 秒才記），回傳本次寫入秒數。"""
        elapsed = int(self._work_elapsed_seconds())
        if elapsed < 1:
            return 0
        self._stats.add_focus_seconds(elapsed)
        return elapsed

    def _game_elapsed_seconds(self) -> float:
        """目前 GAME 階段已走秒數（非進行中回 0）。"""
        if self._machine.mode is not TimerMode.GAME:
            return 0.0
        if self._machine.state not in (TimerState.RUNNING, TimerState.PAUSED):
            return 0.0
        duration = float(self._machine.config.game_minutes) * 60.0
        return max(0.0, duration - self._machine.timer.remaining_seconds())

    def _flush_partial_game(self) -> int:
        """GAME 中途累計已走秒數（>= 1 秒才記），回傳本次寫入秒數。"""
        elapsed = int(self._game_elapsed_seconds())
        if elapsed < 1:
            return 0
        self._stats.add_entertainment_seconds(elapsed)
        return elapsed

    # ------------------------------------------------------------------ #
    # 輪詢
    # ------------------------------------------------------------------ #
    def _poll(self) -> None:
        """100ms 輪詢狀態機；剛好走完就播音效 + 系統通知。"""
        finished_mode = self._machine.mode
        # 遊戲倒數一結束狀態機就會把 timer 歸零，所以先量已走秒數再 tick
        game_seconds = int(self._game_elapsed_seconds()) if finished_mode is TimerMode.GAME else 0
        if self._machine.tick():
            if finished_mode is TimerMode.WORK:
                # WORK 自然完成：場次 +1 並累加整段專注秒數
                self._stats.record_session(int(self._machine.config.work_minutes) * 60)
            elif finished_mode is TimerMode.GAME and game_seconds > 0:
                # 遊戲自然完成：整段遊戲秒數記進今日娛樂時長
                self._stats.add_entertainment_seconds(game_seconds)
            self._on_phase_finished(finished_mode)
        self._refresh()

    def _on_phase_finished(self, finished_mode: TimerMode) -> None:
        config = self._machine.config
        if finished_mode is TimerMode.GAME:
            # 遊戲體系讀專屬提醒欄位，不污染專注設定
            sound_enabled = config.game_sound_enabled
            sound_track = config.game_sound_track
            sound_volume = config.game_sound_volume
            notify_enabled = config.game_notification_enabled
        else:
            sound_enabled = config.sound_enabled
            sound_track = config.sound_track
            sound_volume = config.sound_volume
            notify_enabled = config.notification_enabled
        if sound_enabled:
            self._sound.play(sound_track, sound_volume)
        if notify_enabled:
            title, message = _PHASE_DONE_MESSAGES.get(
                finished_mode, ("階段結束", "換下一階段吧")
            )
            self._notify(title, message)

    def _notify(self, title: str, message: str) -> None:
        """非阻塞呼叫 notify-send；沒裝或失敗都安全降級不報錯。"""
        if not shutil.which("notify-send"):
            return
        try:
            subprocess.Popen(
                ["notify-send", title, message],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # 畫面
    # ------------------------------------------------------------------ #
    def _refresh(self) -> None:
        state = self._machine.state
        self._time_label.setText(self._machine.formatted_time())
        self._cycle_label.setText(self._machine.cycle_display())
        self._play_btn.setText("⏸" if state is TimerState.RUNNING else "▶")
        self._mode_tab_btn.setText(
            "遊戲" if self._machine.mode is TimerMode.GAME else "專注"
        )

        accent = accent_color(self._machine.mode)
        self._dot.set_color(QColor(accent))
        self._dot.set_state(
            active=state is TimerState.RUNNING,
            paused=state is TimerState.PAUSED,
        )
        if accent != self._current_accent:
            self._current_accent = accent
            self.setStyleSheet(build_stylesheet(accent=accent))
        self.update()  # 重繪底部進度條

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if QApplication.platformName().startswith("wayland"):
            painter.setOpacity(self._opacity)

        # 橢圓膠囊畫在頂部小方格下方（244x64 不變），圓角仍是膠囊半高
        capsule = QRectF(0, TOP_TAB_HEIGHT, WIDGET_WIDTH, CAPSULE_HEIGHT)
        radius = CAPSULE_HEIGHT / 2.0
        path = QPainterPath()
        path.addRoundedRect(capsule, radius, radius)

        gradient = QLinearGradient(0, TOP_TAB_HEIGHT, 0, TOP_TAB_HEIGHT + CAPSULE_HEIGHT)
        gradient.setColorAt(0.0, QColor("#2B2B44"))
        gradient.setColorAt(1.0, QColor("#1E1E32"))
        painter.fillPath(path, gradient)

        border = QPen(QColor("#3E3E5C"))
        border.setWidthF(1.0)
        painter.setPen(border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # 底部極細進度條：貼著膠囊底部，顏色隨模式強調色
        capsule_bottom = TOP_TAB_HEIGHT + CAPSULE_HEIGHT
        progress = min(1.0, max(0.0, self._machine.progress()))
        painter.save()
        painter.setClipPath(path)
        track = QColor("#FFFFFF")
        track.setAlpha(28)
        painter.fillRect(
            QRectF(0, capsule_bottom - PROGRESS_HEIGHT, WIDGET_WIDTH, PROGRESS_HEIGHT),
            track,
        )
        if progress > 0.0:
            painter.fillRect(
                QRectF(
                    0,
                    capsule_bottom - PROGRESS_HEIGHT,
                    WIDGET_WIDTH * progress,
                    PROGRESS_HEIGHT,
                ),
                QColor(self._current_accent or "#FF6B6B"),
            )
        painter.restore()
        painter.end()

    # ------------------------------------------------------------------ #
    # 互動：拖曳 / 懸停 / 右鍵選單
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def _clamp_to_available_geometry(self, pos: QPoint) -> QPoint:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return pos
        avail = screen.availableGeometry()
        max_x = max(avail.left(), avail.right() - self.width() + 1)
        max_y = max(avail.top(), avail.bottom() - self.height() + 1)
        x = max(avail.left(), min(pos.x(), max_x))
        y = max(avail.top(), min(pos.y(), max_y))
        return QPoint(x, y)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            target = event.globalPosition().toPoint() - self._drag_offset
            self.move(self._clamp_to_available_geometry(target))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def enterEvent(self, event: QEnterEvent) -> None:
        self._set_buttons_visible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001 - Qt 事件型別
        self._set_buttons_visible(False)
        super().leaveEvent(event)

    def _set_buttons_visible(self, visible: bool) -> None:
        if visible == self._buttons_visible:
            return
        self._buttons_visible = visible
        for button in (self._play_btn, self._skip_btn, self._settings_btn, self._close_btn):
            button.setVisible(visible)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        act_toggle = menu.addAction("開始 / 暫停")
        act_reset = menu.addAction("重設")
        act_skip = menu.addAction("跳過")
        menu.addSeparator()
        act_settings = menu.addAction("偏好設定")
        act_quit = menu.addAction("離開")

        chosen = menu.exec(event.globalPos())
        if chosen is act_toggle:
            self.toggle_start_pause()
        elif chosen is act_reset:
            self.reset_phase()
        elif chosen is act_skip:
            self.skip_phase()
        elif chosen is act_settings:
            self.open_settings()
        elif chosen is act_quit:
            self.quit_app()

    # ------------------------------------------------------------------ #
    # 關閉
    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:  # noqa: ANN001 - Qt 事件型別
        """離開前記住視窗位置；使用者主动離開時先彈今日總結。"""
        # 測試 fixture 的程式化 close() 不會走到這裡的對話框：
        # 只有 quit_app 設旗標或視窗系統自发關閉才彈 modal。
        user_close = self._user_quit or bool(event.spontaneous())
        partial_added = self._flush_partial_work()
        game_added = self._flush_partial_game()
        if user_close:
            dialog = SummaryDialog(self._stats.today())
            if dialog.exec() != QDialog.DialogCode.Accepted:
                # 「繼續專注」：取消離開，並把剛才暫存的部分秒數滾回避免重複計入
                if partial_added:
                    self._stats.add_focus_seconds(-partial_added)
                if game_added:
                    self._stats.add_entertainment_seconds(-game_added)
                event.ignore()
                self._user_quit = False
                return
        config = AppConfig(**asdict(self._machine.config))
        config.window_x = self.x()
        config.window_y = self.y()
        try:
            self._config_manager.save(config)
        except OSError:
            pass
        super().closeEvent(event)
        self._user_quit = False
        if user_close:
            app = QApplication.instance()
            if app is not None:
                app.quit()
