"""每日專注統計測試（純 Python，無 Qt）。"""

from __future__ import annotations

import json
from pathlib import Path

from pomodoro.core.stats import DailyStats, StatsManager


def test_daily_stats_defaults() -> None:
    stats = DailyStats()
    assert stats.date == ""
    assert stats.sessions == 0
    assert stats.focus_seconds == 0
    assert stats.entertainment_seconds == 0


def test_default_stats_path_under_home_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    manager = StatsManager()
    assert manager.stats_path == tmp_path / ".config" / "pomodoro-mini" / "stats.json"


def test_load_missing_file_returns_today(tmp_path: Path) -> None:
    manager = StatsManager(stats_path=tmp_path / "stats.json")
    stats = manager.load()
    from datetime import date

    assert stats.date == date.today().isoformat()
    assert stats.sessions == 0
    assert stats.focus_seconds == 0


def test_load_invalid_json_returns_today(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    path.write_text("{not json", encoding="utf-8")
    stats = StatsManager(stats_path=path).load()
    from datetime import date

    assert stats.date == date.today().isoformat()
    assert stats.sessions == 0


def test_load_non_dict_returns_today(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    stats = StatsManager(stats_path=path).load()
    from datetime import date

    assert stats.date == date.today().isoformat()


def test_rollover_resets_when_date_is_not_today(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    path.write_text(
        json.dumps({"date": "2000-01-01", "sessions": 9, "focus_seconds": 9999}),
        encoding="utf-8",
    )
    stats = StatsManager(stats_path=path).load()
    from datetime import date

    assert stats.date == date.today().isoformat()
    assert stats.sessions == 0
    assert stats.focus_seconds == 0


def test_record_session_increments_both_fields(tmp_path: Path) -> None:
    manager = StatsManager(stats_path=tmp_path / "stats.json")
    manager.record_session(1500)
    manager.record_session(1500)
    stats = manager.today()
    assert stats.sessions == 2
    assert stats.focus_seconds == 3000


def test_add_focus_seconds_without_session(tmp_path: Path) -> None:
    manager = StatsManager(stats_path=tmp_path / "stats.json")
    manager.add_focus_seconds(42)
    manager.add_focus_seconds(-10)  # 滾回也走同一入口
    stats = manager.today()
    assert stats.sessions == 0
    assert stats.focus_seconds == 32


def test_add_focus_seconds_clamped_at_zero(tmp_path: Path) -> None:
    manager = StatsManager(stats_path=tmp_path / "stats.json")
    manager.add_focus_seconds(-100)
    assert manager.today().focus_seconds == 0


def test_record_session_and_add_persist_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    StatsManager(stats_path=path).record_session(60)
    reloaded = StatsManager(stats_path=path).today()
    assert reloaded.sessions == 1
    assert reloaded.focus_seconds == 60


def test_negative_values_in_file_clamped_on_load(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    from datetime import date

    path.write_text(
        json.dumps(
            {"date": date.today().isoformat(), "sessions": -3, "focus_seconds": -7}
        ),
        encoding="utf-8",
    )
    stats = StatsManager(stats_path=path).load()
    assert stats.sessions == 0
    assert stats.focus_seconds == 0


def test_save_fills_missing_date(tmp_path: Path) -> None:
    manager = StatsManager(stats_path=tmp_path / "stats.json")
    manager.save(DailyStats(sessions=1, focus_seconds=30))
    from datetime import date

    assert manager.load().date == date.today().isoformat()


# --------------------------------------------------------------------------- #
# 娛樂時長（遊戲模式）
# --------------------------------------------------------------------------- #
def test_add_entertainment_seconds_accumulates(tmp_path: Path) -> None:
    manager = StatsManager(stats_path=tmp_path / "stats.json")
    manager.add_entertainment_seconds(60)
    manager.add_entertainment_seconds(30)
    stats = manager.today()
    assert stats.entertainment_seconds == 90
    assert stats.sessions == 0  # 娛樂秒數不下場次
    assert stats.focus_seconds == 0  # 不污染專注時長


def test_add_entertainment_seconds_rolls_back_with_negative(tmp_path: Path) -> None:
    manager = StatsManager(stats_path=tmp_path / "stats.json")
    manager.add_entertainment_seconds(60)
    manager.add_entertainment_seconds(-25)  # 「繼續專注」的滾回走同一入口
    assert manager.today().entertainment_seconds == 35


def test_add_entertainment_seconds_clamped_at_zero(tmp_path: Path) -> None:
    manager = StatsManager(stats_path=tmp_path / "stats.json")
    manager.add_entertainment_seconds(-100)
    assert manager.today().entertainment_seconds == 0


def test_entertainment_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    StatsManager(stats_path=path).add_entertainment_seconds(120)
    assert StatsManager(stats_path=path).today().entertainment_seconds == 120


def test_load_without_entertainment_field_defaults_zero(tmp_path: Path) -> None:
    from datetime import date

    path = tmp_path / "stats.json"
    path.write_text(
        json.dumps(
            {"date": date.today().isoformat(), "sessions": 1, "focus_seconds": 60}
        ),
        encoding="utf-8",
    )
    stats = StatsManager(stats_path=path).load()
    assert stats.focus_seconds == 60
    assert stats.entertainment_seconds == 0


def test_negative_entertainment_in_file_clamped_on_load(tmp_path: Path) -> None:
    from datetime import date

    path = tmp_path / "stats.json"
    path.write_text(
        json.dumps(
            {
                "date": date.today().isoformat(),
                "sessions": 1,
                "focus_seconds": 60,
                "entertainment_seconds": -9,
            }
        ),
        encoding="utf-8",
    )
    assert StatsManager(stats_path=path).load().entertainment_seconds == 0


def test_rollover_resets_entertainment_too(tmp_path: Path) -> None:
    from datetime import date

    path = tmp_path / "stats.json"
    path.write_text(
        json.dumps(
            {
                "date": "2000-01-01",
                "sessions": 9,
                "focus_seconds": 9999,
                "entertainment_seconds": 8888,
            }
        ),
        encoding="utf-8",
    )
    stats = StatsManager(stats_path=path).load()
    assert stats.date == date.today().isoformat()
    assert stats.entertainment_seconds == 0
