from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QPushButton, QWidget

from .common import make_app_icon

TITLEBAR_HEIGHT = 40


def _icon_font() -> QFont:
    families = QFontDatabase.families()
    family = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
    f = QFont(family) if family else QFont("Segoe UI Symbol")
    f.setPixelSize(10)
    return f


GLYPHS = {"min": "", "max": "", "restore": "", "close": ""}
FALLBACK = {"min": "—", "max": "□", "restore": "❐", "close": "✕"}


class TitleBar(QWidget):
    def __init__(self, window: QWidget):
        super().__init__(window)
        self.win = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 0, 0)
        lay.setSpacing(12)

        icon = QLabel()
        icon.setPixmap(make_app_icon().pixmap(18, 18))
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(icon)
        self.title = QLabel(window.windowTitle())
        self.title.setObjectName("TitleText")
        self.page = QLabel("")
        self.page.setObjectName("TitlePage")
        for lb in (self.title, self.page):
            lb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(lb)
        lay.addStretch(1)

        has_glyphs = any(f in QFontDatabase.families() for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets"))
        self._glyphs = GLYPHS if has_glyphs else FALLBACK
        font = _icon_font()
        self.btn_min = self._button("min", "Simge durumuna küçült", font, window.showMinimized)
        self.btn_max = self._button("max", "Ekranı kapla", font, self.toggle_maximize)
        self.btn_close = self._button("close", "Kapat", font, window.close)
        self.btn_close.setObjectName("TitleClose")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)
        window.installEventFilter(self)
        self._update_max_button()

    def _button(self, kind: str, tip: str, font: QFont, slot) -> QPushButton:
        b = QPushButton(self._glyphs[kind])
        b.setObjectName("TitleButton")
        b.setFont(font)
        b.setFixedSize(46, TITLEBAR_HEIGHT)
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(slot)
        return b

    def set_page(self, text: str):
        self.page.setText(text)

    def toggle_maximize(self):
        if self.win.isMaximized():
            self.win.showNormal()
        else:
            self.win.showMaximized()

    def _update_max_button(self):
        maxed = self.win.isMaximized()
        self.btn_max.setText(self._glyphs["restore" if maxed else "max"])
        self.btn_max.setToolTip("Önceki boyuta döndür" if maxed else "Ekranı kapla")

    def eventFilter(self, obj, event):
        if obj is self.win:
            if event.type() == QEvent.Type.WindowStateChange:
                self._update_max_button()
            elif event.type() == QEvent.Type.WindowTitleChange:
                self.title.setText(self.win.windowTitle())
            elif event.type() in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate):
                self.setProperty("active", event.type() == QEvent.Type.WindowActivate)
                self.style().unpolish(self)
                self.style().polish(self)
                for lb in (self.title, self.page):
                    lb.style().unpolish(lb)
                    lb.style().polish(lb)
        return False

    def is_drag_area(self, pos) -> bool:
        if not self.rect().contains(pos):
            return False
        child = self.childAt(pos)
        while child is not None and child is not self:
            if isinstance(child, QAbstractButton):
                return False
            child = child.parentWidget()
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.win.windowHandle():
            self.win.windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
