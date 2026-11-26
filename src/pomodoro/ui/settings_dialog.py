"""偏好設定對話框：專注 / 遊戲雙分頁的時長、提醒與共用外觀。"""

from __future__ import annotations

from dataclasses import asdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pomodoro.config import SOUND_TRACK_LABELS, AppConfig, SoundTrack
from pomodoro.core.sound import SoundManager
from pomodoro.ui.style import build_stylesheet

__all__ = ["SettingsDialog"]


class SettingsDialog(QDialog):
    """番茄鐘偏好設定；``config()`` 取得編輯後的設定。

    分頁 0「專注設定」＝番茄鐘時長＋專注提醒；分頁 1「遊戲設定」＝
    遊戲時長＋遊戲提醒；下方「外觀」與 Ok / Cancel 為兩頁共用。
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        parent: QWidget | None = None,
        initial_mode: str = "focus",
    ) -> None:
        super().__init__(parent)
        raw = config if config is not None else AppConfig()
        self._config = AppConfig(**asdict(raw)).normalized()
        self._sound = SoundManager()

        self.setWindowTitle("偏好設定")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setStyleSheet(build_stylesheet())

        self._build_ui(initial_mode)
        self._load_values()

    # ------------------------------------------------------------------ #
    # UI 組裝
    # ------------------------------------------------------------------ #
    def _build_ui(self, initial_mode: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_focus_page(), "專注設定")
        self._tabs.addTab(self._build_game_page(), "遊戲設定")
        self._tabs.setCurrentIndex(1 if initial_mode == "game" else 0)
        root.addWidget(self._tabs)

        # ---- 外觀（兩頁共用） ----
        look_box = QGroupBox("外觀")
        look_form = QFormLayout(look_box)
        look_form.setSpacing(8)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(50, 100)
        self._opacity_label = QLabel("95%")
        self._opacity_label.setMinimumWidth(44)
        self._opacity_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self._opacity_slider, 1)
        opacity_row.addWidget(self._opacity_label)
        look_form.addRow("視窗透明度", opacity_row)

        self._top_check = QCheckBox("視窗始終置頂")
        look_form.addRow(self._top_check)
        root.addWidget(look_box)

        # ---- 按鈕 ----
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # 即時同步數值標籤
        # （一律用 bound method 而非捕捉 self 的 lambda：lambda 會讓訊號
        #  強引用 self，視窗解構時觸發 double-free 崩潰）
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        self._game_volume_slider.valueChanged.connect(self._on_game_volume_changed)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)

    def _build_focus_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        # ---- 階段時長 ----
        timing_box = QGroupBox("階段時長")
        timing_form = QFormLayout(timing_box)
        timing_form.setSpacing(8)

        self._work_spin, work_row = self._make_spin_row(1, 120, "分鐘")
        self._short_spin, short_row = self._make_spin_row(1, 60, "分鐘")
        self._long_spin, long_row = self._make_spin_row(1, 90, "分鐘")
        self._interval_spin, interval_row = self._make_spin_row(1, 12, "次")
        timing_form.addRow("專注（WORK）", work_row)
        timing_form.addRow("短休（SHORT BREAK）", short_row)
        timing_form.addRow("長休（LONG BREAK）", long_row)
        timing_form.addRow("長休週期（幾次工作後）", interval_row)
        layout.addWidget(timing_box)

        # ---- 通知與音效 ----
        notify_box = QGroupBox("通知與音效")
        notify_form = QFormLayout(notify_box)
        notify_form.setSpacing(8)

        self._notify_check = QCheckBox("系統通知（notify-send）")
        self._sound_check = QCheckBox("階段結束播放音效")
        notify_form.addRow(self._notify_check)
        notify_form.addRow(self._sound_check)

        self._track_combo = QComboBox()
        for track, label in SOUND_TRACK_LABELS.items():
            self._track_combo.addItem(label, track)
        notify_form.addRow("音軌", self._track_combo)

        volume_row = QHBoxLayout()
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_label = QLabel("70%")
        self._volume_label.setMinimumWidth(44)
        self._volume_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._preview_btn = QPushButton("試聽")
        self._preview_btn.setObjectName("previewButton")
        self._preview_btn.clicked.connect(self._preview_sound)
        volume_row.addWidget(self._volume_slider, 1)
        volume_row.addWidget(self._volume_label)
        volume_row.addWidget(self._preview_btn)
        notify_form.addRow("音量", volume_row)
        layout.addWidget(notify_box)

        layout.addStretch(1)
        return page

    def _build_game_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        # ---- 遊戲時長 ----
        game_timing_box = QGroupBox("遊戲時長")
        game_timing_form = QFormLayout(game_timing_box)
        game_timing_form.setSpacing(8)
        self._game_spin, game_row = self._make_spin_row(1, 180, "分鐘")
        game_timing_form.addRow("遊戲提醒（GAME）", game_row)
        layout.addWidget(game_timing_box)

        # ---- 通知與音效（遊戲專屬） ----
        game_notify_box = QGroupBox("通知與音效")
        game_notify_form = QFormLayout(game_notify_box)
        game_notify_form.setSpacing(8)

        self._game_notify_check = QCheckBox("系統通知（notify-send）")
        self._game_sound_check = QCheckBox("階段結束播放音效")
        game_notify_form.addRow(self._game_notify_check)
        game_notify_form.addRow(self._game_sound_check)

        self._game_track_combo = QComboBox()
        for track, label in SOUND_TRACK_LABELS.items():
            self._game_track_combo.addItem(label, track)
        game_notify_form.addRow("音軌", self._game_track_combo)

        game_volume_row = QHBoxLayout()
        self._game_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._game_volume_slider.setRange(0, 100)
        self._game_volume_label = QLabel("70%")
        self._game_volume_label.setMinimumWidth(44)
        self._game_volume_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._game_preview_btn = QPushButton("試聽")
        self._game_preview_btn.setObjectName("previewButton")
        self._game_preview_btn.clicked.connect(self._preview_game_sound)
        game_volume_row.addWidget(self._game_volume_slider, 1)
        game_volume_row.addWidget(self._game_volume_label)
        game_volume_row.addWidget(self._game_preview_btn)
        game_notify_form.addRow("音量", game_volume_row)
        layout.addWidget(game_notify_box)

        layout.addStretch(1)
        return page

    def _on_volume_changed(self, value: int) -> None:
        self._volume_label.setText(f"{value}%")

    def _on_game_volume_changed(self, value: int) -> None:
        self._game_volume_label.setText(f"{value}%")

    def _on_opacity_changed(self, value: int) -> None:
        self._opacity_label.setText(f"{value}%")

    @staticmethod
    def _make_spin_row(low: int, high: int, suffix: str) -> tuple[QSpinBox, QHBoxLayout]:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(f" {suffix}")
        spin.setMinimumWidth(90)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)

        minus_btn = QPushButton("−")
        minus_btn.setObjectName("spinStepButton")
        minus_btn.setToolTip("減少（可長按）")
        minus_btn.setAutoRepeat(True)
        minus_btn.setAutoRepeatDelay(350)
        minus_btn.setAutoRepeatInterval(60)
        minus_btn.clicked.connect(spin.stepDown)

        plus_btn = QPushButton("+")
        plus_btn.setObjectName("spinStepButton")
        plus_btn.setToolTip("增加（可長按）")
        plus_btn.setAutoRepeat(True)
        plus_btn.setAutoRepeatDelay(350)
        plus_btn.setAutoRepeatInterval(60)
        plus_btn.clicked.connect(spin.stepUp)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(minus_btn)
        row.addWidget(spin, 1)
        row.addWidget(plus_btn)
        return spin, row

    # ------------------------------------------------------------------ #
    # 載入 / 取得
    # ------------------------------------------------------------------ #
    def _load_values(self) -> None:
        cfg = self._config
        # 專注設定
        self._work_spin.setValue(cfg.work_minutes)
        self._short_spin.setValue(cfg.short_break_minutes)
        self._long_spin.setValue(cfg.long_break_minutes)
        self._interval_spin.setValue(cfg.long_break_interval)
        self._notify_check.setChecked(cfg.notification_enabled)
        self._sound_check.setChecked(cfg.sound_enabled)
        index = self._track_combo.findData(cfg.sound_track)
        self._track_combo.setCurrentIndex(index if index >= 0 else 0)
        self._volume_slider.setValue(cfg.sound_volume)
        # 遊戲設定
        self._game_spin.setValue(cfg.game_minutes)
        self._game_notify_check.setChecked(cfg.game_notification_enabled)
        self._game_sound_check.setChecked(cfg.game_sound_enabled)
        game_index = self._game_track_combo.findData(cfg.game_sound_track)
        self._game_track_combo.setCurrentIndex(game_index if game_index >= 0 else 0)
        self._game_volume_slider.setValue(cfg.game_sound_volume)
        # 共用外觀
        self._opacity_slider.setValue(cfg.window_opacity)
        self._top_check.setChecked(cfg.always_on_top)

    def config(self) -> AppConfig:
        """依目前 UI 內容回傳（已夾緊的）設定。"""
        track: SoundTrack = self._track_combo.currentData() or "chime"
        game_track: SoundTrack = self._game_track_combo.currentData() or "bell"
        cfg = AppConfig(
            work_minutes=self._work_spin.value(),
            short_break_minutes=self._short_spin.value(),
            long_break_minutes=self._long_spin.value(),
            long_break_interval=self._interval_spin.value(),
            game_minutes=self._game_spin.value(),
            notification_enabled=self._notify_check.isChecked(),
            sound_enabled=self._sound_check.isChecked(),
            sound_track=track,
            sound_volume=self._volume_slider.value(),
            game_notification_enabled=self._game_notify_check.isChecked(),
            game_sound_enabled=self._game_sound_check.isChecked(),
            game_sound_track=game_track,
            game_sound_volume=self._game_volume_slider.value(),
            always_on_top=self._top_check.isChecked(),
            window_opacity=self._opacity_slider.value(),
            window_x=self._config.window_x,
            window_y=self._config.window_y,
        )
        return cfg.normalized()

    # ------------------------------------------------------------------ #
    # 試聽
    # ------------------------------------------------------------------ #
    def _preview_sound(self) -> None:
        """立即播放目前選定的專注音軌與音量（SoundManager 內建安全降級）。"""
        track: SoundTrack = self._track_combo.currentData() or "chime"
        self._sound.play(track, self._volume_slider.value())

    def _preview_game_sound(self) -> None:
        """立即播放目前選定的遊戲音軌與音量。"""
        track: SoundTrack = self._game_track_combo.currentData() or "bell"
        self._sound.play(track, self._game_volume_slider.value())
