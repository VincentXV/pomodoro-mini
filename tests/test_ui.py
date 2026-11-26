"""UI 層測試：主題、懸浮膠囊、設定對話框（offscreen 確定性）。"""

from __future__ import annotations

import gc
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from pomodoro.app import build_widget, main
from pomodoro.config import AppConfig, ConfigManager
from pomodoro.core.state_machine import TimerMode, TimerState
from pomodoro.core.stats import DailyStats, StatsManager
from pomodoro.ui.floating_widget import CAPSULE_HEIGHT, TOP_TAB_HEIGHT, WIDGET_HEIGHT, WIDGET_WIDTH
from pomodoro.ui.settings_dialog import SettingsDialog
from pomodoro.ui.style import (
    GAME_ACCENT,
    LONG_BREAK_ACCENT,
    MODE_ACCENT_COLORS,
    SHORT_BREAK_ACCENT,
    WORK_ACCENT,
    accent_color,
    build_stylesheet,
)
from pomodoro.ui.summary_dialog import SummaryDialog, format_focus_duration


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "config.json"


@pytest.fixture
def stats_path(tmp_path: Path) -> Path:
    return tmp_path / "stats.json"


@pytest.fixture
def widget(qapp: QApplication, config_path: Path, stats_path: Path):
    from pomodoro.ui.floating_widget import FloatingWidget

    w = FloatingWidget(
        config_manager=ConfigManager(config_path=config_path),
        stats_manager=StatsManager(stats_path=stats_path),
    )
    w.move(400, 300)  # 離開 (0,0)：避免 show() 時游標在框內觸發 enterEvent
    w.show()
    qapp.processEvents()
    yield w
    w.close()
    w.deleteLater()


# --------------------------------------------------------------------------- #
# style.py
# --------------------------------------------------------------------------- #
def test_three_mode_accent_colors_defined() -> None:
    assert MODE_ACCENT_COLORS["WORK"] == "#FF6B6B"
    assert MODE_ACCENT_COLORS["SHORT_BREAK"] == "#4ECDC4"
    assert MODE_ACCENT_COLORS["LONG_BREAK"] == "#45B7D1"
    assert WORK_ACCENT == "#FF6B6B"
    assert SHORT_BREAK_ACCENT == "#4ECDC4"
    assert LONG_BREAK_ACCENT == "#45B7D1"


def test_game_accent_color_defined() -> None:
    assert GAME_ACCENT == "#A78BFA"
    assert MODE_ACCENT_COLORS["GAME"] == "#A78BFA"
    assert accent_color(TimerMode.GAME) == "#A78BFA"
    assert accent_color("game") == "#A78BFA"


def test_stylesheet_has_mode_tab_button() -> None:
    qss = build_stylesheet()
    assert "QPushButton#modeTabButton" in qss
    assert "QPushButton#modeTabButton:hover" in qss
    assert "QPushButton#modeTabButton:pressed" in qss


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (TimerMode.WORK, "#FF6B6B"),
        (TimerMode.SHORT_BREAK, "#4ECDC4"),
        (TimerMode.LONG_BREAK, "#45B7D1"),
        ("work", "#FF6B6B"),
        ("SHORT_BREAK", "#4ECDC4"),
        (TimerMode.GAME, "#A78BFA"),
        (None, "#FF6B6B"),
        ("unknown", "#FF6B6B"),
    ],
)
def test_accent_color_lookup(mode: object, expected: str) -> None:
    assert accent_color(mode) == expected


def test_stylesheet_embeds_requested_accent() -> None:
    qss = build_stylesheet(TimerMode.LONG_BREAK)
    assert LONG_BREAK_ACCENT in qss
    assert "__ACCENT__" not in qss  # 佔位符必須被替換掉
    assert "QMenu" in qss and "QSlider" in qss  # 深色主題涵蓋選單與滑桿


# --------------------------------------------------------------------------- #
# floating_widget.py
# --------------------------------------------------------------------------- #
def test_widget_is_frameless_capsule(widget) -> None:
    assert widget.width() == WIDGET_WIDTH == 244
    assert widget.height() == WIDGET_HEIGHT == 84
    assert TOP_TAB_HEIGHT == 20
    assert CAPSULE_HEIGHT == 64
    flags = widget.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert widget.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    # Qt 把透明度量化成 8-bit：round(0.95 * 255) / 255
    assert widget.windowOpacity() == pytest.approx(0.95, abs=1 / 255)


def test_mode_tab_button_is_centered_on_top(widget) -> None:
    assert widget._mode_tab_btn.objectName() == "modeTabButton"
    assert widget._mode_tab_btn.text() == "專注"
    assert widget._mode_tab_btn.width() == 76
    assert widget._mode_tab_btn.height() == TOP_TAB_HEIGHT
    assert widget._mode_tab_btn.x() == (WIDGET_WIDTH - 76) // 2
    assert widget._mode_tab_btn.y() == 0
    assert widget._mode_tab_btn.isVisible() is True  # 小方格常駐，不跟控制鍵一起隱藏


def test_mode_tab_click_toggles_game_and_back(widget) -> None:
    assert widget._machine.mode is TimerMode.WORK
    assert widget._cycle_label.text() == "0/4"

    widget._mode_tab_btn.click()
    assert widget._machine.mode is TimerMode.GAME
    assert widget._mode_tab_btn.text() == "遊戲"
    assert widget._cycle_label.text() == "遊戲"
    assert widget._time_label.text() == "30:00"

    widget._mode_tab_btn.click()
    assert widget._machine.mode is TimerMode.WORK
    assert widget._mode_tab_btn.text() == "專注"
    assert widget._cycle_label.text() == "0/4"
    assert widget._time_label.text() == "25:00"


def test_mode_tab_switch_keeps_focus_cycle(widget, qapp: QApplication) -> None:
    """切去遊戲再切回，週期場次與倒數狀態要完整保留。"""
    widget.toggle_start_pause()
    widget._machine.timer.start(0)
    widget._poll()  # WORK 完成 -> 1/4 短休
    assert widget._machine.completed_work_sessions == 1
    widget.toggle_start_pause()  # 開始短休
    timer = widget._machine.timer
    timer._segment_start -= 30.0  # 短休走過 30 秒

    widget._mode_tab_btn.click()
    assert widget._machine.mode is TimerMode.GAME
    assert widget._machine.state is TimerState.IDLE
    assert widget._machine.completed_work_sessions == 1
    assert widget._time_label.text() == "30:00"

    widget._mode_tab_btn.click()
    assert widget._machine.mode is TimerMode.SHORT_BREAK
    assert widget._machine.state is TimerState.PAUSED
    assert widget._machine.completed_work_sessions == 1
    assert widget._cycle_label.text() == "1/4"
    assert widget._machine.remaining_seconds() == 5 * 60 - 30


def test_initial_labels(widget) -> None:
    assert widget._time_label.text() == "25:00"
    assert widget._cycle_label.text() == "0/4"
    assert widget._play_btn.text() == "▶"
    assert widget._skip_btn.text() == "⏭"


def test_toggle_start_pause_updates_state_and_button(widget) -> None:
    widget.toggle_start_pause()
    assert widget._machine.state is TimerState.RUNNING
    assert widget._play_btn.text() == "⏸"

    widget.toggle_start_pause()
    assert widget._machine.state is TimerState.PAUSED
    assert widget._play_btn.text() == "▶"

    widget.toggle_start_pause()
    assert widget._machine.state is TimerState.RUNNING


def test_reset_and_skip_handlers(widget) -> None:
    widget.toggle_start_pause()
    widget.reset_phase()
    assert widget._machine.state is TimerState.IDLE
    assert widget._cycle_label.text() == "0/4"

    # IDLE 狀態直接點快進鍵：0/4 25:00 -> 1/4 05:00
    widget._skip_btn.click()
    assert widget._machine.state is TimerState.COMPLETED
    assert widget._machine.mode is TimerMode.SHORT_BREAK
    assert widget._machine.completed_work_sessions == 1
    assert widget._cycle_label.text() == "1/4"

    # 再點一次快進鍵切回 WORK
    widget._skip_btn.click()
    assert widget._machine.mode is TimerMode.WORK
    assert widget._cycle_label.text() == "1/4"


def test_buttons_hidden_until_hover(widget) -> None:
    assert widget._play_btn.isVisible() is False
    assert widget._skip_btn.isVisible() is False
    widget._set_buttons_visible(True)
    assert widget._play_btn.isVisible() is True
    assert widget._skip_btn.isVisible() is True
    assert widget._settings_btn.isVisible() is True
    assert widget._close_btn.isVisible() is True
    widget._set_buttons_visible(False)
    assert widget._play_btn.isVisible() is False
    assert widget._skip_btn.isVisible() is False


def test_enter_leave_events_toggles_buttons(widget) -> None:
    enter = QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))
    widget.enterEvent(enter)
    assert widget._buttons_visible is True

    leave = QEvent(QEvent.Type.Leave)
    widget.leaveEvent(leave)  # type: ignore[arg-type]
    assert widget._buttons_visible is False


def test_left_drag_moves_window(widget) -> None:
    widget.move(100, 100)

    def makeMouseEvent(
        etype: QEvent.Type, global_x: float, global_y: float, buttons: Qt.MouseButtons
    ) -> QMouseEvent:
        pos = QPointF(global_x, global_y)
        return QMouseEvent(
            etype,
            pos,
            pos,
            pos,
            Qt.MouseButton.LeftButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )

    press = makeMouseEvent(QEvent.Type.MouseButtonPress, 110, 110, Qt.MouseButton.LeftButton)
    widget.mousePressEvent(press)
    assert widget._drag_offset is not None

    move = makeMouseEvent(QEvent.Type.MouseMove, 150, 140, Qt.MouseButton.LeftButton)
    widget.mouseMoveEvent(move)
    assert widget.pos().x() == 140  # 150 - 起按偏移 10
    assert widget.pos().y() == 130  # 140 - 起按偏移 10

    release = makeMouseEvent(
        QEvent.Type.MouseButtonRelease, 150, 140, Qt.MouseButton.NoButton
    )
    widget.mouseReleaseEvent(release)
    assert widget._drag_offset is None


def test_paint_renders_capsule_without_error(widget) -> None:
    pixmap = widget.grab()
    assert not pixmap.isNull()
    assert pixmap.width() == WIDGET_WIDTH
    assert pixmap.height() == WIDGET_HEIGHT


def test_poll_on_finish_plays_sound_and_notifies(widget, monkeypatch) -> None:
    sounds: list[tuple[str, int]] = []
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr(widget._sound, "play", lambda t, v: sounds.append((t, v)))
    monkeypatch.setattr(widget, "_notify", lambda title, msg: notices.append((title, msg)))

    widget.toggle_start_pause()
    widget._machine.timer.start(0)  # 直接把倒數設為已完成
    widget._poll()

    assert len(sounds) == 1
    assert sounds[0][0] == "chime"  # 預設音軌
    assert len(notices) == 1
    assert widget._machine.mode is TimerMode.SHORT_BREAK
    assert widget._machine.state is TimerState.COMPLETED


def test_notify_is_nonblocking_and_safe(widget) -> None:
    # notify-send 存在與否都不准拋例外；呼叫後立刻返回（Popen 非阻塞）
    widget._notify("測試", "訊息")


def test_apply_config_persists_and_updates_look(widget, config_path: Path) -> None:
    new_config = AppConfig(
        work_minutes=10,
        window_opacity=60,
        always_on_top=False,
        sound_enabled=False,
    )
    widget.apply_config(new_config)

    assert config_path.exists()
    reloaded = ConfigManager(config_path=config_path).load()
    assert reloaded.work_minutes == 10
    assert reloaded.window_opacity == 60
    assert widget._machine.config.work_minutes == 10
    assert widget._machine.remaining_seconds() == 10 * 60
    assert widget.windowOpacity() == pytest.approx(0.60)


def test_build_widget_and_main(qapp: QApplication, monkeypatch) -> None:
    w = build_widget()
    assert w is not None
    w.close()
    w.deleteLater()

    # 讓事件迴圈跑一圈就退出，驗證 main() 回傳 0
    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, qapp.quit)
    assert main() == 0


# --------------------------------------------------------------------------- #
# settings_dialog.py
# --------------------------------------------------------------------------- #
def test_settings_dialog_defaults(qapp: QApplication) -> None:
    dialog = SettingsDialog()
    assert dialog._work_spin.value() == 25
    assert dialog._short_spin.value() == 5
    assert dialog._long_spin.value() == 15
    assert dialog._interval_spin.value() == 4
    assert dialog._notify_check.isChecked() is True
    assert dialog._sound_check.isChecked() is True
    assert dialog._volume_slider.value() == 70
    assert dialog._opacity_slider.value() == 95
    assert dialog._top_check.isChecked() is True
    assert dialog._track_combo.currentData() == "chime"
    assert dialog._volume_slider.minimum() == 0
    assert dialog._volume_slider.maximum() == 100
    assert dialog._opacity_slider.minimum() == 50
    assert dialog._opacity_slider.maximum() == 100


def test_settings_dialog_edits_produce_new_config(qapp: QApplication) -> None:
    dialog = SettingsDialog(AppConfig(work_minutes=30))
    assert dialog._work_spin.value() == 30

    dialog._work_spin.setValue(45)
    dialog._short_spin.setValue(8)
    dialog._long_spin.setValue(20)
    dialog._interval_spin.setValue(3)
    dialog._notify_check.setChecked(False)
    dialog._sound_check.setChecked(False)
    dialog._track_combo.setCurrentIndex(dialog._track_combo.findData("bell"))
    dialog._volume_slider.setValue(88)
    dialog._opacity_slider.setValue(77)
    dialog._top_check.setChecked(False)

    cfg = dialog.config()
    assert cfg.work_minutes == 45
    assert cfg.short_break_minutes == 8
    assert cfg.long_break_minutes == 20
    assert cfg.long_break_interval == 3
    assert cfg.notification_enabled is False
    assert cfg.sound_enabled is False
    assert cfg.sound_track == "bell"
    assert cfg.sound_volume == 88
    assert cfg.window_opacity == 77
    assert cfg.always_on_top is False


def test_settings_dialog_reads_and_writes_game_minutes(qapp: QApplication) -> None:
    dialog = SettingsDialog()
    assert dialog._game_spin.value() == 30  # 預設
    assert dialog._game_spin.minimum() == 1
    assert dialog._game_spin.maximum() == 180
    assert dialog.config().game_minutes == 30

    dialog._game_spin.setValue(45)
    assert dialog.config().game_minutes == 45

    again = SettingsDialog(dialog.config())
    assert again._game_spin.value() == 45


def test_settings_does_not_mutate_original_config(qapp: QApplication) -> None:
    original = AppConfig(work_minutes=30)
    SettingsDialog(original)
    assert original.work_minutes == 30


def test_preview_plays_selected_track_and_volume(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = SettingsDialog()
    played: list[tuple[str, int]] = []
    monkeypatch.setattr(
        dialog._sound, "play", lambda track, volume: played.append((track, volume))
    )

    dialog._track_combo.setCurrentIndex(dialog._track_combo.findData("wood"))
    dialog._volume_slider.setValue(42)
    dialog._preview_sound()

    assert played == [("wood", 42)]


def test_preview_button_is_wired(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = SettingsDialog()
    played: list[tuple[str, int]] = []
    monkeypatch.setattr(
        dialog._sound, "play", lambda track, volume: played.append((track, volume))
    )
    dialog._preview_btn.click()
    assert len(played) == 1


def test_settings_dialog_destroy_without_crash(qapp: QApplication) -> None:
    """解構不得崩潰。

    回歸：valueChanged 曾接捕捉 self 的 lambda，視窗刪除時
    信號強引用來回釋放造成 double-free（整個 pytest 會 135 掛掉）。
    """
    dialog = SettingsDialog()
    dialog._volume_slider.setValue(55)
    dialog._opacity_slider.setValue(66)
    dialog.close()
    del dialog
    gc.collect()
    qapp.processEvents()


# --------------------------------------------------------------------------- #
# settings_dialog.py：專注 / 遊戲雙分頁
# --------------------------------------------------------------------------- #
def test_settings_dialog_has_two_tabs(qapp: QApplication) -> None:
    dialog = SettingsDialog()
    assert dialog._tabs.count() == 2
    assert dialog._tabs.tabText(0) == "專注設定"
    assert dialog._tabs.tabText(1) == "遊戲設定"
    assert dialog._tabs.currentIndex() == 0  # 預設 focus 分頁

    game_dialog = SettingsDialog(initial_mode="game")
    assert game_dialog._tabs.count() == 2
    assert game_dialog._tabs.currentIndex() == 1
    assert game_dialog._tabs.tabText(game_dialog._tabs.currentIndex()) == "遊戲設定"


def test_settings_dialog_game_reminder_independent_of_focus(qapp: QApplication) -> None:
    """遊戲分頁的提醒開關 / 音軌 / 音量讀寫不影響專注分頁，反之亦然。"""
    cfg = AppConfig(
        notification_enabled=True,
        sound_enabled=True,
        sound_track="chime",
        sound_volume=70,
        game_notification_enabled=False,
        game_sound_enabled=False,
        game_sound_track="wood",
        game_sound_volume=30,
    )
    dialog = SettingsDialog(cfg, initial_mode="game")

    # 載入：兩組各自獨立
    assert dialog._notify_check.isChecked() is True
    assert dialog._sound_check.isChecked() is True
    assert dialog._track_combo.currentData() == "chime"
    assert dialog._volume_slider.value() == 70
    assert dialog._game_notify_check.isChecked() is False
    assert dialog._game_sound_check.isChecked() is False
    assert dialog._game_track_combo.currentData() == "wood"
    assert dialog._game_volume_slider.value() == 30
    assert dialog._game_volume_label.text() == "30%"

    # 只動遊戲分頁：專注欄位不被波及
    dialog._game_notify_check.setChecked(True)
    dialog._game_sound_check.setChecked(True)
    dialog._game_track_combo.setCurrentIndex(dialog._game_track_combo.findData("bell"))
    dialog._game_volume_slider.setValue(90)
    dialog._game_spin.setValue(45)

    out = dialog.config()
    assert out.game_notification_enabled is True
    assert out.game_sound_enabled is True
    assert out.game_sound_track == "bell"
    assert out.game_sound_volume == 90
    assert out.game_minutes == 45
    assert out.notification_enabled is True
    assert out.sound_enabled is True
    assert out.sound_track == "chime"
    assert out.sound_volume == 70

    # 只動專注分頁：遊戲欄位不被波及
    dialog._notify_check.setChecked(False)
    dialog._track_combo.setCurrentIndex(dialog._track_combo.findData("beep"))
    dialog._volume_slider.setValue(10)
    out2 = dialog.config()
    assert out2.notification_enabled is False
    assert out2.sound_track == "beep"
    assert out2.sound_volume == 10
    assert out2.game_sound_track == "bell"
    assert out2.game_sound_volume == 90
    assert out2.game_minutes == 45


def test_settings_dialog_game_preview_uses_game_track(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = SettingsDialog(initial_mode="game")
    played: list[tuple[str, int]] = []
    monkeypatch.setattr(
        dialog._sound, "play", lambda track, volume: played.append((track, volume))
    )

    dialog._game_track_combo.setCurrentIndex(dialog._game_track_combo.findData("bell"))
    dialog._game_volume_slider.setValue(33)
    dialog._game_preview_btn.click()
    assert played == [("bell", 33)]

    # 專注試聽仍走專注設定
    dialog._preview_btn.click()
    assert played[-1] == ("chime", 70)


def test_settings_dialog_destroy_both_tabs_sliders_without_crash(
    qapp: QApplication,
) -> None:
    """兩個分頁的滑桿都操作過再解構，不得 double-free 崩潰。"""
    dialog = SettingsDialog(initial_mode="game")
    dialog._volume_slider.setValue(55)
    dialog._game_volume_slider.setValue(42)
    dialog._opacity_slider.setValue(66)
    assert dialog._game_volume_label.text() == "42%"
    dialog.close()
    del dialog
    gc.collect()
    qapp.processEvents()


def test_config_normalizes_game_sound_fields() -> None:
    cfg = AppConfig(game_sound_volume=150, game_sound_track="nope")  # type: ignore[arg-type]
    cfg.normalized()
    assert cfg.game_sound_volume == 100
    assert cfg.game_sound_track == "bell"

    low = AppConfig(game_sound_volume=-5).normalized()
    assert low.game_sound_volume == 0
    assert low.game_sound_track == "bell"  # 合法值不受影響


# --------------------------------------------------------------------------- #
# summary_dialog.py
# --------------------------------------------------------------------------- #
def test_format_focus_duration() -> None:
    assert format_focus_duration(4510) == "1 小時 15 分鐘"
    assert format_focus_duration(90) == "1 分鐘 30 秒"
    assert format_focus_duration(45) == "45 秒"
    assert format_focus_duration(0) == "0 秒"
    assert format_focus_duration(-5) == "0 秒"


def test_summary_dialog_shows_stats(qapp: QApplication) -> None:
    dialog = SummaryDialog(DailyStats(date="2026-11-22", sessions=3, focus_seconds=4510))
    assert "2026-11-22" in dialog._date_label.text()
    assert "3" in dialog._sessions_label.text()
    assert "1 小時 15 分鐘" in dialog._duration_label.text()
    assert dialog._leave_btn.text() == "確定離開"
    assert dialog._stay_btn.text() == "繼續專注"
    assert dialog._leave_btn.objectName() == "primaryButton"
    assert dialog.isModal()


def test_summary_dialog_shows_entertainment_duration(qapp: QApplication) -> None:
    dialog = SummaryDialog(
        DailyStats(
            date="2026-11-22",
            sessions=1,
            focus_seconds=60,
            entertainment_seconds=4510,
        )
    )
    assert dialog._entertainment_label.objectName() == "entertainmentDurationLabel"
    assert "今日娛樂總時長" in dialog._entertainment_label.text()
    assert "1 小時 15 分鐘" in dialog._entertainment_label.text()


def test_summary_dialog_leave_accepts(qapp: QApplication) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = SummaryDialog(DailyStats(date="2026-11-22"))
    dialog._leave_btn.click()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_summary_dialog_stay_rejects(qapp: QApplication) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = SummaryDialog(DailyStats(date="2026-11-22"))
    dialog._stay_btn.click()
    assert dialog.result() == QDialog.DialogCode.Rejected


# --------------------------------------------------------------------------- #
# closeEvent：今日總結 + 不卡 modal
# --------------------------------------------------------------------------- #
def test_programmatic_close_skips_summary_dialog(widget, monkeypatch) -> None:
    """fixture 的 w.close() 不准彈 modal，否則 pytest 掛死。"""

    class _Boom:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("程式化 close 不應建立 SummaryDialog")

    monkeypatch.setattr("pomodoro.ui.floating_widget.SummaryDialog", _Boom)
    widget.close()
    assert widget.isVisible() is False


def test_work_completion_records_session(widget) -> None:
    widget.toggle_start_pause()
    widget._machine.timer.start(0)  # 直接把倒數設為已完成
    widget._poll()

    stats = widget._stats.today()
    assert stats.sessions == 1
    assert stats.focus_seconds == 25 * 60


def test_reset_mid_work_accumulates_seconds_only(widget) -> None:
    widget.toggle_start_pause()
    timer = widget._machine.timer
    timer._segment_start -= 5.0  # 人造已走 >= 1 秒
    widget.reset_phase()

    stats = widget._stats.today()
    assert stats.sessions == 0
    assert stats.focus_seconds >= 4  # 至少記到 4~5 秒
    assert widget._machine.state is TimerState.IDLE


def test_skip_mid_work_accumulates_seconds_only(widget) -> None:
    widget.toggle_start_pause()
    timer = widget._machine.timer
    timer._segment_start -= 5.0
    widget.skip_phase()

    stats = widget._stats.today()
    assert stats.sessions == 0  # 中途跳過不加次數
    assert stats.focus_seconds >= 4
    assert widget._machine.mode is TimerMode.SHORT_BREAK


# --------------------------------------------------------------------------- #
# 遊戲模式（GAME）統計整合
# --------------------------------------------------------------------------- #
def test_game_reset_accumulates_entertainment_seconds(widget) -> None:
    widget._mode_tab_btn.click()  # 進 GAME
    widget.toggle_start_pause()
    widget._machine.timer._segment_start -= 5.0
    widget.reset_phase()

    stats = widget._stats.today()
    assert stats.entertainment_seconds >= 4
    assert stats.focus_seconds == 0  # 不污染專注時長
    assert stats.sessions == 0
    assert widget._machine.mode is TimerMode.GAME
    assert widget._machine.state is TimerState.IDLE


def test_game_skip_accumulates_entertainment_seconds(widget) -> None:
    widget._mode_tab_btn.click()
    widget.toggle_start_pause()
    widget._machine.timer._segment_start -= 5.0
    widget.skip_phase()

    stats = widget._stats.today()
    assert stats.entertainment_seconds >= 4
    assert stats.focus_seconds == 0
    assert widget._machine.mode is TimerMode.GAME  # 遊戲跳過不換模式
    assert widget._machine.state is TimerState.IDLE
    assert widget._machine.remaining_seconds() == 30 * 60


def test_game_natural_completion_records_full_entertainment(widget) -> None:
    widget._mode_tab_btn.click()
    widget.toggle_start_pause()
    widget._machine.timer.start(0)  # 直接把倒數設為已完成
    widget._poll()

    stats = widget._stats.today()
    assert stats.entertainment_seconds == 30 * 60  # 整段遊戲秒數
    assert stats.sessions == 0  # 遊戲不進專注場次
    assert stats.focus_seconds == 0
    assert widget._machine.mode is TimerMode.GAME
    assert widget._machine.state is TimerState.IDLE  # 自動歸零待命
    assert widget._machine.remaining_seconds() == 30 * 60


def test_game_completion_notifies_with_game_message(widget, monkeypatch) -> None:
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr(widget, "_notify", lambda title, msg: notices.append((title, msg)))
    widget._mode_tab_btn.click()
    widget.toggle_start_pause()
    widget._machine.timer.start(0)
    widget._poll()

    assert notices == [("遊戲時間到", "起身走動一下，讓眼睛休息吧")]


def test_phase_finished_game_uses_game_sound_settings(widget, monkeypatch) -> None:
    """_on_phase_finished(GAME) 讀遊戲專屬音軌 / 音量，專注仍讀原欄位。"""
    widget.apply_config(
        AppConfig(
            sound_enabled=True,
            sound_track="chime",
            sound_volume=50,
            game_sound_enabled=True,
            game_sound_track="bell",
            game_sound_volume=25,
            game_notification_enabled=True,
        )
    )
    played: list[tuple[str, int]] = []
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr(widget._sound, "play", lambda t, v: played.append((t, v)))
    monkeypatch.setattr(widget, "_notify", lambda title, msg: notices.append((title, msg)))

    widget._on_phase_finished(TimerMode.GAME)
    assert played == [("bell", 25)]
    assert notices == [("遊戲時間到", "起身走動一下，讓眼睛休息吧")]

    widget._on_phase_finished(TimerMode.WORK)
    assert played[-1] == ("chime", 50)  # 專注體系不受遊戲設定影響
    assert notices[-1] == ("專注結束", "這一輪完成了，休息一下吧")


def test_phase_finished_game_respects_game_toggles(widget, monkeypatch) -> None:
    """遊戲提醒關掉就不出聲不通知；專注開關不連坐。"""
    widget.apply_config(
        AppConfig(
            notification_enabled=True,
            sound_enabled=True,
            game_notification_enabled=False,
            game_sound_enabled=False,
        )
    )
    played: list[tuple[str, int]] = []
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr(widget._sound, "play", lambda t, v: played.append((t, v)))
    monkeypatch.setattr(widget, "_notify", lambda title, msg: notices.append((title, msg)))

    widget._on_phase_finished(TimerMode.GAME)
    assert played == []
    assert notices == []

    widget._on_phase_finished(TimerMode.SHORT_BREAK)
    assert len(played) == 1  # 專注體系開關照常生效
    assert len(notices) == 1


def test_open_settings_passes_initial_mode(widget, monkeypatch) -> None:
    """open_settings 依目前模式傳 initial_mode（game / focus）。"""
    captured: list[str] = []

    class _FakeDialog:
        def __init__(self, config=None, parent=None, initial_mode: str = "focus") -> None:
            captured.append(initial_mode)

        def exec(self) -> bool:
            return False

    monkeypatch.setattr("pomodoro.ui.floating_widget.SettingsDialog", _FakeDialog)

    widget.open_settings()
    assert captured[-1] == "focus"

    widget._mode_tab_btn.click()  # 進 GAME
    assert widget._machine.mode is TimerMode.GAME
    widget.open_settings()
    assert captured[-1] == "game"


def test_quit_accepted_keeps_entertainment_seconds(
    widget, qapp: QApplication, monkeypatch
) -> None:
    from PySide6.QtWidgets import QDialog

    widget._mode_tab_btn.click()
    widget.toggle_start_pause()
    widget._machine.timer._segment_start -= 3.0

    class _FakeDialog:
        def __init__(self, stats: DailyStats, parent=None) -> None:
            self._stats = stats

        def exec(self) -> int:
            assert self._stats.entertainment_seconds >= 2
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("pomodoro.ui.floating_widget.SummaryDialog", _FakeDialog)
    widget.quit_app()

    assert widget.isVisible() is False
    assert widget._stats.today().entertainment_seconds >= 2


def test_quit_rejected_rolls_back_entertainment_seconds(
    widget, qapp: QApplication, monkeypatch
) -> None:
    from PySide6.QtWidgets import QDialog

    widget._mode_tab_btn.click()
    widget.toggle_start_pause()
    widget._machine.timer._segment_start -= 3.0

    class _FakeDialog:
        def __init__(self, stats: DailyStats, parent=None) -> None:
            pass

        def exec(self) -> int:
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr("pomodoro.ui.floating_widget.SummaryDialog", _FakeDialog)
    widget.quit_app()

    assert widget.isVisible() is True  # 繼續專注：留在畫面
    assert widget._machine.mode is TimerMode.GAME
    assert widget._stats.today().entertainment_seconds == 0  # 暫存秒數已滾回
    widget._user_quit = False  # 還原，讓 fixture teardown 正常關閉


def test_quit_accepted_shows_summary_saves_and_quits(
    widget, qapp: QApplication, monkeypatch, config_path: Path
) -> None:
    from PySide6.QtWidgets import QDialog

    widget.toggle_start_pause()
    timer = widget._machine.timer
    timer._segment_start -= 3.0

    quits: list[bool] = []
    monkeypatch.setattr(QApplication, "quit", lambda self=None: quits.append(True))

    class _FakeDialog:
        def __init__(self, stats: DailyStats, parent=None) -> None:
            self._stats = stats

        def exec(self) -> int:
            assert self._stats.sessions == 0
            assert self._stats.focus_seconds >= 2  # 部分秒數已先寫入
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("pomodoro.ui.floating_widget.SummaryDialog", _FakeDialog)
    widget.quit_app()

    assert widget.isVisible() is False
    assert config_path.exists()
    assert quits == [True]
    assert widget._stats.today().focus_seconds >= 2  # 確定離開：秒數保留


def test_quit_rejected_stays_open_and_rolls_back(
    widget, qapp: QApplication, monkeypatch
) -> None:
    from PySide6.QtWidgets import QDialog

    widget.toggle_start_pause()
    timer = widget._machine.timer
    timer._segment_start -= 3.0

    class _FakeDialog:
        def __init__(self, stats: DailyStats, parent=None) -> None:
            pass

        def exec(self) -> int:
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr("pomodoro.ui.floating_widget.SummaryDialog", _FakeDialog)
    widget.quit_app()

    assert widget.isVisible() is True  # 繼續專注：留在畫面
    assert widget._machine.state is TimerState.RUNNING
    assert widget._stats.today().focus_seconds == 0  # 部分秒數已滾回
    widget._user_quit = False  # 還原，讓 fixture teardown 正常關閉
