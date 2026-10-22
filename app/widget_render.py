from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

from .config import POS_TR
from .pronunciation import clean_ipa

MAX_WIDTH = 900


@dataclass
class WidgetStyle:
    family: str
    bg: QColor
    radius: int
    padding: int
    min_width: int
    align: str
    shadow: bool
    border: bool
    text_alpha: float
    show_tr: bool
    show_ipa: bool
    show_pron: bool
    show_ex: bool
    show_badge: bool
    sizes: dict
    colors: dict

    @classmethod
    def from_settings(cls, get) -> "WidgetStyle":
        bg = QColor(get("widget.bg_color"))
        bg.setAlphaF(max(0.0, min(1.0, get("widget.bg_opacity") / 100)))
        return cls(
            family=get("widget.font_family"),
            bg=bg,
            radius=int(get("widget.corner_radius")),
            padding=int(get("widget.padding")),
            min_width=int(get("widget.min_width")),
            align=get("widget.align"),
            shadow=bool(get("widget.shadow")),
            border=bool(get("widget.border")),
            text_alpha=max(0.05, get("widget.text_opacity") / 100),
            show_tr=bool(get("widget.show_tr")),
            show_ipa=bool(get("widget.show_ipa")),
            show_pron=bool(get("widget.show_pron")),
            show_ex=bool(get("widget.show_ex")),
            show_badge=bool(get("widget.show_badge")),
            sizes={r: int(get(f"widget.size_{r}")) for r in ("en", "tr", "ipa", "pron", "ex")},
            colors={r: QColor(get(f"widget.color_{r}")) for r in ("en", "tr", "ipa", "pron", "ex")},
        )


@dataclass
class Line:
    text: str
    font: QFont
    color: QColor
    hidden: bool = False


def _font(family: str, px: int, weight=QFont.Weight.Normal, italic=False) -> QFont:
    f = QFont(family)
    f.setPixelSize(max(8, int(px)))
    f.setWeight(weight)
    f.setItalic(italic)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def build_lines(item: dict | None, style: WidgetStyle, pron_fn, revealed: bool = True) -> list[Line]:
    lines: list[Line] = []
    if not item:
        return [Line("EMG English", _font(style.family, style.sizes["en"], QFont.Weight.Bold), style.colors["en"])]
    muted = QColor(200, 205, 230)
    if item.get("kind") == "tense":
        lines.append(Line("TENSE · " + item["title"],_font(style.family, style.sizes["ipa"], QFont.Weight.DemiBold),
                          style.colors["ipa"]))
        lines.append(Line(item["en"], _font(style.family, max(14, int(style.sizes["en"] * 0.72)), QFont.Weight.Bold),
                          style.colors["en"]))
        if style.show_tr:
            lines.append(Line(item["tr"], _font(style.family, style.sizes["tr"]), style.colors["tr"],
                              hidden=not revealed))
        lines.append(Line(item["formula"], _font(style.family, style.sizes["pron"], italic=True),
                          style.colors["pron"]))
        return lines

    if style.show_badge:
        pos = ", ".join(POS_TR.get(p.strip(), p.strip()) for p in (item.get("pos") or "").split(",") if p.strip())
        badge = " · ".join(x for x in (pos, item.get("level") or "") if x)
        if badge:
            lines.append(Line(badge, _font(style.family, max(10, int(style.sizes["ipa"] * 0.8))), muted))
    lines.append(Line(item["english"], _font(style.family, style.sizes["en"], QFont.Weight.Bold),
                      style.colors["en"]))
    if style.show_tr:
        lines.append(Line(item.get("turkish") or "", _font(style.family, style.sizes["tr"], QFont.Weight.DemiBold),
                          style.colors["tr"], hidden=not revealed))
    if style.show_ipa and item.get("phonetic"):
        lines.append(Line(clean_ipa(item["phonetic"]), _font("Segoe UI", style.sizes["ipa"]), style.colors["ipa"]))
    if style.show_pron:
        pron = pron_fn(item)
        if pron:
            lines.append(Line(pron, _font(style.family, style.sizes["pron"], italic=True), style.colors["pron"]))
    if style.show_ex and item.get("example"):
        lines.append(Line(f"“{item['example']}”", _font(style.family, style.sizes["ex"], italic=True),
                          style.colors["ex"]))
    return lines


def measure(lines: list[Line], style: WidgetStyle) -> QSize:
    width = 0.0
    height = 0.0
    for i, ln in enumerate(lines):
        fm = QFontMetricsF(ln.font)
        width = max(width, fm.horizontalAdvance(ln.text if not ln.hidden else "? ? ?"))
        height += fm.height() + (4 if i else 0)
    w = int(min(MAX_WIDTH, max(style.min_width, width + 2 * style.padding + 8)))
    h = int(height + 2 * style.padding)
    return QSize(w, h)


def paint(painter: QPainter, rect: QRectF, lines: list[Line], style: WidgetStyle, opacity: float = 1.0):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    if style.bg.alpha() > 0:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(style.bg)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), style.radius, style.radius)
    if style.border:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), style.radius, style.radius)

    alpha = style.text_alpha * opacity
    if alpha <= 0.01:
        return
    inner = rect.adjusted(style.padding, style.padding, -style.padding, -style.padding)
    y = inner.top()
    for i, ln in enumerate(lines):
        fm = QFontMetricsF(ln.font)
        if i:
            y += 4
        text = ln.text
        color = QColor(ln.color)
        if ln.hidden:
            text = "? ? ?"
            color = QColor(170, 175, 200)
        text = fm.elidedText(text, Qt.TextElideMode.ElideRight, inner.width())
        tw = fm.horizontalAdvance(text)
        if style.align == "left":
            x = inner.left()
        elif style.align == "right":
            x = inner.right() - tw
        else:
            x = inner.left() + (inner.width() - tw) / 2
        baseline = y + fm.ascent()
        color.setAlphaF(max(0.0, min(1.0, color.alphaF() * alpha)))
        if style.shadow:
            path = QPainterPath()
            path.addText(QPointF(x, baseline), ln.font, text)
            outline = QColor(0, 0, 0)
            outline.setAlphaF(min(1.0, 0.85 * alpha))
            pen = QPen(outline, max(2.0, ln.font.pixelSize() / 7.5))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.strokePath(path, pen)
            painter.fillPath(path, color)
        else:
            painter.setPen(color)
            painter.setFont(ln.font)
            painter.drawText(QPointF(x, baseline), text)
        y += fm.height()
