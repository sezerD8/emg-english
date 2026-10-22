from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLineEdit,
    QListWidget, QListWidgetItem, QSizePolicy, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from ..config import LEVEL_COLORS, LEVEL_RARITY, LEVELS, STATUS_TR
from ..online import fetch_word_info, run_async
from ..pronunciation import clean_ipa
from ..theme import C, FONT_IPA, FONT_SERIF, FONT_UI, FONT_WORD
from .common import Card, Page, button, clear_layout, confirm, label, pos_text


class DraftCard(QFrame):
    clicked = Signal()

    def __init__(self, ctx, parent=None, interactive: bool = True):
        super().__init__(parent)
        self.ctx = ctx
        self.word: dict | None = None
        self.hover = False
        self.interactive = interactive
        self.setMinimumSize(220, 320)
        self.setMaximumHeight(440)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if interactive:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_word(self, word: dict | None):
        self.word = word
        self.update()

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if self.interactive and e.button() == Qt.MouseButton.LeftButton and self.word:
            self.clicked.emit()

    def mouseDoubleClickEvent(self, e):
        if self.word:
            self.ctx.speak(self.word["english"])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        w = self.word
        level = (w or {}).get("level") or "B1"
        rarity = QColor(LEVEL_COLORS.get(level, "#8A929E"))
        active = self.hover and self.interactive
        card = QPainterPath()
        card.addRoundedRect(r, 8, 8)
        p.fillPath(card, QColor(C["surface"]))
        p.save()
        p.setClipPath(card)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 6), rarity)
        p.restore()
        p.setPen(QPen(QColor(C["text"] if active else C["border"]), 1.5 if active else 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(card)

        inner = r.adjusted(22, 22, -22, -20)
        f = QFont(FONT_UI)
        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(rarity)
        p.drawText(QRectF(inner.left(), inner.top(), inner.width(), 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, LEVEL_RARITY.get(level, ""))
        p.setPen(QColor(C["muted"]))
        p.drawText(QRectF(inner.left(), inner.top(), inner.width(), 18),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, level)
        if not w:
            p.end()
            return

        def text_line(txt, family, px, color, italic=False, y=0.0, wrap=False, weight=QFont.Weight.Normal):
            fnt = QFont(family)
            fnt.setPixelSize(px)
            fnt.setItalic(italic)
            fnt.setWeight(weight)
            p.setFont(fnt)
            p.setPen(QColor(color))
            fm = QFontMetricsF(fnt)
            flags = Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap
            if wrap:
                rect = QRectF(inner.left(), y, inner.width(), fm.lineSpacing() * 4)
                br = p.boundingRect(rect, flags, txt)
                p.drawText(rect, flags, txt)
                return y + min(br.height(), fm.lineSpacing() * 4) + 4
            while fm.horizontalAdvance(txt) > inner.width() and fnt.pixelSize() > 16:
                fnt.setPixelSize(fnt.pixelSize() - 2)
                p.setFont(fnt)
                fm = QFontMetricsF(fnt)
            txt = fm.elidedText(txt, Qt.TextElideMode.ElideRight, inner.width())
            p.drawText(QRectF(inner.left(), y, inner.width(), fm.height()), Qt.AlignmentFlag.AlignLeft, txt)
            return y + fm.height() + 2

        y = inner.top() + max(46.0, inner.height() * 0.22)
        y = text_line(w["english"], FONT_WORD, 34, C["text"], y=y, weight=QFont.Weight.DemiBold)
        if w.get("phonetic"):
            y = text_line(clean_ipa(w["phonetic"]), FONT_IPA, 14, C["muted"], y=y)
        pron = self.ctx.pron(w)
        if pron:
            y = text_line(f"okunuşu {pron}", FONT_UI, 14, C["muted"], y=y)
        y += 14
        p.setPen(QPen(QColor(C["border"]), 1))
        p.drawLine(int(inner.left()), int(y), int(inner.right()), int(y))
        y += 14
        text_line(w.get("turkish") or "", FONT_SERIF, 18, C["gold"], y=y, wrap=True)
        foot = pos_text(w.get("pos", ""))
        status = w.get("status")
        if status:
            foot += f", {STATUS_TR.get(status, '').lower()}"
        f = QFont(FONT_UI)
        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(QColor(C["dim"]))
        p.drawText(QRectF(inner.left(), inner.bottom() - 18, inner.width(), 18), Qt.AlignmentFlag.AlignLeft, foot)
        p.end()


class CardDraftPage(Page):
    def __init__(self, ctx):
        super().__init__("Card Draft", "Oyunlardaki draft gibi: her turda 3 kart çıkar, öğrenmek istediğini seç, "
                                       "kendi kelime desteni kur. Sonra desteyi çalış ya da widget'ta döndür.")
        self.ctx = ctx
        self.db = ctx.db
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_draft_tab(), "Draft")
        self.tabs.addTab(self._build_decks_tab(), "Destelerim")
        self.tabs.addTab(self._build_create_tab(), "Kart oluştur")
        self.tabs.currentChanged.connect(lambda i: self._refresh_decks() if i == 1 else None)
        ctx.decksChanged.connect(self._refresh_decks)
        ctx.decksChanged.connect(self._fill_target_decks)

    def _build_draft_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(0, 12, 0, 0)
        self.draft_stack = QStackedWidget()
        lay.addWidget(self.draft_stack)

        setup = QWidget()
        sl = QVBoxLayout(setup)
        sl.setContentsMargins(0, 0, 0, 0)
        card = Card()
        card.lay.addWidget(label("Yeni draft", "SectionTitle"))
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.deck_name = QLineEdit()
        self.deck_name.setPlaceholderText("örn. Oyun kelimelerim")
        form.addRow("Deste adı:", self.deck_name)
        self.deck_size = QComboBox()
        for n in (10, 15, 20, 30, 40):
            self.deck_size.addItem(f"{n} kart", n)
        self.deck_size.setCurrentIndex(1)
        form.addRow("Deste boyutu:", self.deck_size)
        lv = QHBoxLayout()
        self.draft_levels = {}
        for level in LEVELS:
            cb = QCheckBox(f"{level} · {LEVEL_RARITY[level]}")
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {LEVEL_COLORS[level]}; font-weight: 600;")
            self.draft_levels[level] = cb
            lv.addWidget(cb)
        lv.addStretch(1)
        form.addRow("Kart havuzu:", lv)
        card.lay.addLayout(form)
        card.lay.addWidget(label("Her turda öğrenmediğin kelimelerden 3 kart çıkar. Birini seç; 'Yeniden çek' "
                                 "hakkını (her 5 seçimde 1) beğenmediğin elleri değiştirmek için kullan. "
                                 "Kartın üzerine çift tıklarsan seslendirilir.", "Muted", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        start = button("Draft'a başla", "Primary", self._start_draft)
        start.setMinimumSize(220, 46)
        start.setStyleSheet("font-size: 16px;")
        row.addWidget(start)
        row.addStretch(1)
        card.lay.addLayout(row)
        sl.addWidget(card)
        rarity = Card()
        rarity.lay.addWidget(label("Kart nadirlikleri", "SectionTitle"))
        rr = QHBoxLayout()
        for level, name in LEVEL_RARITY.items():
            rr.addWidget(label(f"<b style='color:{LEVEL_COLORS[level]}'>{name}</b><br>"
                               f"<span style='color:{C['muted']}'>{level}"
                               f"{', senin kartların' if level == 'C1' else ''}</span>"))
        rarity.lay.addLayout(rr)
        sl.addWidget(rarity)
        sl.addStretch(1)
        self.draft_stack.addWidget(setup)

        pick = QWidget()
        pl = QVBoxLayout(pick)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(12)
        top = QHBoxLayout()
        self.pick_label = label("", "SectionTitle")
        top.addWidget(self.pick_label)
        top.addStretch(1)
        self.reroll_btn = button("", None, self._reroll)
        top.addWidget(self.reroll_btn)
        top.addWidget(button("Draft'ı iptal et", "Ghost", self._cancel_draft))
        pl.addLayout(top)
        cards = QHBoxLayout()
        cards.setSpacing(18)
        self.draft_cards = []
        for i in range(3):
            c = DraftCard(self.ctx)
            c.clicked.connect(lambda i=i: self._pick(i))
            self.draft_cards.append(c)
            cards.addWidget(c)
        pl.addLayout(cards, 1)
        pl.addWidget(label("Seçtiğin kartlar:", "Dim"))
        self.picked_label = label("", "Muted", wrap=True)
        pl.addWidget(self.picked_label)
        self.draft_stack.addWidget(pick)

        done = QWidget()
        dl = QVBoxLayout(done)
        dl.setContentsMargins(0, 0, 0, 0)
        self.done_card = Card(margins=(28, 24, 28, 24))
        dl.addWidget(self.done_card)
        dl.addStretch(1)
        self.draft_stack.addWidget(done)
        return tab

    def _start_draft(self):
        self.draft_target = self.deck_size.currentData()
        self.draft_levels_sel = [lv for lv, cb in self.draft_levels.items() if cb.isChecked()] or LEVELS
        self.draft_picked: list[dict] = []
        self.draft_seen: set[int] = set()
        self.rerolls = 1
        self._deal()
        self.draft_stack.setCurrentIndex(1)

    def _deal(self):
        hand = self.db.draft_candidates(3, self.draft_levels_sel, self.draft_seen)
        if len(hand) < 3:
            hand += self.db.draft_candidates(3 - len(hand), self.draft_levels_sel,
                                             {w["id"] for w in self.draft_picked} | {w["id"] for w in hand})
        if not hand:
            self._finish_draft()
            return
        self.hand = hand
        for c, w in zip(self.draft_cards, hand + [None] * 3):
            c.set_word(w)
            c.setVisible(w is not None)
        for w in hand:
            self.draft_seen.add(w["id"])
        self.pick_label.setText(f"Seçim {len(self.draft_picked) + 1} / {self.draft_target}. Desteye eklemek istediğin kartı seç.")
        self.reroll_btn.setText(f"Yeniden çek ({self.rerolls})")
        self.reroll_btn.setEnabled(self.rerolls > 0)
        self.picked_label.setText("  ".join(
            f"<span style='color:{LEVEL_COLORS.get(w['level'], C['text'])}'>◆</span> {w['english']}"
            for w in self.draft_picked) or "—")

    def _pick(self, i: int):
        if i >= len(self.hand):
            return
        self.draft_picked.append(self.hand[i])
        if len(self.draft_picked) % 5 == 0:
            self.rerolls += 1
        if len(self.draft_picked) >= self.draft_target:
            self._finish_draft()
        else:
            self._deal()

    def _reroll(self):
        if self.rerolls <= 0:
            return
        self.rerolls -= 1
        self._deal()

    def _cancel_draft(self):
        if self.draft_picked and not confirm(self, "Draft'ı iptal et",
                                             f"{len(self.draft_picked)} seçim yaptın. Yine de iptal edilsin mi?"):
            return
        self.draft_stack.setCurrentIndex(0)

    def _finish_draft(self):
        if not self.draft_picked:
            self.draft_stack.setCurrentIndex(0)
            return
        name = self.deck_name.text().strip() or f"Draft {dt.datetime.now():%d.%m %H:%M}"
        deck_id = self.db.create_deck(name, "draft", f"{len(self.draft_picked)} kartlık draft destesi")
        self.db.add_to_deck(deck_id, [w["id"] for w in self.draft_picked])
        self.ctx.decksChanged.emit()
        self.deck_name.clear()
        clear_layout(self.done_card.lay)
        self.done_card.lay.addWidget(label(f"Deste hazır: {name}", "PageTitle"))
        counts = {}
        for w in self.draft_picked:
            counts[w["level"]] = counts.get(w["level"], 0) + 1
        self.done_card.lay.addWidget(label("  ".join(
            f"<b style='color:{LEVEL_COLORS.get(lv, C['text'])}'>◆ {LEVEL_RARITY.get(lv, lv)}: {n}</b>"
            for lv, n in sorted(counts.items()))))
        grid = QGridLayout()
        for i, w in enumerate(self.draft_picked):
            grid.addWidget(label(f"<b>{w['english']}</b> <span style='color:{C['muted']}'>— {w['turkish']}</span>",
                                 wrap=True), i // 3, i % 3)
        self.done_card.lay.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(button("Bu desteyi çalış", "Primary",
                             lambda: self.ctx.navigate("training", deck_id=deck_id, mode="flash")))
        row.addWidget(button("Widget'ta döndür", None, lambda: self._deck_to_widget(deck_id)))
        row.addWidget(button("Yeni draft", None, lambda: self.draft_stack.setCurrentIndex(0)))
        row.addStretch(1)
        self.done_card.lay.addLayout(row)
        self.draft_stack.setCurrentIndex(2)

    def _deck_to_widget(self, deck_id: int):
        self.ctx.set("widget.deck_id", deck_id)
        self.ctx.set("widget.source", "deck")
        if not self.ctx.get("widget.enabled"):
            self.ctx.set("widget.enabled", True)
        self.ctx.toast("Widget artık bu desteyi gösteriyor")

    def _build_decks_tab(self) -> QWidget:
        tab = QWidget()
        lay = QHBoxLayout(tab)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(14)
        self.deck_list = QListWidget()
        self.deck_list.setFixedWidth(280)
        self.deck_list.currentItemChanged.connect(lambda *_: self._show_deck())
        lay.addWidget(self.deck_list)
        right = QVBoxLayout()
        self.deck_title = label("", "SectionTitle")
        self.deck_info = label("", "Muted")
        right.addWidget(self.deck_title)
        right.addWidget(self.deck_info)
        btns = QHBoxLayout()
        self.d_study = button("Çalış", "Primary", lambda: self._deck_action("study"))
        self.d_widget = button("Widget'ta döndür", None, lambda: self._deck_action("widget"))
        self.d_rename = button("Yeniden adlandır", None, lambda: self._deck_action("rename"))
        self.d_remove = button("Seçili kartı çıkar", None, lambda: self._deck_action("remove"))
        self.d_delete = button("Desteyi sil", "Danger", lambda: self._deck_action("delete"))
        for b in (self.d_study, self.d_widget, self.d_rename, self.d_remove, self.d_delete):
            btns.addWidget(b)
        btns.addStretch(1)
        right.addLayout(btns)
        self.deck_cards = QListWidget()
        self.deck_cards.itemDoubleClicked.connect(
            lambda it: self.ctx.speak(it.data(Qt.ItemDataRole.UserRole + 1) or ""))
        right.addWidget(self.deck_cards, 1)
        self.decks_empty = label("Henüz desten yok. 'Draft' sekmesinden ilk desteni kur! ", "Muted")
        right.addWidget(self.decks_empty)
        lay.addLayout(right, 1)
        return tab

    def _refresh_decks(self):
        cur = self.deck_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.deck_list.currentItem() else None
        self.deck_list.blockSignals(True)
        self.deck_list.clear()
        decks = self.db.list_decks()
        for d in decks:
            it = QListWidgetItem(f"{d['name']}\n{d['cards']} kart, {d['learned']} öğrenildi")
            it.setData(Qt.ItemDataRole.UserRole, d["id"])
            self.deck_list.addItem(it)
        self.deck_list.blockSignals(False)
        idx = 0
        for i in range(self.deck_list.count()):
            if self.deck_list.item(i).data(Qt.ItemDataRole.UserRole) == cur:
                idx = i
        if decks:
            self.deck_list.setCurrentRow(idx)
        self._show_deck()

    def _current_deck_id(self):
        it = self.deck_list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _show_deck(self):
        deck_id = self._current_deck_id()
        has = deck_id is not None
        for b in (self.d_study, self.d_widget, self.d_rename, self.d_remove, self.d_delete):
            b.setEnabled(has)
        self.decks_empty.setVisible(self.deck_list.count() == 0)
        self.deck_cards.clear()
        if not has:
            self.deck_title.setText("")
            self.deck_info.setText("")
            return
        d = next((x for x in self.db.list_decks() if x["id"] == deck_id), None)
        if not d:
            return
        words = self.db.deck_words(deck_id)
        self.deck_title.setText(d["name"])
        pct = 100 * d["learned"] / d["cards"] if d["cards"] else 0
        widget_on = self.ctx.get("widget.source") == "deck" and self.ctx.get("widget.deck_id") == deck_id
        self.deck_info.setText(f"{d['cards']} kart, {d['learned']} tanesi öğrenildi (%{pct:.0f}). "
                               f"Oluşturma tarihi {d['created_at'][:10]}." + (" Şu an widget'ta gösteriliyor." if widget_on else ""))
        for w in words:
            it = QListWidgetItem(f"{w['english']}    {w['turkish']}    ({STATUS_TR[w['status']].lower()})")
            it.setData(Qt.ItemDataRole.UserRole, w["id"])
            it.setData(Qt.ItemDataRole.UserRole + 1, w["english"])
            self.deck_cards.addItem(it)

    def _deck_action(self, action: str):
        deck_id = self._current_deck_id()
        if deck_id is None:
            return
        if action == "study":
            self.ctx.navigate("training", deck_id=deck_id)
        elif action == "widget":
            self._deck_to_widget(deck_id)
            self._show_deck()
        elif action == "rename":
            name, ok = QInputDialog.getText(self, "Yeniden adlandır", "Yeni ad:")
            if ok and name.strip():
                self.db.rename_deck(deck_id, name)
                self.ctx.decksChanged.emit()
        elif action == "remove":
            it = self.deck_cards.currentItem()
            if it:
                self.db.remove_from_deck(deck_id, it.data(Qt.ItemDataRole.UserRole))
                self.ctx.decksChanged.emit()
        elif action == "delete":
            if confirm(self, "Desteyi sil", "Bu deste silinsin mi? (Kelimeler kütüphanede kalır.)"):
                self.db.delete_deck(deck_id)
                if self.ctx.get("widget.deck_id") == deck_id:
                    self.ctx.set("widget.source", "smart")
                    self.ctx.set("widget.deck_id", None)
                self.ctx.decksChanged.emit()

    def _build_create_tab(self) -> QWidget:
        tab = QWidget()
        lay = QHBoxLayout(tab)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(18)
        card = Card()
        card.lay.addWidget(label("Kendi kartını oluştur", "SectionTitle"))
        card.lay.addWidget(label("Oyunda, dizide, işte karşılaştığın kelimeleri ekle. Efsanevi (C1) kart olarak "
                                 "kütüphaneye ve seçtiğin desteye eklenir.", "Muted", wrap=True))
        form = QFormLayout()
        form.setVerticalSpacing(9)
        self.c_en = QLineEdit()
        self.c_tr = QLineEdit()
        self.c_ipa = QLineEdit()
        self.c_ex = QLineEdit()
        self.c_ex_tr = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(self.c_en, 1)
        self.c_fetch = button("İnternetten doldur", None, self._create_fetch)
        row.addWidget(self.c_fetch)
        form.addRow("İngilizce *", row)
        form.addRow("Türkçe *", self.c_tr)
        form.addRow("Fonetik (IPA)", self.c_ipa)
        form.addRow("Örnek cümle", self.c_ex)
        form.addRow("Örnek (Türkçe)", self.c_ex_tr)
        self.c_deck = QComboBox()
        form.addRow("Desteye ekle", self.c_deck)
        card.lay.addLayout(form)
        self.c_status = label("", "Muted", wrap=True)
        card.lay.addWidget(self.c_status)
        r2 = QHBoxLayout()
        r2.addStretch(1)
        r2.addWidget(button("Kartı oluştur", "Primary", self._create_card))
        card.lay.addLayout(r2)
        card.lay.addStretch(1)
        lay.addWidget(card, 3)
        self.c_preview = DraftCard(self.ctx, interactive=False)
        self.c_preview.setFixedWidth(280)
        lay.addWidget(self.c_preview)
        for w in (self.c_en, self.c_tr, self.c_ipa):
            w.textChanged.connect(self._update_preview)
        self._fill_target_decks()
        self._update_preview()
        return tab

    def _fill_target_decks(self):
        if not hasattr(self, "c_deck"):
            return
        cur = self.c_deck.currentData()
        self.c_deck.clear()
        self.c_deck.addItem("(desteye ekleme)", None)
        self.c_deck.addItem("'Kendi Kartlarım' destesi", "__mine__")
        for d in self.db.list_decks():
            self.c_deck.addItem(f"{d['name']} ({d['cards']})", d["id"])
        i = self.c_deck.findData(cur)
        self.c_deck.setCurrentIndex(i if i >= 0 else 1)

    def _update_preview(self):
        ipa = self.c_ipa.text().strip()
        self.c_preview.set_word({
            "id": 0, "english": self.c_en.text().strip() or "your word", "turkish": self.c_tr.text().strip() or "anlamı",
            "phonetic": ipa, "pron_tr": None, "pos": "", "level": "C1", "status": 0,
        })

    def _create_fetch(self):
        word = self.c_en.text().strip()
        if not word:
            self.c_status.setText("Önce İngilizce kelimeyi yaz.")
            return
        self.c_fetch.setEnabled(False)
        self.c_status.setText("Getiriliyor…")

        def done(data):
            self.c_fetch.setEnabled(True)
            if data.get("turkish") and not self.c_tr.text():
                self.c_tr.setText(data["turkish"])
            if data.get("phonetic") and not self.c_ipa.text():
                self.c_ipa.setText(data["phonetic"])
            if data.get("example") and not self.c_ex.text():
                self.c_ex.setText(data["example"])
                self.c_ex_tr.setText(data.get("example_tr", ""))
            self.c_status.setText("Dolduruldu." + (" " + " | ".join(data["errors"]) if data.get("errors") else ""))

        def fail(msg):
            self.c_fetch.setEnabled(True)
            self.c_status.setText(f"{msg}")

        run_async(fetch_word_info, word, on_done=done, on_error=fail)

    def _create_card(self):
        en, tr = self.c_en.text().strip(), self.c_tr.text().strip()
        if not en or not tr:
            self.c_status.setText("<span style='color:#EF4444'>İngilizce ve Türkçe zorunlu.</span>")
            return
        existing = self.db.get_word_by_english(en)
        if existing:
            word_id = existing["id"]
            msg = f"'{en}' zaten kütüphanede vardı"
        else:
            word_id = self.db.add_word(en, tr, self.c_ipa.text().strip().strip("/[]"), None, "", "C1",
                                       self.c_ex.text(), self.c_ex_tr.text(), source="user")
            msg = f"'{en}' kartı oluşturuldu"
            self.ctx.wordsChanged.emit()
        target = self.c_deck.currentData()
        if target == "__mine__":
            mine = next((d for d in self.db.list_decks() if d["name"] == "Kendi Kartlarım"), None)
            target = mine["id"] if mine else self.db.create_deck("Kendi Kartlarım", "custom")
        if target is not None:
            self.db.add_to_deck(target, [word_id])
            self.ctx.decksChanged.emit()
            msg += " ve desteye eklendi"
        self.c_status.setText(msg)
        self.ctx.toast(msg)
        for w in (self.c_en, self.c_tr, self.c_ipa, self.c_ex, self.c_ex_tr):
            w.clear()
        self.c_en.setFocus()

    def on_show(self):
        if self.tabs.currentIndex() == 1:
            self._refresh_decks()
