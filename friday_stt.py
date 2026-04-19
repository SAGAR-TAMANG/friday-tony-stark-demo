"""
Speech-to-text for FRIDAY's fullvoice mode.

Uses faster-whisper with a small English model (tiny.en by default ~75MB)
and sounddevice for mic capture.  Push-to-talk UX: the caller drives
record_until_enter() from the main thread, which returns a numpy float32
mono buffer; transcribe() feeds that to Whisper.

Model is loaded lazily and cached — first call downloads ~75MB once.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

log = logging.getLogger("friday.stt")

SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1

_model_cache: dict[str, WhisperModel] = {}


def load_whisper(size: str = "tiny.en") -> WhisperModel:
    """Load and cache a faster-whisper model.  CPU-only, int8 quant for speed."""
    if size in _model_cache:
        return _model_cache[size]
    log.info("loading whisper model: %s (first run downloads ~75MB)", size)
    model = WhisperModel(size, device="cpu", compute_type="int8")
    _model_cache[size] = model
    return model


def record_until_enter() -> np.ndarray:
    """
    Record from the default input device until the user hits Enter.

    Returns a (N,) float32 array in the range [-1, 1] at 16kHz mono.
    Prints prompts to stdout; uses input() to gate start/stop.
    """
    print("[press ENTER to start recording]", flush=True)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return np.zeros(0, dtype=np.float32)

    chunks: list[np.ndarray] = []
    stop_flag = threading.Event()

    def _on_audio(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        # PortAudio thread — just append; don't do heavy work here.
        if status:
            log.debug("audio status: %s", status)
        chunks.append(indata.copy().flatten())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        callback=_on_audio,
    )

    print("[recording... press ENTER to stop]", flush=True)
    with stream:
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        stop_flag.set()

    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)


def transcribe(model: WhisperModel, audio: np.ndarray) -> str:
    """Transcribe a float32 mono 16kHz buffer; return the joined text."""
    if audio.size == 0 or np.abs(audio).max() < 0.002:
        return ""  # silence or empty
    segments, _info = model.transcribe(
        audio,
        language="en",
        beam_size=1,           # greedy decode — fast on CPU
        vad_filter=True,       # skip silences
        vad_parameters={"min_silence_duration_ms": 500},
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def ensure_stdin_tty() -> bool:
    """Return True if stdin is a terminal (PTT requires interactive input)."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False
