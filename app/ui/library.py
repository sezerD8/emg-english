from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLineEdit, QMenu, QPlainTextEdit, QTableView, QVBoxLayout,
)

from ..config import LEVEL_COLORS, LEVELS, POS_TR, STATUS_COLORS, STATUS_LEARNED, STATUS_LEARNING, STATUS_NEW, \
    STATUS_TR
from ..database import parse_ts
from ..online import fetch_word_info, run_async
from ..pronunciation import clean_ipa, ipa_to_turkish
from ..theme import C
from .common import Card, Page, WordView, button, confirm, info, label, pos_text

COLUMNS = ["★", "İngilizce", "Türkçe", "Fonetik", "Okunuş", "Tür", "Seviye", "Durum", "Görülme"]


class WordTableModel(QAbstractTableModel):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.rows: list[dict] = []
        self._bold = QFont()
        self._bold.setBold(True)

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        w = self.rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return "★" if w["favorite"] else ""
            if col == 1:
                return w["english"]
            if col == 2:
                return w["turkish"]
            if col == 3:
                return clean_ipa(w["phonetic"])
            if col == 4:
                return self.ctx.pron(w)
            if col == 5:
                return pos_text(w["pos"])
            if col == 6:
                return w["level"]
            if col == 7:
                return STATUS_TR.get(w["status"], "")
            if col == 8:
                return str(w["widget_seen"]) if w["widget_seen"] else ""
        if role == Qt.ItemDataRole.ToolTipRole and col == 8:
            return f"Widget'ta {w['widget_seen']} kez görüldü. Eğitimde {w['correct']} doğru, {w['wrong']} yanlış."
        if role == Qt.ItemDataRole.UserRole:
            return [w["favorite"], w["english"].lower(), w["turkish"].lower(), w["phonetic"], self.ctx.pron(w),
                    w["pos"], (w["rank"] or 999999), w["status"], w["widget_seen"]][col]
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 0:
                return QColor(C["gold"])
            if col == 6:
                return QColor(LEVEL_COLORS.get(w["level"], C["text"]))
            if col == 7:
                return QColor(STATUS_COLORS.get(w["status"], C["muted"]))
            if col in (3, 4, 8):
                return QColor(C["muted"])
        if role == Qt.ItemDataRole.FontRole and col == 1:
            return self._bold
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (0, 6, 8):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def word_at(self, row: int) -> dict | None:
        return self.rows[row] if 0 <= row < len(self.rows) else None


class WordDialog(QDialog):
    def __init__(self, ctx, word: dict | None = None, parent=None, preset_english: str = ""):
        super().__init__(parent)
        self.ctx = ctx
        self.word = word
        self.setWindowTitle("Kelimeyi düzenle" if word else "Yeni kelime ekle")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        lay.addWidget(label("Kelimeyi düzenle" if word else "Yeni kelime ekle", "SectionTitle"))
        form = QFormLayout()
        form.setVerticalSpacing(9)
        self.english = QLineEdit()
        self.turkish = QLineEdit()
        self.phonetic = QLineEdit()
        self.pron = QLineEdit()
        self.pron.setPlaceholderText("Boş bırakılırsa fonetikten otomatik üretilir")
        self.pos = QComboBox()
        self.pos.addItem("—", "")
        for k, v in POS_TR.items():
            self.pos.addItem(v, k)
        self.level = QComboBox()
        for lv in LEVELS + ["C1"]:
            self.level.addItem(lv, lv)
        self.example = QLineEdit()
        self.example_tr = QLineEdit()

        en_row = QHBoxLayout()
        en_row.addWidget(self.english, 1)
        self.fetch_btn = button("İnternetten doldur", None, self._fetch,
                                "Fonetik, örnek cümle ve Türkçe anlamı ücretsiz sözlük/çeviri servislerinden getirir")
        en_row.addWidget(self.fetch_btn)
        form.addRow("İngilizce *", en_row)
        form.addRow("Türkçe anlamı *", self.turkish)
        form.addRow("Fonetik (IPA)", self.phonetic)
        pr = QHBoxLayout()
        pr.addWidget(self.pron, 1)
        self.auto_pron = label("", "Dim")
        pr.addWidget(self.auto_pron)
        form.addRow("Türkçe okunuş", pr)
        form.addRow("Tür", self.pos)
        form.addRow("Seviye", self.level)
        form.addRow("Örnek cümle", self.example)
        form.addRow("Örnek (Türkçe)", self.example_tr)
        lay.addLayout(form)
        self.status = label("", "Muted", wrap=True)
        lay.addWidget(self.status)
        buttons = QDialogButtonBox()
        self.ok_btn = buttons.addButton("Kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok_btn.setObjectName("Primary")
        buttons.addButton("Vazgeç", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.phonetic.textChanged.connect(self._update_auto_pron)

        if word:
            self.english.setText(word["english"])
            self.turkish.setText(word["turkish"])
            self.phonetic.setText(word["phonetic"])
            self.pron.setText(word.get("pron_tr") or "")
            self.pos.setCurrentIndex(max(0, self.pos.findData((word["pos"] or "").split(",")[0])))
            self.level.setCurrentIndex(max(0, self.level.findData(word["level"])))
            self.example.setText(word.get("example") or "")
            self.example_tr.setText(word.get("example_tr") or "")
        else:
            self.level.setCurrentIndex(self.level.findData("C1"))
            self.english.setText(preset_english)
        self._update_auto_pron()

    def _update_auto_pron(self):
        auto = ipa_to_turkish(self.phonetic.text(), bool(self.ctx.get("pron.keep_w")), bool(self.ctx.get("pron.keep_th")))
        self.auto_pron.setText(f"otomatik: {auto}" if auto else "")

    def _fetch(self):
        word = self.english.text().strip()
        if not word:
            self.status.setText("Önce İngilizce kelimeyi yaz.")
            return
        self.fetch_btn.setEnabled(False)
        self.status.setText("İnternetten getiriliyor…")
        run_async(fetch_word_info, word, on_done=self._fetched, on_error=self._fetch_failed)

    def _fetched(self, data: dict):
        self.fetch_btn.setEnabled(True)
        filled = []
        if data.get("turkish") and not self.turkish.text().strip():
            self.turkish.setText(data["turkish"])
            filled.append("anlam")
        if data.get("phonetic") and not self.phonetic.text().strip():
            self.phonetic.setText(data["phonetic"])
            filled.append("fonetik")
        if data.get("pos") and not self.pos.currentData():
            self.pos.setCurrentIndex(max(0, self.pos.findData(data["pos"].split(",")[0])))
            filled.append("tür")
        if data.get("example") and not self.example.text().strip():
            self.example.setText(data["example"])
            self.example_tr.setText(data.get("example_tr") or self.example_tr.text())
            filled.append("örnek")
        msg = ("Dolduruldu: " + ", ".join(filled)) if filled else "Yeni bilgi bulunamadı (alanlar zaten dolu olabilir)."
        if data.get("errors"):
            msg += "\n" + " | ".join(data["errors"])
        if data.get("definition"):
            msg += f"\nTanım: {data['definition']}"
        self.status.setText(msg)

    def _fetch_failed(self, message: str):
        self.fetch_btn.setEnabled(True)
        self.status.setText(f"Getirilemedi: {message}")

    def _save(self):
        en, tr = self.english.text().strip(), self.turkish.text().strip()
        if not en or not tr:
            self.status.setText("<span style='color:#EF4444'>İngilizce ve Türkçe alanları zorunlu.</span>")
            return
        fields = dict(english=en, turkish=tr, phonetic=self.phonetic.text().strip().strip("/[]"),
                      pron_tr=self.pron.text().strip() or None, pos=self.pos.currentData() or "",
                      level=self.level.currentData(), example=self.example.text().strip(),
                      example_tr=self.example_tr.text().strip())
        try:
            if self.word:
                other = self.ctx.db.get_word_by_english(en)
                if other and other["id"] != self.word["id"]:
                    raise ValueError(f"'{en}' zaten kütüphanede var.")
                self.ctx.db.update_word(self.word["id"], **fields)
                self.saved_id = self.word["id"]
            else:
                self.saved_id = self.ctx.db.add_word(source="user", **fields)
        except ValueError as exc:
            self.status.setText(f"<span style='color:#EF4444'>{exc}</span>")
            return
        self.accept()


class LibraryPage(Page):
    def __init__(self, ctx):
        super().__init__("Kütüphane", "Tüm kelimeler burada. Ara, filtrele, düzenle, kendi kelimelerini ekle.")
        self.ctx = ctx
        self.db = ctx.db
        self.header_actions.addWidget(button("Kelime ekle", "Primary", self.add_word))
        self.header_actions.addWidget(button("İçe aktar", None, self.import_csv,
                                             "CSV: english;turkish;phonetic;pos;example;example_tr"))
        self.header_actions.addWidget(button("Dışa aktar", None, self.export_csv))

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("İngilizce veya Türkçe ara…")
        self.search.setClearButtonEnabled(True)
        bar.addWidget(self.search, 3)
        self.f_level = QComboBox()
        self.f_level.addItem("Tüm seviyeler", None)
        for lv in LEVELS + ["C1"]:
            self.f_level.addItem(lv, lv)
        self.f_status = QComboBox()
        self.f_status.addItem("Tüm durumlar", None)
        for k, v in STATUS_TR.items():
            self.f_status.addItem(v, k)
        self.f_pos = QComboBox()
        self.f_pos.addItem("Tüm türler", None)
        for k, v in POS_TR.items():
            self.f_pos.addItem(v, k)
        self.f_source = QComboBox()
        self.f_source.addItem("Tüm kaynaklar", None)
        self.f_source.addItem("Hazır liste", "builtin")
        self.f_source.addItem("Benim eklediklerim", "user")
        self.f_source.addItem("Düzenlediklerim", "edited")
        self.f_fav = QCheckBox("Sadece favoriler")
        for w in (self.f_level, self.f_status, self.f_pos, self.f_source):
            bar.addWidget(w, 1)
            w.currentIndexChanged.connect(self.reload)
        bar.addWidget(self.f_fav)
        self.f_fav.toggled.connect(self.reload)
        self.root.addLayout(bar)

        self._search_timer = QTimer(self, singleShot=True, interval=250)
        self._search_timer.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda _: self._search_timer.start())

        body = QHBoxLayout()
        body.setSpacing(14)
        left = QVBoxLayout()
        self.model = WordTableModel(ctx)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(lambda _: self.edit_word())
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(False)
        for col, width in enumerate([30, 118, 200, 100, 90, 70, 50, 92, 62]):
            self.table.setColumnWidth(col, width)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        left.addWidget(self.table, 1)
        self.count_label = label("", "Dim")
        left.addWidget(self.count_label)
        body.addLayout(left, 1)

        self.detail = Card()
        self.detail.setFixedWidth(340)
        self.detail.setStyleSheet("QPushButton { padding: 7px 8px; }")
        self.detail_view = WordView(ctx, compact=True, marker=False)
        self.detail.lay.addWidget(self.detail_view)
        self.detail_info = label("", "Muted", wrap=True)
        self.detail_info.setTextFormat(Qt.TextFormat.RichText)
        self.detail.lay.addWidget(self.detail_info)
        st = QHBoxLayout()
        self.b_learned = button("Öğrendim", "Success", lambda: self._set_status(STATUS_LEARNED))
        self.b_learning = button("Tekrarla", None, lambda: self._set_status(STATUS_LEARNING),
                                 "Öğreniliyor olarak işaretle (tekrar listesine al)")
        self.b_reset = button("Sıfırla", "Ghost", lambda: self._set_status(STATUS_NEW))
        for b in (self.b_learned, self.b_learning, self.b_reset):
            st.addWidget(b)
        self.detail.lay.addLayout(st)
        ac = QHBoxLayout()
        self.b_fav = button("Favorilere ekle", None, self._toggle_fav)
        self.b_deck = button("Desteye ekle", None, self._deck_menu)
        ac.addWidget(self.b_fav)
        ac.addWidget(self.b_deck)
        self.detail.lay.addLayout(ac)
        ac2 = QHBoxLayout()
        ac2.addWidget(button("Düzenle", None, self.edit_word))
        self.b_example = button("Örnek getir", None, self._fetch_example,
                                "Örnek cümleyi ücretsiz sözlükten getirir")
        ac2.addWidget(self.b_example)
        ac2.addWidget(button("Sil", "Danger", self.delete_words, "Kelimeyi ve ilerlemesini sil"))
        self.detail.lay.addLayout(ac2)
        self.detail.lay.addWidget(label("Notun", "Dim"))
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Bu kelimeyle ilgili notun, cümlen, hatırlatıcın…")
        self.note.setFixedHeight(70)
        self.detail.lay.addWidget(self.note)
        self._note_timer = QTimer(self, singleShot=True, interval=600)
        self._note_timer.timeout.connect(self._save_note)
        self.note.textChanged.connect(lambda: self._note_timer.start())
        self.detail.lay.addStretch(1)
        body.addWidget(self.detail)
        self.root.addLayout(body, 1)

        self.current: dict | None = None
        self._loading_note = False
        self._dirty = True
        ctx.progressChanged.connect(self._mark_dirty)
        ctx.wordsChanged.connect(self._mark_dirty)
        ctx.settingsChanged.connect(lambda k: self.model.layoutChanged.emit() if k.startswith("pron.") else None)
        self._show_detail(None)

    def _mark_dirty(self):
        self._dirty = True
        if self.isVisible():
            self.reload()

    def on_show(self):
        if self._dirty:
            self.reload()

    def apply_params(self, params: dict):
        if "search" in params:
            self.search.setText(params["search"])

    def reload(self):
        selected_id = self.current["id"] if self.current else None
        rows = self.db.search_words(
            text=self.search.text().strip(), level=self.f_level.currentData(), status=self.f_status.currentData(),
            pos=self.f_pos.currentData(), favorites=self.f_fav.isChecked(), source=self.f_source.currentData())
        self.model.set_rows(rows)
        self._dirty = False
        tot = self.db.word_count()
        shown, total = (f"{n:,}".replace(",", ".") for n in (len(rows), tot))
        self.count_label.setText(f"{shown} kelime gösteriliyor, kütüphanede toplam {total} kelime var.")
        if selected_id is not None:
            for r, w in enumerate(rows):
                if w["id"] == selected_id:
                    idx = self.proxy.mapFromSource(self.model.index(r, 0))
                    self.table.selectRow(idx.row())
                    self.table.scrollTo(idx)
                    self._show_detail(self.db.get_word(selected_id))
                    return
        if rows:
            self.table.selectRow(0)
        else:
            self._show_detail(None)

    def _selected_words(self) -> list[dict]:
        rows = sorted({self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.rows[r] for r in rows if r < len(self.model.rows)]

    def _selection_changed(self):
        sel = self._selected_words()
        self._show_detail(self.db.get_word(sel[0]["id"]) if sel else None)

    def _show_detail(self, w: dict | None):
        self.current = w
        self.detail_view.set_word(w)
        enabled = w is not None
        for b in (self.b_learned, self.b_learning, self.b_reset, self.b_fav, self.b_deck, self.b_example):
            b.setEnabled(enabled)
        self._loading_note = True
        self.note.setPlainText(w.get("note", "") if w else "")
        self._loading_note = False
        self.note.setEnabled(enabled)
        if not w:
            self.detail_info.setText("Bir kelime seç.")
            return
        due = parse_ts(w["due_at"])
        due_sentence = "Henüz çalışılmadı."
        if due and w["status"] > 0:
            days = (due - dt.datetime.now()).total_seconds() / 86400
            if days <= 0:
                due_sentence = "Tekrar zamanı geldi."
            elif days < 1 / 24:
                due_sentence = "Bir saat içinde tekrar edilecek."
            elif days < 1:
                due_sentence = f"{days * 24:.0f} saat sonra tekrar edilecek."
            else:
                due_sentence = f"{days:.0f} gün sonra tekrar edilecek."
        example = ""
        if w.get("example"):
            example = (f"<p style='margin-top:6px'><i>“{w['example']}”</i>"
                       + (f"<br><span style='color:{C['dim']}'>{w['example_tr']}</span>" if w.get("example_tr") else "")
                       + "</p>")
        self.detail_info.setText(
            f"<span style='color:{STATUS_COLORS[w['status']]}'>{STATUS_TR[w['status']]}</span>"
            f", sıklık sırası {w['rank'] or 'yok'}<br>"
            f"Widget'ta {w['widget_seen']} kez görüldü, {w['reviews']} kez tekrar edildi "
            f"({w['correct']} doğru, {w['wrong']} yanlış).<br>"
            f"{due_sentence}"
            f"{example}")
        fav = bool(w["favorite"])
        self.b_fav.setText("Favorilerden çıkar" if fav else "Favorilere ekle")


    def _changed(self, word_id: int | None = None):
        self.ctx.progressChanged.emit()
        if word_id is not None:
            self._show_detail(self.db.get_word(word_id))

    def _word_below_selection(self) -> dict | None:
        rows = [i.row() for i in self.table.selectionModel().selectedRows()]
        if not rows:
            return None
        nxt = self.proxy.index(max(rows) + 1, 0)
        return self.model.word_at(self.proxy.mapToSource(nxt).row()) if nxt.isValid() else None

    def _set_status(self, status: int):
        sel = self._selected_words() or ([self.current] if self.current else [])
        if not sel:
            return
        nxt = self._word_below_selection()
        for w in sel:
            self.db.set_status(w["id"], status)
        self.ctx.toast(f"{len(sel)} kelime → {STATUS_TR[status]}")
        if nxt:
            self.current = nxt
            self._changed(nxt["id"])
        else:
            self._changed(sel[0]["id"])

    def _toggle_fav(self):
        if self.current:
            self.db.toggle_favorite(self.current["id"])
            self._changed(self.current["id"])

    def _save_note(self):
        if self.current and not self._loading_note:
            self.db.set_note(self.current["id"], self.note.toPlainText())

    def add_word(self, preset: str = ""):
        dlg = WordDialog(self.ctx, None, self, preset_english=preset if isinstance(preset, str) else "")
        if dlg.exec():
            self.ctx.wordsChanged.emit()
            self.search.setText(dlg.english.text().strip())
            self.ctx.toast("Kelime eklendi")

    def edit_word(self):
        if not self.current:
            return
        dlg = WordDialog(self.ctx, self.current, self)
        if dlg.exec():
            self.ctx.wordsChanged.emit()
            self._show_detail(self.db.get_word(self.current["id"]))

    def delete_words(self):
        sel = self._selected_words()
        if not sel:
            return
        names = ", ".join(w["english"] for w in sel[:5]) + (" …" if len(sel) > 5 else "")
        if not confirm(self, "Sil", f"{len(sel)} kelime ve ilerlemesi silinsin mi?\n{names}"):
            return
        for w in sel:
            self.db.delete_word(w["id"])
        self.current = None
        self.ctx.wordsChanged.emit()

    def _deck_menu(self):
        sel = self._selected_words()
        if not sel:
            return
        menu = QMenu(self)
        for d in self.db.list_decks():
            act = QAction(f"{d['name']} ({d['cards']} kart)", menu)
            act.triggered.connect(lambda _=False, did=d["id"], dn=d["name"]: self._add_to_deck(did, dn, sel))
            menu.addAction(act)
        if menu.actions():
            menu.addSeparator()
        new = QAction("Yeni deste oluştur…", menu)
        new.triggered.connect(lambda: self._new_deck(sel))
        menu.addAction(new)
        menu.exec(self.b_deck.mapToGlobal(self.b_deck.rect().bottomLeft()))

    def _add_to_deck(self, deck_id, name, words):
        self.db.add_to_deck(deck_id, [w["id"] for w in words])
        self.ctx.decksChanged.emit()
        self.ctx.toast(f"{len(words)} kart {name} destesine eklendi")

    def _new_deck(self, words):
        name, ok = QInputDialog.getText(self, "Yeni deste", "Deste adı:")
        if ok and name.strip():
            did = self.db.create_deck(name.strip(), "custom")
            self._add_to_deck(did, name.strip(), words)

    def _fetch_example(self):
        w = self.current
        if not w:
            return
        self.b_example.setEnabled(False)
        self.b_example.setText("…")
        wid = w["id"]

        def done(data):
            self.b_example.setEnabled(True)
            self.b_example.setText("Örnek getir")
            fields = {}
            if data.get("example"):
                fields["example"] = data["example"]
                fields["example_tr"] = data.get("example_tr", "")
            if data.get("phonetic") and not w["phonetic"]:
                fields["phonetic"] = data["phonetic"]
            if fields:
                self.db.update_word(wid, **fields)
                self._changed(wid)
                self.ctx.toast("Örnek cümle eklendi")
            else:
                self.ctx.toast("Bu kelime için örnek bulunamadı")

        def fail(msg):
            self.b_example.setEnabled(True)
            self.b_example.setText("Örnek getir")
            self.ctx.toast(f"İnternet hatası: {msg}")

        run_async(fetch_word_info, w["english"], on_done=done, on_error=fail)

    def _context_menu(self, pos):
        if not self._selected_words():
            return
        menu = QMenu(self)
        items = [
            ("Seslendir", lambda: self.current and self.ctx.speak(self.current["english"])),
            (None, None),
            ("Öğrendim", lambda: self._set_status(STATUS_LEARNED)),
            ("Öğreniyorum", lambda: self._set_status(STATUS_LEARNING)),
            ("Sıfırla (yeni kelime yap)", lambda: self._set_status(STATUS_NEW)),
            ("Favorilere ekle / çıkar", self._toggle_fav),
            ("Desteye ekle…", self._deck_menu),
            (None, None),
            ("Düzenle", self.edit_word),
            ("Sil", self.delete_words),
        ]
        for text, slot in items:
            if text is None:
                menu.addSeparator()
                continue
            act = QAction(text, menu)
            act.triggered.connect(slot)
            menu.addAction(act)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Dışa aktar", str(Path.home() / "emg_kelimeler.csv"),
                                              "CSV (*.csv)")
        if not path:
            return
        rows = self.model.rows
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            wr = csv.writer(f, delimiter=";")
            wr.writerow(["english", "turkish", "phonetic", "pronunciation_tr", "pos", "level", "status",
                         "favorite", "widget_seen", "correct", "wrong", "example", "example_tr", "note"])
            for w in rows:
                wr.writerow([w["english"], w["turkish"], w["phonetic"], self.ctx.pron(w), w["pos"], w["level"],
                             STATUS_TR[w["status"]], w["favorite"], w["widget_seen"], w["correct"], w["wrong"],
                             w["example"], w["example_tr"], w["note"]])
        info(self, "Dışa aktarıldı", f"{len(rows)} kelime kaydedildi:\n{path}")

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "İçe aktar", str(Path.home()), "CSV / TXT (*.csv *.txt)")
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
        added, skipped = self.import_text(text)
        self.ctx.wordsChanged.emit()
        info(self, "İçe aktarma", f"{added} kelime eklendi, {skipped} kelime zaten vardı / atlandı.")

    def import_text(self, text: str) -> tuple[int, int]:
        try:
            dialect = csv.Sniffer().sniff(text[:4000], delimiters=";,\t|")
            delim = dialect.delimiter
        except csv.Error:
            delim = ";" if ";" in text else ","
        rows = [[c.strip() for c in r] for r in csv.reader(text.splitlines(), delimiter=delim)]
        rows = [r for r in rows if r and any(r)]
        if not rows:
            return 0, 0
        default_cols = ["english", "turkish", "phonetic", "pos", "example", "example_tr"]
        header = [h.lower() for h in rows[0]]
        if "english" in header or "ingilizce" in header:
            header = ["english" if h == "ingilizce" else "turkish" if h in ("türkçe", "turkce") else h for h in header]
            rows = rows[1:]
        else:
            header = default_cols
        added = skipped = 0
        for r in rows:
            rec = {header[i]: r[i] for i in range(min(len(header), len(r)))}
            en, tr = rec.get("english", ""), rec.get("turkish", "")
            if not en or not tr:
                skipped += 1
                continue
            pos = ",".join(p.strip() for p in rec.get("pos", "").split(",") if p.strip() in POS_TR)
            ipa = rec.get("phonetic", "").strip("/[] ")
            pron = rec.get("pronunciation_tr", "").strip()
            if pron and pron == self.ctx.pron({"phonetic": ipa}):
                pron = ""
            try:
                self.db.add_word(en, tr, ipa, pron or None, pos, "C1", rec.get("example", ""),
                                 rec.get("example_tr", ""), source="user")
                added += 1
            except ValueError:
                skipped += 1
        return added, skipped
