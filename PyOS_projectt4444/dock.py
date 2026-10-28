# """
# dock.py — PyOS Futuristic Dock  (drop-in replacement for the Dock / DockIcon
#           section that lives inside main_gui.py)

# Drop-in usage
# ─────────────
# Replace the existing Dock / DockIcon classes in main_gui.py with:

#     from dock import Dock, DockIcon          # (or just paste this file in)

# The public API is identical:
#     dock = Dock(parent)
#     dock.add_icon(emoji, label, callback, with_separator=False)  → DockIcon
#     dock.set_active(label, True/False)

# Key improvements over the original
# ────────────────────────────────────
# • Icons NEVER overlap — dynamic spacing pushes neighbours aside with spring
# • Glow is soft, layered, perceptually correct (inner + outer, capped alpha)
# • Tooltip is centred above the icon (not clipped by neighbours), fade-in
# • Dock height grows during hover so enlarged icons are never cropped
# • All animations (scale · glow · tooltip · spacing) share one master timer
# • Active indicator: animated glowing pill under the icon (minimal, modern)
# • GPU-friendly: pixmap-cached emoji, minimal blur passes, no QGraphicsEffect

# Palette (cyber dark purple / blue)
# ────────────────────────────────────
#   GLOW_INNER   #8ab4ff  (periwinkle)
#   GLOW_OUTER   #5070c8  (medium blue)
#   ACTIVE_RING  #a07aff  (violet)
#   DOT          #c8e0ff  (ice blue)
#   BG_TOP       rgba(38,28,72, .82)
#   BG_BOT       rgba( 8, 5,24, .92)
# """

# from __future__ import annotations

# import math
# from typing import List, Optional

# from PyQt6.QtCore import (
#     Qt, QTimer, QRect, QRectF, QPointF, pyqtSignal
# )
# from PyQt6.QtGui import (
#     QColor, QFont, QPainter, QLinearGradient, QRadialGradient,
#     QBrush, QPen, QFontMetrics, QPixmap
# )
# from PyQt6.QtWidgets import QWidget, QFrame, QSizePolicy


# # ═══════════════════════════════════════════════════════════════════
# #  Theme colours — single source of truth
# # ═══════════════════════════════════════════════════════════════════

# class _T:
#     GLOW_INNER  = QColor(138, 180, 255)
#     GLOW_OUTER  = QColor( 80, 112, 200)
#     ACTIVE      = QColor(160, 122, 255)
#     DOT         = QColor(200, 225, 255)
#     TIP_BG_TOP  = QColor( 40,  30,  85, 215)
#     TIP_BG_BOT  = QColor( 18,  12,  48, 235)
#     TIP_BORDER  = QColor(160, 185, 255, 90)
#     TIP_TEXT    = QColor(235, 242, 255)
#     DOCK_TOP    = QColor( 38,  28,  72, 205)
#     DOCK_BOT    = QColor(  8,   5,  24, 232)
#     BORDER_HI   = QColor(255, 255, 255, 70)
#     BORDER_LO   = QColor(130, 100, 255, 50)


# # ═══════════════════════════════════════════════════════════════════
# #  Emoji pixmap cache  (avoids re-rasterising on every frame)
# # ═══════════════════════════════════════════════════════════════════

# _emoji_cache: dict[tuple[str, int], QPixmap] = {}

# def _emoji_pixmap(emoji: str, size: int) -> QPixmap:
#     key = (emoji, size)
#     if key not in _emoji_cache:
#         px = QPixmap(size, size)
#         px.fill(Qt.GlobalColor.transparent)
#         p = QPainter(px)
#         p.setRenderHint(QPainter.RenderHint.Antialiasing)
#         f = QFont()
#         f.setPointSize(max(10, int(size * 0.42)))
#         p.setFont(f)
#         p.setPen(Qt.GlobalColor.white)
#         p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, emoji)
#         p.end()
#         _emoji_cache[key] = px
#     return _emoji_cache[key]


# # ═══════════════════════════════════════════════════════════════════
# #  Spring helper
# # ═══════════════════════════════════════════════════════════════════

# class _Spring:
#     """Damped spring.  call step() every frame → returns current value."""
#     __slots__ = ("cur", "vel", "tgt", "_ks", "_kd")

#     def __init__(self, ks: float = 0.28, kd: float = 0.64, initial: float = 0.0):
#         self.cur  = initial
#         self.vel  = 0.0
#         self.tgt  = initial
#         self._ks  = ks
#         self._kd  = kd

#     def step(self) -> float:
#         diff     = self.tgt - self.cur
#         self.vel = self.vel * self._kd + diff * self._ks
#         self.cur += self.vel
#         self.cur  = max(-0.06, min(1.10, self.cur))
#         return self.cur

#     @property
#     def settled(self) -> bool:
#         return abs(self.tgt - self.cur) < 0.002 and abs(self.vel) < 0.002


# # ═══════════════════════════════════════════════════════════════════
# #  DockIcon
# # ═══════════════════════════════════════════════════════════════════

# class DockIcon(QWidget):
#     """
#     A single dock icon.

#     Layout contract
#     ───────────────
#     The widget always occupies SLOT_W × DOCK_H pixels.
#     The icon face grows *upward* from the bottom edge, so the
#     dock floor never shifts — exactly like macOS.

#     The Dock parent adjusts its own minimum height via
#     sizeHint() so enlarged icons are never cropped.
#     """

#     clicked = pyqtSignal()

#     # ── geometry constants ──────────────────────────────────────────
#     BASE   = 46          # resting icon face size (px)
#     PEAK   = 70          # maximum face size at full magnification
#     SLOT_W = 62          # slot width  — NEVER changes
#     DOCK_H = 92          # slot height — matches dock container

#     def __init__(self, emoji: str, label: str, parent: Optional[QWidget] = None):
#         super().__init__(parent)
#         self._emoji   = emoji
#         self._label   = label
#         self._active  = False
#         self._hover   = False

#         # springs
#         self._mag     = _Spring(ks=0.26, kd=0.65)   # magnification  [0..1]
#         self._glow    = _Spring(ks=0.18, kd=0.60)   # glow intensity [0..1]
#         self._tip     = _Spring(ks=0.22, kd=0.62)   # tooltip alpha  [0..1]
#         self._active_s= _Spring(ks=0.14, kd=0.68)   # active pill    [0..1]
#         self._pill    = _Spring(ks=0.20, kd=0.65)   # active pulse helper

#         # phases (always-running oscillators)
#         self._phase   = 0.0    # active pulse phase
#         self._bounce  = 0.0    # launch bounce phase
#         self._bouncing = False

#         self.setFixedSize(self.SLOT_W, self.DOCK_H)
#         self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
#         self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
#         self.setCursor(Qt.CursorShape.PointingHandCursor)

#     # ── public API ──────────────────────────────────────────────────

#     def set_active(self, active: bool) -> None:
#         self._active = active
#         self._active_s.tgt = 1.0 if active else 0.0

#     # ── driven by Dock master timer ──────────────────────────────────

#     def step(self) -> bool:
#         """Advance all springs one tick.  Returns True if still animating."""
#         self._mag.step()
#         self._glow.step()
#         self._tip.step()
#         self._active_s.step()

#         self._phase = (self._phase + 0.052) % (2 * math.pi)
#         if self._bouncing:
#             self._bounce += 0.10
#             if self._bounce > 2 * math.pi:
#                 self._bounce  = 0.0
#                 self._bouncing = False

#         self.update()

#         busy = (
#             not self._mag.settled or not self._glow.settled
#             or not self._tip.settled or not self._active_s.settled
#             or self._bouncing or self._active
#         )
#         return busy

#     def trigger_bounce(self) -> None:
#         self._bouncing = True
#         self._bounce   = 0.0
#         self._mag.vel -= 0.45

#     # ── events ──────────────────────────────────────────────────────

#     def mousePressEvent(self, _e):
#         self.clicked.emit()
#         self.trigger_bounce()

#     def enterEvent(self, _e):
#         self._hover      = True
#         self._glow.tgt   = 1.0
#         self._tip.tgt    = 1.0

#     def leaveEvent(self, _e):
#         self._hover      = False
#         self._glow.tgt   = 0.0
#         self._tip.tgt    = 0.0
#         self.update()

#     # ── paint ────────────────────────────────────────────────────────

#     def paintEvent(self, _e):
#         p = QPainter(self)
#         p.setRenderHint(QPainter.RenderHint.Antialiasing)
#         p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

#         W, H  = self.width(), self.height()
#         mag   = max(0.0, min(1.0, self._mag.cur))
#         glow  = max(0.0, min(1.0, self._glow.cur))
#         tip_a = max(0.0, min(1.0, self._tip.cur))
#         act   = max(0.0, min(1.0, self._active_s.cur))
#         pulse = math.sin(self._phase)

#         # bounce offset
#         bounce_y = 0
#         if self._bouncing:
#             bounce_y = int(-11 * math.sin(self._bounce)
#                            * math.exp(-self._bounce * 0.55))

#         # ── icon geometry — pinned-to-bottom, grows upward ───────────
#         sz   = int(self.BASE + (self.PEAK - self.BASE) * mag)
#         sz   = max(self.BASE, min(self.PEAK + 2, sz))
#         ix   = (W - sz) // 2
#         iy   = H - sz - 10 + bounce_y
#         face = QRect(ix, iy, sz, sz)
#         rad  = max(9, sz // 5)

#         # ── 1. Outer ambient glow ─────────────────────────────────────
#         if glow > 0.02 or act > 0.02:
#             gc   = _T.ACTIVE if self._active else _T.GLOW_OUTER
#             str_ = min(glow * 0.9 + act * 0.5, 1.0)
#             for expand, base_a in ((16, 8), (10, 16), (5, 28)):
#                 a = int(base_a * str_)
#                 if a > 1:
#                     p.setPen(Qt.PenStyle.NoPen)
#                     p.setBrush(QBrush(QColor(gc.red(), gc.green(), gc.blue(), a)))
#                     p.drawRoundedRect(
#                         face.adjusted(-expand, -expand, expand, expand),
#                         rad + expand, rad + expand)

#         # ── 2. Inner tight glow ring ──────────────────────────────────
#         if glow > 0.05 or act > 0.05:
#             ic   = _T.ACTIVE if self._active else _T.GLOW_INNER
#             ia   = int(min((glow + act * 0.6) * 48, 55))
#             if ia > 2:
#                 p.setPen(Qt.PenStyle.NoPen)
#                 p.setBrush(QBrush(QColor(ic.red(), ic.green(), ic.blue(), ia)))
#                 p.drawRoundedRect(
#                     face.adjusted(-3, -3, 3, 3), rad + 3, rad + 3)

#         # ── 3. Glass body ─────────────────────────────────────────────
#         hb   = 20 if self._hover else 0
#         body = QLinearGradient(ix, iy, ix, iy + sz)
#         body.setColorAt(0.00, QColor(255, 255, 255, 60 + hb + int(28 * mag)))
#         body.setColorAt(0.30, QColor(210, 220, 255, 30 + hb + int(14 * mag)))
#         body.setColorAt(0.65, QColor(150, 170, 240, 20  + int( 9 * mag)))
#         body.setColorAt(1.00, QColor( 90, 115, 200, 12  + int( 6 * mag)))
#         p.setBrush(QBrush(body))
#         p.setPen(Qt.PenStyle.NoPen)
#         p.drawRoundedRect(face, rad, rad)

#         # ── 4. Inner depth shadow ─────────────────────────────────────
#         dep = QLinearGradient(ix, iy + sz * 0.55, ix, iy + sz)
#         dep.setColorAt(0.0, QColor(0, 0, 0, 0))
#         dep.setColorAt(1.0, QColor(0, 0, 0, 26 + int(16 * mag)))
#         p.setBrush(QBrush(dep))
#         p.drawRoundedRect(face.adjusted(1, 1, -1, -1), rad - 1, rad - 1)

#         # ── 5. Top frosted shine ──────────────────────────────────────
#         sh = QLinearGradient(ix, iy, ix, iy + sz * 0.42)
#         sh.setColorAt(0.0, QColor(255, 255, 255, 64 + hb))
#         sh.setColorAt(0.5, QColor(255, 255, 255, 16))
#         sh.setColorAt(1.0, QColor(255, 255, 255,  0))
#         p.setBrush(QBrush(sh))
#         p.drawRoundedRect(face.adjusted(1, 1, -1, -int(sz * 0.58)), rad - 1, rad - 1)

#         # ── 6. Border ─────────────────────────────────────────────────
#         if self._active:
#             pulse_a = int((90 + 60 * mag) * (0.72 + 0.28 * pulse))
#             ac = _T.ACTIVE
#             p.setPen(QPen(QColor(ac.red(), ac.green(), ac.blue(), pulse_a), 1.5))
#             p.setBrush(Qt.BrushStyle.NoBrush)
#             p.drawRoundedRect(face.adjusted(-1, -1, 1, 1), rad + 1, rad + 1)
#             p.setPen(QPen(QColor(255, 255, 255, pulse_a // 3), 0.8))
#             p.drawRoundedRect(face, rad, rad)
#         else:
#             ba   = int(55 + 80 * mag) if self._hover else int(35 + 30 * mag)
#             bg   = QLinearGradient(ix, iy, ix + sz, iy + sz)
#             bg.setColorAt(0.0, QColor(255, 255, 255, ba))
#             bg.setColorAt(0.5, QColor(180, 200, 255, ba // 2))
#             bg.setColorAt(1.0, QColor(140, 160, 255, ba // 3))
#             p.setPen(QPen(QBrush(bg), 1.0))
#             p.setBrush(Qt.BrushStyle.NoBrush)
#             p.drawRoundedRect(face, rad, rad)

#         # ── 7. Emoji (cached pixmap) ──────────────────────────────────
#         px = _emoji_pixmap(self._emoji, sz)
#         p.drawPixmap(ix, iy, px)

#         # ── 8. Tooltip — frosted glassmorphism pill ───────────────────
#         if tip_a > 0.02:
#             lf  = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
#             fm  = QFontMetrics(lf)
#             lw  = fm.horizontalAdvance(self._label) + 24
#             lh  = fm.height() + 12
#             # centre above the face, clamp to widget bounds
#             lx  = max(0, min(W - lw, (W - lw) // 2))
#             ly  = iy - lh - 10
#             if ly >= 0:
#                 a255 = int(tip_a * 255)
#                 # frosted background
#                 tg  = QLinearGradient(lx, ly, lx, ly + lh)
#                 tg.setColorAt(0.0, QColor(_T.TIP_BG_TOP.red(),
#                                           _T.TIP_BG_TOP.green(),
#                                           _T.TIP_BG_TOP.blue(),
#                                           min(a255, 215)))
#                 tg.setColorAt(1.0, QColor(_T.TIP_BG_BOT.red(),
#                                           _T.TIP_BG_BOT.green(),
#                                           _T.TIP_BG_BOT.blue(),
#                                           min(a255, 235)))
#                 p.setBrush(QBrush(tg))
#                 p.setPen(QPen(QColor(_T.TIP_BORDER.red(),
#                                      _T.TIP_BORDER.green(),
#                                      _T.TIP_BORDER.blue(),
#                                      int(_T.TIP_BORDER.alpha() * tip_a)), 1.0))
#                 corner = lh // 2
#                 p.drawRoundedRect(lx, ly, lw, lh, corner, corner)
#                 # shine
#                 ts = QLinearGradient(lx, ly, lx, ly + lh * 0.5)
#                 ts.setColorAt(0.0, QColor(255, 255, 255, int(tip_a * 38)))
#                 ts.setColorAt(1.0, QColor(255, 255, 255, 0))
#                 p.setBrush(QBrush(ts))
#                 p.setPen(Qt.PenStyle.NoPen)
#                 p.drawRoundedRect(lx, ly, lw, int(lh * 0.5), corner, corner)
#                 # text
#                 p.setFont(lf)
#                 p.setPen(QPen(QColor(_T.TIP_TEXT.red(),
#                                      _T.TIP_TEXT.green(),
#                                      _T.TIP_TEXT.blue(),
#                                      a255)))
#                 p.drawText(QRect(lx, ly, lw, lh),
#                            Qt.AlignmentFlag.AlignCenter, self._label)

#         # ── 9. Active indicator — animated glowing pill ───────────────
#         if act > 0.02:
#             pill_w   = int((16 + 14 * act) * (0.85 + 0.15 * pulse))
#             pill_h   = 3
#             pill_x   = (W - pill_w) // 2
#             pill_y   = H - 7
#             dc  = _T.DOT
#             dg  = QLinearGradient(pill_x, pill_y,
#                                   pill_x + pill_w, pill_y)
#             a_c = int(act * (170 + 55 * pulse))
#             a_e = int(act * 30)
#             dg.setColorAt(0.0, QColor(dc.red(), dc.green(), dc.blue(), a_e))
#             dg.setColorAt(0.5, QColor(dc.red(), dc.green(), dc.blue(), a_c))
#             dg.setColorAt(1.0, QColor(dc.red(), dc.green(), dc.blue(), a_e))
#             # halo
#             hg  = QLinearGradient(pill_x - 4, pill_y - 2,
#                                   pill_x + pill_w + 4, pill_y + pill_h + 2)
#             hg.setColorAt(0.0, QColor(dc.red(), dc.green(), dc.blue(), 0))
#             hg.setColorAt(0.5, QColor(dc.red(), dc.green(), dc.blue(),
#                                       int(act * 28)))
#             hg.setColorAt(1.0, QColor(dc.red(), dc.green(), dc.blue(), 0))
#             p.setPen(Qt.PenStyle.NoPen)
#             p.setBrush(QBrush(hg))
#             p.drawRoundedRect(pill_x - 4, pill_y - 2,
#                               pill_w + 8, pill_h + 4, 3, 3)
#             p.setBrush(QBrush(dg))
#             p.drawRoundedRect(pill_x, pill_y, pill_w, pill_h,
#                               pill_h // 2, pill_h // 2)

#         # ── 10. Hover light-bar ───────────────────────────────────────
#         if glow > 0.08:
#             ba2  = int(glow * 90)
#             bw   = int(sz * 0.55)
#             bx   = (W - bw) // 2
#             bg_y = H - 7
#             blg  = QLinearGradient(bx, bg_y, bx + bw, bg_y)
#             gc2  = _T.GLOW_INNER
#             blg.setColorAt(0.0, QColor(gc2.red(), gc2.green(), gc2.blue(), 0))
#             blg.setColorAt(0.5, QColor(gc2.red(), gc2.green(), gc2.blue(), ba2))
#             blg.setColorAt(1.0, QColor(gc2.red(), gc2.green(), gc2.blue(), 0))
#             p.setBrush(QBrush(blg))
#             p.setPen(Qt.PenStyle.NoPen)
#             p.drawRoundedRect(bx, bg_y, bw, 2, 1, 1)


# # ═══════════════════════════════════════════════════════════════════
# #  Dock
# # ═══════════════════════════════════════════════════════════════════

# class Dock(QWidget):
#     """
#     Futuristic floating dock.

#     Layout
#     ──────
#     Icons sit in a manual horizontal layout so we can apply
#     dynamic spacing (neighbours push apart when one enlarges).
#     We do NOT use QHBoxLayout for icons — spacing is computed
#     per-frame in _apply_spacing() and icons are moved via setGeometry.

#     The Dock's own height adapts so enlarged icons are never cropped.
#     """

#     # Magnification influence radius
#     RANGE   = 210        # px
#     # Extra height headroom above BASE for enlarged icons
#     _PAD_V  = 14         # vertical padding (top + bottom share)
#     _PAD_H  = 22         # horizontal padding each side

#     def __init__(self, parent: Optional[QWidget] = None):
#         super().__init__(parent)
#         self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
#         self.setMouseTracking(True)
#         self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

#         self._icons:  List[DockIcon] = []
#         self._seps:   List[tuple[int, QWidget]] = []  # (before_index, widget)
#         self._border_phase = 0.0

#         # Master timer — single heartbeat for everything
#         self._timer = QTimer(self)
#         self._timer.setInterval(8)          # ~120 fps feel
#         self._timer.timeout.connect(self._tick)
#         self._timer.start()

#         # Recompute geometry on first show
#         self._dirty_layout = True

#     # ── public API ──────────────────────────────────────────────────

#     def add_icon(self, emoji: str, label: str,
#                  callback, with_separator: bool = False) -> DockIcon:
#         if with_separator:
#             sep = _SeparatorLine(self)
#             self._seps.append((len(self._icons), sep))
#             sep.show()

#         icon = DockIcon(emoji, label, self)
#         icon.clicked.connect(callback)
#         self._icons.append(icon)
#         icon.show()
#         self._dirty_layout = True
#         return icon

#     def set_active(self, label: str, active: bool) -> None:
#         for icon in self._icons:
#             if icon._label == label:
#                 icon.set_active(active)

#     # ── geometry helpers ─────────────────────────────────────────────

#     def _total_content_width(self) -> int:
#         """Width needed for all icons + separators + padding."""
#         n    = len(self._icons)
#         nsep = len(self._seps)
#         return (2 * self._PAD_H
#                 + n * DockIcon.SLOT_W
#                 + (n - 1) * 4        # default gap
#                 + nsep * 13)         # separator width

#     def _base_height(self) -> int:
#         return DockIcon.DOCK_H + self._PAD_V * 2

#     def _peak_height(self) -> int:
#         return DockIcon.PEAK + self._PAD_V * 2 + 24

#     def sizeHint(self):
#         from PyQt6.QtCore import QSize
#         # height adapts to max magnification
#         max_mag = max((ic._mag.cur for ic in self._icons), default=0.0)
#         h = int(self._base_height() + (self._peak_height() - self._base_height()) * max_mag)
#         return __import__('PyQt6.QtCore', fromlist=['QSize']).QSize(
#             self._total_content_width(), h)

#     # ── master tick ──────────────────────────────────────────────────

#     def _tick(self):
#         self._border_phase = (self._border_phase + 0.016) % (2 * math.pi)
#         for icon in self._icons:
#             icon.step()

#         # Adaptive height: grow dock when icons enlarge
#         max_mag  = max((ic._mag.cur for ic in self._icons), default=0.0)
#         new_h    = int(self._base_height()
#                        + (self._peak_height() - self._base_height()) * max_mag)
#         if self.height() != new_h:
#             self.setFixedHeight(new_h)

#         self._apply_spacing()
#         self.update()

#     def _apply_spacing(self):
#         """
#         Position icons manually so magnified icons push neighbours outward.
#         Algorithm: compute each icon's rendered face width (proportional to
#         its spring value), then lay them out with equal gaps.
#         """
#         if not self._icons:
#             return

#         W = self.width()
#         H = self.height()

#         # Build list of (index, effective_slot_width, is_sep_before)
#         slot_widths = []
#         for icon in self._icons:
#             mag = max(0.0, min(1.0, icon._mag.cur))
#             # Slot expands to accommodate face, never collapses below BASE
#             eff = int(DockIcon.SLOT_W + (DockIcon.PEAK - DockIcon.BASE) * mag * 0.55)
#             slot_widths.append(eff)

#         # Separators contribute fixed 13 px
#         sep_set = {idx for idx, _ in self._seps}
#         total_w  = sum(slot_widths) + 4 * (len(self._icons) - 1)
#         for idx in sep_set:
#             total_w += 13

#         # X start — centred in dock
#         x = max(self._PAD_H, (W - total_w) // 2)

#         for i, (icon, sw) in enumerate(zip(self._icons, slot_widths)):
#             # Position separator before this icon
#             for sep_idx, sep_w in self._seps:
#                 if sep_idx == i:
#                     sep_w.setGeometry(x, H // 2 - 25, 1, 50)
#                     x += 13

#             icon.setGeometry(x, H - DockIcon.DOCK_H - self._PAD_V // 2, sw, DockIcon.DOCK_H)
#             x += sw + 4

#     # ── mouse ────────────────────────────────────────────────────────

#     def mouseMoveEvent(self, e):
#         mx = e.position().x()
#         for icon in self._icons:
#             cx   = icon.x() + icon.width() / 2
#             dist = abs(cx - mx)
#             if dist >= self.RANGE:
#                 icon._mag.tgt = 0.0
#             else:
#                 norm = dist / self.RANGE
#                 icon._mag.tgt = math.exp(-norm * norm * 2.8)

#     def leaveEvent(self, _e):
#         for icon in self._icons:
#             icon._mag.tgt  = 0.0
#             icon._glow.tgt = 0.0
#             icon._tip.tgt  = 0.0

#     def resizeEvent(self, e):
#         super().resizeEvent(e)
#         self._apply_spacing()

#     # ── paint — glassmorphism dock container ─────────────────────────

#     def paintEvent(self, _e):
#         p = QPainter(self)
#         p.setRenderHint(QPainter.RenderHint.Antialiasing)
#         w, h   = self.width(), self.height()
#         rect   = self.rect().adjusted(3, 3, -3, -3)
#         corner = 24

#         # Layer 1: outer shadow
#         for ex, sa in ((10, 8), (6, 18), (3, 30)):
#             p.setPen(Qt.PenStyle.NoPen)
#             p.setBrush(QBrush(QColor(6, 4, 20, sa)))
#             p.drawRoundedRect(rect.adjusted(-ex, -ex, ex, ex),
#                               corner + ex, corner + ex)

#         # Layer 2: deep glass body
#         body = QLinearGradient(0, 0, 0, h)
#         body.setColorAt(0.00, QColor(38,  28,  72, 200))
#         body.setColorAt(0.40, QColor(22,  16,  52, 212))
#         body.setColorAt(0.78, QColor(12,   8,  34, 222))
#         body.setColorAt(1.00, QColor( 8,   4,  22, 232))
#         p.setBrush(QBrush(body))
#         p.setPen(Qt.PenStyle.NoPen)
#         p.drawRoundedRect(rect, corner, corner)

#         # Layer 3: top frosted shine
#         sh = QLinearGradient(0, 0, 0, h * 0.46)
#         sh.setColorAt(0.0, QColor(255, 255, 255, 28))
#         sh.setColorAt(0.6, QColor(255, 255, 255,  7))
#         sh.setColorAt(1.0, QColor(255, 255, 255,  0))
#         p.setBrush(QBrush(sh))
#         p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), corner - 1, corner - 1)

#         # Layer 4: bottom purple reflection
#         refl = QLinearGradient(0, h * 0.68, 0, h)
#         refl.setColorAt(0.0, QColor(110, 90, 240, 0))
#         refl.setColorAt(1.0, QColor(110, 90, 240, 18))
#         p.setBrush(QBrush(refl))
#         p.drawRoundedRect(rect, corner, corner)

#         # Layer 5: subtle side specular
#         side = QLinearGradient(0, 0, w, 0)
#         side.setColorAt(0.0, QColor(180, 200, 255, 10))
#         side.setColorAt(0.5, QColor(255, 255, 255,  3))
#         side.setColorAt(1.0, QColor(180, 200, 255, 10))
#         p.setBrush(QBrush(side))
#         p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), corner - 1, corner - 1)

#         # Layer 6: animated gradient border (cinematic neon edge)
#         ph    = self._border_phase
#         bx1   = w * (0.5 + 0.5 * math.cos(ph))
#         by1   = h * (0.5 + 0.5 * math.sin(ph))
#         bx2   = w * (0.5 - 0.5 * math.cos(ph))
#         by2   = h * (0.5 - 0.5 * math.sin(ph))
#         bdr   = QLinearGradient(bx1, by1, bx2, by2)
#         at    = int(60 + 22 * math.sin(ph))
#         am    = int(38 + 15 * math.sin(ph + 2.1))
#         ab_   = int(28 + 12 * math.sin(ph + 4.2))
#         bdr.setColorAt(0.00, QColor(255, 255, 255, at))
#         bdr.setColorAt(0.30, QColor(160, 190, 255, am))
#         bdr.setColorAt(0.55, QColor(130, 100, 255, am))
#         bdr.setColorAt(0.80, QColor(100, 140, 255, ab_))
#         bdr.setColorAt(1.00, QColor(200, 210, 255, at))
#         p.setBrush(Qt.BrushStyle.NoBrush)
#         p.setPen(QPen(QBrush(bdr), 1.1))
#         p.drawRoundedRect(rect, corner, corner)


# # ═══════════════════════════════════════════════════════════════════
# #  Thin separator line
# # ═══════════════════════════════════════════════════════════════════

# class _SeparatorLine(QWidget):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setFixedSize(1, 50)

#     def paintEvent(self, _e):
#         p = QPainter(self)
#         g = QLinearGradient(0, 0, 0, self.height())
#         g.setColorAt(0.0, QColor(140, 160, 255, 0))
#         g.setColorAt(0.5, QColor(140, 160, 255, 55))
#         g.setColorAt(1.0, QColor(140, 160, 255, 0))
#         p.fillRect(self.rect(), g)



"""
dock.py — PyOS Futuristic Dock
Centered layout, compact size (only as wide as icons)
Smooth magnification with raised icons
"""

from __future__ import annotations

import math
from typing import List, Optional

from PyQt6.QtCore import (
    Qt, QTimer, QRect, QRectF, QPointF, pyqtSignal
)
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QLinearGradient, QRadialGradient,
    QBrush, QPen, QFontMetrics, QPixmap
)
from PyQt6.QtWidgets import QWidget, QFrame, QSizePolicy


# ═══════════════════════════════════════════════════════════════════
#  Theme colours
# ═══════════════════════════════════════════════════════════════════

class _T:
    GLOW_INNER  = QColor(138, 180, 255)
    GLOW_OUTER  = QColor(80, 112, 200)
    ACTIVE      = QColor(160, 122, 255)
    DOT         = QColor(200, 225, 255)
    TIP_BG_TOP  = QColor(40, 30, 85, 215)
    TIP_BG_BOT  = QColor(18, 12, 48, 235)
    TIP_BORDER  = QColor(160, 185, 255, 90)
    TIP_TEXT    = QColor(235, 242, 255)
    DOCK_TOP    = QColor(38, 28, 72, 205)
    DOCK_BOT    = QColor(8, 5, 24, 232)
    BORDER_HI   = QColor(255, 255, 255, 70)
    BORDER_LO   = QColor(130, 100, 255, 50)


# ═══════════════════════════════════════════════════════════════════
#  Emoji pixmap cache
# ═══════════════════════════════════════════════════════════════════

_emoji_cache: dict[tuple[str, int], QPixmap] = {}

def _emoji_pixmap(emoji: str, size: int) -> QPixmap:
    key = (emoji, size)
    if key not in _emoji_cache:
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont()
        f.setPointSize(max(10, int(size * 0.42)))
        p.setFont(f)
        p.setPen(Qt.GlobalColor.white)
        p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, emoji)
        p.end()
        _emoji_cache[key] = px
    return _emoji_cache[key]


# ═══════════════════════════════════════════════════════════════════
#  Spring helper (smooth animation)
# ═══════════════════════════════════════════════════════════════════

class _Spring:
    __slots__ = ("cur", "vel", "tgt", "_ks", "_kd")

    def __init__(self, ks: float = 0.42, kd: float = 0.78, initial: float = 0.0):
        self.cur  = initial
        self.vel  = 0.0
        self.tgt  = initial
        self._ks  = ks
        self._kd  = kd

    def step(self) -> float:
        diff     = self.tgt - self.cur
        self.vel = self.vel * self._kd + diff * self._ks
        self.cur += self.vel
        self.cur  = max(-0.05, min(1.05, self.cur))
        return self.cur

    @property
    def settled(self) -> bool:
        return abs(self.tgt - self.cur) < 0.003 and abs(self.vel) < 0.003


# ═══════════════════════════════════════════════════════════════════
#  DockIcon
# ═══════════════════════════════════════════════════════════════════

class DockIcon(QWidget):
    clicked = pyqtSignal()

    BASE     = 46
    PEAK     = 70
    SLOT_W   = 62
    DOCK_H   = 80          # صغير شوية
    OFFSET_Y = 16          # ارتفاع الأيقونة من تحت

    def __init__(self, emoji: str, label: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._emoji   = emoji
        self._label   = label
        self._active  = False
        self._hover   = False

        self._mag     = _Spring(ks=0.42, kd=0.78)
        self._glow    = _Spring(ks=0.35, kd=0.72)
        self._tip     = _Spring(ks=0.38, kd=0.74)
        self._active_s = _Spring(ks=0.30, kd=0.68)

        self._phase   = 0.0
        self._bounce  = 0.0
        self._bouncing = False

        self.setFixedSize(self.SLOT_W, self.DOCK_H)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_active(self, active: bool) -> None:
        self._active = active
        self._active_s.tgt = 1.0 if active else 0.0

    def step(self) -> bool:
        self._mag.step()
        self._glow.step()
        self._tip.step()
        self._active_s.step()

        self._phase = (self._phase + 0.048) % (2 * math.pi)
        if self._bouncing:
            self._bounce += 0.12
            if self._bounce > 2 * math.pi:
                self._bounce = 0.0
                self._bouncing = False

        self.update()
        busy = not (self._mag.settled and self._glow.settled
                    and self._tip.settled and self._active_s.settled)
        return busy

    def trigger_bounce(self) -> None:
        self._bouncing = True
        self._bounce = 0.0
        self._mag.vel -= 0.48

    def mousePressEvent(self, _e):
        self.clicked.emit()
        self.trigger_bounce()

    def enterEvent(self, _e):
        self._hover = True
        self._glow.tgt = 1.0
        self._tip.tgt = 1.0

    def leaveEvent(self, _e):
        self._hover = False
        self._glow.tgt = 0.0
        self._tip.tgt = 0.0
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W, H = self.width(), self.height()
        mag = max(0.0, min(1.0, self._mag.cur))
        glow = max(0.0, min(1.0, self._glow.cur))
        tip_a = max(0.0, min(1.0, self._tip.cur))
        act = max(0.0, min(1.0, self._active_s.cur))
        pulse = math.sin(self._phase)

        bounce_y = 0
        if self._bouncing:
            bounce_y = int(-12 * math.sin(self._bounce) * math.exp(-self._bounce * 0.6))

        sz = int(self.BASE + (self.PEAK - self.BASE) * mag)
        sz = max(self.BASE, min(self.PEAK + 2, sz))
        ix = (W - sz) // 2
        iy = H - sz - self.OFFSET_Y + bounce_y
        face = QRect(ix, iy, sz, sz)
        rad = max(9, sz // 5)

        # Outer glow
        if glow > 0.02 or act > 0.02:
            gc = _T.ACTIVE if self._active else _T.GLOW_OUTER
            str_ = min(glow * 0.85 + act * 0.5, 1.0)
            for expand, base_a in ((14, 8), (8, 16), (4, 28)):
                a = int(base_a * str_)
                if a > 1:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(QColor(gc.red(), gc.green(), gc.blue(), a)))
                    p.drawRoundedRect(face.adjusted(-expand, -expand, expand, expand),
                                      rad + expand, rad + expand)

        # Inner glow
        if glow > 0.05 or act > 0.05:
            ic = _T.ACTIVE if self._active else _T.GLOW_INNER
            ia = int(min((glow + act * 0.6) * 52, 60))
            if ia > 2:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(ic.red(), ic.green(), ic.blue(), ia)))
                p.drawRoundedRect(face.adjusted(-3, -3, 3, 3), rad + 3, rad + 3)

        # Glass body
        hb = 20 if self._hover else 0
        body = QLinearGradient(ix, iy, ix, iy + sz)
        body.setColorAt(0.00, QColor(255, 255, 255, 60 + hb + int(30 * mag)))
        body.setColorAt(0.35, QColor(210, 220, 255, 30 + hb + int(16 * mag)))
        body.setColorAt(0.70, QColor(150, 170, 240, 18 + int(10 * mag)))
        body.setColorAt(1.00, QColor(90, 115, 200, 10 + int(6 * mag)))
        p.setBrush(QBrush(body))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(face, rad, rad)

        # Depth shadow
        dep = QLinearGradient(ix, iy + sz * 0.55, ix, iy + sz)
        dep.setColorAt(0.0, QColor(0, 0, 0, 0))
        dep.setColorAt(1.0, QColor(0, 0, 0, 28 + int(18 * mag)))
        p.setBrush(QBrush(dep))
        p.drawRoundedRect(face.adjusted(1, 1, -1, -1), rad - 1, rad - 1)

        # Top shine
        sh = QLinearGradient(ix, iy, ix, iy + sz * 0.42)
        sh.setColorAt(0.0, QColor(255, 255, 255, 70 + hb))
        sh.setColorAt(0.5, QColor(255, 255, 255, 18))
        sh.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(sh))
        p.drawRoundedRect(face.adjusted(1, 1, -1, -int(sz * 0.58)), rad - 1, rad - 1)

        # Border
        if self._active:
            pulse_a = int((95 + 60 * mag) * (0.72 + 0.28 * pulse))
            ac = _T.ACTIVE
            p.setPen(QPen(QColor(ac.red(), ac.green(), ac.blue(), pulse_a), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(face.adjusted(-1, -1, 1, 1), rad + 1, rad + 1)
            p.setPen(QPen(QColor(255, 255, 255, pulse_a // 3), 0.8))
            p.drawRoundedRect(face, rad, rad)
        else:
            ba = int(60 + 85 * mag) if self._hover else int(38 + 32 * mag)
            bg = QLinearGradient(ix, iy, ix + sz, iy + sz)
            bg.setColorAt(0.0, QColor(255, 255, 255, ba))
            bg.setColorAt(0.5, QColor(180, 200, 255, ba // 2))
            bg.setColorAt(1.0, QColor(140, 160, 255, ba // 3))
            p.setPen(QPen(QBrush(bg), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(face, rad, rad)

        # Emoji
        px = _emoji_pixmap(self._emoji, sz)
        p.drawPixmap(ix, iy, px)

        # Tooltip
        if tip_a > 0.03:
            lf = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
            fm = QFontMetrics(lf)
            lw = fm.horizontalAdvance(self._label) + 24
            lh = fm.height() + 12
            lx = max(0, min(W - lw, (W - lw) // 2))
            ly = iy - lh - 6
            if ly >= 0:
                a255 = int(tip_a * 255)
                tg = QLinearGradient(lx, ly, lx, ly + lh)
                tg.setColorAt(0.0, QColor(_T.TIP_BG_TOP.red(), _T.TIP_BG_TOP.green(),
                                          _T.TIP_BG_TOP.blue(), min(a255, 215)))
                tg.setColorAt(1.0, QColor(_T.TIP_BG_BOT.red(), _T.TIP_BG_BOT.green(),
                                          _T.TIP_BG_BOT.blue(), min(a255, 235)))
                p.setBrush(QBrush(tg))
                p.setPen(QPen(QColor(_T.TIP_BORDER.red(), _T.TIP_BORDER.green(),
                                     _T.TIP_BORDER.blue(), int(_T.TIP_BORDER.alpha() * tip_a)), 1.0))
                corner = lh // 2
                p.drawRoundedRect(lx, ly, lw, lh, corner, corner)
                ts = QLinearGradient(lx, ly, lx, ly + lh * 0.5)
                ts.setColorAt(0.0, QColor(255, 255, 255, int(tip_a * 42)))
                ts.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(QBrush(ts))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(lx, ly, lw, int(lh * 0.5), corner, corner)
                p.setFont(lf)
                p.setPen(QPen(QColor(_T.TIP_TEXT.red(), _T.TIP_TEXT.green(),
                                     _T.TIP_TEXT.blue(), a255)))
                p.drawText(QRect(lx, ly, lw, lh), Qt.AlignmentFlag.AlignCenter, self._label)

        # Active indicator
        if act > 0.02:
            pill_w = int((16 + 14 * act) * (0.85 + 0.15 * pulse))
            pill_h = 3
            pill_x = (W - pill_w) // 2
            pill_y = H - 5
            dc = _T.DOT
            dg = QLinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y)
            a_c = int(act * (180 + 55 * pulse))
            a_e = int(act * 32)
            dg.setColorAt(0.0, QColor(dc.red(), dc.green(), dc.blue(), a_e))
            dg.setColorAt(0.5, QColor(dc.red(), dc.green(), dc.blue(), a_c))
            dg.setColorAt(1.0, QColor(dc.red(), dc.green(), dc.blue(), a_e))
            hg = QLinearGradient(pill_x - 4, pill_y - 2, pill_x + pill_w + 4, pill_y + pill_h + 2)
            hg.setColorAt(0.0, QColor(dc.red(), dc.green(), dc.blue(), 0))
            hg.setColorAt(0.5, QColor(dc.red(), dc.green(), dc.blue(), int(act * 30)))
            hg.setColorAt(1.0, QColor(dc.red(), dc.green(), dc.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(hg))
            p.drawRoundedRect(pill_x - 4, pill_y - 2, pill_w + 8, pill_h + 4, 3, 3)
            p.setBrush(QBrush(dg))
            p.drawRoundedRect(pill_x, pill_y, pill_w, pill_h, pill_h // 2, pill_h // 2)

        # Hover light-bar
        if glow > 0.08:
            ba2 = int(glow * 95)
            bw = int(sz * 0.55)
            bx = (W - bw) // 2
            bg_y = H - 5
            blg = QLinearGradient(bx, bg_y, bx + bw, bg_y)
            gc2 = _T.GLOW_INNER
            blg.setColorAt(0.0, QColor(gc2.red(), gc2.green(), gc2.blue(), 0))
            blg.setColorAt(0.5, QColor(gc2.red(), gc2.green(), gc2.blue(), ba2))
            blg.setColorAt(1.0, QColor(gc2.red(), gc2.green(), gc2.blue(), 0))
            p.setBrush(QBrush(blg))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bx, bg_y, bw, 2, 1, 1)


# ═══════════════════════════════════════════════════════════════════
#  Dock — compact (width = icons only)
# ═══════════════════════════════════════════════════════════════════

class Dock(QWidget):
    """Compact futuristic dock — only as wide as the icons themselves."""

    RANGE = 200
    _PAD_H = 12         # padding أقل عشان يبقى ضيق
    _PAD_V = 6

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        # لجعل حجم الـ Dock حسب محتواه فقط (مش بيتمدد)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._icons: List[DockIcon] = []
        self._seps: List[tuple[int, QWidget]] = []
        self._border_phase = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(12)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._dirty_layout = True

    # ── public API ──────────────────────────────────────────────────

    def add_icon(self, emoji: str, label: str,
                 callback, with_separator: bool = False) -> DockIcon:
        if with_separator:
            sep = _SeparatorLine(self)
            self._seps.append((len(self._icons), sep))
            sep.show()

        icon = DockIcon(emoji, label, self)
        icon.clicked.connect(callback)
        self._icons.append(icon)
        icon.show()
        self._dirty_layout = True
        self._update_self_size()
        return icon

    def set_active(self, label: str, active: bool) -> None:
        for icon in self._icons:
            if icon._label == label:
                icon.set_active(active)

    def _update_self_size(self):
        """يجعل حجم الـ Dock مساويًا لعرض الأيقونات + padding بسيط"""
        if not self._icons:
            self.setFixedWidth(100)
            self.setFixedHeight(DockIcon.DOCK_H + self._PAD_V * 2)
            return

        icon_width = DockIcon.SLOT_W
        spacing = 5
        total_width = len(self._icons) * icon_width + (len(self._icons) - 1) * spacing

        # أضف عرض الفواصل
        for _, sep in self._seps:
            total_width += sep.width() + spacing

        total_width += self._PAD_H * 2
        self.setFixedWidth(total_width)
        self.setFixedHeight(DockIcon.DOCK_H + self._PAD_V * 2)

    # ── Master tick ──────────────────────────────────────────────────

    def _tick(self):
        self._border_phase = (self._border_phase + 0.016) % (2 * math.pi)

        any_anim = False
        for icon in self._icons:
            if icon.step():
                any_anim = True

        if self._dirty_layout or any_anim:
            self._apply_centered_layout()

        self.update()

    def _apply_centered_layout(self):
        """
        Position icons centered within the dock widget.
        """
        if not self._icons:
            return

        W = self.width()
        H = self.height()
        icon_h = DockIcon.DOCK_H
        y = (H - icon_h) // 2

        icon_width = DockIcon.SLOT_W
        spacing = 5

        # احسب العرض الإجمالي للأيقونات
        total_icons_width = len(self._icons) * icon_width + (len(self._icons) - 1) * spacing
        for _, sep in self._seps:
            total_icons_width += sep.width() + spacing

        # نبدأ من X محسوب ليكون في النص، مع الـ padding
        x_start = max(self._PAD_H, (W - total_icons_width) // 2)
        x = x_start

        for i, icon in enumerate(self._icons):
            # ضع الفاصل قبل الأيقونة لو موجود
            for sep_idx, sep in self._seps:
                if sep_idx == i:
                    sep_x = x
                    sep_y = (H - sep.height()) // 2
                    sep.setGeometry(sep_x, sep_y, sep.width(), sep.height())
                    x += sep.width() + spacing

            icon.setGeometry(x, y, icon_width, icon_h)
            x += icon_width + spacing

    # ── Mouse tracking for magnification ─────────────────────────────

    def mouseMoveEvent(self, e):
        mx = e.position().x()
        for icon in self._icons:
            cx = icon.x() + icon.width() / 2
            dist = abs(cx - mx)
            if dist >= self.RANGE:
                icon._mag.tgt = 0.0
            else:
                norm = dist / self.RANGE
                icon._mag.tgt = math.exp(-norm * norm * 3.2)

    def leaveEvent(self, _e):
        for icon in self._icons:
            icon._mag.tgt = 0.0
            icon._glow.tgt = 0.0
            icon._tip.tgt = 0.0

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_centered_layout()

    # ── Paint — glassmorphism dock container ─────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        rect = self.rect().adjusted(3, 3, -3, -3)
        corner = 20

        # Outer shadow
        for ex, sa in ((10, 8), (6, 18), (3, 30)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(6, 4, 20, sa)))
            p.drawRoundedRect(rect.adjusted(-ex, -ex, ex, ex), corner + ex, corner + ex)

        # Glass body
        body = QLinearGradient(0, 0, 0, h)
        body.setColorAt(0.00, QColor(38, 28, 72, 200))
        body.setColorAt(0.50, QColor(22, 16, 52, 212))
        body.setColorAt(0.85, QColor(12, 8, 34, 222))
        body.setColorAt(1.00, QColor(8, 4, 22, 232))
        p.setBrush(QBrush(body))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, corner, corner)

        # Top frosted shine
        sh = QLinearGradient(0, 0, 0, h * 0.45)
        sh.setColorAt(0.0, QColor(255, 255, 255, 28))
        sh.setColorAt(0.6, QColor(255, 255, 255, 6))
        sh.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(sh))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), corner - 1, corner - 1)

        # Bottom reflection
        refl = QLinearGradient(0, h * 0.70, 0, h)
        refl.setColorAt(0.0, QColor(110, 90, 240, 0))
        refl.setColorAt(1.0, QColor(110, 90, 240, 16))
        p.setBrush(QBrush(refl))
        p.drawRoundedRect(rect, corner, corner)

        # Animated border
        ph = self._border_phase
        bx1 = w * (0.5 + 0.45 * math.cos(ph))
        by1 = h * (0.5 + 0.45 * math.sin(ph))
        bx2 = w * (0.5 - 0.45 * math.cos(ph))
        by2 = h * (0.5 - 0.45 * math.sin(ph))
        bdr = QLinearGradient(bx1, by1, bx2, by2)
        at = int(65 + 20 * math.sin(ph))
        am = int(42 + 14 * math.sin(ph + 2.1))
        ab_ = int(30 + 10 * math.sin(ph + 4.2))
        bdr.setColorAt(0.00, QColor(255, 255, 255, at))
        bdr.setColorAt(0.30, QColor(160, 190, 255, am))
        bdr.setColorAt(0.55, QColor(130, 100, 255, am))
        bdr.setColorAt(0.80, QColor(100, 140, 255, ab_))
        bdr.setColorAt(1.00, QColor(200, 210, 255, at))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(bdr), 1.0))
        p.drawRoundedRect(rect, corner, corner)


# ═══════════════════════════════════════════════════════════════════
#  Separator line
# ═══════════════════════════════════════════════════════════════════

class _SeparatorLine(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(2, 40)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(140, 160, 255, 0))
        g.setColorAt(0.5, QColor(140, 160, 255, 70))
        g.setColorAt(1.0, QColor(140, 160, 255, 0))
        p.fillRect(self.rect(), g)