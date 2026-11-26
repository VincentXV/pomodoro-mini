"""PrecisionTimer 單元測試（使用假 clock，完全確定性）。"""

from __future__ import annotations

import math

import pytest

from pomodoro.core.timer import PrecisionTimer


class FakeClock:
    """手動推進的假 monotonic clock。"""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def timer(clock: FakeClock) -> PrecisionTimer:
    return PrecisionTimer(clock=clock)


def test_initial_state(timer: PrecisionTimer) -> None:
    assert timer.is_running is False
    assert timer.is_paused is False
    assert timer.is_finished() is False
    assert timer.remaining_seconds() == pytest.approx(0.0)
    assert timer.progress() == pytest.approx(0.0)


def test_start_sets_duration(timer: PrecisionTimer) -> None:
    timer.start(60.0)
    assert timer.is_running is True
    assert timer.is_paused is False
    assert timer.is_finished() is False
    assert timer.remaining_seconds() == pytest.approx(60.0)
    assert timer.progress() == pytest.approx(0.0)


def test_remaining_counts_down(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(60.0)
    clock.advance(10.0)
    assert timer.remaining_seconds() == pytest.approx(50.0)
    assert timer.progress() == pytest.approx(10.0 / 60.0)


def test_pause_freezes_time(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(60.0)
    clock.advance(10.0)
    timer.pause()
    assert timer.is_paused is True
    assert timer.is_running is False
    assert timer.remaining_seconds() == pytest.approx(50.0)

    clock.advance(100.0)  # 暫停期間時間不走
    assert timer.remaining_seconds() == pytest.approx(50.0)
    assert timer.is_finished() is False


def test_resume_continues_countdown(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(60.0)
    clock.advance(10.0)
    timer.pause()
    clock.advance(30.0)
    timer.resume()
    assert timer.is_running is True
    assert timer.is_paused is False
    clock.advance(5.0)
    assert timer.remaining_seconds() == pytest.approx(45.0)


def test_finish_state(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(60.0)
    clock.advance(60.0)
    assert timer.is_finished() is True
    assert timer.is_running is False
    assert timer.is_paused is False
    assert timer.remaining_seconds() == pytest.approx(0.0)
    assert timer.progress() == pytest.approx(1.0)


def test_pause_after_finish_is_noop(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(60.0)
    clock.advance(60.0)
    timer.pause()
    assert timer.is_paused is False
    assert timer.remaining_seconds() == pytest.approx(0.0)


def test_resume_after_finish_is_noop(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(60.0)
    clock.advance(60.0)
    timer.resume()
    assert timer.is_paused is False
    assert timer.is_running is False
    assert timer.is_finished() is True


def test_progress_clamps_at_one(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(60.0)
    clock.advance(120.0)
    assert timer.progress() == pytest.approx(1.0)
    assert timer.remaining_seconds() == pytest.approx(0.0)


def test_reset_restores_full_duration(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(60.0)
    clock.advance(25.0)
    timer.reset()
    assert timer.is_running is False
    assert timer.is_paused is False
    assert timer.is_finished() is False
    assert timer.remaining_seconds() == pytest.approx(60.0)
    assert timer.progress() == pytest.approx(0.0)


def test_reset_with_new_duration(timer: PrecisionTimer) -> None:
    timer.start(60.0)
    timer.reset(30.0)
    assert timer.remaining_seconds() == pytest.approx(30.0)


def test_reset_while_paused(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(60.0)
    clock.advance(10.0)
    timer.pause()
    timer.reset()
    assert timer.is_paused is False
    assert timer.remaining_seconds() == pytest.approx(60.0)
    clock.advance(5.0)
    assert timer.remaining_seconds() == pytest.approx(60.0)  # 未 start 不倒數


def test_remaining_before_start_shows_full_duration(timer: PrecisionTimer) -> None:
    timer.reset(45.0)
    assert timer.is_finished() is False
    assert timer.remaining_seconds() == pytest.approx(45.0)
    assert timer.progress() == pytest.approx(0.0)


def test_negative_duration_raises(timer: PrecisionTimer) -> None:
    with pytest.raises(ValueError):
        timer.start(-1.0)
    with pytest.raises(ValueError):
        timer.reset(-0.5)


def test_non_finite_duration_raises(timer: PrecisionTimer) -> None:
    """NaN / inf 不能當時長，否則 remaining / progress 會變 NaN 汙染畫面。"""
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            timer.start(bad)
        with pytest.raises(ValueError):
            timer.reset(bad)
    with pytest.raises(ValueError):
        PrecisionTimer(duration_seconds=float("nan"))
    with pytest.raises(ValueError):
        PrecisionTimer(duration_seconds=float("inf"))
    # 拒絕後狀態不受影響
    timer.start(60.0)
    with pytest.raises(ValueError):
        timer.start(float("nan"))
    assert timer.remaining_seconds() == pytest.approx(60.0)


def test_duration_nan_does_not_leak_into_progress(timer: PrecisionTimer) -> None:
    timer.reset(60.0)
    timer.start(60.0)
    assert math.isfinite(timer.remaining_seconds())
    assert math.isfinite(timer.progress())


def test_clock_rollback_keeps_elapsed_non_negative(timer: PrecisionTimer, clock: FakeClock) -> None:
    """clock 倒退時 elapsed 不得變負、remaining 不得超過原時長。"""
    clock.now = 10.0
    timer.start(60.0)  # segment_start = 10
    clock.now = 20.0
    assert timer.remaining_seconds() == pytest.approx(50.0)

    clock.now = 5.0  # 時鐘倒退
    assert timer.remaining_seconds() == pytest.approx(50.0)  # 不會變 65
    assert timer.progress() == pytest.approx(10.0 / 60.0)
    assert timer.is_finished() is False


def test_clock_rollback_before_start_keeps_remaining_clamped(timer: PrecisionTimer, clock: FakeClock) -> None:
    clock.now = 10.0
    timer.start(60.0)  # segment_start = 10
    clock.now = 5.0  # 倒退到 segment_start 之前
    assert timer.remaining_seconds() == pytest.approx(60.0)  # 增量夾緊為 0
    assert timer.progress() == pytest.approx(0.0)


def test_pause_during_clock_rollback_never_goes_negative(timer: PrecisionTimer, clock: FakeClock) -> None:
    clock.now = 10.0
    timer.start(60.0)  # segment_start = 10
    clock.now = 5.0  # 時鐘倒退後暫停：增量夾緊為 0
    timer.pause()
    assert timer.is_paused is True
    assert timer.remaining_seconds() == pytest.approx(60.0)  # 不會 > 60
    clock.now = 4.0  # 暫停期間再倒退也不影響（時間凍結）
    assert timer.remaining_seconds() == pytest.approx(60.0)
    timer.resume()  # segment_start = 4
    assert timer.is_running is True
    clock.now = 14.0  # 從原點前進 10 秒
    assert timer.remaining_seconds() == pytest.approx(50.0)
    assert math.isfinite(timer.progress())


def test_single_clock_read_per_operation(timer: PrecisionTimer, clock: FakeClock) -> None:
    """pause / resume 內部不得重複讀 clock（避免兩次讀取之間時間跳動）。"""
    timer.start(60.0)
    clock.advance(10.0)

    calls = {"n": 0}

    def counting_clock() -> float:
        calls["n"] += 1
        return clock.now

    timer._clock = counting_clock  # type: ignore[method-assign]

    calls["n"] = 0
    timer.pause()
    assert calls["n"] == 1, f"pause 讀了 {calls['n']} 次 clock"

    calls["n"] = 0
    timer.resume()
    assert calls["n"] == 1, f"resume 讀了 {calls['n']} 次 clock"

    calls["n"] = 0
    timer.remaining_seconds()
    assert calls["n"] == 1, f"remaining_seconds 讀了 {calls['n']} 次 clock"


def test_zero_duration_is_finished_immediately(timer: PrecisionTimer) -> None:
    timer.start(0.0)
    assert timer.is_finished() is True
    assert timer.is_running is False
    assert timer.remaining_seconds() == pytest.approx(0.0)
    assert timer.progress() == pytest.approx(1.0)


def test_restart_after_finish(timer: PrecisionTimer, clock: FakeClock) -> None:
    timer.start(10.0)
    clock.advance(10.0)
    assert timer.is_finished() is True
    timer.start(20.0)
    assert timer.is_finished() is False
    assert timer.is_running is True
    assert timer.remaining_seconds() == pytest.approx(20.0)
