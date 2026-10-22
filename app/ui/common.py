from __future__ import annotations

from html import escape

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QFrame, QHBoxLayout, QLabel, QLayout, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from ..config import POS_TR
from ..pronunciation import clean_ipa
from .. import theme
from ..theme import C, FONT_WORD


def clear_layout(layout: QLayout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def label(text: str = "", name: str | None = None, wrap: bool = False, align=None) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    if wrap:
        lb.setWordWrap(True)
    if align is not None:
        lb.setAlignment(align)
    return lb


def button(text: str, name: str | None = None, slot=None, tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    if slot:
        b.clicked.connect(slot)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def rule() -> QFrame:
    line = QFrame()
    line.setObjectName("Rule")
    line.setFixedHeight(1)
    return line


def pos_text(pos: str) -> str:
    return ", ".join(POS_TR.get(p.strip(), p.strip()) for p in (pos or "").split(",") if p.strip())


def confirm(parent, title: str, text: str, yes_text: str = "Evet") -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Question)
    yes = box.addButton(yes_text, QMessageBox.ButtonRole.YesRole)
    box.addButton("Vazgeç", QMessageBox.ButtonRole.NoRole)
    box.exec()
    return box.clickedButton() is yes


def info(parent, title: str, text: str):
    QMessageBox.information(parent, title, text)


class Card(QFrame):
    def __init__(self, parent=None, alt: bool = False, margins=(20, 18, 20, 18), spacing=10):
        super().__init__(parent)
        self.setObjectName("CardAlt" if alt else "Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(*margins)
        self.lay.setSpacing(spacing)


class Page(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(36, 22, 36, 24)
        self.root.setSpacing(16)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.title_label = label(title, "PageTitle")
        titles.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = label(subtitle, "PageSubtitle", wrap=True)
            self.subtitle_label.setMaximumWidth(640)
            sub_row = QHBoxLayout()
            sub_row.setContentsMargins(0, 0, 0, 0)
            sub_row.addWidget(self.subtitle_label, 1)
            sub_row.addStretch(0)
            titles.addLayout(sub_row)
        head.addLayout(titles, 1)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(8)
        head.addLayout(self.header_actions)
        self.root.addLayout(head)

    def on_show(self):
        pass


class Headword(QWidget):
    def __init__(self, size: int = 56, marker: bool = True, align=Qt.AlignmentFlag.AlignLeft, parent=None):
        super().__init__(parent)
        self.text = ""
        self.marker = marker
        self.align = align
        self.font_ = QFont(FONT_WORD)
        self.font_.setPixelSize(size)
        self.font_.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetricsF(self.font_)
        self.setFixedHeight(int(fm.height() + 6))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_text(self, text: str):
        self.text = text
        self.update()

    def _fitted_font(self) -> QFont:
        f = QFont(self.font_)
        while QFontMetricsF(f).horizontalAdvance(self.text) > self.width() - 8 and f.pixelSize() > 18:
            f.setPixelSize(f.pixelSize() - 2)
        return f

    def paintEvent(self, event):
        if not self.text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = self._fitted_font()
        fm = QFontMetricsF(f)
        w = fm.horizontalAdvance(self.text)
        if self.align & Qt.AlignmentFlag.AlignHCenter:
            x = (self.width() - w) / 2
        else:
            x = 2
        baseline = (self.height() + fm.ascent() - fm.descent()) / 2
        if self.marker:
            xh = fm.xHeight()
            top = baseline - xh * 0.62
            mark = QPainterPath()
            r = QRectF(x - 6, top, w + 12, xh * 0.78)
            mark.moveTo(r.left() + 3, r.top() + 2)
            mark.lineTo(r.right(), r.top())
            mark.lineTo(r.right() - 3, r.bottom())
            mark.lineTo(r.left(), r.bottom() + 1.5)
            mark.closeSubpath()
            color = QColor(C["highlight"])
            color.setAlphaF(0.9 if theme.CURRENT == "light" else 0.4)
            p.fillPath(mark, color)
        p.setFont(f)
        p.setPen(QColor(C["text"]))
        p.drawText(QPointF(x, baseline), self.text)
        p.end()


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(QSize(56, 28))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> str:
        return self._color

    def set_color(self, color: str):
        self._color = color
        self._refresh()

    def _refresh(self):
        self.setStyleSheet(
            f"QPushButton {{ background: {self._color}; border: 1px solid {C['border']}; border-radius: 4px; }}"
            f"QPushButton:hover {{ border-color: {C['text']}; }}")
        self.setToolTip(self._color.upper())

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self.window(), "Renk seç")
        if c.isValid():
            self._color = c.name()
            self._refresh()
            self.colorChanged.emit(self._color)


class WordView(QWidget):
    speakRequested = Signal()

    def __init__(self, ctx, show_meaning: bool = True, parent=None, compact: bool = False,
                 marker: bool = True, centered: bool = True, show_example: bool = False):
        super().__init__(parent)
        self.ctx = ctx
        self.show_example = show_example
        align = Qt.AlignmentFlag.AlignHCenter if centered else Qt.AlignmentFlag.AlignLeft
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.english = Headword(34 if compact else 52, marker=marker, align=align)
        lay.addWidget(self.english)
        line = QHBoxLayout()
        line.setSpacing(14)
        if centered:
            line.addStretch(1)
        self.ipa = label("", "Ipa")
        self.pron = label("", "Pron")
        self.badge = label("", "Badge")
        self.speak_btn = button("Dinle", "Ghost", self.speakRequested.emit, "Kelimeyi seslendir")
        self.speak_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for w in (self.ipa, self.pron, self.badge, self.speak_btn):
            line.addWidget(w)
        line.addStretch(1)
        lay.addLayout(line)
        self.meaning = label("", "Meaning", wrap=True,
                             align=Qt.AlignmentFlag.AlignCenter if centered else Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.meaning)
        self.example = label("", "Muted", wrap=True,
                             align=Qt.AlignmentFlag.AlignCenter if centered else Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.example)
        self.speakRequested.connect(self._speak)
        self.word: dict | None = None
        self.set_meaning_visible(show_meaning)

    def set_word(self, word: dict | None):
        self.word = word
        if not word:
            self.english.set_text("")
            for lb in (self.meaning, self.ipa, self.pron, self.badge, self.example):
                lb.setText("")
            return
        self.english.set_text(word["english"])
        self.meaning.setText(word.get("turkish") or "")
        ex, ex_tr = word.get("example") or "", word.get("example_tr") or ""
        self.example.setText(f"<i>“{escape(ex)}”</i>" + (f"<br>{escape(ex_tr)}" if ex_tr else "") if ex else "")
        self.set_meaning_visible(not self.meaning.isHidden())
        self.ipa.setText(clean_ipa(word.get("phonetic") or ""))
        pron = self.ctx.pron(word)
        self.pron.setText(f"okunuşu {pron}" if pron else "")
        bits = [x for x in (pos_text(word.get("pos", "")), word.get("level") or "") if x]
        self.badge.setText(", ".join(bits))

    def set_meaning_visible(self, visible: bool):
        self.meaning.setVisible(visible)
        self.example.setVisible(visible and self.show_example and bool(self.example.text()))

    def _speak(self):
        if self.word:
            self.ctx.speak(self.word["english"])


def make_app_icon(size: int = 256) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1F2633"))
    p.drawRoundedRect(QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92), size * 0.18, size * 0.18)
    mark = QPainterPath()
    mark.moveTo(size * 0.20, size * 0.56)
    mark.lineTo(size * 0.82, size * 0.53)
    mark.lineTo(size * 0.80, size * 0.74)
    mark.lineTo(size * 0.18, size * 0.76)
    mark.closeSubpath()
    p.fillPath(mark, QColor("#FFE14D"))
    f = QFont(FONT_WORD)
    f.setPixelSize(int(size * 0.72))
    f.setWeight(QFont.Weight.DemiBold)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(0, -size * 0.06, size, size), Qt.AlignmentFlag.AlignCenter, "e")
    p.end()
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(pm.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    return icon
