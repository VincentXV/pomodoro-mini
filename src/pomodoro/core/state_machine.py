"""番茄鐘狀態機（與 GUI 無關的核心邏輯）。"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from enum import StrEnum

from pomodoro.config import AppConfig
from pomodoro.core.timer import PrecisionTimer

__all__ = ["PomodoroStateMachine", "TimerMode", "TimerState"]


class TimerMode(StrEnum):
    """目前所處的階段。"""

    WORK = "work"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"
    GAME = "game"


class TimerState(StrEnum):
    """狀態機狀態。"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class PomodoroStateMachine:
    """番茄鐘狀態機。

    - ``tick()`` 在倒數「剛好結束」的那次呼叫回傳 True，並自動切到下一模式：
      WORK 完成累計 ``completed_work_sessions``，每達 ``long_break_interval``
      次切 LONG_BREAK，否則 SHORT_BREAK；休息完成切回 WORK，同時把計時器
      重置為新模式的時長（狀態進 COMPLETED，等使用者再按開始）。
    - ``skip()`` 跳過「進行中」的階段（RUNNING / PAUSED），走與完成相同的
      路徑（工作場次照計）；IDLE / COMPLETED 沒有進行中的階段，為 no-op。
    - 遊戲模式（GAME）與專注體系各自保存獨立上下文：``toggle_game_mode()``
      來回切換時互不干擾（週期場次只屬於專注體系），遊戲沒有週期，
      倒數結束一律重設回 ``game_minutes * 60`` 待命。
    """

    def __init__(self, config: AppConfig, clock: Callable[[], float] = time.monotonic) -> None:
        self._config = config.normalized()
        self._clock = clock
        # 專注體系上下文（WORK / SHORT_BREAK / LONG_BREAK）
        self._focus_timer = PrecisionTimer(clock=clock)
        self._focus_mode = TimerMode.WORK
        self._focus_state = TimerState.IDLE
        # 遊戲體系上下文（GAME）；_game_ready 表示已用 game_minutes 建過 IDLE timer
        self._game_timer = PrecisionTimer(clock=clock)
        self._game_state = TimerState.IDLE
        self._game_ready = False
        # 目前作用中的上下文預設為專注體系
        self._timer = self._focus_timer
        self._mode = self._focus_mode
        self._state = self._focus_state
        self._completed_work_sessions = 0  # 只屬於專注體系，GAME 不會動它
        self._timer.reset(self._duration_for(self._mode))

    # ------------------------------------------------------------------ #
    # 屬性
    # ------------------------------------------------------------------ #
    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def timer(self) -> PrecisionTimer:
        return self._timer

    @property
    def mode(self) -> TimerMode:
        return self._mode

    @property
    def state(self) -> TimerState:
        return self._state

    @property
    def completed_work_sessions(self) -> int:
        return self._completed_work_sessions

    # ------------------------------------------------------------------ #
    # 內部工具
    # ------------------------------------------------------------------ #
    def _duration_for(self, mode: TimerMode) -> float:
        if mode is TimerMode.GAME:
            minutes = self._config.game_minutes
        elif mode is TimerMode.WORK:
            minutes = self._config.work_minutes
        elif mode is TimerMode.SHORT_BREAK:
            minutes = self._config.short_break_minutes
        else:
            minutes = self._config.long_break_minutes
        return float(minutes) * 60.0

    def _interval(self) -> int:
        return max(1, int(self._config.long_break_interval))

    def _reset_game(self) -> None:
        """遊戲模式沒有週期：一律重設回 game_minutes * 60 並回到 IDLE 待命。"""
        self._timer.reset(self._duration_for(TimerMode.GAME))
        self._state = TimerState.IDLE

    def _pause_active_for_save(self) -> TimerState:
        """保存上下文前先把 RUNNING 暫停，回傳要存起來的狀態。"""
        if self._state is TimerState.RUNNING:
            self._timer.pause()
            return TimerState.PAUSED
        return self._state

    def toggle_game_mode(self) -> TimerMode:
        """在專注體系與遊戲模式之間切換，各自保存／還原自己的計時狀態。

        - 離開 GAME：遊戲計時狀態存回（RUNNING 先 pause），還原專注體系的
          mode / timer / state 與 ``completed_work_sessions``。
        - 進入 GAME：專注體系狀態存回，切到 GAME 與遊戲 timer；
          遊戲 timer 還沒初始化時以 ``game_minutes * 60`` 建 IDLE timer。
        """
        if self._mode is TimerMode.GAME:
            self._game_state = self._pause_active_for_save()
            self._mode = self._focus_mode
            self._state = self._focus_state
            self._timer = self._focus_timer
            return self._mode

        self._focus_mode = self._mode
        self._focus_state = self._pause_active_for_save()
        self._mode = TimerMode.GAME
        self._timer = self._game_timer
        if not self._game_ready:
            self._game_timer.reset(self._duration_for(TimerMode.GAME))
            self._game_state = TimerState.IDLE
            self._game_ready = True
        self._state = self._game_state
        return self._mode

    def _complete_phase(self) -> None:
        """結束目前階段並準備下一模式。"""
        if self._mode is TimerMode.WORK:
            self._completed_work_sessions += 1
            if self._completed_work_sessions % self._interval() == 0:
                next_mode = TimerMode.LONG_BREAK
            else:
                next_mode = TimerMode.SHORT_BREAK
        else:
            next_mode = TimerMode.WORK
        self._mode = next_mode
        self._timer.reset(self._duration_for(next_mode))
        self._state = TimerState.COMPLETED

    # ------------------------------------------------------------------ #
    # 操作
    # ------------------------------------------------------------------ #
    def start_or_pause(self) -> None:
        """IDLE / COMPLETED 開始；RUNNING 暫停；PAUSED 繼續。"""
        if self._state is TimerState.RUNNING and self._timer.is_finished():
            # 時間已到但還沒人 tick，先補完成流程，避免卡在矛盾狀態
            self.tick()
            return
        if self._state in (TimerState.IDLE, TimerState.COMPLETED):
            self._timer.start(self._duration_for(self._mode))
            self._state = TimerState.RUNNING
        elif self._state is TimerState.RUNNING:
            self._timer.pause()
            if self._timer.is_finished():
                # 暫停瞬間剛好走完：補完成流程，不留在矛盾的 PAUSED
                self.tick()
            else:
                self._state = TimerState.PAUSED
        elif self._state is TimerState.PAUSED:
            self._timer.resume()
            if self._timer.is_finished():
                # 續跑瞬間已走完：同樣補完成流程，狀態直接進 COMPLETED
                self._state = TimerState.RUNNING
                self.tick()
            else:
                self._state = TimerState.RUNNING

    def reset(self) -> None:
        """重置目前階段（已完成的工作場次數保留）。"""
        self._timer.reset(self._duration_for(self._mode))
        self._state = TimerState.IDLE

    def skip(self) -> None:
        """跳過進行中的階段；沒有進行中的階段時不做任何事。"""
        if self._state not in (TimerState.RUNNING, TimerState.PAUSED):
            return
        if self._mode is TimerMode.GAME:
            self._reset_game()
            return
        self._complete_phase()

    def advance_phase(self) -> None:
        """不論目前狀態為何，直接結束目前階段並推進至下一階段（含累計場次與長休判定）。"""
        if self._mode is TimerMode.GAME:
            self._reset_game()
            return
        self._complete_phase()

    def set_mode(self, mode: TimerMode) -> None:
        """手動切換模式，計時器重置為該模式時長並回到 IDLE。"""
        target = TimerMode(mode)
        if target is TimerMode.GAME:
            if self._mode is not TimerMode.GAME:
                self.toggle_game_mode()
            self.reset()
            return
        if self._mode is TimerMode.GAME:
            self.toggle_game_mode()
        self._mode = target
        self._timer.reset(self._duration_for(self._mode))
        self._state = TimerState.IDLE

    def update_config(self, config: AppConfig) -> None:
        """套用新設定。

        IDLE / COMPLETED 會立刻重算目前模式的時長；RUNNING / PAUSED 不打斷
        進行中的倒數，新設定從下一個階段開始生效。遊戲 timer 若也處於
        IDLE / COMPLETED，一併更新為新的 ``game_minutes * 60``。
        """
        self._config = config.normalized()
        if self._state in (TimerState.IDLE, TimerState.COMPLETED):
            self._timer.reset(self._duration_for(self._mode))
        if self._mode is TimerMode.GAME:
            game_state, game_timer = self._state, self._timer
        else:
            game_state, game_timer = self._game_state, self._game_timer
        if game_state in (TimerState.IDLE, TimerState.COMPLETED):
            game_timer.reset(self._duration_for(TimerMode.GAME))

    def tick(self) -> bool:
        """推進一次；若本次剛好完成倒數則回傳 True。"""
        if self._state is not TimerState.RUNNING:
            return False
        if not self._timer.is_finished():
            return False
        if self._mode is TimerMode.GAME:
            self._reset_game()
            return True
        self._complete_phase()
        return True

    # ------------------------------------------------------------------ #
    # 顯示
    # ------------------------------------------------------------------ #
    def remaining_seconds(self) -> int:
        """剩餘秒數（進位到整秒，避免畫面提前掉到 00:00）。"""
        return int(math.ceil(self._timer.remaining_seconds()))

    def formatted_time(self) -> str:
        """MM:SS 格式。"""
        total = self.remaining_seconds()
        return f"{total // 60:02d}:{total % 60:02d}"

    def progress(self) -> float:
        """目前階段完成比例 0.0 ~ 1.0。"""
        return self._timer.progress()

    def cycle_display(self) -> str:
        """本週期已完成的工作場次 / 週期長度，例如 ``2/4``；遊戲模式回「遊戲」。"""
        if self._mode is TimerMode.GAME:
            return "遊戲"
        interval = self._interval()
        done = self._completed_work_sessions % interval
        return f"{done}/{interval}"
