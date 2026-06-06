"""Process-local amplitude bus.

A tiny QObject singleton that holds the *current speaking/listening
amplitude* on a 0..1 scale and emits ``amplitude_changed(float)`` at
~30 Hz. Two kinds of producers:

* **Synthetic envelope** — used today, while the desktop process has no
  real TTS audio path. ``push_synthetic(duration_s)`` runs a smoothed
  random walk that decays to zero, giving the orb a believable
  "speaking" envelope. Length is set from the assistant message size.

* **Real audio RMS** — forward-compatible. Anyone holding a chunk of
  audio (mic capture, future TTS bridge) can call ``push_rms(value)``
  with an already-computed RMS in [0, 1]; the bus low-passes it.

The orb subscribes once at construction and never has to care which
producer is driving it.
"""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QObject, QTimer, Signal


_DECAY = 0.86       # per-tick decay toward 0 when no input
_LOWPASS = 0.55     # smoothing factor for incoming RMS
_TICK_MS = 33       # ~30 Hz


class AudioBus(QObject):
    """Singleton-ish — use ``AudioBus.instance()``."""

    amplitude_changed = Signal(float)

    _instance: "AudioBus | None" = None

    @classmethod
    def instance(cls) -> "AudioBus":
        if cls._instance is None:
            cls._instance = AudioBus()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._value = 0.0
        self._target = 0.0
        self._synth_until = 0.0
        self._synth_phase = 0.0
        self._synth_seed = random.random() * 1000

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(_TICK_MS)

    # ------------------------------------------------------------------
    # Public producers
    # ------------------------------------------------------------------

    def push_rms(self, rms: float) -> None:
        """Direct amplitude push, low-passed. Clamped to [0, 1]."""
        rms = max(0.0, min(1.0, float(rms)))
        self._target = rms * _LOWPASS + self._target * (1.0 - _LOWPASS)

    def push_synthetic(self, duration_s: float, intensity: float = 0.75) -> None:
        """Kick off a synthesized envelope for ``duration_s`` seconds.

        Used when the brain emits a reply but we don't have real TTS audio
        — the orb still needs to *visibly* speak.
        """
        now = time.monotonic()
        self._synth_until = max(self._synth_until, now + max(0.4, duration_s))
        self._synth_intensity = max(0.2, min(1.0, intensity))

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def value(self) -> float:
        return self._value

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_tick(self) -> None:
        now = time.monotonic()

        # Synthetic envelope wins while active — smoothed random walk
        # plus a 3 Hz wobble keeps it from looking like a sawtooth.
        if now < self._synth_until:
            self._synth_phase += 0.18
            wobble = 0.5 + 0.5 * math.sin(self._synth_phase)
            jitter = random.uniform(-0.18, 0.18)
            base = getattr(self, "_synth_intensity", 0.75)
            target = max(0.0, min(1.0, base * (0.55 + 0.45 * wobble) + jitter))
            # Smoothly approach.
            self._target = target * 0.45 + self._target * 0.55
        else:
            self._target *= _DECAY

        self._value = self._target * 0.55 + self._value * 0.45
        if self._value < 0.005:
            self._value = 0.0
        self.amplitude_changed.emit(self._value)
