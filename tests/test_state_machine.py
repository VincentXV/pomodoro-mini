"""PomodoroStateMachine 單元測試（使用假 clock，完全確定性）。"""

from __future__ import annotations

import re

import pytest

from pomodoro.config import AppConfig
from pomodoro.core.state_machine import PomodoroStateMachine, TimerMode, TimerState


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ScriptClock:
    """可程式化假 clock：可改當下值，也可設定每次呼叫自動前進。

    用來模擬「兩次檢查之間時間剛好跳過」的邊界（茱蒂抓到的分支）。
    """

    def __init__(self, now: float = 0.0, auto_tick: float = 0.0) -> None:
        self.now = now
        self.auto_tick = auto_tick

    def __call__(self) -> float:
        value = self.now
        self.now += self.auto_tick
        return value

    def advance(self, seconds: float) -> None:
        self.now += seconds


WORK_SECONDS = 25 * 60
SHORT_SECONDS = 5 * 60
LONG_SECONDS = 15 * 60
GAME_SECONDS = 30 * 60


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sm(clock: FakeClock) -> PomodoroStateMachine:
    return PomodoroStateMachine(AppConfig(), clock=clock)


def test_initial_state(sm: PomodoroStateMachine) -> None:
    assert sm.mode is TimerMode.WORK
    assert sm.state is TimerState.IDLE
    assert sm.completed_work_sessions == 0
    assert sm.remaining_seconds() == WORK_SECONDS
    assert sm.formatted_time() == "25:00"
    assert sm.progress() == pytest.approx(0.0)
    assert sm.cycle_display() == "0/4"


def test_start_pause_resume(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    assert sm.state is TimerState.RUNNING
    assert sm.timer.is_running is True

    clock.advance(60.0)
    sm.start_or_pause()
    assert sm.state is TimerState.PAUSED
    assert sm.timer.is_paused is True

    clock.advance(60.0)  # 暫停不走
    sm.start_or_pause()
    assert sm.state is TimerState.RUNNING
    clock.advance(60.0)
    assert sm.remaining_seconds() == WORK_SECONDS - 120


def test_tick_before_finish_returns_false(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(WORK_SECONDS - 1)
    assert sm.tick() is False
    assert sm.state is TimerState.RUNNING
    assert sm.mode is TimerMode.WORK


def test_tick_when_idle_returns_false(sm: PomodoroStateMachine) -> None:
    assert sm.tick() is False


def test_complete_work_session(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(WORK_SECONDS)
    assert sm.tick() is True

    assert sm.state is TimerState.COMPLETED
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.completed_work_sessions == 1
    assert sm.remaining_seconds() == SHORT_SECONDS
    assert sm.formatted_time() == "05:00"
    assert sm.progress() == pytest.approx(0.0)
    assert sm.cycle_display() == "1/4"


def test_start_next_phase_from_completed(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(WORK_SECONDS)
    assert sm.tick() is True

    sm.start_or_pause()  # 開始短休息
    assert sm.state is TimerState.RUNNING
    clock.advance(60.0)
    assert sm.remaining_seconds() == SHORT_SECONDS - 60

    clock.advance(SHORT_SECONDS - 60)
    assert sm.tick() is True
    assert sm.mode is TimerMode.WORK
    assert sm.state is TimerState.COMPLETED
    assert sm.completed_work_sessions == 1  # 休息不累計
    assert sm.remaining_seconds() == WORK_SECONDS


def test_long_break_every_interval(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(long_break_interval=4), clock=clock)
    for expected_short in (1, 2, 3):
        sm.start_or_pause()
        clock.advance(WORK_SECONDS)
        assert sm.tick() is True
        assert sm.mode is TimerMode.SHORT_BREAK
        assert sm.completed_work_sessions == expected_short
        sm.start_or_pause()
        clock.advance(SHORT_SECONDS)
        assert sm.tick() is True
        assert sm.mode is TimerMode.WORK

    sm.start_or_pause()
    clock.advance(WORK_SECONDS)
    assert sm.tick() is True
    assert sm.mode is TimerMode.LONG_BREAK
    assert sm.completed_work_sessions == 4
    assert sm.remaining_seconds() == LONG_SECONDS
    assert sm.formatted_time() == "15:00"
    assert sm.cycle_display() == "0/4"


def test_custom_interval(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(long_break_interval=2), clock=clock)
    sm.start_or_pause()
    clock.advance(WORK_SECONDS)
    assert sm.tick() is True
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.cycle_display() == "1/2"

    sm.start_or_pause()
    clock.advance(SHORT_SECONDS)
    assert sm.tick() is True
    sm.start_or_pause()
    clock.advance(WORK_SECONDS)
    assert sm.tick() is True
    assert sm.mode is TimerMode.LONG_BREAK
    assert sm.cycle_display() == "0/2"


def test_progress_midway(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(WORK_SECONDS / 2)
    assert sm.progress() == pytest.approx(0.5)
    assert sm.remaining_seconds() == WORK_SECONDS // 2
    assert sm.formatted_time() == "12:30"


def test_remaining_seconds_is_int(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(0.25)
    value = sm.remaining_seconds()
    assert isinstance(value, int)
    assert value == WORK_SECONDS  # 進位，畫面不提前掉秒


def test_formatted_time_is_mmss(sm: PomodoroStateMachine) -> None:
    assert re.fullmatch(r"\d{2}:\d{2}", sm.formatted_time()) is not None


def test_set_mode(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(30.0)
    sm.set_mode(TimerMode.LONG_BREAK)
    assert sm.mode is TimerMode.LONG_BREAK
    assert sm.state is TimerState.IDLE
    assert sm.remaining_seconds() == LONG_SECONDS
    assert sm.timer.is_running is False

    sm.set_mode("short_break")  # 字串也可
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.remaining_seconds() == SHORT_SECONDS


def test_reset_keeps_session_count(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(WORK_SECONDS)
    assert sm.tick() is True
    sm.start_or_pause()
    clock.advance(60.0)
    sm.reset()
    assert sm.state is TimerState.IDLE
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.remaining_seconds() == SHORT_SECONDS
    assert sm.completed_work_sessions == 1


def test_update_config_while_idle(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(work_minutes=25), clock=clock)
    sm.update_config(AppConfig(work_minutes=10))
    assert sm.remaining_seconds() == 10 * 60
    assert sm.formatted_time() == "10:00"


def test_update_config_while_running_keeps_countdown(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(60.0)
    sm.update_config(AppConfig(work_minutes=10))
    assert sm.state is TimerState.RUNNING
    assert sm.remaining_seconds() == WORK_SECONDS - 60  # 進行中不被打斷
    # 下一個 WORK 階段套用新設定
    clock.advance(WORK_SECONDS - 60)
    assert sm.tick() is True
    sm.start_or_pause()
    clock.advance(SHORT_SECONDS)
    assert sm.tick() is True
    sm.set_mode(TimerMode.WORK)
    assert sm.remaining_seconds() == 10 * 60


def test_skip_while_running(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(60.0)
    sm.skip()
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.state is TimerState.COMPLETED
    assert sm.completed_work_sessions == 1
    assert sm.remaining_seconds() == SHORT_SECONDS


def test_skip_while_paused(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(60.0)
    sm.start_or_pause()  # 暫停
    assert sm.state is TimerState.PAUSED
    sm.skip()
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.completed_work_sessions == 1


def test_skip_break_returns_to_work(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(), clock=clock)
    sm.start_or_pause()
    clock.advance(WORK_SECONDS)
    assert sm.tick() is True
    sm.start_or_pause()
    clock.advance(60.0)
    sm.skip()
    assert sm.mode is TimerMode.WORK
    assert sm.completed_work_sessions == 1  # 跳過休息不加場次
    assert sm.state is TimerState.COMPLETED


def test_skip_idle_is_noop(sm: PomodoroStateMachine) -> None:
    sm.skip()
    assert sm.mode is TimerMode.WORK
    assert sm.state is TimerState.IDLE
    assert sm.completed_work_sessions == 0


def test_start_or_pause_after_finished_timer_completes(sm: PomodoroStateMachine, clock: FakeClock) -> None:
    sm.start_or_pause()
    clock.advance(WORK_SECONDS)
    # 時間到了但還沒 tick，直接按開始/暫停也應完成切階段
    sm.start_or_pause()
    assert sm.state is TimerState.COMPLETED
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.completed_work_sessions == 1


def test_running_branch_rechecks_finished_after_pause() -> None:
    """RUNNING 分支呼叫 pause() 後要重查 is_finished，否則才設 PAUSED。

    用會自動前進的 clock 模擬：第一道檢查沒結束、pause() 當下剛好走完。
    """
    clock = ScriptClock(now=1499.0, auto_tick=0.0)
    sm = PomodoroStateMachine(AppConfig(), clock=clock)
    sm.start_or_pause()  # segment_start = 1499
    assert sm.state is TimerState.RUNNING

    # 下一次呼叫內：第一道 is_finished 看到 1499.5（未完），
    # pause() 內部看到 2999.5（已完）→ pause 變 no-op → 重查補完成流程
    clock.now = 2998.5
    clock.auto_tick = 1.0
    sm.start_or_pause()

    assert sm.state is TimerState.COMPLETED  # 不留在矛盾的 PAUSED
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.completed_work_sessions == 1
    assert sm.timer.is_paused is False


def test_paused_branch_rechecks_finished_after_resume() -> None:
    """PAUSED 分支呼叫 resume() 後若已走完，同樣補完成流程。"""
    clock = ScriptClock(now=0.0, auto_tick=0.0)
    sm = PomodoroStateMachine(AppConfig(), clock=clock)
    sm.start_or_pause()  # segment_start = 0
    clock.now = 1499.5
    sm.start_or_pause()  # 暫停（凍結在 1499.5）
    assert sm.state is TimerState.PAUSED

    # 暫停期間時間大幅跳過：resume 原點之後一步就超過時長
    clock.now = 4999.0
    clock.auto_tick = 1.0
    sm.start_or_pause()

    assert sm.state is TimerState.COMPLETED
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.completed_work_sessions == 1
    assert sm.timer.is_paused is False
    assert sm.timer.is_running is False


# --------------------------------------------------------------------------- #
# 遊戲模式（GAME）：獨立上下文 + 無週期 + 自動歸零待命
# --------------------------------------------------------------------------- #
def test_toggle_game_mode_initializes_idle_game_timer(sm: PomodoroStateMachine) -> None:
    assert sm.mode is TimerMode.WORK
    assert sm.toggle_game_mode() is TimerMode.GAME
    assert sm.mode is TimerMode.GAME
    assert sm.state is TimerState.IDLE
    assert sm.remaining_seconds() == GAME_SECONDS
    assert sm.formatted_time() == "30:00"
    assert sm.cycle_display() == "遊戲"
    assert sm.progress() == pytest.approx(0.0)
    assert sm.completed_work_sessions == 0


def test_toggle_game_mode_preserves_focus_cycle(clock: FakeClock) -> None:
    """切去遊戲再切回：週期場次、模式與倒數狀態都要完整保留。"""
    sm = PomodoroStateMachine(AppConfig(), clock=clock)
    sm.start_or_pause()
    clock.advance(WORK_SECONDS)
    assert sm.tick() is True  # -> 1/4 短休
    sm.start_or_pause()
    clock.advance(30.0)

    sm.toggle_game_mode()
    assert sm.mode is TimerMode.GAME
    assert sm.state is TimerState.IDLE
    assert sm.remaining_seconds() == GAME_SECONDS
    assert sm.completed_work_sessions == 1
    assert sm.cycle_display() == "遊戲"

    sm.toggle_game_mode()
    assert sm.mode is TimerMode.SHORT_BREAK
    assert sm.state is TimerState.PAUSED  # 原本 RUNNING 已先 pause
    assert sm.completed_work_sessions == 1
    assert sm.cycle_display() == "1/4"
    assert sm.remaining_seconds() == SHORT_SECONDS - 30
    assert sm.timer.is_paused is True

    sm.start_or_pause()  # 續跑短休
    assert sm.state is TimerState.RUNNING
    clock.advance(SHORT_SECONDS - 30)
    assert sm.tick() is True
    assert sm.mode is TimerMode.WORK
    assert sm.completed_work_sessions == 1  # 休息完成不加場次


def test_toggle_game_mode_twice_restores_idle_focus(sm: PomodoroStateMachine) -> None:
    sm.toggle_game_mode()
    sm.toggle_game_mode()
    assert sm.mode is TimerMode.WORK
    assert sm.state is TimerState.IDLE
    assert sm.remaining_seconds() == WORK_SECONDS
    assert sm.cycle_display() == "0/4"


def test_game_mode_has_no_cycle_display(sm: PomodoroStateMachine) -> None:
    sm.toggle_game_mode()
    assert sm.cycle_display() == "遊戲"
    sm.toggle_game_mode()
    assert sm.cycle_display() == "0/4"


def test_game_tick_completes_and_resets_to_idle(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(game_minutes=2), clock=clock)
    sm.toggle_game_mode()
    assert sm.remaining_seconds() == 120

    sm.start_or_pause()
    assert sm.state is TimerState.RUNNING
    clock.advance(60.0)
    assert sm.tick() is False

    clock.advance(60.0)
    assert sm.tick() is True
    assert sm.mode is TimerMode.GAME  # 遊戲完成不切階段
    assert sm.state is TimerState.IDLE  # 自動歸零待命
    assert sm.remaining_seconds() == 120
    assert sm.completed_work_sessions == 0  # 不動專注場次
    assert sm.cycle_display() == "遊戲"


def test_game_skip_resets_to_idle(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(game_minutes=2), clock=clock)
    sm.toggle_game_mode()
    sm.start_or_pause()
    clock.advance(50.0)
    sm.skip()

    assert sm.mode is TimerMode.GAME
    assert sm.state is TimerState.IDLE
    assert sm.remaining_seconds() == 120


def test_game_skip_while_idle_is_noop(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(game_minutes=2), clock=clock)
    sm.toggle_game_mode()
    sm.skip()
    assert sm.mode is TimerMode.GAME
    assert sm.state is TimerState.IDLE
    assert sm.remaining_seconds() == 120


def test_game_advance_phase_resets_to_idle(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(game_minutes=2), clock=clock)
    sm.toggle_game_mode()
    sm.start_or_pause()
    clock.advance(30.0)
    sm.advance_phase()

    assert sm.mode is TimerMode.GAME
    assert sm.state is TimerState.IDLE
    assert sm.remaining_seconds() == 120
    assert sm.completed_work_sessions == 0


def test_game_start_pause_resume(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(game_minutes=1), clock=clock)
    sm.toggle_game_mode()
    sm.start_or_pause()
    assert sm.state is TimerState.RUNNING
    clock.advance(20.0)
    sm.start_or_pause()
    assert sm.state is TimerState.PAUSED
    clock.advance(20.0)  # 暫停不走
    sm.start_or_pause()
    assert sm.state is TimerState.RUNNING
    assert sm.remaining_seconds() == 60 - 20


def test_update_config_updates_idle_game_timer(sm: PomodoroStateMachine) -> None:
    sm.toggle_game_mode()  # 進遊戲建立 IDLE game timer
    sm.toggle_game_mode()  # 回專注，遊戲存成 IDLE
    sm.update_config(AppConfig(game_minutes=45))

    sm.toggle_game_mode()
    assert sm.mode is TimerMode.GAME
    assert sm.remaining_seconds() == 45 * 60


def test_update_config_while_in_game_idle(sm: PomodoroStateMachine) -> None:
    sm.toggle_game_mode()
    sm.update_config(AppConfig(game_minutes=10))
    assert sm.mode is TimerMode.GAME
    assert sm.remaining_seconds() == 10 * 60


def test_update_config_keeps_running_game_countdown(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(game_minutes=30), clock=clock)
    sm.toggle_game_mode()
    sm.start_or_pause()
    clock.advance(60.0)
    sm.update_config(AppConfig(game_minutes=10))
    assert sm.state is TimerState.RUNNING
    assert sm.remaining_seconds() == GAME_SECONDS - 60  # 進行中不被打斷


def test_update_config_keeps_running_focus_countdown_then_uses_new_game(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(game_minutes=30), clock=clock)
    sm.toggle_game_mode()  # 建立 IDLE game timer
    sm.toggle_game_mode()
    sm.start_or_pause()
    clock.advance(60.0)
    sm.update_config(AppConfig(work_minutes=10, game_minutes=20))
    assert sm.state is TimerState.RUNNING
    assert sm.remaining_seconds() == WORK_SECONDS - 60
    sm.toggle_game_mode()
    assert sm.remaining_seconds() == 20 * 60


def test_set_mode_from_game_switches_context(clock: FakeClock) -> None:
    sm = PomodoroStateMachine(AppConfig(), clock=clock)
    sm.set_mode(TimerMode.GAME)
    assert sm.mode is TimerMode.GAME
    assert sm.remaining_seconds() == GAME_SECONDS

    sm.set_mode(TimerMode.LONG_BREAK)
    assert sm.mode is TimerMode.LONG_BREAK
    assert sm.state is TimerState.IDLE
    assert sm.remaining_seconds() == LONG_SECONDS

