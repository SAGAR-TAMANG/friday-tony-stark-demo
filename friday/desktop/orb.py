"""The animated FRIDAY orb.

A single custom-painted QWidget that runs at ~60fps and feels alive:

- Breathing radius (low-frequency sine).
- Organic deformation (sum of harmonics around the perimeter).
- Warm radial gradient — hot white-amber core, fading to deep red.
- Rotating outer arc rings (HUD shoulder).
- Drifting particles ("motes") at random orbits.
- State-driven colour shift — idle / listening / thinking / speaking.

No external image assets. Pure paint.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import (
    QPointF, QRectF, QTimer, Qt, Property, QEasingCurve,
    QPropertyAnimation,
)
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from . import theme
from .audio_bus import AudioBus


@dataclass
class Mote:
    radius: float      # orbital radius (multiplier of base_r)
    theta: float       # current angle
    speed: float       # angular speed (rad / tick)
    size: float        # pixel size
    alpha: float       # 0..255


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _mix(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(
        int(_lerp(c1.red(),   c2.red(),   t)),
        int(_lerp(c1.green(), c2.green(), t)),
        int(_lerp(c1.blue(),  c2.blue(),  t)),
        int(_lerp(c1.alpha(), c2.alpha(), t)),
    )


class Orb(QWidget):
    """Living orb widget. Drop it anywhere — it'll fill itself."""

    # Recognised states. Anything else falls back to "idle".
    STATES = ("idle", "listening", "thinking", "speaking")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMinimumSize(360, 360)

        self._phase = 0.0
        self._state = "idle"
        # state_blend → 0 = base palette, 1 = state palette. Animated.
        self._state_blend = 0.0
        self._intensity = 1.0        # extra brightness on "speaking"
        self._speak_anim = 0.0       # used by speaking ripple

        # Amplitude-driven extras (sonar rings + equalizer bars).
        self._amp = 0.0
        self._rings: list[dict] = []   # each: {age, max_age, intensity}
        self._ring_cooldown = 0.0
        AudioBus.instance().amplitude_changed.connect(self._on_amp)

        random.seed(7)
        self._motes: list[Mote] = [
            Mote(
                radius=random.uniform(1.6, 3.4),
                theta=random.uniform(0, 2 * math.pi),
                speed=random.uniform(-0.012, 0.012),
                size=random.uniform(1.0, 2.4),
                alpha=random.uniform(60, 180),
            )
            for _ in range(46)
        ]

        # Animation tick.
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(16)  # ~60fps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        if state not in self.STATES:
            state = "idle"
        if state == self._state:
            return
        self._state = state
        # Animate the blend smoothly toward the new palette.
        target = 0.0 if state == "idle" else 1.0
        anim = QPropertyAnimation(self, b"stateBlend", self)
        anim.setDuration(450)
        anim.setStartValue(self._state_blend)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def pulse(self, magnitude: float = 1.0) -> None:
        """One-shot brightness kick. Use when she finishes a tool call."""
        self._intensity = min(2.0, self._intensity + magnitude)

    def _on_amp(self, value: float) -> None:
        self._amp = value

    # Qt property so QPropertyAnimation can drive _state_blend.
    def _get_blend(self) -> float: return self._state_blend
    def _set_blend(self, v: float) -> None:
        self._state_blend = float(v)
        self.update()
    stateBlend = Property(float, _get_blend, _set_blend)

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def _on_tick(self) -> None:
        self._phase += 0.04
        # Speaking ripple gently decays back to 0.
        self._speak_anim *= 0.92
        if self._state == "speaking" and self._speak_anim < 0.4:
            self._speak_anim = min(1.0, self._speak_anim + random.uniform(0.1, 0.6))
        # Intensity decays back to 1.
        self._intensity = _lerp(self._intensity, 1.0, 0.04)
        # Advance motes around their orbits.
        for m in self._motes:
            m.theta += m.speed

        # Sonar rings: spawn while speaking, age all rings every tick.
        self._ring_cooldown -= 1
        if self._state == "speaking" and self._amp > 0.05 and self._ring_cooldown <= 0:
            self._rings.append({
                "age": 0.0,
                "max_age": 55.0,
                "intensity": min(1.0, 0.5 + self._amp),
            })
            # Faster cadence when louder.
            self._ring_cooldown = max(4, int(14 - self._amp * 10))
        alive = []
        for ring in self._rings:
            ring["age"] += 1.0
            if ring["age"] < ring["max_age"]:
                alive.append(ring)
        self._rings = alive[-6:]   # cap to 6 concurrent rings

        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        base_r = min(w, h) * 0.20

        # ── 1. Backdrop wash ────────────────────────────────────────────
        wash = QRadialGradient(cx, cy, max(w, h) * 0.7)
        wash.setColorAt(0.0, QColor(20, 50, 90, 110))
        wash.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(wash)
        p.drawRect(self.rect())

        # ── 2. Halo bloom ───────────────────────────────────────────────
        halo_r = base_r * (4.2 + 0.15 * math.sin(self._phase * 1.3))
        halo = QRadialGradient(cx, cy, halo_r)
        c_halo = self._tinted(theme.ORB_HALO)
        halo.setColorAt(0.00, QColor(c_halo.red(), c_halo.green(), c_halo.blue(), 75))
        halo.setColorAt(0.45, QColor(c_halo.red(), c_halo.green(), c_halo.blue(), 22))
        halo.setColorAt(1.00, QColor(c_halo.red(), c_halo.green(), c_halo.blue(),  0))
        p.setBrush(halo)
        p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        # ── 2.5  Sonar rings (born at orb body, expand + fade) ─────────
        if self._rings:
            for ring in self._rings:
                t = ring["age"] / ring["max_age"]   # 0..1
                # Ease-out: fast early expansion, slow finish.
                eased = 1.0 - (1.0 - t) ** 2.5
                radius = base_r * (1.05 + eased * 3.6)
                alpha = int(max(0, 220 * (1.0 - t) * ring["intensity"]))
                width = max(1.0, 3.5 * (1.0 - t) + 0.5)
                rc = self._tinted(theme.ORB_HALO, lighten=0.15)
                pen = QPen(QColor(rc.red(), rc.green(), rc.blue(), alpha))
                pen.setWidthF(width)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), radius, radius)

        # ── 2.6  Equalizer arc (radial bars driven by AudioBus) ─────────
        if self._amp > 0.02 and self._state in ("speaking", "listening"):
            N_BARS = 36
            inner = base_r * 1.30
            max_len = base_r * 0.55
            # Per-bar amplitude with a soft pseudo-spectrum.
            bar_color = self._tinted(
                theme.ORB_HALO if self._state == "speaking" else theme.ORB_LISTEN,
                lighten=0.18,
            )
            pen = QPen(QColor(bar_color.red(), bar_color.green(),
                              bar_color.blue(), 200))
            pen.setWidthF(2.0)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            for i in range(N_BARS):
                theta = 2 * math.pi * i / N_BARS - math.pi / 2
                # Each bar samples a different phase so they don't all
                # peak at once.
                local = (
                    0.55 + 0.45 * math.sin(self._phase * 3.0 + i * 0.7)
                ) * (0.4 + 0.6 * self._amp)
                length = max_len * max(0.05, local)
                x0 = cx + inner * math.cos(theta)
                y0 = cy + inner * math.sin(theta)
                x1 = cx + (inner + length) * math.cos(theta)
                y1 = cy + (inner + length) * math.sin(theta)
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

        # ── 3. Rotating arc rings ───────────────────────────────────────
        speed_mul = {"idle": 1.0, "listening": 1.6, "thinking": 2.2, "speaking": 1.3}[self._state]
        ring_specs = [
            # (radius_mult, base_speed, line_width, alpha, arc_span_deg, n_arcs)
            (2.55, 0.28,  1.4, 110, 70, 3),
            (3.05, -0.18, 0.8,  60, 40, 4),
            (2.15, 0.42,  1.8, 140, 30, 2),
        ]
        ring_color = self._tinted(theme.ORB_HALO, lighten=0.10)
        p.save()
        p.translate(cx, cy)
        for r_mult, base_speed, lw, alpha, span_deg, n_arcs in ring_specs:
            radius = base_r * r_mult
            pen = QPen(QColor(ring_color.red(), ring_color.green(), ring_color.blue(), alpha))
            pen.setWidthF(lw)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            rot_deg = (self._phase * base_speed * speed_mul * 180.0 / math.pi) * 6
            for j in range(n_arcs):
                start = (j * (360 / n_arcs) + rot_deg) % 360
                # Qt drawArc uses 1/16 degree.
                p.drawArc(
                    QRectF(-radius, -radius, radius * 2, radius * 2),
                    int(start * 16), int(span_deg * 16),
                )
        p.restore()

        # ── 4. Motes (drifting particles around the orb) ────────────────
        mote_color = self._tinted(theme.ORB_MID, lighten=0.20)
        for m in self._motes:
            r = base_r * m.radius
            x = cx + r * math.cos(m.theta)
            y = cy + r * math.sin(m.theta)
            # Twinkle.
            twinkle = 0.6 + 0.4 * math.sin(self._phase * 1.7 + m.theta * 3.0)
            a = int(max(0, min(255, m.alpha * twinkle)))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(mote_color.red(), mote_color.green(), mote_color.blue(), a))
            p.drawEllipse(QPointF(x, y), m.size, m.size)

        # ── 5. Orb body — organic deformed disk ─────────────────────────
        breath = 1.0 + 0.045 * math.sin(self._phase * 1.1)
        speak = self._speak_anim if self._state == "speaking" else 0.0
        N = 96
        poly = QPolygonF()
        for k in range(N):
            theta = 2 * math.pi * k / N
            deform = (
                0.055 * math.sin(3 * theta + self._phase * 1.6) +
                0.030 * math.sin(5 * theta - self._phase * 0.9) +
                0.018 * math.sin(7 * theta + self._phase * 2.3) +
                0.040 * speak * math.sin(9 * theta + self._phase * 5.5)
            )
            r = base_r * breath * (1.0 + deform)
            poly.append(QPointF(cx + r * math.cos(theta), cy + r * math.sin(theta)))

        body = QRadialGradient(cx - base_r * 0.22, cy - base_r * 0.28, base_r * 1.7)
        core = self._tinted(theme.ORB_CORE, lighten=0.0)
        mid  = self._tinted(theme.ORB_MID)
        deep = self._tinted(theme.ORB_DEEP)
        dark = self._tinted(theme.ORB_DARK)
        i = min(1.0, self._intensity)
        body.setColorAt(0.00, QColor(core.red(), core.green(), core.blue(), int(255 * i)))
        body.setColorAt(0.28, QColor(mid.red(),  mid.green(),  mid.blue(),  235))
        body.setColorAt(0.65, QColor(deep.red(), deep.green(), deep.blue(), 215))
        body.setColorAt(1.00, QColor(dark.red(), dark.green(), dark.blue(), 150))
        p.setBrush(body)
        p.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        p.drawPath(path)

        # ── 6. Specular highlight ───────────────────────────────────────
        hx, hy = cx - base_r * 0.35, cy - base_r * 0.42
        hi = QRadialGradient(hx, hy, base_r * 0.55)
        hi.setColorAt(0.0, QColor(245, 252, 255, 200))
        hi.setColorAt(1.0, QColor(245, 252, 255,   0))
        p.setBrush(hi)
        p.drawEllipse(QPointF(hx, hy), base_r * 0.55, base_r * 0.55)

        # ── 7. Inner rim glow (subtle ring just inside the body) ────────
        rim = QRadialGradient(cx, cy, base_r * 1.05)
        rim.setColorAt(0.85, QColor(160, 220, 255,   0))
        rim.setColorAt(0.97, QColor(160, 220, 255,  70))
        rim.setColorAt(1.00, QColor(160, 220, 255,   0))
        p.setBrush(rim)
        p.drawEllipse(QPointF(cx, cy), base_r * 1.05, base_r * 1.05)

        p.end()

    # ------------------------------------------------------------------
    # Colour helpers
    # ------------------------------------------------------------------

    def _state_color(self) -> QColor:
        if self._state == "listening": return theme.ORB_LISTEN
        if self._state == "thinking":  return theme.ORB_THINK
        return theme.ORB_HALO  # idle / speaking → no shift

    def _tinted(self, base: QColor, lighten: float = 0.0) -> QColor:
        """Blend the warm base toward the current state's tint."""
        c = base
        if lighten > 0:
            c = QColor(
                min(255, int(c.red()   + (255 - c.red())   * lighten)),
                min(255, int(c.green() + (255 - c.green()) * lighten)),
                min(255, int(c.blue()  + (255 - c.blue())  * lighten)),
                c.alpha(),
            )
        if self._state in ("listening", "thinking") and self._state_blend > 0:
            c = _mix(c, self._state_color(), self._state_blend * 0.5)
        return c
