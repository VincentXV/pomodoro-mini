"""通知音效：以標準庫合成 4 種純音 WAV，並安全地播放。"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Any

from pomodoro.config import SoundTrack

__all__ = ["MAX_CONCURRENT_EFFECTS", "SAMPLE_RATE", "SoundManager", "TRACK_NAMES"]

SAMPLE_RATE = 44_100
TRACK_NAMES: tuple[SoundTrack, ...] = ("chime", "beep", "wood", "bell")

# 軟上限：優先靠 stopped 訊號回收，滿了只清「已播完的」，不動還在播的
MAX_CONCURRENT_EFFECTS = 8
# 硬上限：訊號失效時的保命線，逼近才丟最舊，避免清單無限增長
_HARD_EFFECT_LIMIT = 32

# 各音色的合成參數（時長互不相同，確保 4 個檔案不重複）
_CHIME_PARTIALS: tuple[tuple[float, float, float], ...] = (
    (1318.51, 1.00, 0.55),  # E6
    (1975.53, 0.62, 0.45),
    (2637.02, 0.40, 0.34),
    (3520.00, 0.24, 0.26),
)
_WOOD_PARTIALS: tuple[tuple[float, float, float], ...] = (
    (392.0, 1.00, 0.055),
    (655.0, 0.65, 0.040),
    (1120.0, 0.45, 0.028),
    (2350.0, 0.30, 0.018),
    (4700.0, 0.22, 0.010),
    (6100.0, 0.15, 0.008),
)
_BELL_PARTIALS: tuple[tuple[float, float, float], ...] = (
    (523.25, 1.00, 1.20),  # C5
    (1046.50, 0.55, 0.95),
    (1567.98, 0.38, 0.75),
    (2180.00, 0.26, 0.55),
    (3100.00, 0.16, 0.40),
)


# --------------------------------------------------------------------------- #
# 合成工具
# --------------------------------------------------------------------------- #
def _fade_tail(t: float, duration: float, fade: float = 0.03) -> float:
    """結尾淡出，避免切斷造成爆音。"""
    if t >= duration:
        return 0.0
    remaining = duration - t
    if fade <= 0.0:
        return 1.0
    return min(1.0, remaining / fade)


def _normalize(samples: list[float], peak: float) -> list[float]:
    max_abs = max((abs(s) for s in samples), default=0.0)
    if max_abs <= 0.0:
        return samples
    gain = peak / max_abs
    return [s * gain for s in samples]


def _to_pcm(samples: list[float]) -> bytes:
    """float samples -> 16-bit PCM (little-endian)。"""
    out = bytearray()
    for sample in samples:
        clipped = -1.0 if sample < -1.0 else (1.0 if sample > 1.0 else sample)
        out += struct.pack("<h", int(clipped * 32767.0))
    return bytes(out)


def _gen_chime() -> list[float]:
    """清脆風鈴：高頻泛音 + 第二下輕敲，1.6 秒。"""
    duration = 1.6
    n = int(SAMPLE_RATE * duration)
    samples: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        value = 0.0
        for freq, amp, tau in _CHIME_PARTIALS:
            value += amp * math.sin(2.0 * math.pi * freq * t) * math.exp(-t / tau)
        if t >= 0.62:  # 第二下較輕的敲擊
            t2 = t - 0.62
            for freq, amp, tau in _CHIME_PARTIALS[:3]:
                value += 0.45 * amp * math.sin(2.0 * math.pi * freq * t2) * math.exp(-t2 / tau)
        attack = min(1.0, t / 0.004)
        samples.append(value * attack * _fade_tail(t, duration))
    return _normalize(samples, 0.80)


def _gen_beep() -> list[float]:
    """數位蜂鳴：三段 880Hz 方波感短音，0.52 秒。"""
    duration = 0.52
    n = int(SAMPLE_RATE * duration)
    pulses = ((0.0, 0.12), (0.18, 0.12), (0.36, 0.12))
    samples: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        value = 0.0
        for start, length in pulses:
            if start <= t < start + length:
                tt = t - start
                env = min(1.0, tt / 0.003) * min(1.0, (length - tt) / 0.012)
                value += env * (
                    math.sin(2.0 * math.pi * 880.0 * tt)
                    + 0.35 * math.sin(2.0 * math.pi * 2640.0 * tt)
                )
        samples.append(value * 0.7)
    return _normalize(samples, 0.75)


def _gen_wood() -> list[float]:
    """沉靜木魚：不諧和泛音快速衰減，0.32 秒。"""
    duration = 0.32
    n = int(SAMPLE_RATE * duration)
    samples: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        value = 0.0
        for freq, amp, tau in _WOOD_PARTIALS:
            value += amp * math.sin(2.0 * math.pi * freq * t) * math.exp(-t / tau)
        attack = min(1.0, t / 0.0015)
        samples.append(value * attack * _fade_tail(t, duration, fade=0.02))
    return _normalize(samples, 0.85)


def _gen_bell() -> list[float]:
    """柔和鈴鐺：低頻鐘體泛音 + 輕微顫音，2.4 秒。"""
    duration = 2.4
    n = int(SAMPLE_RATE * duration)
    samples: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        value = 0.0
        for freq, amp, tau in _BELL_PARTIALS:
            value += amp * math.sin(2.0 * math.pi * freq * t) * math.exp(-t / tau)
        tremolo = 1.0 - 0.12 * math.sin(2.0 * math.pi * 4.5 * t)
        attack = min(1.0, t / 0.012)
        samples.append(value * tremolo * attack * _fade_tail(t, duration, fade=0.05))
    return _normalize(samples, 0.78)


_RENDERERS = {
    "chime": _gen_chime,
    "beep": _gen_beep,
    "wood": _gen_wood,
    "bell": _gen_bell,
}


def _write_track(path: Path, track: SoundTrack) -> None:
    renderer = _RENDERERS.get(track)
    if renderer is None:
        raise ValueError(f"未知的音軌: {track}")
    pcm = _to_pcm(renderer())
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)


def _is_valid_wav(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() > 0 and wav.getframerate() > 0
    except (OSError, EOFError, wave.Error):
        return False


# --------------------------------------------------------------------------- #
# SoundManager
# --------------------------------------------------------------------------- #
class SoundManager:
    """產生並播放 4 種通知音（WAV）。"""

    def __init__(self, cache_dir: Path | None = None) -> None:
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "pomodoro-mini" / "sounds"
        self.cache_dir = Path(cache_dir)
        self._effects: list[Any] = []

    # ------------------------------------------------------------------ #
    # 音量
    # ------------------------------------------------------------------ #
    def normalize_volume(self, volume: int) -> float:
        """0~100 夾緊後轉成 0.0~1.0；NaN / inf / 非數值一律安全回 0.0。"""
        try:
            value = int(volume)
        except (TypeError, ValueError, OverflowError):
            # int(float('nan')) -> ValueError；int(float('inf')) -> OverflowError
            return 0.0
        return max(0, min(100, value)) / 100.0

    # ------------------------------------------------------------------ #
    # 檔案
    # ------------------------------------------------------------------ #
    def _track_path(self, track: SoundTrack) -> Path:
        return self.cache_dir / f"{track}.wav"

    def ensure_tracks_generated(self) -> dict[SoundTrack, Path]:
        """確保 4 個音軌 WAV 都存在且有效，回傳 軌名 -> 路徑。"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[SoundTrack, Path] = {}
        for name in TRACK_NAMES:
            path = self._track_path(name)
            if not (path.is_file() and path.stat().st_size > 44 and _is_valid_wav(path)):
                _write_track(path, name)
            paths[name] = path
        return paths

    # ------------------------------------------------------------------ #
    # 播放
    # ------------------------------------------------------------------ #
    def _discard_effect(self, effect: Any) -> None:
        """從回收清單移除指定 effect（stopped 訊號到達時呼叫）。"""
        try:
            self._effects.remove(effect)
        except ValueError:
            pass

    def _purge_finished_effects(self) -> None:
        """清掉「已播完」的 effect；仍在播放的一律保留。"""
        alive: list[Any] = []
        for effect in self._effects:
            try:
                finished = bool(effect.isLoaded() and effect.isStopped())
            except Exception:
                finished = False  # 查不出狀態就當還在播，寧可多留不可誤殺
            if not finished:
                alive.append(effect)
        self._effects = alive

    def _register_effect(self, effect: Any) -> None:
        """登錄新 effect：播完（stopped 訊號）才移除，避免 GC 掐掉正在播的音。

        上限保護：滿了先清「已播完的」；若全都還在播就允許暫時超限，
        交給 stopped 訊號陸續回收，只有逼近硬上限才丟最舊保命。
        """
        try:
            effect.stopped.connect(lambda e=effect: self._discard_effect(e))
        except Exception:
            pass  # 沒有訊號就退回清單回收，不擋播放
        self._purge_finished_effects()
        if len(self._effects) >= MAX_CONCURRENT_EFFECTS:
            self._purge_finished_effects()
            while len(self._effects) >= _HARD_EFFECT_LIMIT:
                self._effects.pop(0)
        self._effects.append(effect)

    def play(self, track: SoundTrack, volume: int) -> None:
        """播放音軌；Qt / 音效裝置 / QApplication 缺乏時安全降級，不拋例外。"""
        level = self.normalize_volume(volume)
        if level <= 0.0 or track not in TRACK_NAMES:
            return
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtWidgets import QApplication
        except Exception:
            return
        try:
            if QApplication.instance() is None:
                return
        except Exception:
            return
        try:
            path = self.ensure_tracks_generated()[track]
        except Exception:
            return
        try:
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(str(path)))
            effect.setVolume(level)
            effect.play()
        except Exception:
            return
        self._register_effect(effect)
