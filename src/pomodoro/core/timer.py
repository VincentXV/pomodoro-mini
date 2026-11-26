"""精準倒數計時器（可注入 clock，方便做確定性測試）。"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

__all__ = ["PrecisionTimer"]


class PrecisionTimer:
    """倒數計時器，由可替換的 monotonic clock 驅動。

    生命週期：idle -> running <-> paused，時間到 -> finished。
    ``is_running`` 只在真的倒數中為 True；``is_paused`` 與 ``is_finished()``
    任一時刻最多只有一個為 True。
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        duration_seconds: float | None = None,
    ) -> None:
        self._clock = clock
        self._duration = 0.0
        self._elapsed = 0.0
        self._segment_start = 0.0
        self._started = False
        self._paused = False
        if duration_seconds is not None:
            self._duration = self._validate_duration(duration_seconds)

    # ------------------------------------------------------------------ #
    # 內部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate_duration(value: float) -> float:
        value = float(value)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("duration_seconds 必須是有限數且 >= 0（拒絕 NaN/inf/負數）")
        return value

    def _elapsed_now(self) -> float:
        """目前已流逝秒數（暫停時凍結）。

        每次只讀一次 clock，並把段落原點推到當下：負增量夾緊為 0，
        因此 clock 倒退既不會產生負 elapsed，也不會讓倒數往回跳。
        """
        if self._started and not self._paused:
            now = self._clock()
            delta = max(0.0, now - self._segment_start)
            self._segment_start = now
            self._elapsed += delta
        return self._elapsed

    # ------------------------------------------------------------------ #
    # 生命週期
    # ------------------------------------------------------------------ #
    def start(self, duration_seconds: float) -> None:
        """開始（或重新開始）倒數。"""
        self._duration = self._validate_duration(duration_seconds)
        self._elapsed = 0.0
        self._segment_start = self._clock()
        self._started = True
        self._paused = False

    def pause(self) -> None:
        """暫停；未開始或已結束時為 no-op。"""
        if not self._started or self._paused:
            return
        # _elapsed_now 內部只讀一次 clock 並累積，這裡直接凍結
        if self._elapsed_now() >= self._duration:
            return  # 已結束，維持 no-op 語意
        self._paused = True

    def resume(self) -> None:
        """從暫停處繼續；未處於暫停或已結束時為 no-op。"""
        if not self._started or not self._paused:
            return
        if self._elapsed >= self._duration:
            return  # 暫停前已走完，不復活
        self._segment_start = self._clock()  # 單次讀取
        self._paused = False

    def reset(self, duration_seconds: float | None = None) -> None:
        """回到未開始狀態；可順帶換新時長（不傳則沿用原時長）。"""
        if duration_seconds is not None:
            self._duration = self._validate_duration(duration_seconds)
        self._elapsed = 0.0
        self._segment_start = self._clock()  # 單次讀取
        self._started = False
        self._paused = False

    # ------------------------------------------------------------------ #
    # 查詢
    # ------------------------------------------------------------------ #
    def remaining_seconds(self) -> float:
        """剩餘秒數（未開始時回傳完整時長，下限 0）。"""
        if not self._started:
            return max(0.0, self._duration)
        return max(0.0, self._duration - self._elapsed_now())

    def progress(self) -> float:
        """完成比例 0.0 ~ 1.0。"""
        if not self._started:
            return 0.0
        if self._duration <= 0.0:
            return 1.0 if self.is_finished() else 0.0
        ratio = self._elapsed_now() / self._duration
        if ratio < 0.0:
            return 0.0
        if ratio > 1.0:
            return 1.0
        return ratio

    @property
    def is_running(self) -> bool:
        """正在倒數（已開始、未暫停、未結束）。"""
        return self._started and not self._paused and not self.is_finished()

    @property
    def is_paused(self) -> bool:
        """已開始且處於暫停。"""
        return self._started and self._paused and not self.is_finished()

    def is_finished(self) -> bool:
        """倒數已走完。"""
        return self._started and self._elapsed_now() >= self._duration
