"""
Login Screen — PyOS
Compact glassmorphism login card over animated aurora background.
"""

import math
import random

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPointF, QRectF, QSize
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QBrush, QPen, QPainterPath
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QFrame, QCheckBox,
    QApplication, QSizePolicy,
)

from user_manager import get_user_manager


# ══════════════════════════════════════════════════════════════════
_CSS = """
QWidget#loginRoot { background: transparent; }
GlassCard         { background: transparent; }

QLabel#title {
    color: #ede0ff; font-size: 22px; font-weight: 800;
    letter-spacing: 1px; background: transparent;
}
QLabel#subtitle {
    color: rgba(180,160,230,0.65); font-size: 11px;
    background: transparent;
}
QLabel.fl {
    color: rgba(190,160,255,0.80); font-size: 10px;
    font-weight: 700; letter-spacing: 1.2px;
    background: transparent;
}
QLineEdit {
    background: rgba(14, 7, 40, 0.55);
    color: #ede0ff;
    border: 1px solid rgba(160, 100, 255, 0.40);
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 16px;
    max-height: 36px;
}
QLineEdit:focus {
    border-color: rgba(200, 140, 255, 0.85);
    background: rgba(20, 10, 55, 0.65);
}
QPushButton#primary {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #7c3aed, stop:0.55 #4f46e5, stop:1 #2563eb);
    color: #fff; border: none; border-radius: 10px;
    padding: 10px 0; font-size: 13px; font-weight: 700;
    min-height: 16px; max-height: 38px;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #8b5cf6, stop:0.55 #6366f1, stop:1 #3b82f6);
}
QPushButton#secondary {
    background: rgba(100, 60, 200, 0.12);
    color: rgba(200, 170, 255, 0.90);
    border: 1px solid rgba(150, 100, 255, 0.28);
    border-radius: 10px; padding: 8px 0; font-size: 12px;
    min-height: 14px; max-height: 34px;
}
QPushButton#secondary:hover {
    background: rgba(130, 80, 230, 0.22);
    border-color: rgba(180, 130, 255, 0.55);
}
QLabel#error   { color: #f87171; font-size: 11px; background: transparent; }
QLabel#success { color: #34d399; font-size: 11px; background: transparent; }
QCheckBox {
    color: rgba(190,160,255,0.80); font-size: 11px;
    spacing: 6px; background: transparent;
}
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 2px solid rgba(150, 90, 255, 0.50);
    border-radius: 4px;
    background: rgba(14, 7, 40, 0.55);
}
QCheckBox::indicator:checked { background: #7c3aed; border-color: #c4b5fd; }
QFrame#sep {
    border: none; border-top: 1px solid rgba(150,100,255,0.18);
    background: transparent;
}
"""


# ══════════════════════════════════════════════════════════════════
#  Aurora animated background
# ══════════════════════════════════════════════════════════════════
class _GradientBG(QWidget):
    _BANDS = [
        (270, 0.88, 40, 0.30, 55, 0.0035, 0.22, 0.0),
        (220, 0.90, 34, 0.44, 42, 0.0028, 0.17, 1.1),
        (190, 0.85, 28, 0.60, 58, 0.0042, 0.28, 2.2),
        (310, 0.82, 26, 0.74, 36, 0.0031, 0.19, 0.6),
        (250, 0.80, 22, 0.86, 46, 0.0038, 0.24, 1.8),
        (170, 0.78, 18, 0.18, 30, 0.0025, 0.15, 3.0),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t = 0.0
        self._orbs: list = []
        self._stars: list = []
        QTimer(self, timeout=self._tick, interval=30).start()

    def _init_scene(self):
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            return
        rng = random.Random(7)
        hues = [270, 220, 190, 310, 250, 170, 340]
        self._orbs = [
            [rng.uniform(.08,.92)*w, rng.uniform(.08,.92)*h,
             rng.uniform(.12,.26)*min(w,h), hues[i%7],
             rng.uniform(0,math.tau), rng.uniform(-.15,.15), rng.uniform(-.12,.12)]
            for i in range(8)
        ]
        rng2 = random.Random(42)
        self._stars = [
            (rng2.randint(0,w), rng2.randint(0,int(h*.65)),
             rng2.uniform(0,math.tau), rng2.uniform(.3,2.5))
            for _ in range(140)
        ]

    def resizeEvent(self, e): super().resizeEvent(e); self._init_scene()
    def showEvent(self, e):   super().showEvent(e);   self._init_scene()

    def _tick(self):
        self._t += 0.018
        if not self._orbs and self.width() > 10:
            self._init_scene()
        w, h = max(self.width(),1), max(self.height(),1)
        for o in self._orbs:
            o[0] += o[5] + .28*math.sin(self._t*.4+o[4])
            o[1] += o[6] + .20*math.cos(self._t*.3+o[4]*.7)
            if o[0] < -o[2]: o[0] = w+o[2]
            if o[0] > w+o[2]: o[0] = -o[2]
            if o[1] < -o[2]: o[1] = h+o[2]
            if o[1] > h+o[2]: o[1] = -o[2]
        self.update()

    def paintEvent(self, _):
        if not self._orbs: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h, t = self.width(), self.height(), self._t
        r0=int(4+5*math.sin(t*.09)); g0=int(3+4*math.sin(t*.07+1)); b0=int(18+14*math.sin(t*.05+2))
        base = QLinearGradient(0,0,w,h)
        base.setColorAt(0.0, QColor(r0,g0,b0))
        base.setColorAt(0.5, QColor(r0//2,g0//2,b0+10))
        base.setColorAt(1.0, QColor(r0+4,g0//2,b0//2+14))
        p.fillRect(0,0,w,h,base)
        for o in self._orbs:
            ox,oy,or_,hue,phase = o[0],o[1],o[2],o[3],o[4]
            r = or_*(.90+.10*math.sin(t*.5+phase))
            g = QRadialGradient(QPointF(ox,oy),r)
            g.setColorAt(0.0, QColor.fromHsvF(hue/360,.88,1.0,.20))
            g.setColorAt(0.5, QColor.fromHsvF(hue/360,.88,1.0,.07))
            g.setColorAt(1.0, QColor.fromHsvF(hue/360,.88,1.0,.00))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(ox,oy),r,r)
        for hue,sat,alpha,y_frac,amp,freq,speed,phase in self._BANDS:
            cy = h*y_frac
            path = QPainterPath(); path.moveTo(0,h)
            for x in range(0, w+6, 5):
                y = cy + amp*math.sin(x*freq+t*speed+phase)
                path.lineTo(x,y)
            path.lineTo(w,h); path.closeSubpath()
            bg = QLinearGradient(0,cy-h*.08,0,cy+h*.08)
            bg.setColorAt(0.0, QColor.fromHsvF(hue/360,sat,.7,.0))
            bg.setColorAt(0.45,QColor.fromHsvF(hue/360,sat,1.0,alpha/255))
            bg.setColorAt(1.0, QColor.fromHsvF(hue/360,sat,.7,.0))
            p.setBrush(QBrush(bg)); p.setPen(Qt.PenStyle.NoPen); p.drawPath(path)
        for sx,sy,phase,spd in self._stars:
            twinkle = .30+.70*abs(math.sin(t*spd*.35+phase))
            p.setPen(QPen(QColor(210,200,255,int(220*twinkle)), .7+.8*twinkle))
            p.drawPoint(sx,sy)
        vig = QRadialGradient(w/2,h/2,max(w,h)*.75)
        vig.setColorAt(0.0, QColor(0,0,0,0)); vig.setColorAt(1.0, QColor(0,0,8,150))
        p.setBrush(QBrush(vig)); p.setPen(Qt.PenStyle.NoPen); p.drawRect(0,0,w,h)


# ══════════════════════════════════════════════════════════════════
#  GlassCard
# ══════════════════════════════════════════════════════════════════
class GlassCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Preferred,Preferred — sizes naturally to layout content, no forced expansion
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        radius = 20.0
        rect = QRectF(0, 0, w, h)
        path = QPainterPath(); path.addRoundedRect(rect, radius, radius)
        body = QLinearGradient(0, 0, 0, h)
        body.setColorAt(0.00, QColor(65,34,130,100))
        body.setColorAt(0.30, QColor(25,12, 72, 85))
        body.setColorAt(0.70, QColor(10, 5, 32, 88))
        body.setColorAt(1.00, QColor( 7, 3, 24, 95))
        p.setPen(Qt.PenStyle.NoPen); p.fillPath(path, QBrush(body))
        sheen = QLinearGradient(0,0,w*.5,0)
        sheen.setColorAt(0.0, QColor(110,55,240,16))
        sheen.setColorAt(1.0, QColor(110,55,240, 0))
        p.fillPath(path, QBrush(sheen))
        p.setPen(QPen(QColor(160,100,255,22), 6.0)); p.drawPath(path)
        p.setPen(QPen(QColor(165,110,255,65), 1.2))
        inner = QPainterPath()
        inner.addRoundedRect(QRectF(.6,.6,w-1.2,h-1.2), radius-.5, radius-.5)
        p.drawPath(inner)
        spec = QLinearGradient(w*.15,0,w*.85,0)
        spec.setColorAt(0.0, QColor(255,255,255,0))
        spec.setColorAt(0.3, QColor(210,170,255,90))
        spec.setColorAt(0.7, QColor(180,140,255,90))
        spec.setColorAt(1.0, QColor(255,255,255,0))
        p.setPen(QPen(QBrush(spec),1.0))
        p.drawLine(int(radius),0,int(w-radius),0)


# ══════════════════════════════════════════════════════════════════
#  _AdaptiveStack — sizes to CURRENT page only
# ══════════════════════════════════════════════════════════════════
class _AdaptiveStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _: self.updateGeometry())
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def sizeHint(self) -> QSize:
        w = self.currentWidget()
        return w.sizeHint() if w else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        w = self.currentWidget()
        return w.minimumSizeHint() if w else super().minimumSizeHint()


# ══════════════════════════════════════════════════════════════════
#  Form helpers — every widget has FIXED vertical size policy
# ══════════════════════════════════════════════════════════════════
_FIX = QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed

def _lbl(text: str) -> QLabel:
    l = QLabel(text); l.setProperty("class","fl")
    l.setSizePolicy(*_FIX); return l

def _inp(pw=False) -> QLineEdit:
    e = QLineEdit(); e.setSizePolicy(*_FIX)
    if pw: e.setEchoMode(QLineEdit.EchoMode.Password)
    return e

def _btn(text: str, obj: str) -> QPushButton:
    b = QPushButton(text); b.setObjectName(obj); b.setSizePolicy(*_FIX)
    return b

def _err_lbl() -> QLabel:
    l = QLabel(""); l.setObjectName("error")
    l.setAlignment(Qt.AlignmentFlag.AlignCenter)
    l.setSizePolicy(*_FIX); l.setVisible(False)
    return l


def _vbox(*items, spacing=7) -> QVBoxLayout:
    """Build a compact QVBoxLayout from widgets and int spacers."""
    lay = QVBoxLayout(); lay.setContentsMargins(0,0,0,0); lay.setSpacing(spacing)
    for item in items:
        if isinstance(item, QWidget): lay.addWidget(item)
        elif isinstance(item, int):  lay.addSpacing(item)
    return lay


# ══════════════════════════════════════════════════════════════════
#  Page widgets
# ══════════════════════════════════════════════════════════════════
class _LoginPage(QWidget):
    login_requested = pyqtSignal(str, str)
    go_register     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._user = _inp(); self._pw = _inp(pw=True)
        self._pw.returnPressed.connect(self._submit)
        self._err = _err_lbl()
        btn_in  = _btn("Sign In",             "primary")
        btn_reg = _btn("Create a new account","secondary")
        btn_in.clicked.connect(self._submit)
        btn_reg.clicked.connect(self.go_register)
        lay = _vbox(
            _lbl("USERNAME"), self._user, 2,
            _lbl("PASSWORD"), self._pw,
            self._err, 6,
            btn_in, btn_reg,
        )
        self.setLayout(lay)

    def reset(self):     self._pw.clear(); self._hide_err(); self._user.setFocus()
    def _hide_err(self): self._err.setVisible(False); self._err.clear()

    def set_error(self, msg: str):
        self._err.setText(msg); self._err.setVisible(True); self.updateGeometry()

    def _submit(self):
        u, pw = self._user.text().strip(), self._pw.text()
        if not u or not pw:
            self.set_error("Please enter username and password."); return
        self._hide_err(); self.login_requested.emit(u, pw)


class _RegisterPage(QWidget):
    register_requested = pyqtSignal(str, str, str, bool)
    go_login           = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._user = _inp(); self._pw = _inp(pw=True); self._pw2 = _inp(pw=True)
        self._adm  = QCheckBox("Give admin (sudo) privileges")
        self._adm.setSizePolicy(*_FIX)
        self._err  = _err_lbl()
        btn_reg  = _btn("Create Account", "primary")
        btn_back = _btn("← Back to Login","secondary")
        btn_reg.clicked.connect(self._submit)
        btn_back.clicked.connect(self.go_login)
        lay = _vbox(
            _lbl("USERNAME"),         self._user, 2,
            _lbl("PASSWORD"),         self._pw,   2,
            _lbl("CONFIRM PASSWORD"), self._pw2,  4,
            self._adm, self._err,     6,
            btn_reg, btn_back,
        )
        self.setLayout(lay)

    def reset(self):
        self._user.clear(); self._pw.clear(); self._pw2.clear()
        self._err.setVisible(False); self._adm.setChecked(False); self._user.setFocus()

    def set_error(self, msg: str):
        self._err.setText(msg); self._err.setVisible(True); self.updateGeometry()

    def _submit(self):
        u, pw, pw2 = self._user.text().strip(), self._pw.text(), self._pw2.text()
        if not u:     self.set_error("Username is required."); return
        if not pw:    self.set_error("Password is required."); return
        if pw != pw2: self.set_error("Passwords do not match."); return
        self._err.setVisible(False)
        self.register_requested.emit(u, pw, "", self._adm.isChecked())


class _GroupPage(QWidget):
    group_created = pyqtSignal(str)
    go_login      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._gname  = _inp()
        self._err    = _err_lbl()
        self._ok_lbl = QLabel(""); self._ok_lbl.setObjectName("success")
        self._ok_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ok_lbl.setSizePolicy(*_FIX); self._ok_lbl.setVisible(False)
        btn_create = _btn("Create Group",    "primary")
        btn_back   = _btn("← Back to Login","secondary")
        btn_create.clicked.connect(self._submit)
        btn_back.clicked.connect(self.go_login)
        lay = _vbox(
            _lbl("GROUP NAME"), self._gname,
            self._err, self._ok_lbl, 6,
            btn_create, btn_back,
        )
        self.setLayout(lay)

    def reset(self):
        self._gname.clear()
        self._err.setVisible(False); self._ok_lbl.setVisible(False)
        self._gname.setFocus()

    def _submit(self):
        name = self._gname.text().strip()
        if not name: self._err.setText("Group name is required."); self._err.setVisible(True); return
        ok, msg = get_user_manager().create_group(name)
        if ok:
            self._err.setVisible(False)
            self._ok_lbl.setText(f"✓ {msg}"); self._ok_lbl.setVisible(True)
            self._gname.clear(); self.group_created.emit(name)
        else:
            self._ok_lbl.setVisible(False)
            self._err.setText(msg); self._err.setVisible(True)


# ══════════════════════════════════════════════════════════════════
#  LoginWindow
# ══════════════════════════════════════════════════════════════════
_PAGE_META = {
    "login":    ("PyOS",           "Sign in to continue"),
    "register": ("Create Account", "Set up your profile"),
    "group":    ("New Group",      "Create a system group"),
}


class LoginWindow(QWidget):
    login_success = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("loginRoot")
        self.setStyleSheet(_CSS)
        self.setWindowTitle("PyOS — Login")
        self._um = get_user_manager()
        self._build_ui()
        self.showFullScreen()

    def _build_ui(self):
        # animated background (always fills the full window)
        self._bg = _GradientBG(self)
        scr = QApplication.primaryScreen()
        self._bg.setGeometry(scr.geometry() if scr else self.rect())
        self._bg.lower()

        # Root layout: stretch + card + stretch = card vertically centred
        # WITHOUT stretch the card would expand to fill the window.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addStretch(1)             # pushes card down from top

        # Glass card — fixed width, height = content
        self._card = GlassCard(self)
        self._card.setFixedWidth(390)

        cl = QVBoxLayout(self._card)
        cl.setContentsMargins(34, 24, 34, 22)
        cl.setSpacing(0)               # controlled manually below

        # ── Header ──────────────────────────────────────────
        logo = QHBoxLayout(); logo.setSpacing(6)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("◈")
        icon.setStyleSheet("color:rgba(200,150,255,0.80);font-size:17px;background:transparent;")
        icon.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._title_lbl = QLabel("PyOS"); self._title_lbl.setObjectName("title")
        logo.addWidget(icon); logo.addWidget(self._title_lbl)
        cl.addLayout(logo)
        cl.addSpacing(3)
        self._sub_lbl = QLabel("Sign in to continue"); self._sub_lbl.setObjectName("subtitle")
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_lbl.setSizePolicy(*_FIX); cl.addWidget(self._sub_lbl)
        cl.addSpacing(16)

        # ── Form stack ──────────────────────────────────────
        self._stack = _AdaptiveStack()
        self._stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._login_page    = _LoginPage()
        self._register_page = _RegisterPage()
        self._group_page    = _GroupPage()
        self._stack.addWidget(self._login_page)
        self._stack.addWidget(self._register_page)
        self._stack.addWidget(self._group_page)
        cl.addWidget(self._stack)

        # ── Divider + shortcut ──────────────────────────────
        cl.addSpacing(12)
        sep = QFrame(); sep.setObjectName("sep")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sep.setFixedHeight(1); cl.addWidget(sep)
        cl.addSpacing(8)
        btn_grp = _btn("+ Create Group","secondary")
        btn_grp.clicked.connect(lambda: self._switch("group"))
        cl.addWidget(btn_grp)

        root.addWidget(self._card, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)             # pushes card up from bottom

        # ── Signals ─────────────────────────────────────────
        self._login_page.login_requested.connect(self._do_login)
        self._login_page.go_register.connect(lambda: self._switch("register"))
        self._register_page.register_requested.connect(self._do_register)
        self._register_page.go_login.connect(lambda: self._switch("login"))
        self._group_page.go_login.connect(lambda: self._switch("login"))
        self._group_page.group_created.connect(
            lambda _: QTimer.singleShot(1500, lambda: self._switch("login"))
        )

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "_bg"):
            self._bg.setGeometry(self.rect())

    def _switch(self, page: str):
        self._stack.setCurrentIndex({"login":0,"register":1,"group":2}[page])
        title, sub = _PAGE_META[page]
        self._title_lbl.setText(title); self._sub_lbl.setText(sub)
        getattr(self, f"_{page}_page").reset()

    def _do_login(self, username: str, password: str):
        user = self._um.authenticate(username, password)
        if user: self.login_success.emit(user)
        else:    self._login_page.set_error("Incorrect username or password.")

    def _do_register(self, username: str, password: str, _: str, is_admin: bool):
        groups = ["sudo"] if is_admin else []
        ok, msg = self._um.create_user(username, password, groups=groups, is_admin=is_admin)
        if ok:
            user = self._um.authenticate(username, password)
            if user: self.login_success.emit(user)
        else:
            self._register_page.set_error(msg)
