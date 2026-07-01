"""Silence-based utterance segmentation for live dogsound audio."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class AudioSegment:
    samples: list[float]
    duration_ms: int
    frame_count: int


@dataclass
class AudioSegmenter:
    sample_rate: int = 16000
    frame_ms: int = 40
    silence_ms: int = 900
    min_utterance_ms: int = 120
    start_threshold: float = 0.015
    stop_threshold: float = 0.010

    def __post_init__(self) -> None:
        self.silence_frames = max(1, math.ceil(self.silence_ms / self.frame_ms))
        self.min_frames = max(1, math.ceil(self.min_utterance_ms / self.frame_ms))
        self._recording = False
        self._buffer: list[float] = []
        self._frames = 0
        self._silent_tail_frames = 0

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def recording_ms(self) -> int:
        if not self._recording:
            return 0
        return self._frames * self.frame_ms

    @property
    def silent_tail_ms(self) -> int:
        if not self._recording:
            return 0
        return self._silent_tail_frames * self.frame_ms

    def process_frame(self, frame: Sequence[float]) -> list[AudioSegment]:
        values = [float(value) for value in frame]
        energy = _rms(values)
        emitted: list[AudioSegment] = []

        if not self._recording:
            if energy >= self.start_threshold:
                self._recording = True
                self._buffer = list(values)
                self._frames = 1
                self._silent_tail_frames = 0
            return emitted

        self._buffer.extend(values)
        self._frames += 1

        if energy < self.stop_threshold:
            self._silent_tail_frames += 1
        else:
            self._silent_tail_frames = 0

        if self._silent_tail_frames >= self.silence_frames:
            emitted.extend(self._finish_segment(trim_silent_tail=True))

        return emitted

    def flush(self) -> list[AudioSegment]:
        if not self._recording:
            return []
        return self._finish_segment(trim_silent_tail=True)

    def _finish_segment(self, *, trim_silent_tail: bool) -> list[AudioSegment]:
        frame_size = max(1, int(self.sample_rate * self.frame_ms / 1000))
        trim_frames = self._silent_tail_frames if trim_silent_tail else 0
        kept_frames = max(0, self._frames - trim_frames)
        kept_samples = self._buffer[: kept_frames * frame_size]

        self._recording = False
        self._buffer = []
        self._frames = 0
        self._silent_tail_frames = 0

        if kept_frames < self.min_frames:
            return []

        duration_ms = int(kept_samples and len(kept_samples) / self.sample_rate * 1000)
        return [AudioSegment(samples=kept_samples, duration_ms=duration_ms, frame_count=kept_frames)]


def _rms(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))
