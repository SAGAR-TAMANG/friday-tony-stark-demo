"""Voice input — mic button + click-to-toggle capture + Whisper transcribe.

Click the mic button → recording starts (red pulsing glow). Click again
→ recording stops, audio gets pushed to OpenAI Whisper, the transcript
is emitted as text. From the brain's point of view this is identical to
the user typing a message.

Captures at 16 kHz mono int16 (Whisper's sweet spot, ~32 KB/sec). Audio
is buffered in-memory and written to a temp WAV only when the user
stops talking. While recording, RMS amplitude is pushed onto the
``AudioBus`` so the orb and HUD react to the user's voice in real time.

If ``OPENAI_API_KEY`` is missing the button paints itself disabled and
shows a tooltip.
"""

from __future__ import annotations

import math
import os
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QPushButton

from . import theme
from .audio_bus import AudioBus


SAMPLE_RATE = 16_000
CHANNELS = 1


class VoiceCapture(QObject):
    """Owns a sounddevice InputStream + the buffer + the Whisper call.

    Lifecycle:
        idle  -> recording -> transcribing -> idle
    """

    state_changed = Signal(str)    # "idle" | "recording" | "transcribing"
    transcribed = Signal(str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "idle"
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def toggle(self) -> None:
        if self._state == "idle":
            self._start()
        elif self._state == "recording":
            self._stop_and_transcribe()
        # transcribing → ignore clicks

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _set_state(self, state: str) -> None:
        self._state = state
        self.state_changed.emit(state)

    def _start(self) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            self.error.emit(f"sounddevice unavailable: {exc}")
            return

        with self._lock:
            self._chunks = []

        def _cb(indata, frames, _time, status):
            if status:
                # Drop xruns silently — surfacing them would spam the log.
                pass
            chunk = np.copy(indata[:, 0])
            with self._lock:
                self._chunks.append(chunk)
            # Push amplitude (RMS) onto the bus for live HUD feedback.
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) + 1e-9)
            # int16 max amplitude ≈ 32767. Map to [0,1] with a soft knee.
            norm = min(1.0, rms / 8000.0)
            AudioBus.instance().push_rms(norm)

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                callback=_cb,
                blocksize=1024,
            )
            self._stream.start()
        except Exception as exc:
            self.error.emit(f"mic open failed: {exc}")
            return

        self._set_state("recording")

    def _stop_and_transcribe(self) -> None:
        self._set_state("transcribing")
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None

        # Run the upload + transcribe on a worker thread so the UI never
        # blocks waiting for Whisper.
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        with self._lock:
            if not self._chunks:
                self._set_state("idle")
                return
            audio = np.concatenate(self._chunks)

        # Sanity gate — < 0.4s of audio almost never transcribes to
        # anything useful and just wastes an API call.
        if audio.size < int(SAMPLE_RATE * 0.4):
            self._set_state("idle")
            return

        try:
            tmp = Path(tempfile.gettempdir()) / "friday-voicein.wav"
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(CHANNELS)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes(audio.tobytes())

            from openai import OpenAI
            client = OpenAI()
            with tmp.open("rb") as fh:
                resp = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=fh,
                )
            text = (getattr(resp, "text", "") or "").strip()
            if text:
                self.transcribed.emit(text)
        except Exception as exc:
            self.error.emit(f"transcribe failed: {exc}")
        finally:
            self._set_state("idle")


class MicButton(QPushButton):
    """Round HUD button with three visual states: idle / recording / busy."""

    SIZE = 28

    def __init__(self, capture: VoiceCapture, parent=None):
        super().__init__(parent)
        self._capture = capture
        self._state = "idle"
        self._phase = 0.0
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("background: transparent; border: none;")
        if not capture.available():
            self.setEnabled(False)
            self.setToolTip("Whisper offline — set OPENAI_API_KEY")
        else:
            self.setToolTip("Click to talk · click again to send")

        self.clicked.connect(self._capture.toggle)
        self._capture.state_changed.connect(self._on_state)

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(33)

    def _on_state(self, state: str) -> None:
        self._state = state
        self.update()

    def _tick(self) -> None:
        self._phase += 0.18
        if self._state != "idle":
            self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        cx, cy = r.width() / 2, r.height() / 2
        radius = self.SIZE / 2 - 4

        enabled = self.isEnabled()
        if not enabled:
            ring = theme.TEXT_FAINT
            icon = theme.TEXT_FAINT
        elif self._state == "recording":
            pulse = 0.5 + 0.5 * math.sin(self._phase)
            ring = QColor(
                theme.HUD_RED.red(),
                theme.HUD_RED.green(),
                theme.HUD_RED.blue(),
                int(180 + 70 * pulse),
            )
            # Outer glow ring while recording.
            for k, alpha in enumerate((40, 25, 14)):
                glow = QColor(theme.HUD_RED.red(), theme.HUD_RED.green(),
                              theme.HUD_RED.blue(), int(alpha * (0.6 + 0.4 * pulse)))
                p.setPen(Qt.NoPen)
                p.setBrush(glow)
                p.drawEllipse(int(cx - radius - 2 - k * 2),
                              int(cy - radius - 2 - k * 2),
                              int((radius + 2 + k * 2) * 2),
                              int((radius + 2 + k * 2) * 2))
            icon = theme.HUD_RED
        elif self._state == "transcribing":
            ring = theme.HUD_AMBER
            icon = theme.HUD_AMBER
        else:
            ring = theme.HUD_CYAN
            icon = theme.HUD_CYAN

        # Ring.
        pen = p.pen()
        from PySide6.QtGui import QPen
        pen = QPen(ring)
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(int(cx - radius), int(cy - radius),
                      int(radius * 2), int(radius * 2))

        # Mic glyph — minimalist: a vertical capsule + base bracket.
        p.setPen(Qt.NoPen)
        p.setBrush(icon)
        body_w = max(4, int(radius * 0.55))
        body_h = max(8, int(radius * 1.1))
        p.drawRoundedRect(int(cx - body_w / 2), int(cy - body_h / 2),
                          body_w, body_h, body_w / 2, body_w / 2)
        # Base arc.
        pen = QPen(icon)
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        arc_r = int(radius * 0.8)
        from PySide6.QtCore import QRectF
        p.drawArc(QRectF(cx - arc_r, cy - arc_r * 0.7, arc_r * 2, arc_r * 1.5),
                  200 * 16, 140 * 16)
