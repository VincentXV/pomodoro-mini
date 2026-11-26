"""深色質感 QSS 主題與三種模式的強調色。"""

from __future__ import annotations

__all__ = [
    "GAME_ACCENT",
    "LONG_BREAK_ACCENT",
    "MODE_ACCENT_COLORS",
    "SHORT_BREAK_ACCENT",
    "WORK_ACCENT",
    "accent_color",
    "build_stylesheet",
]

# 三種模式的強調色（茱蒂規格指定）＋遊戲模式
WORK_ACCENT = "#FF6B6B"
SHORT_BREAK_ACCENT = "#4ECDC4"
LONG_BREAK_ACCENT = "#45B7D1"
GAME_ACCENT = "#A78BFA"

MODE_ACCENT_COLORS: dict[str, str] = {
    "WORK": WORK_ACCENT,
    "SHORT_BREAK": SHORT_BREAK_ACCENT,
    "LONG_BREAK": LONG_BREAK_ACCENT,
    "GAME": GAME_ACCENT,
}

_DEFAULT_ACCENT = WORK_ACCENT
_ACCENT_PLACEHOLDER = "__ACCENT__"

# 深色質感主題；__ACCENT__ 會被替換成目前模式的強調色。
_DARK_QSS = f"""
/* ---- 膠囊內的靜態文字 ---- */
QLabel {{
    background: transparent;
    color: #E8E8F0;
}}
QLabel#timeLabel {{
    color: #FFFFFF;
    font-size: 20px;
    font-weight: 700;
}}
QLabel#cycleLabel {{
    color: #9A9AB4;
    font-size: 10px;
}}
QLabel#dotLabel {{
    background: transparent;
}}

/* ---- 控制按鈕：平時低調，懸停清晰 ---- */
QToolButton {{
    background: transparent;
    color: #B8B8CC;
    border: none;
    border-radius: 12px;
    font-size: 13px;
    padding: 4px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
}}
QToolButton:hover {{
    background: #3A3A55;
    color: {_ACCENT_PLACEHOLDER};
}}
QToolButton:pressed {{
    background: #4A4A6A;
}}

/* ---- 右鍵選單 ---- */
QMenu {{
    background: #26263A;
    color: #E8E8F0;
    border: 1px solid #3C3C58;
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 24px 6px 14px;
    border-radius: 6px;
    background: transparent;
}}
QMenu::item:selected {{
    background: {_ACCENT_PLACEHOLDER};
    color: #14141F;
}}
QMenu::separator {{
    height: 1px;
    background: #3C3C58;
    margin: 4px 8px;
}}

/* ---- 設定對話框 ---- */
QDialog, SettingsDialog {{
    background: #1B1B2A;
    color: #E8E8F0;
    font-size: 13px;
}}
QGroupBox {{
    color: #C8C8DE;
    border: 1px solid #34344E;
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {_ACCENT_PLACEHOLDER};
}}

/* ---- 設定對話框分頁籤 ---- */
QTabWidget::pane {{
    background: #1B1B2A;
    border: 1px solid #34344E;
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background: #26263A;
    color: #C8C8DE;
    border: 1px solid #34344E;
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 6px 18px;
    margin-right: 4px;
    min-width: 72px;
}}
QTabBar::tab:selected {{
    background: #1B1B2A;
    color: {_ACCENT_PLACEHOLDER};
    border: 1px solid {_ACCENT_PLACEHOLDER};
    border-bottom: 2px solid {_ACCENT_PLACEHOLDER};
}}
QTabBar::tab:hover:!selected {{
    background: #34344E;
    color: {_ACCENT_PLACEHOLDER};
}}
QTabBar::tab:focus {{
    outline: none;
}}

QSpinBox, QComboBox {{
    background: #26263A;
    color: #E8E8F0;
    border: 1px solid #3C3C58;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
}}
QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {_ACCENT_PLACEHOLDER};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
}}
QPushButton#spinStepButton {{
    background: #34344E;
    color: #FFFFFF;
    border: 1px solid #4A4A6A;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 700;
    min-width: 26px;
    max-width: 26px;
    min-height: 24px;
    max-height: 24px;
    padding: 0px;
}}
QPushButton#spinStepButton:hover {{
    background: #48486B;
    border-color: {_ACCENT_PLACEHOLDER};
}}
QPushButton#spinStepButton:pressed {{
    background: {_ACCENT_PLACEHOLDER};
    color: #14141F;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: #26263A;
    color: #E8E8F0;
    selection-background-color: {_ACCENT_PLACEHOLDER};
    selection-color: #14141F;
    border: 1px solid #3C3C58;
    outline: none;
}}
QCheckBox {{
    color: #E8E8F0;
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid #4A4A68;
    background: #26263A;
}}
QCheckBox::indicator:checked {{
    background: {_ACCENT_PLACEHOLDER};
    border: 1px solid {_ACCENT_PLACEHOLDER};
}}
QSlider::groove:horizontal {{
    height: 5px;
    border-radius: 3px;
    background: #34344E;
}}
QSlider::sub-page:horizontal {{
    background: {_ACCENT_PLACEHOLDER};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #F0F0F8;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {_ACCENT_PLACEHOLDER};
}}
QPushButton {{
    background: #2E2E46;
    color: #E8E8F0;
    border: 1px solid #44446A;
    border-radius: 8px;
    padding: 7px 18px;
    min-height: 22px;
}}
QPushButton:hover {{
    border: 1px solid {_ACCENT_PLACEHOLDER};
    color: {_ACCENT_PLACEHOLDER};
}}
QPushButton:pressed {{
    background: #3A3A55;
}}
QPushButton#primaryButton {{
    background: {_ACCENT_PLACEHOLDER};
    color: #14141F;
    border: none;
    font-weight: 700;
}}
QPushButton#primaryButton:hover {{
    color: #14141F;
}}
QPushButton#previewButton {{
    padding: 4px 12px;
    min-height: 20px;
}}
/* ---- 頂部模式切換小方格標籤（專注 / 遊戲） ---- */
/* 注意：QSS 的 min/max-height 是「內容盒」，上下各 1px 邊框要另外算，
   所以 18 + 1 + 1 = 畫面上的 20px。 */
QPushButton#modeTabButton {{
    background: #26263A;
    color: #C8C8DE;
    border: 1px solid #4A4A6A;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    text-align: center;
    padding: 0px 6px;
    min-height: 18px;
    max-height: 18px;
}}
QPushButton#modeTabButton:hover {{
    background: #34344E;
    border: 1px solid {_ACCENT_PLACEHOLDER};
    color: {_ACCENT_PLACEHOLDER};
}}
QPushButton#modeTabButton:pressed {{
    background: {_ACCENT_PLACEHOLDER};
    color: #14141F;
}}
QDialogButtonBox QPushButton {{
    min-width: 76px;
}}
QToolTip {{
    background: #26263A;
    color: #E8E8F0;
    border: 1px solid #3C3C58;
    padding: 4px;
}}
"""


def accent_color(mode: object) -> str:
    """回傳模式對應的強調色；不認識的模式回 WORK 色。

    接受 ``TimerMode``、其 name（``WORK`` / ``SHORT_BREAK``）或值（``work``）。
    """
    if mode is None:
        return _DEFAULT_ACCENT
    key = getattr(mode, "name", None)
    if not isinstance(key, str):
        key = str(mode)
    key = key.strip().upper().replace("-", "_").replace(" ", "_")
    return MODE_ACCENT_COLORS.get(key, _DEFAULT_ACCENT)


def build_stylesheet(mode: object = None, accent: str | None = None) -> str:
    """產生深色主題 QSS；可指定模式或直接指定強調色。"""
    color = accent if accent is not None else accent_color(mode)
    if not isinstance(color, str) or not color.startswith("#"):
        color = _DEFAULT_ACCENT
    return _DARK_QSS.replace(_ACCENT_PLACEHOLDER, color)
