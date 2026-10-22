from __future__ import annotations

FONT_UI = "Bahnschrift"
FONT_WORD = "Sitka Banner"
FONT_SERIF = "Sitka Text"
FONT_IPA = "Segoe UI"

PALETTES = {
    "light": {
        "bg": "#F2F4F6",
        "surface": "#FFFFFF",
        "surface2": "#F8F9FA",
        "surface3": "#E7EAEE",
        "border": "#D9DEE5",
        "text": "#1F2633",
        "muted": "#5F6876",
        "dim": "#8A929E",
        "accent": "#1F2633",
        "accent_hover": "#363F4F",
        "ink_on": "#FFFFFF",
        "accent2": "#2E4A7A",
        "gold": "#2E4A7A",
        "highlight": "#FFE14D",
        "success": "#2F7A4C",
        "warning": "#A86A12",
        "danger": "#C23B30",
    },
    "dark": {
        "bg": "#1C2028",
        "surface": "#242934",
        "surface2": "#2A303C",
        "surface3": "#333A47",
        "border": "#3A4250",
        "text": "#E7E9EE",
        "muted": "#A0A8B5",
        "dim": "#7A8290",
        "accent": "#E7E9EE",
        "accent_hover": "#FFFFFF",
        "ink_on": "#1C2028",
        "accent2": "#9DB7E0",
        "gold": "#9DB7E0",
        "highlight": "#D9B93F",
        "success": "#73C08F",
        "warning": "#E0B060",
        "danger": "#E2766B",
    },
}

THEME_NAMES = {"light": "Gündüz", "dark": "Gece"}

C: dict[str, str] = dict(PALETTES["light"])
CURRENT = "light"


def apply(name: str):
    global CURRENT
    CURRENT = name if name in PALETTES else "light"
    C.clear()
    C.update(PALETTES[CURRENT])


def highlight_rgba(alpha: float = 0.85) -> str:
    h = C["highlight"].lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _check_icon() -> str:
    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
        if QGuiApplication.instance() is None:
            return ""
        from .config import USER_DIR
        folder = USER_DIR / "ui"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"check_{CURRENT}.png"
        for scale, name in ((1, path.name), (2, f"check_{CURRENT}@2x.png")):
            size = 16 * scale
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(C["ink_on"]), 2 * scale)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            tick = QPainterPath(QPointF(4 * scale, 8.5 * scale))
            tick.lineTo(7 * scale, 11.5 * scale)
            tick.lineTo(12.5 * scale, 5 * scale)
            p.drawPath(tick)
            p.end()
            pm.save(str(folder / name))
        return path.as_posix()
    except Exception:
        return ""


def stylesheet() -> str:
    c = C
    check = _check_icon()
    check_rule = f"QCheckBox::indicator:checked {{ image: url({check}); }}" if check else ""
    return check_rule + f"""
* {{
    font-family: "{FONT_UI}", "Segoe UI", sans-serif;
    font-size: 14px;
    color: {c['text']};
}}
QMainWindow, QWidget#Root, QWidget#Page, QDialog {{ background: {c['bg']}; }}
QToolTip {{
    background: {c['text']}; color: {c['bg']}; border: none; padding: 6px 8px; border-radius: 4px;
}}

/* ---------- Menü (sağda) ---------- */
QFrame#Sidebar {{ background: {c['bg']}; border-left: 1px solid {c['border']}; }}
QPushButton#NavButton {{
    text-align: left; padding: 9px 14px 9px 13px; border: none; border-left: 3px solid transparent;
    border-radius: 0; background: transparent; color: {c['muted']}; font-size: 15px;
}}
QPushButton#NavButton:hover {{ color: {c['text']}; }}
QPushButton#NavButton:checked {{
    color: {c['text']}; border-left: 3px solid {c['highlight']}; font-weight: 600;
}}
QLabel#SideNote {{ color: {c['muted']}; font-size: 13px; }}

/* ---------- Metin ---------- */
/* Bahnschrift'in dikey ölçüleri sıkı: İ'nin noktası kırpılmasın diye başlıklara üst boşluk */
QLabel#PageTitle {{ font-size: 24px; font-weight: 600; padding: 4px 0 0 0; qproperty-indent: 0; }}
QLabel#PageSubtitle {{ color: {c['muted']}; font-size: 14px; }}
QLabel#SectionTitle {{ font-size: 17px; font-weight: 600; padding: 3px 0 0 0; qproperty-indent: 0; }}
QLabel#Muted {{ color: {c['muted']}; }}
QLabel#Dim {{ color: {c['dim']}; font-size: 13px; }}
QLabel#Meaning {{ font-family: "{FONT_SERIF}"; font-size: 20px; color: {c['gold']}; }}
QLabel#Ipa {{ font-family: "{FONT_IPA}"; font-size: 15px; color: {c['muted']}; }}
QLabel#Example {{ font-family: "{FONT_SERIF}"; font-style: italic; font-size: 16px; color: {c['muted']}; }}
QLabel#Pron {{ font-size: 15px; color: {c['muted']}; }}
QLabel#Badge {{ color: {c['muted']}; font-size: 13px; }}
QLabel#Lead {{ font-size: 16px; padding: 2px 0 0 0; qproperty-indent: 0; }}

/* ---------- Bloklar ---------- */
QFrame#Card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; }}
QFrame#CardAlt {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; }}
QFrame#Rule {{ background: {c['border']}; max-height: 1px; min-height: 1px; border: none; }}

/* ---------- Butonlar ---------- */
QPushButton {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px;
    padding: 7px 14px; font-size: 14px;
}}
QPushButton:hover {{ border-color: {c['muted']}; }}
QPushButton:pressed {{ background: {c['surface3']}; }}
QPushButton:disabled {{ color: {c['dim']}; background: transparent; border-color: {c['border']}; }}
QPushButton:checked {{ background: {c['text']}; border-color: {c['text']}; color: {c['ink_on']}; }}
QPushButton:focus {{ outline: none; border-color: {c['accent2']}; }}
QPushButton#Primary {{ background: {c['accent']}; border-color: {c['accent']}; color: {c['ink_on']}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
QPushButton#Primary:disabled {{ background: {c['surface3']}; border-color: {c['surface3']}; color: {c['dim']}; }}
QPushButton#Success {{ color: {c['success']}; border-color: {c['success']}; }}
QPushButton#Danger {{ color: {c['danger']}; border-color: {c['border']}; }}
QPushButton#Danger:hover {{ border-color: {c['danger']}; }}
QPushButton#Warning {{ color: {c['warning']}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {c['muted']}; }}
QPushButton#Ghost:hover {{ color: {c['text']}; border-color: {c['border']}; }}
QPushButton#Choice {{
    text-align: left; padding: 13px 16px; font-size: 16px; border-radius: 6px; background: {c['surface']};
}}
QPushButton#Choice:checked {{ background: {c['surface']}; color: {c['text']}; border: 2px solid {c['text']}; }}
QPushButton#Choice[state="correct"] {{ border: 2px solid {c['success']}; color: {c['success']}; }}
QPushButton#Choice[state="wrong"] {{ border: 2px solid {c['danger']}; color: {c['danger']}; }}

/* ---------- AI Koç ---------- */
QFrame#ChatBubble {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; }}
QLabel#ChatText {{ font-size: 15px; }}
QLabel#ChatError {{ font-size: 14px; color: {c['danger']}; }}
QPushButton#Suggestion {{
    text-align: left; background: transparent; border: 1px solid {c['border']}; color: {c['muted']};
    padding: 7px 12px;
}}
QPushButton#Suggestion:hover {{ color: {c['text']}; border-color: {c['muted']}; }}
QPlainTextEdit#ChatInput {{ font-size: 15px; padding: 8px 10px; }}

/* ---------- Form ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QFontComboBox {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px 8px;
    selection-background-color: {c['highlight']}; selection-color: #1F2633;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c['text']};
}}
QLineEdit#AnswerInput {{ font-family: "{FONT_SERIF}"; font-size: 22px; padding: 10px 14px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {c['surface']}; border: 1px solid {c['border']}; outline: none;
    selection-background-color: {c['surface3']}; selection-color: {c['text']};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 3px; border: 1px solid {c['muted']}; background: {c['surface']};
}}
QCheckBox::indicator:checked {{ background: {c['text']}; border-color: {c['text']}; }}
QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c['text']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {c['surface']}; border: 2px solid {c['text']}; width: 12px; height: 12px;
    margin: -6px 0; border-radius: 8px;
}}
QGroupBox {{
    background: transparent; border: none; border-top: 1px solid {c['border']};
    margin-top: 30px; padding: 24px 0 6px 0; font-weight: 600; font-size: 17px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 0; top: 6px; padding: 3px 0 0 0; }}

/* ---------- İlerleme ---------- */
QProgressBar {{
    background: {c['border']}; border: none; border-radius: 2px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {c['accent2']}; border-radius: 2px; }}

/* ---------- Tablo / liste ---------- */
QTableView, QListWidget, QTreeWidget, QTextBrowser {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px;
    alternate-background-color: {c['surface2']}; gridline-color: transparent;
    selection-background-color: {highlight_rgba(0.55)}; selection-color: {c['text']}; outline: none;
}}
QTableView::item {{ padding: 4px 6px; border: none; }}
QHeaderView::section {{
    background: {c['surface']}; color: {c['muted']}; border: none; border-bottom: 1px solid {c['border']};
    padding: 8px 6px; font-weight: 600;
}}
QListWidget::item {{ padding: 8px 10px; border: none; }}
QListWidget::item:hover {{ background: {c['surface2']}; }}
QListWidget::item:selected {{ background: {highlight_rgba(0.55)}; color: {c['text']}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {c['muted']}; padding: 8px 0; margin-right: 24px;
    border-bottom: 2px solid transparent; font-size: 15px;
}}
QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['text']}; }}
QTabBar::tab:hover {{ color: {c['text']}; }}

/* ---------- Kaydırma çubukları ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['dim']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['surface3']}; color: {c['text']}; }}
QMenu::item:disabled {{ color: {c['dim']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
QMessageBox {{ background: {c['bg']}; }}

/* ---------- Başlık çubuğu ---------- */
QWidget#TitleBar {{ background: {c['bg']}; }}
QLabel#TitleText {{ font-size: 13px; color: {c['muted']}; }}
QLabel#TitlePage {{ font-size: 13px; color: {c['text']}; }}
QPushButton#TitleButton, QPushButton#TitleClose {{
    background: transparent; border: none; border-radius: 0; padding: 0; color: {c['text']};
}}
QPushButton#TitleButton:hover {{ background: {c['surface3']}; }}
QPushButton#TitleButton:pressed {{ background: {c['border']}; }}
QPushButton#TitleClose:hover {{ background: #C42B1C; color: white; }}
QPushButton#TitleClose:pressed {{ background: #A1251A; color: white; }}
"""
