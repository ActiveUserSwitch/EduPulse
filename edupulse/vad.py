"""Energy-based VAD segment assembler for radio PTT (shared by capture tools)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .audio_io import get_levels


@dataclass
class VadConfig:
    speech_threshold_db: float = -32.0
    silence_timeout: float = 0.8
    tail_padding_sec: float = 0.4
    pre_roll_sec: float = 0.25
    min_speech_sec: float = 0.3
    max_segment_sec: float = 30.0
    sample_rate: int = 16000
    block_samples: int = 1024
    adaptive_margin_db: float = 10.0
    quiet_learn_rate: float = 0.05


@dataclass
class CompletedSegment:
    """Raw multi-channel audio for one finished transmission."""

    audio: np.ndarray
    start_time: float
    end_time: float
    duration_sec: float


@dataclass
class EnergyVAD:
    """Block-wise energy VAD with pre-roll and tail padding.

    Call ``push(block, now)`` for each capture block; may return a completed
    segment. Adaptive quiet floor optional via ``use_adaptive``.
    """

    config: VadConfig = field(default_factory=VadConfig)
    use_adaptive: bool = True
    quiet_db_ema: float = -50.0

    is_speaking: bool = False
    audio_buffer: list[np.ndarray] = field(default_factory=list)
    pre_buffer: list[np.ndarray] = field(default_factory=list)
    segment_start_time: float | None = None
    silence_start: float | None = None
    segment_done_time: float | None = None

    def _pre_roll_blocks(self) -> int:
        return max(1, int(self.config.pre_roll_sec * self.config.sample_rate / self.config.block_samples))

    def _effective_threshold(self) -> float:
        if not self.use_adaptive:
            return self.config.speech_threshold_db
        return max(
            self.config.speech_threshold_db,
            self.quiet_db_ema + self.config.adaptive_margin_db,
        )

    def push(self, audio: np.ndarray, now: float) -> CompletedSegment | None:
        """Ingest one block; return a finished segment or None."""
        cfg = self.config
        levels = get_levels(audio)
        dominant_db = max(levels["db_rms_l"], levels["db_rms_r"])

        # Pre-roll ring
        self.pre_buffer.append(audio.copy())
        max_pre = self._pre_roll_blocks()
        if len(self.pre_buffer) > max_pre:
            self.pre_buffer = self.pre_buffer[-max_pre:]

        if self.use_adaptive and dominant_db < self.quiet_db_ema + 6:
            self.quiet_db_ema = (1 - cfg.quiet_learn_rate) * self.quiet_db_ema + cfg.quiet_learn_rate * dominant_db

        thr = self._effective_threshold()
        is_speech = dominant_db > thr
        finished: CompletedSegment | None = None

        if is_speech:
            if not self.is_speaking:
                self.is_speaking = True
                self.audio_buffer = self.pre_buffer[:] + [audio.copy()]
                self.segment_start_time = now
                self.silence_start = None
                self.segment_done_time = None
            else:
                self.audio_buffer.append(audio.copy())
                self.silence_start = None
                self.segment_done_time = None
            if self.segment_start_time and (now - self.segment_start_time) > cfg.max_segment_sec:
                self.is_speaking = False
                self.segment_done_time = now
        else:
            if self.is_speaking:
                if self.silence_start is None:
                    self.silence_start = now
                if (now - self.silence_start) >= cfg.silence_timeout and self.segment_done_time is None:
                    self.is_speaking = False
                    self.segment_done_time = now
            if self.silence_start is not None:
                time_since_done = now - (self.segment_done_time or self.silence_start)
                pad = (cfg.silence_timeout if self.segment_done_time is None else 0) + cfg.tail_padding_sec
                if time_since_done <= pad:
                    self.audio_buffer.append(audio.copy())

        cut = False
        if (
            self.segment_done_time is not None
            and (now - self.segment_done_time) > cfg.tail_padding_sec
            and self.audio_buffer
            and self.segment_start_time is not None
        ):
            cut = True
        elif (
            (not self.is_speaking)
            and self.segment_done_time is None
            and self.audio_buffer
            and self.segment_start_time is not None
        ):
            cut = True

        if cut and self.segment_start_time is not None:
            full = np.concatenate(self.audio_buffer, axis=0)
            duration = len(full) / cfg.sample_rate
            if duration >= cfg.min_speech_sec:
                finished = CompletedSegment(
                    audio=full,
                    start_time=self.segment_start_time,
                    end_time=now,
                    duration_sec=duration,
                )
            self.audio_buffer = []
            self.segment_start_time = None
            self.silence_start = None
            self.segment_done_time = None

        # Memory safety
        max_blocks = int((cfg.max_segment_sec + 5) * cfg.sample_rate / max(1, cfg.block_samples))
        if len(self.audio_buffer) > max_blocks:
            self.audio_buffer = self.audio_buffer[-max(1, int(5 * cfg.sample_rate / cfg.block_samples)) :]

        return finished
