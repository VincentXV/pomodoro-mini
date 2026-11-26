"""Configuration management for Pomodoro desktop timer."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

SoundTrack = Literal["chime", "beep", "wood", "bell"]

SOUND_TRACK_LABELS: dict[SoundTrack, str] = {
    "chime": "清脆風鈴 (Chime)",
    "beep": "數位蜂鳴 (Digital Beep)",
    "wood": "沉靜木魚 (Wood Block)",
    "bell": "柔和鈴鐺 (Soft Bell)",
}


@dataclass
class AppConfig:
    """Application settings persisted as JSON."""

    work_minutes: int = 25
    short_break_minutes: int = 5
    long_break_minutes: int = 15
    long_break_interval: int = 4
    game_minutes: int = 30  # 遊戲模式（GAME）倒數時長

    notification_enabled: bool = True
    sound_enabled: bool = True
    sound_track: SoundTrack = "chime"
    sound_volume: int = 70  # 0 to 100

    # 遊戲模式（GAME）專屬提醒，與專注體系各自獨立
    game_notification_enabled: bool = True
    game_sound_enabled: bool = True
    game_sound_track: SoundTrack = "bell"
    game_sound_volume: int = 70  # 0 to 100

    always_on_top: bool = True
    window_opacity: int = 95  # 50 to 100
    window_x: int | None = None
    window_y: int | None = None

    def normalized(self) -> AppConfig:
        """Clamp numeric fields to safe ranges."""
        self.work_minutes = max(1, min(120, int(self.work_minutes)))
        self.short_break_minutes = max(1, min(60, int(self.short_break_minutes)))
        self.long_break_minutes = max(1, min(90, int(self.long_break_minutes)))
        self.long_break_interval = max(1, min(12, int(self.long_break_interval)))
        self.game_minutes = max(1, min(120, int(self.game_minutes)))
        self.sound_volume = max(0, min(100, int(self.sound_volume)))
        self.game_sound_volume = max(0, min(100, int(self.game_sound_volume)))
        self.window_opacity = max(50, min(100, int(self.window_opacity)))
        if self.sound_track not in SOUND_TRACK_LABELS:
            self.sound_track = "chime"
        if self.game_sound_track not in SOUND_TRACK_LABELS:
            self.game_sound_track = "bell"
        return self


class ConfigManager:
    """Load and save AppConfig to a JSON file."""

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is None:
            config_dir = Path.home() / ".config" / "pomodoro-mini"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = config_dir / "config.json"
        else:
            self.config_path = config_path

    def load(self) -> AppConfig:
        """Load config from disk, returning defaults if missing or invalid."""
        if not self.config_path.exists():
            return AppConfig().normalized()
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return AppConfig().normalized()
            valid_fields = {k: v for k, v in raw.items() if k in AppConfig.__dataclass_fields__}
            return AppConfig(**valid_fields).normalized()
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return AppConfig().normalized()

    def save(self, config: AppConfig) -> None:
        """Save config to disk."""
        config.normalized()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
