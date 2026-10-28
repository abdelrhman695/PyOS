"""
Animated Background Module
Provides multiple dynamic wallpaper styles:
  - Aurora, Matrix, Waves, Particles, Cosmos, Solid

Supports theme integration: set_theme(theme, accent_hex) tunes the
base palette to match the active color scheme.
"""

import math
import random
import colorsys

from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QFont, QPen, QBrush, QPainterPath
)
from PyQt6.QtWidgets import QWidget


BACKGROUND_STYLES = ["Aurora", "Matrix", "Waves", "Particles", "Cosmos", "Solid"]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        r, g, b = 0, 120, 212
    return r, g, b


class Particle:
    def __init__(self, w, h, mode="particle", base_color: QColor | None = None):
        self.base_color = base_color
        self.reset(w, h, mode)

    def reset(self, w, h, mode):
        self.mode = mode
        if mode == "particle":
            self.x = random.uniform(0, w)
            self.y = random.uniform(0, h)
            self.vx = random.uniform(-0.4, 0.4)
            self.vy = random.uniform(-0.4, 0.4)
            self.radius = random.uniform(1.5, 4.0)
            self.alpha = random.randint(80, 200)
            if self.base_color:
                r = max(0, min(255, self.base_color.red()   + random.randint(-40, 60)))
                g = max(0, min(255, self.base_color.green() + random.randint(-40, 60)))
                b = max(0, min(255, self.base_color.blue()  + random.randint(-40, 60)))
                self.color = QColor(r, g, b, self.alpha)
            else:
                self.color = QColor(
                    random.randint(100, 200),
                    random.randint(150, 255),
                    random.randint(200, 255),
                    self.alpha,
                )
        else:
            self.x = random.uniform(0, w)
            self.y = random.uniform(0, h)
            self.vx = 0
            self.vy = random.uniform(0.05, 0.3)
            self.radius = random.uniform(0.5, 2.5)
            self.alpha = random.randint(100, 255)
            self.color = QColor(255, 255, 255, self.alpha)
        self.w = w
        self.h = h

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if self.mode == "particle":
            if self.x < 0 or self.x > self.w:
                self.vx = -self.vx
            if self.y < 0 or self.y > self.h:
                self.vy = -self.vy
        else:
            if self.y > self.h:
                self.y = 0
                self.x = random.uniform(0, self.w)


MATRIX_CHARS = "ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789"


class MatrixColumn:
    def __init__(self, x, h, col_w, char_color: QColor | None = None):
        self.x = x
        self.col_w = col_w
        self.h = h
        self.y = random.randint(-h, 0)
        self.speed = random.randint(2, 6)
        self.length = random.randint(10, 30)
        self.chars = [random.choice(MATRIX_CHARS) for _ in range(self.length + 2)]
        self.char_color = char_color or QColor(0, 200, 0)

    def update(self):
        self.y += self.speed
        if self.y - self.length * 16 > self.h:
            self.y = random.randint(-200, -50)
            self.speed = random.randint(2, 6)
            self.length = random.randint(10, 30)
        idx = random.randint(0, len(self.chars) - 1)
        self.chars[idx] = random.choice(MATRIX_CHARS)


class AnimatedBackground(QWidget):
    """
    Full-window animated background.
    Call set_style(name) to switch style.
    Call set_theme(theme, accent_hex) to sync colors with the active theme.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        self._style = "Aurora"
        self._t = 0.0
        self._particles: list[Particle] = []
        self._matrix_cols: list[MatrixColumn] = []
        self._font = QFont("Courier New", 13)

        # Theme integration defaults
        self._theme = "dark"
        self._accent_r, self._accent_g, self._accent_b = 0, 120, 212

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(33)

    # ── Public API ────────────────────────────────────────────────────

    def set_style(self, style: str):
        if style not in BACKGROUND_STYLES:
            return
        self._style = style
        self._particles.clear()
        self._matrix_cols.clear()
        self._init_state()
        self.update()

    def set_theme(self, theme: str, accent_hex: str):
        """Sync background palette with the active UI theme and accent color."""
        self._theme = theme
        self._accent_r, self._accent_g, self._accent_b = _hex_to_rgb(accent_hex)
        # Re-init particles/columns with updated colors
        self._particles.clear()
        self._matrix_cols.clear()
        self._init_state()
        self.update()

    # ── Internal ──────────────────────────────────────────────────────

    def _accent_color(self, alpha=255) -> QColor:
        return QColor(self._accent_r, self._accent_g, self._accent_b, alpha)

    def _base_dark(self) -> tuple[QColor, QColor]:
        """Return two background gradient colors influenced by the theme."""
        if self._theme == "light":
            return QColor(180, 200, 230), QColor(210, 220, 245)
        # dark / default
        ar, ag, ab = self._accent_r, self._accent_g, self._accent_b
        c1 = QColor(max(0, ar // 8), max(0, ag // 8), max(0, ab // 6))
        c2 = QColor(max(0, ar // 6), max(0, ag // 6), max(0, ab // 4))
        return c1, c2

    def _init_state(self):
        w, h = self.width() or 1920, self.height() or 1080
        accent_q = self._accent_color()
        if self._style == "Particles":
            self._particles = [
                Particle(w, h, "particle", accent_q) for _ in range(90)
            ]
        elif self._style == "Cosmos":
            self._particles = [Particle(w, h, "cosmos") for _ in range(200)]
        elif self._style == "Matrix":
            col_w = 16
            char_c = self._accent_color(200)
            self._matrix_cols = [
                MatrixColumn(x, h, col_w, char_c)
                for x in range(0, w, col_w)
            ]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._init_state()

    def _tick(self):
        self._t += 0.016
        for p in self._particles:
            p.update()
        for col in self._matrix_cols:
            col.update()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if self._style == "Aurora":
            self._paint_aurora(painter, w, h)
        elif self._style == "Matrix":
            self._paint_matrix(painter, w, h)
        elif self._style == "Waves":
            self._paint_waves(painter, w, h)
        elif self._style == "Particles":
            self._paint_particles(painter, w, h)
        elif self._style == "Cosmos":
            self._paint_cosmos(painter, w, h)
        else:
            self._paint_solid(painter, w, h)

    # ── Paint methods ─────────────────────────────────────────────────

    def _paint_aurora(self, p: QPainter, w, h):
        c1, c2 = self._base_dark()
        base = QLinearGradient(0, 0, 0, h)
        base.setColorAt(0, c1)
        base.setColorAt(1, c2)
        p.fillRect(0, 0, w, h, base)

        ar, ag, ab = self._accent_r, self._accent_g, self._accent_b
        t = self._t
        bands = [
            (0.3 + 0.1  * math.sin(t * 0.4),       QColor(ar, ag, ab, 35),         QColor(ar, ag, ab, 0)),
            (0.5 + 0.15 * math.sin(t * 0.3 + 1.0), QColor(ab // 2, ag // 3, ab, 30), QColor(0, 0, 0, 0)),
            (0.7 + 0.1  * math.sin(t * 0.5 + 2.0), QColor(0, ag, ar, 28),           QColor(0, 0, 0, 0)),
        ]
        for center_y_frac, color_a, color_b in bands:
            cy = int(h * center_y_frac)
            band_h = int(h * 0.25)
            g = QLinearGradient(0, cy - band_h, 0, cy + band_h)
            g.setColorAt(0.0, color_b)
            g.setColorAt(0.5, color_a)
            g.setColorAt(1.0, color_b)
            p.fillRect(0, cy - band_h, w, 2 * band_h, g)

        random.seed(42)
        for _ in range(120):
            sx = random.randint(0, w)
            sy = random.randint(0, h // 2)
            twinkle = abs(math.sin(t + random.random() * 10))
            alpha = int(50 + 200 * twinkle)
            p.setPen(QPen(QColor(255, 255, 255, alpha), 1))
            p.drawPoint(sx, sy)

    def _paint_matrix(self, p: QPainter, w, h):
        p.fillRect(0, 0, w, h, QColor(0, 0, 0))
        p.setFont(self._font)
        ar, ag, ab = self._accent_r, self._accent_g, self._accent_b
        for col in self._matrix_cols:
            for i, ch in enumerate(col.chars):
                cy = col.y - i * 16
                if cy < 0 or cy > h:
                    continue
                fade = 1.0 - i / max(len(col.chars), 1)
                if i == 0:
                    color = QColor(min(255, ar + 60), min(255, ag + 60), min(255, ab + 60), 255)
                else:
                    color = QColor(
                        int(ar * fade * 0.6),
                        int(ag * fade),
                        int(ab * fade * 0.6),
                        int(255 * fade),
                    )
                p.setPen(QPen(color))
                p.drawText(col.x, cy, ch)

    def _paint_waves(self, p: QPainter, w, h):
        c1, c2 = self._base_dark()
        base = QLinearGradient(0, 0, 0, h)
        base.setColorAt(0, c1)
        base.setColorAt(1, c2)
        p.fillRect(0, 0, w, h, base)

        ar, ag, ab = self._accent_r, self._accent_g, self._accent_b
        t = self._t
        wave_defs = [
            (0.03, 60, 0.8, QColor(ar, ag, ab, 30)),
            (0.02, 40, 1.2, QColor(ab // 2, ag // 2, ab, 25)),
            (0.04, 30, 0.5, QColor(ar // 2, ag, ab // 2, 20)),
        ]
        for freq, amp, speed, color in wave_defs:
            path_points = []
            for x in range(0, w + 1, 4):
                y = h // 2 + int(amp * math.sin(x * freq + t * speed))
                path_points.append((x, y))
            path = QPainterPath()
            if path_points:
                path.moveTo(0, h)
                path.lineTo(path_points[0][0], path_points[0][1])
                for px, py in path_points[1:]:
                    path.lineTo(px, py)
                path.lineTo(w, h)
                path.closeSubpath()
                p.fillPath(path, QBrush(color))

    def _paint_particles(self, p: QPainter, w, h):
        c1, c2 = self._base_dark()
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0, c1)
        base.setColorAt(1, c2)
        p.fillRect(0, 0, w, h, base)

        for part in self._particles:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(part.color))
            p.drawEllipse(QPointF(part.x, part.y), part.radius, part.radius)

        pts = self._particles
        for i in range(len(pts)):
            for j in range(i + 1, min(i + 6, len(pts))):
                dx = pts[i].x - pts[j].x
                dy = pts[i].y - pts[j].y
                dist = math.hypot(dx, dy)
                if dist < 120:
                    alpha = int(40 * (1 - dist / 120))
                    p.setPen(QPen(self._accent_color(alpha), 1))
                    p.drawLine(int(pts[i].x), int(pts[i].y), int(pts[j].x), int(pts[j].y))

    def _paint_cosmos(self, p: QPainter, w, h):
        c1, c2 = self._base_dark()
        base = QLinearGradient(0, 0, 0, h)
        base.setColorAt(0, c1)
        base.setColorAt(1, c2)
        p.fillRect(0, 0, w, h, base)

        ar, ag, ab = self._accent_r, self._accent_g, self._accent_b
        for cx_frac, cy_frac, r_frac, alpha in [
            (0.3, 0.4, 0.2, 18),
            (0.7, 0.6, 0.15, 15),
            (0.5, 0.2, 0.25, 12),
        ]:
            grad = QRadialGradient(w * cx_frac, h * cy_frac, w * r_frac)
            grad.setColorAt(0, QColor(ar // 3, ag // 3, ab // 2, alpha))
            grad.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(0, 0, w, h, grad)

        p.setPen(Qt.PenStyle.NoPen)
        for star in self._particles:
            p.setBrush(QBrush(star.color))
            p.drawEllipse(QPointF(star.x, star.y), star.radius, star.radius)

    def _paint_solid(self, p: QPainter, w, h):
        c1, c2 = self._base_dark()
        t = self._t
        shift = int(8 * math.sin(t * 0.2))
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0, c1.lighter(100 + shift))
        grad.setColorAt(0.5, c2)
        grad.setColorAt(1, c1.lighter(100 - shift + 15))
        p.fillRect(0, 0, w, h, grad)
