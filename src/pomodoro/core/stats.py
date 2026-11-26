"""每日專注統計：JSON 持久化、換日自動歸零。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

__all__ = ["DailyStats", "StatsManager"]


@dataclass
class DailyStats:
    """單日專注紀錄（ISO 日期字串 + 場次數 + 累計秒數）。"""

    date: str = ""
    sessions: int = 0
    focus_seconds: int = 0
    entertainment_seconds: int = 0  # 獨立娛樂時長（遊戲模式）


class StatsManager:
    """讀寫 stats.json；預設路徑與設定檔同目錄（~/.config/pomodoro-mini）。"""

    def __init__(self, stats_path: Path | None = None) -> None:
        if stats_path is None:
            stats_dir = Path.home() / ".config" / "pomodoro-mini"
            stats_dir.mkdir(parents=True, exist_ok=True)
            self.stats_path = stats_dir / "stats.json"
        else:
            self.stats_path = stats_path

    # ------------------------------------------------------------------ #
    # 內部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _today() -> str:
        return date.today().isoformat()

    # ------------------------------------------------------------------ #
    # 讀寫
    # ------------------------------------------------------------------ #
    def load(self) -> DailyStats:
        """載入今日紀錄；缺檔、壞檔或日期不是今天一律回傳今日新紀錄。"""
        today = self._today()
        if not self.stats_path.exists():
            return DailyStats(date=today)
        try:
            raw = json.loads(self.stats_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return DailyStats(date=today)
        if not isinstance(raw, dict):
            return DailyStats(date=today)
        try:
            stats = DailyStats(
                date=str(raw.get("date", "")),
                sessions=int(raw.get("sessions", 0)),
                focus_seconds=int(raw.get("focus_seconds", 0)),
                entertainment_seconds=int(raw.get("entertainment_seconds", 0)),
            )
        except (TypeError, ValueError):
            return DailyStats(date=today)
        if stats.date != today:
            # 換日自動歸零
            return DailyStats(date=today)
        stats.sessions = max(0, stats.sessions)
        stats.focus_seconds = max(0, stats.focus_seconds)
        stats.entertainment_seconds = max(0, stats.entertainment_seconds)
        return stats

    def save(self, stats: DailyStats) -> None:
        """寫回 JSON（自動補上今日日期）。"""
        if not stats.date:
            stats.date = self._today()
        self.stats_path.parent.mkdir(parents=True, exist_ok=True)
        self.stats_path.write_text(
            json.dumps(asdict(stats), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def today(self) -> DailyStats:
        """回傳今日紀錄（換日自動歸零）。"""
        return self.load()

    def record_session(self, focus_seconds: int) -> DailyStats:
        """完成一整輪專注：場次 +1、秒數累加。"""
        stats = self.load()
        stats.sessions += 1
        stats.focus_seconds = max(0, stats.focus_seconds + max(0, int(focus_seconds)))
        self.save(stats)
        return stats

    def add_focus_seconds(self, seconds: int) -> DailyStats:
        """只累加秒數（中途重設／跳過／離開的部分專注），不下場次。"""
        stats = self.load()
        stats.focus_seconds = max(0, stats.focus_seconds + int(seconds))
        self.save(stats)
        return stats

    def add_entertainment_seconds(self, seconds: int) -> DailyStats:
        """累加／回滾今日娛樂時長（正數累加、負數回滾，下限夾緊 0）。"""
        stats = self.load()
        stats.entertainment_seconds = max(0, stats.entertainment_seconds + int(seconds))
        self.save(stats)
        return stats
