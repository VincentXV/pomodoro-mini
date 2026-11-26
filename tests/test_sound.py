"""SoundManager 單元測試：合成、快取與安全播放。"""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path

import pytest

from pomodoro.config import SOUND_TRACK_LABELS
from pomodoro.core.sound import SAMPLE_RATE, SoundManager, TRACK_NAMES


@pytest.fixture(scope="session")
def manager(tmp_path_factory: pytest.TempPathFactory) -> SoundManager:
    return SoundManager(cache_dir=tmp_path_factory.mktemp("sounds"))


@pytest.mark.parametrize(
    ("volume", "expected"),
    [
        (0, 0.0),
        (100, 1.0),
        (50, 0.5),
        (70, 0.7),
        (-10, 0.0),
        (250, 1.0),
    ],
)
def test_normalize_volume(manager: SoundManager, volume: int, expected: float) -> None:
    assert manager.normalize_volume(volume) == pytest.approx(expected)


def test_default_cache_dir_is_under_home() -> None:
    manager = SoundManager()
    assert manager.cache_dir == Path.home() / ".cache" / "pomodoro-mini" / "sounds"


def test_ensure_tracks_creates_four_valid_wavs(manager: SoundManager) -> None:
    paths = manager.ensure_tracks_generated()
    assert set(paths) == set(SOUND_TRACK_LABELS)
    assert set(paths) == set(TRACK_NAMES)

    for name, path in paths.items():
        assert path.is_file(), f"{name} 未產生"
        with wave.open(str(path), "rb") as wav:
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
            assert wav.getframerate() == SAMPLE_RATE
            nframes = wav.getnframes()
            assert nframes > 0
            frames = wav.readframes(nframes)
        assert len(frames) == nframes * 2


def test_tracks_are_all_distinct(manager: SoundManager) -> None:
    paths = manager.ensure_tracks_generated()
    digests = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in paths.items()
    }
    assert len(set(digests.values())) == 4, "4 個音軌內容必須互不相同"

    durations = set()
    for path in paths.values():
        with wave.open(str(path), "rb") as wav:
            durations.add(wav.getnframes())
    assert len(durations) == 4, "4 個音軌時長必須互不相同"


def test_ensure_tracks_is_idempotent(manager: SoundManager) -> None:
    first = manager.ensure_tracks_generated()
    before = {name: path.read_bytes() for name, path in first.items()}
    mtimes = {name: path.stat().st_mtime_ns for name, path in first.items()}

    second = manager.ensure_tracks_generated()
    assert second == first
    for name, path in second.items():
        assert path.read_bytes() == before[name]
        assert path.stat().st_mtime_ns == mtimes[name]  # 沒有重新生成


def test_play_without_qapp_is_safe(manager: SoundManager) -> None:
    # QApplication 未啟動 / 無音效裝置時必須安全降級，不能拋例外
    manager.play("chime", 70)
    manager.play("beep", 100)
    manager.play("wood", -10)  # 音量 0 以下直接略過
    manager.play("bell", 250)
    manager.play("chime", 0)


def test_play_rejects_unknown_track(manager: SoundManager) -> None:
    manager.play("nope", 70)  # type: ignore[arg-type]


def test_play_after_generating_tracks_is_safe(manager: SoundManager) -> None:
    manager.ensure_tracks_generated()
    manager.play("bell", 50)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "abc", None])
def test_normalize_volume_rejects_non_finite(manager: SoundManager, bad: object) -> None:
    """NaN / inf / 垃圾值不得穿透成 NaN 音量，也不得拋 OverflowError。"""
    assert manager.normalize_volume(bad) == 0.0  # type: ignore[arg-type]


def test_play_with_non_finite_volume_is_safe(manager: SoundManager) -> None:
    manager.play("chime", float("nan"))  # type: ignore[arg-type]
    manager.play("chime", float("inf"))  # type: ignore[arg-type]


class _FakeSignal:
    """模擬 Qt 訊號：只支援 connect / emit。"""

    def __init__(self) -> None:
        self._slots: list = []

    def connect(self, slot) -> None:  # noqa: ANN001
        self._slots.append(slot)

    def emit(self) -> None:
        for slot in list(self._slots):
            slot()


class _FakeEffect:
    """模擬 QSoundEffect：stopped 訊號 + 播放狀態。"""

    def __init__(self, playing: bool = True) -> None:
        self.stopped = _FakeSignal()
        self._playing = playing

    def isLoaded(self) -> bool:
        return True

    def isStopped(self) -> bool:
        return not self._playing

    def finish(self) -> None:
        self._playing = False
        self.stopped.emit()


def test_ninth_play_does_not_kill_still_playing_effects(manager: SoundManager) -> None:
    """連續第 9 次播放不得誤殺仍在播放的音效（回收只認 stopped 訊號）。"""
    effects = [_FakeEffect() for _ in range(9)]
    for effect in effects:
        manager._register_effect(effect)

    assert len(manager._effects) == 9
    assert all(e in manager._effects for e in effects), "第 9 個（含前 8 個）都必須活著"


def test_effect_removed_only_after_stopped_signal(manager: SoundManager) -> None:
    first = _FakeEffect()
    manager._register_effect(first)
    assert first in manager._effects

    first.finish()  # stopped 訊號
    assert first not in manager._effects


def test_soft_limit_purges_finished_but_keeps_playing(manager: SoundManager) -> None:
    """到達軟上限時只清「已播完的」，還在播的一律保留。"""
    done = [_FakeEffect(playing=False) for _ in range(4)]
    playing = [_FakeEffect() for _ in range(6)]
    manager._effects = [*done, *playing]

    manager._register_effect(_FakeEffect())
    for effect in done:
        assert effect not in manager._effects
    for effect in playing:
        assert effect in manager._effects


def test_hard_limit_caps_runaway_growth(manager: SoundManager) -> None:
    """訊號全部失效時仍有硬上限，避免清單無限增長。"""
    from pomodoro.core.sound import _HARD_EFFECT_LIMIT

    for _ in range(_HARD_EFFECT_LIMIT + 10):
        manager._register_effect(_FakeEffect())
    assert len(manager._effects) < _HARD_EFFECT_LIMIT + 10
    assert len(manager._effects) <= _HARD_EFFECT_LIMIT
