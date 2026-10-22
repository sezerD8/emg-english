from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFontComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from .. import widget_render as wr
from ..config import DEFAULT_SETTINGS, KINDS, LEVELS
from ..hotkeys import HOTKEYS
from ..theme import C
from .common import Card, ColorButton, Page, button, confirm, label

SAMPLE_WORD = {"id": 0, "english": "break the ice", "turkish": "buzları eritmek, ilk gerginliği atmak",
               "phonetic": "breɪk ðə aɪs", "pron_tr": None, "pos": "idiom", "level": "B2", "favorite": 0,
               "example": "He told a joke to break the ice."}

PRESETS = {
    "Koyu": {"widget.bg_color": "#1C2028", "widget.bg_opacity": 60, "widget.color_en": "#FFFFFF",
             "widget.color_tr": "#FFE14D", "widget.color_ipa": "#C9D1DC", "widget.color_pron": "#C9D1DC",
             "widget.color_ex": "#E3E7ED", "widget.shadow": True, "widget.border": False},
    "Açık": {"widget.bg_color": "#F2F4F6", "widget.bg_opacity": 90, "widget.color_en": "#1F2633",
             "widget.color_tr": "#2E4A7A", "widget.color_ipa": "#5F6876", "widget.color_pron": "#5F6876",
             "widget.color_ex": "#3A4250", "widget.shadow": False, "widget.border": False},
    "Sadece yazı": {"widget.bg_opacity": 0, "widget.color_en": "#FFFFFF", "widget.color_tr": "#FFE14D",
                    "widget.color_ipa": "#E3E7ED", "widget.color_pron": "#E3E7ED", "widget.color_ex": "#E3E7ED",
                    "widget.shadow": True, "widget.border": False},
    "Yüksek kontrast": {"widget.bg_color": "#000000", "widget.bg_opacity": 85, "widget.color_en": "#FFFFFF",
                        "widget.color_tr": "#FFE14D", "widget.color_ipa": "#FFFFFF", "widget.color_pron": "#FFFFFF",
                        "widget.color_ex": "#FFFFFF", "widget.shadow": False, "widget.border": True},
}

POSITION_GRID = [
    ["top-left", "top-center", "top-right"],
    ["middle-left", "center", "middle-right"],
    ["bottom-left", "bottom-center", "bottom-right"],
]
POSITION_ARROWS = {"top-left": "↖", "top-center": "↑", "top-right": "↗", "middle-left": "←", "center": "•",
                   "middle-right": "→", "bottom-left": "↙", "bottom-center": "↓", "bottom-right": "↘"}
POSITION_TR = {"top-left": "Sol üst", "top-center": "Üst orta", "top-right": "Sağ üst", "middle-left": "Sol orta",
               "center": "Tam orta", "middle-right": "Sağ orta", "bottom-left": "Sol alt",
               "bottom-center": "Alt orta", "bottom-right": "Sağ alt", "custom": "Özel konum (sürüklenmiş)"}


class PreviewArea(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setMinimumHeight(230)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#6E7A8A"))
        p.drawRoundedRect(r, 6, 6)
        left = QRectF(r.width() * 0.05, r.height() * 0.1, r.width() * 0.5, r.height() * 0.8)
        right = QRectF(r.width() * 0.5, r.height() * 0.1, r.width() * 0.45, r.height() * 0.8)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(left, 4, 4)
        p.setBrush(QColor("#22262E"))
        p.drawRoundedRect(right, 4, 4)
        p.setBrush(QColor("#D9DEE5"))
        for i in range(6):
            p.drawRect(QRectF(left.left() + 12, left.top() + 14 + i * 14, left.width() * (0.75 - 0.08 * (i % 3)), 5))
        p.setBrush(QColor("#3A404B"))
        for i in range(6):
            p.drawRect(QRectF(right.left() + 12, right.top() + 14 + i * 14, right.width() * (0.7 - 0.1 * (i % 2)), 5))
        style = wr.WidgetStyle.from_settings(self.ctx.get)
        overlay = self.ctx.overlay
        item = overlay.current if overlay is not None and overlay.current else SAMPLE_WORD
        lines = wr.build_lines(item, style, self.ctx.pron, True)
        size = wr.measure(lines, style)
        w = min(size.width(), int(r.width()) - 16)
        target = QRectF((r.width() - w) / 2, (r.height() - size.height()) / 2, w, size.height())
        wr.paint(p, target, lines, style, 1.0)
        p.end()


class WidgetSettingsPage(Page):
    def __init__(self, ctx):
        super().__init__("Widget Ayarları", "Masaüstünde her uygulamanın ve oyunun üstünde duran kelime "
                                            "widget'ını buradan özelleştir. Değişiklikler anında uygulanır.")
        self.ctx = ctx
        self._syncers: list = []
        self._syncing = False

        self.btn_toggle = button("", "Primary", lambda: ctx.set("widget.enabled", not ctx.get("widget.enabled")))
        self.btn_next = button("Sonraki", None, lambda: ctx.overlay and ctx.overlay.manual_next())
        self.btn_pause = button("", None, lambda: ctx.overlay and ctx.overlay.toggle_pause())
        for b in (self.btn_toggle, self.btn_next, self.btn_pause):
            self.header_actions.addWidget(b)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.root.addLayout(body, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self.form = QVBoxLayout(inner)
        self.form.setContentsMargins(0, 0, 8, 0)
        self.form.setSpacing(12)
        scroll.setWidget(inner)
        body.addWidget(scroll, 3)

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 8, 0)
        side.setSpacing(12)
        prev_card = Card(margins=(16, 14, 16, 14))
        prev_card.lay.addWidget(label("Canlı önizleme", "SectionTitle"))
        self.preview = PreviewArea(ctx)
        prev_card.lay.addWidget(self.preview)
        prev_card.lay.addWidget(label("İpucu: Widget'ı fareyle sürükleyerek taşıyabilirsin. Sağ tık → menü, "
                                      "çift tık → seslendir. Fare üzerindeyken kelime değişmez.", "Dim", wrap=True))
        side.addWidget(prev_card)
        side.addWidget(self._build_position_card())
        side.addStretch(1)
        side_w = QWidget()
        side_w.setLayout(side)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll.setWidget(side_w)
        side_scroll.setFixedWidth(400)
        body.addWidget(side_scroll)

        self._build_general()
        self._build_fullscreen()
        self._build_appearance()
        self._build_lines()
        self._build_hotkeys()
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset_row.addWidget(button("Widget ayarlarını varsayılana döndür", "Ghost", self._reset))
        self.form.addLayout(reset_row)
        self.form.addStretch(1)

        ctx.settingsChanged.connect(self._on_setting)
        if ctx.overlay is not None:
            ctx.overlay.stateChanged.connect(self._update_header)
            ctx.overlay.itemChanged.connect(self.preview.update)
        self._update_header()

    def _set(self, key, value):
        if not self._syncing:
            self.ctx.set(key, value)

    def bind_check(self, cb: QCheckBox, key: str):
        cb.setChecked(bool(self.ctx.get(key)))
        cb.toggled.connect(lambda v: self._set(key, bool(v)))
        self._syncers.append((key, lambda: cb.setChecked(bool(self.ctx.get(key)))))
        return cb

    def bind_spin(self, sp: QSpinBox, key: str, lo: int, hi: int, suffix: str = ""):
        sp.setRange(lo, hi)
        sp.setSuffix(suffix)
        sp.setValue(int(self.ctx.get(key)))
        sp.valueChanged.connect(lambda v: self._set(key, int(v)))
        self._syncers.append((key, lambda: sp.setValue(int(self.ctx.get(key)))))
        return sp

    def bind_slider(self, key: str, lo: int, hi: int, fmt: str = "{}") -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setMinimumWidth(80)
        s.setRange(lo, hi)
        s.setValue(int(self.ctx.get(key)))
        val = QLabel(fmt.format(int(self.ctx.get(key))))
        val.setMinimumWidth(52)
        val.setObjectName("Muted")
        s.valueChanged.connect(lambda v: (val.setText(fmt.format(v)), self._set(key, int(v))))
        lay.addWidget(s, 1)
        lay.addWidget(val)
        self._syncers.append((key, lambda: s.setValue(int(self.ctx.get(key)))))
        return w

    def bind_combo(self, combo: QComboBox, key: str, items: list[tuple]):
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(16)
        for value, text in items:
            combo.addItem(text, value)
        combo.setCurrentIndex(max(0, combo.findData(self.ctx.get(key))))
        combo.currentIndexChanged.connect(lambda _: self._set(key, combo.currentData()))
        self._syncers.append((key, lambda: combo.setCurrentIndex(max(0, combo.findData(self.ctx.get(key))))))
        return combo

    def bind_color(self, key: str) -> ColorButton:
        b = ColorButton(self.ctx.get(key))
        b.colorChanged.connect(lambda c: self._set(key, c))
        self._syncers.append((key, lambda: b.set_color(self.ctx.get(key))))
        return b

    def _group(self, title: str) -> QFormLayout:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.form.addWidget(box)
        return form

    def _build_general(self):
        f = self._group("Genel")
        f.addRow(self.bind_check(QCheckBox("Widget'ı masaüstünde göster"), "widget.enabled"))
        f.addRow("Kelime değişme süresi:", self.bind_slider("widget.interval", 2, 120, "{} sn"))
        self.interval_spin = self.bind_spin(QSpinBox(), "widget.interval", 1, 3600, " saniye")
        f.addRow("Tam değer:", self.interval_spin)
        f.addRow("Sıralama:", self.bind_combo(QComboBox(), "widget.order", [
            ("smart", "Akıllı karışık"), ("random", "Rastgele"), ("sequential", "Sıklık sırasıyla (1 → 5000)")]))
        src_row = QHBoxLayout()
        src_row.setContentsMargins(0, 0, 0, 0)
        self.source_combo = self.bind_combo(QComboBox(), "widget.source", [
            ("smart", "Akıllı (öğrenilenler + sıradaki yeniler)"),
            ("all", "Tüm kelimeler"),
            ("new", "Sadece yeni kelimeler"),
            ("learning", "Öğrenmekte olduklarım"),
            ("learned", "Öğrendiklerim (unutmamak için)"),
            ("favorites", "Favorilerim"),
            ("hard", "En çok yanıldıklarım"),
            ("deck", "Bir deste"),
        ])
        src_row.addWidget(self.source_combo, 2)
        self.deck_combo = QComboBox()
        self.deck_combo.currentIndexChanged.connect(
            lambda _: self._set("widget.deck_id", self.deck_combo.currentData()))
        src_row.addWidget(self.deck_combo, 1)
        f.addRow("Kelime kaynağı:", src_row)
        self._fill_decks()
        self.ctx.decksChanged.connect(self._fill_decks)

        lv = QHBoxLayout()
        self.level_checks = {}
        for level in LEVELS:
            cb = QCheckBox(level)
            cb.setChecked(level in (self.ctx.get("widget.levels") or LEVELS))
            cb.toggled.connect(self._levels_changed)
            cb.setToolTip("B1: orta seviye kelimeler, kalıplar ve hazır cümleler. B2: ileri kelimeler, deyimler ve "
                          "atasözleri. Kendi eklediğin kelimeler her zaman dahildir.")
            self.level_checks[level] = cb
            lv.addWidget(cb)
        lv.addStretch(1)
        f.addRow("Seviyeler:", lv)

        kd = QGridLayout()
        kd.setHorizontalSpacing(14)
        self.kind_checks = {}
        for i, (kind, name) in enumerate(KINDS.items()):
            cb = QCheckBox(name)
            cb.setChecked(kind in (self.ctx.get("widget.kinds") or KINDS))
            cb.toggled.connect(self._kinds_changed)
            self.kind_checks[kind] = cb
            kd.addWidget(cb, i // 3, i % 3)
        kd.setColumnStretch(3, 1)
        f.addRow("İçerik:", kd)

        quiz = self.bind_check(QCheckBox("Aktif hatırlama modu"), "widget.quiz_mode")
        quiz.setToolTip("Önce sadece İngilizce kelime görünür, Türkçe anlam birkaç saniye sonra açılır. "
                        "Beynin anlamı hatırlamaya çalışır — kalıcı öğrenme için çok etkilidir.")
        f.addRow(quiz)
        f.addRow("Anlam açılma süresi:", self.bind_spin(QSpinBox(), "widget.reveal_delay", 1, 60, " saniye sonra"))
        tm = self.bind_spin(QSpinBox(), "widget.tense_mix", 0, 50)
        tm.setSpecialValueText("kapalı")
        tm.setPrefix("her ")
        tm.setSuffix(" kelimede bir")
        tm.setToolTip("Kelimelerin arasına tense örnek cümleleri (İngilizce + Türkçe + formül) karıştırır.")
        f.addRow("Tense cümlesi:", tm)
        f.addRow(self.bind_check(QCheckBox("Her yeni kelimeyi sesli oku"), "widget.auto_speak"))
        f.addRow(self.bind_check(QCheckBox("Geçişte yumuşak animasyon"), "widget.fade"))

    def _build_fullscreen(self):
        f = self._group("Tam ekran ve oyunlar")
        f.addRow("Tam ekranda:", self.bind_combo(QComboBox(), "widget.fs_mode", [
            ("show_voice", "Üstte göster, exclusive modda sesli oku (önerilen)"),
            ("show", "Sadece üstte göster"),
            ("voice", "Widget'ı gizle, kelimeleri sesli oku"),
            ("hide", "Widget'ı gizle (oyunu hiç etkileme)"),
        ]))
        f.addRow("Sesli okuma aralığı:", self.bind_spin(QSpinBox(), "widget.fs_voice_interval", 5, 600,
                                                         " saniyede bir"))
        self.fs_status = label("", None, wrap=True)
        f.addRow("Şu an:", self.fs_status)
        f.addRow(label(
            "<b>Borderless / pencereli tam ekran</b> oyunlarda widget oyunun üstünde kalır (oyun algılanınca "
            "üstlük saniyede ~3 kez yenilenir). <b>Exclusive (özel) tam ekranda</b> ekranı oyun tek başına "
            "kullanır; Windows hiçbir pencerenin üstüne çizilmesine izin vermez. Bu modda kelime ve Türkçe "
            "anlamı sesli okunur — ya da oyunun görüntü ayarından <i>Borderless / Pencereli tam ekran</i>'ı seç.",
            "Dim", wrap=True))
        self.ctx.speaker.voicesChanged.connect(self._update_fs_status)
        self._update_fs_status()
        if self.ctx.overlay is not None:
            self.ctx.overlay.fullscreenChanged.connect(lambda _s: self._update_fs_status())
            self.ctx.overlay.stateChanged.connect(self._update_fs_status)

    def _update_fs_status(self):
        ov = self.ctx.overlay
        state = ov.fs_state if ov is not None else "none"
        if state == "exclusive":
            text = f"<span style='color:{C['warning']}'>● Exclusive tam ekran oyun algılandı</span>"
        elif state == "fullscreen":
            text = f"<span style='color:{C['success']}'>Tam ekran uygulama algılandı, widget üstte tutuluyor.</span>"
        else:
            text = f"<span style='color:{C['muted']}'>● Tam ekran uygulama yok</span>"
        if ov is not None and ov.voice_active:
            text += " Sesli mod açık."
        if ov is not None and ov.fs_hidden:
            text += " Widget gizlendi."
        if self.ctx.speaker.voices() and not self.ctx.speaker.has_turkish:
            text += "<br><span style='color:#9AA0C3'>Türkçe ses yok: sesli modda sadece İngilizce okunur.</span>"
        self.fs_status.setText(text)

    def _fill_decks(self):
        self._syncing = True
        self.deck_combo.clear()
        decks = self.ctx.db.list_decks()
        if not decks:
            self.deck_combo.addItem("(deste yok)", None)
        for d in decks:
            self.deck_combo.addItem(f"{d['name']} ({d['cards']})", d["id"])
        i = self.deck_combo.findData(self.ctx.get("widget.deck_id"))
        self.deck_combo.setCurrentIndex(max(0, i))
        self._syncing = False
        self.deck_combo.setVisible(self.ctx.get("widget.source") == "deck")
        if self.ctx.get("widget.source") == "deck" and self.ctx.get("widget.deck_id") is None and decks:
            self.ctx.set("widget.deck_id", decks[0]["id"])

    def _levels_changed(self):
        levels = [lv for lv, cb in self.level_checks.items() if cb.isChecked()]
        if not levels:
            levels = list(LEVELS)
        self._set("widget.levels", levels)

    def _kinds_changed(self):
        kinds = [k for k, cb in self.kind_checks.items() if cb.isChecked()]
        self._set("widget.kinds", kinds or list(KINDS))

    def _build_appearance(self):
        f = self._group("Görünüm")
        presets = QGridLayout()
        presets.setSpacing(6)
        for i, (name, values) in enumerate(PRESETS.items()):
            b = button(name, None, lambda _=False, v=values: self._apply_preset(v))
            presets.addWidget(b, i // 2, i % 2)
        f.addRow("Hazır temalar:", presets)
        f.addRow("Arka plan rengi:", self.bind_color("widget.bg_color"))
        f.addRow("Arka plan opaklığı:", self.bind_slider("widget.bg_opacity", 0, 100, "%{}"))
        f.addRow("Yazı opaklığı:", self.bind_slider("widget.text_opacity", 10, 100, "%{}"))
        f.addRow("Köşe yuvarlaklığı:", self.bind_slider("widget.corner_radius", 0, 40, "{} px"))
        f.addRow("İç boşluk:", self.bind_slider("widget.padding", 2, 40, "{} px"))
        f.addRow("Minimum genişlik:", self.bind_slider("widget.min_width", 100, 800, "{} px"))
        font = QFontComboBox()
        font.setCurrentFont(QFont(self.ctx.get("widget.font_family")))
        font.currentFontChanged.connect(lambda fnt: self._set("widget.font_family", fnt.family()))
        self._syncers.append(("widget.font_family", lambda: font.setCurrentFont(QFont(self.ctx.get("widget.font_family")))))
        f.addRow("Yazı tipi:", font)
        f.addRow("Hizalama:", self.bind_combo(QComboBox(), "widget.align", [
            ("left", "Sola"), ("center", "Ortaya"), ("right", "Sağa")]))
        f.addRow(self.bind_check(QCheckBox("Yazılara kontur ekle (her zeminde okunur)"), "widget.shadow"))
        f.addRow(self.bind_check(QCheckBox("İnce çerçeve"), "widget.border"))
        f.addRow(self.bind_check(QCheckBox("Üstte tür ve seviye rozeti"), "widget.show_badge"))

    def _build_lines(self):
        box = QGroupBox("Satırlar")
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for col, text in enumerate(["Göster", "Satır", "Boyut", "Renk", "Örnek"]):
            grid.addWidget(label(text, "Dim"), 0, col)
        rows = [
            ("en", None, "1. İngilizce kelime", "awesome"),
            ("tr", "widget.show_tr", "2. Türkçe anlamı", "harika, müthiş"),
            ("ipa", "widget.show_ipa", "3. Fonetik (IPA)", "/ˈɔːsəm/"),
            ("pron", "widget.show_pron", "4. Türkçe okunuşu", "osım"),
            ("ex", "widget.show_ex", "5. Örnek cümle", "“That's awesome!”"),
        ]
        for r, (role, show_key, name, sample) in enumerate(rows, start=1):
            cb = QCheckBox()
            if show_key:
                self.bind_check(cb, show_key)
            else:
                cb.setChecked(True)
                cb.setEnabled(False)
            grid.addWidget(cb, r, 0)
            grid.addWidget(label(name), r, 1)
            grid.addWidget(self.bind_spin(QSpinBox(), f"widget.size_{role}", 8, 96, " px"), r, 2)
            grid.addWidget(self.bind_color(f"widget.color_{role}"), r, 3)
            ex = label(sample, "Muted")
            grid.addWidget(ex, r, 4)
        grid.setColumnStretch(4, 1)
        self.form.addWidget(box)

    def _build_position_card(self) -> QWidget:
        card = Card(margins=(16, 14, 16, 14))
        card.lay.addWidget(label("Ekrandaki konum", "SectionTitle"))
        monitor = QWidget()
        monitor.setObjectName("CardAlt")
        monitor.setStyleSheet(f"QWidget#CardAlt {{ background: {C['surface2']}; border: 1px solid {C['border']};"
                              f" border-radius: 10px; }}")
        g = QGridLayout(monitor)
        g.setContentsMargins(10, 10, 10, 10)
        g.setSpacing(8)
        self.pos_buttons: dict[str, QPushButton] = {}
        for r, row in enumerate(POSITION_GRID):
            for c, key in enumerate(row):
                b = QPushButton(POSITION_ARROWS[key])
                b.setCheckable(True)
                b.setToolTip(POSITION_TR[key])
                b.setFixedHeight(40)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _=False, k=key: self.ctx.set("widget.position", k))
                self.pos_buttons[key] = b
                g.addWidget(b, r, c)
        card.lay.addWidget(monitor)
        self.pos_label = label("", "Muted")
        card.lay.addWidget(self.pos_label)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.screen_combo = QComboBox()
        self.screen_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.screen_combo.setMinimumContentsLength(10)
        for i, s in enumerate(QGuiApplication.screens()):
            geo = s.geometry()
            self.screen_combo.addItem(f"Ekran {i + 1}: {s.name()} ({geo.width()}×{geo.height()})", i)
        self.screen_combo.setCurrentIndex(max(0, self.screen_combo.findData(self.ctx.get("widget.screen"))))
        self.screen_combo.currentIndexChanged.connect(lambda _: self._set("widget.screen", self.screen_combo.currentData()))
        form.addRow("Monitör:", self.screen_combo)
        form.addRow("Kenar boşluğu:", self.bind_spin(QSpinBox(), "widget.margin", 0, 400, " px"))
        xy = QHBoxLayout()
        self.x_spin = QSpinBox()
        self.y_spin = QSpinBox()
        for sp, key in ((self.x_spin, "widget.custom_x"), (self.y_spin, "widget.custom_y")):
            sp.setRange(-10000, 20000)
            sp.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            sp.setValue(int(self.ctx.get(key)))
            sp.valueChanged.connect(lambda v, k=key: self._set_custom(k, v))
            self._syncers.append((key, lambda sp=sp, k=key: sp.setValue(int(self.ctx.get(k)))))
        xy.addWidget(label("X"))
        xy.addWidget(self.x_spin)
        xy.addWidget(label("Y"))
        xy.addWidget(self.y_spin)
        form.addRow("Özel konum:", xy)
        card.lay.addLayout(form)
        card.lay.addWidget(self.bind_check(QCheckBox("Oyun modu (tıklamalar içinden geçer)"),
                                           "widget.click_through"))
        card.lay.addWidget(label("Oyun modunda widget'a tıklanamaz (oyunu engellemez). Kapatmak için: "
                                 "Ctrl+Alt+C, tepsi menüsü veya bu ayar.", "Dim", wrap=True))
        self._update_position_ui()
        return card

    def _set_custom(self, key, value):
        if self._syncing:
            return
        self.ctx.db.set(key, int(value))
        if self.ctx.get("widget.position") != "custom":
            self.ctx.set("widget.position", "custom")
        else:
            self.ctx.settingsChanged.emit(key)

    def _build_hotkeys(self):
        box = QGroupBox("Kısayollar")
        lay = QVBoxLayout(box)
        lay.addWidget(self.bind_check(QCheckBox("Kısayolları kullan (oyun içindeyken de çalışır)"), "widget.hotkeys"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for i, (_, (keys, _vk, desc)) in enumerate(HOTKEYS.items()):
            k = label(f"<b>{keys}</b>")
            k.setStyleSheet(f"background:{C['surface']}; border:1px solid {C['border']}; border-radius:4px; padding:2px 8px;")
            grid.addWidget(k, i, 0)
            grid.addWidget(label(desc, "Muted", wrap=True), i, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.hotkey_status = label("", "Dim", wrap=True)
        lay.addWidget(self.hotkey_status)
        self.form.addWidget(box)

    def set_hotkey_status(self, failed: list[str]):
        if failed:
            self.hotkey_status.setText("Başka bir program tarafından kullanıldığı için kaydedilemeyenler: "
                                       + ", ".join(failed))
        else:
            self.hotkey_status.setText("")

    def _apply_preset(self, values: dict):
        for k, v in values.items():
            self.ctx.set(k, v)

    def _reset(self):
        if not confirm(self, "Varsayılana dön", "Tüm widget ayarları varsayılan değerlere dönsün mü?"):
            return
        self.ctx.db.reset_settings("widget.")
        for key in DEFAULT_SETTINGS:
            if key.startswith("widget."):
                self.ctx.settingsChanged.emit(key)

    def _update_position_ui(self):
        pos = self.ctx.get("widget.position")
        for k, b in self.pos_buttons.items():
            b.setChecked(k == pos)
        self.pos_label.setText("Şu an: " + POSITION_TR.get(pos, pos))

    def _update_header(self):
        on = bool(self.ctx.get("widget.enabled"))
        self.btn_toggle.setText("Widget'ı gizle" if on else "Widget'ı göster")
        paused = bool(self.ctx.overlay and self.ctx.overlay.paused)
        self.btn_pause.setText("▶ Devam" if paused else "Duraklat")
        self.btn_pause.setEnabled(on)
        self.btn_next.setEnabled(on)

    def _on_setting(self, key: str):
        if not key.startswith(("widget.", "pron.")):
            return
        self._syncing = True
        try:
            for k, fn in self._syncers:
                if k == key:
                    fn()
            if key == "widget.levels":
                levels = self.ctx.get("widget.levels") or LEVELS
                for lv, cb in self.level_checks.items():
                    cb.setChecked(lv in levels)
            if key == "widget.kinds":
                kinds = self.ctx.get("widget.kinds") or KINDS
                for k, cb in self.kind_checks.items():
                    cb.setChecked(k in kinds)
            if key == "widget.source":
                self.deck_combo.setVisible(self.ctx.get("widget.source") == "deck")
                if self.ctx.get("widget.source") == "deck" and self.ctx.get("widget.deck_id") is None:
                    self._syncing = False
                    self._set("widget.deck_id", self.deck_combo.currentData())
        finally:
            self._syncing = False
        if key in ("widget.position", "widget.custom_x", "widget.custom_y"):
            self._update_position_ui()
        if key == "widget.enabled":
            self._update_header()
        self.preview.update()

    def on_show(self):
        self._update_header()
        self.preview.update()
