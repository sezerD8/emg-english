from __future__ import annotations

import random
import time
import unicodedata

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLineEdit, QProgressBar, QPushButton, QSpinBox,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..config import KINDS, LEVELS, STATUS_LEARNED, STATUS_NEW
from ..pronunciation import clean_ipa
from ..theme import C, FONT_SERIF
from .common import Card, Page, WordView, button, clear_layout, label, pos_text

MODES = {
    "flash": ("", "Kartlar (aralıklı tekrar)", "Hatırla, kendini puanla; tekrarlar otomatik planlanır."),
    "choice_en": ("", "İngilizce → Türkçe", "İngilizce kelimeyi gör, doğru anlamı seç."),
    "choice_tr": ("", "Türkçe → İngilizce", "Türkçe anlamı gör, doğru kelimeyi seç."),
    "typing": ("", "Yazma", "Türkçe anlamı gör, İngilizcesini yaz (spelling)."),
    "listening": ("", "Dinleme", "Kelimeyi dinle ve duyduğunu yaz."),
}

SOURCES = [
    ("smart", "Akıllı (tekrarı gelenler + yeni kelimeler)"),
    ("due", "Sadece tekrar zamanı gelenler"),
    ("new", "Yeni kelimeler (sıklık sırasıyla)"),
    ("widget", "Widget'ta en çok gördüklerim"),
    ("learning", "Öğrenmekte olduklarım"),
    ("hard", "En çok yanıldıklarım"),
    ("favorites", "Favorilerim"),
    ("learned", "Öğrendiklerim (pekiştirme)"),
    ("random", "Rastgele"),
    ("deck", "Bir desteden"),
]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").strip().lower()
    text = text.replace("’", "'").replace("`", "'")
    text = "".join(ch for ch in text if ch not in ",.!?;:\"“”")
    return " ".join(text.split())


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def first_meaning(turkish: str) -> str:
    return (turkish or "").split(";")[0].strip()


class TrainingPage(Page):
    def __init__(self, ctx):
        super().__init__("Eğitim", "Kelimeleri aktif olarak çalış. Widget sana kelimeleri gösterir; burada "
                                   "onları gerçekten öğrenirsin.")
        self.ctx = ctx
        self.db = ctx.db
        self.mode = "flash"
        self.words: list[dict] = []
        self.index = 0
        self.results: list[tuple[dict, bool]] = []
        self.started_at = 0.0
        self.answered = False
        self.pending_quality: int | None = None

        self.stack = QStackedWidget()
        self.root.addWidget(self.stack, 1)
        self._build_setup()
        self._build_session()
        self._build_summary()
        self._build_shortcuts()
        ctx.decksChanged.connect(self._fill_decks)

    def _build_setup(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        lay.addWidget(label("Çalışma şekli", "SectionTitle"))
        grid = QGridLayout()
        grid.setSpacing(12)
        self.mode_buttons: dict[str, QPushButton] = {}
        for i, (key, (icon, title, desc)) in enumerate(MODES.items()):
            b = QPushButton(f"{title}\n{desc}")
            b.setCheckable(True)
            b.setObjectName("Choice")
            b.setMinimumHeight(84)
            b.setStyleSheet("text-align: left; font-size: 15px;")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._select_mode(k))
            self.mode_buttons[key] = b
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)

        lay.addWidget(label("Hangi kelimeler", "SectionTitle"))
        opts = Card()
        row = QHBoxLayout()
        row.addWidget(label("Kaynak:"))
        self.source = QComboBox()
        for key, text in SOURCES:
            self.source.addItem(text, key)
        self.source.currentIndexChanged.connect(self._source_changed)
        row.addWidget(self.source, 2)
        self.deck = QComboBox()
        row.addWidget(self.deck, 1)
        row.addWidget(label("Kelime sayısı:"))
        self.size = QSpinBox()
        self.size.setRange(5, 200)
        self.size.setValue(int(self.ctx.get("training.session_size")))
        self.size.valueChanged.connect(lambda v: self.ctx.set("training.session_size", v))
        row.addWidget(self.size)
        opts.lay.addLayout(row)
        lv = QHBoxLayout()
        lv.addWidget(label("Seviyeler:"))
        self.level_checks = {}
        for level in LEVELS:
            cb = QCheckBox(level)
            cb.setChecked(True)
            self.level_checks[level] = cb
            lv.addWidget(cb)
        lv.addStretch(1)
        self.info = label("", "Muted")
        lv.addWidget(self.info)
        opts.lay.addLayout(lv)
        kd = QHBoxLayout()
        kd.addWidget(label("İçerik:"))
        self.kind_checks = {}
        for kind, name in KINDS.items():
            cb = QCheckBox(name)
            cb.setChecked(True)
            self.kind_checks[kind] = cb
            kd.addWidget(cb)
        kd.addStretch(1)
        opts.lay.addLayout(kd)
        lay.addWidget(opts)

        start_row = QHBoxLayout()
        start_row.addStretch(1)
        self.start_btn = button("Başla", "Primary", lambda: self.start_session())
        self.start_btn.setMinimumSize(200, 46)
        self.start_btn.setStyleSheet("font-size: 16px;")
        start_row.addWidget(self.start_btn)
        start_row.addStretch(1)
        lay.addLayout(start_row)
        lay.addWidget(label("Klavyeyle: Space cevabı gösterir, 1–4 puan verir ya da seçenek seçer, Enter devam eder.",
                            "Dim", align=Qt.AlignmentFlag.AlignCenter))
        lay.addStretch(1)
        self.stack.addWidget(page)
        self._fill_decks()
        self._select_mode(self.ctx.get("training.mode", "flash") or "flash")
        idx = self.source.findData(self.ctx.get("training.source"))
        self.source.setCurrentIndex(max(0, idx))
        self._source_changed()

    def _fill_decks(self):
        current = self.deck.currentData()
        self.deck.clear()
        for d in self.db.list_decks():
            self.deck.addItem(f"{d['name']} ({d['cards']})", d["id"])
        if current is not None:
            i = self.deck.findData(current)
            if i >= 0:
                self.deck.setCurrentIndex(i)

    def _select_mode(self, key: str):
        if key not in MODES:
            key = "flash"
        self.mode = key
        for k, b in self.mode_buttons.items():
            b.setChecked(k == key)
        self.ctx.db.set("training.mode", key)

    def _source_changed(self):
        src = self.source.currentData()
        self.deck.setVisible(src == "deck")
        self.ctx.db.set("training.source", src)
        tot = self.db.totals()
        self.info.setText(f"Tekrar zamanı gelen {tot['due']} kelime var. {tot['learning']} kelime öğreniliyor, "
                          f"{tot['learned']} kelime öğrenildi.")

    def apply_params(self, params: dict):
        self.stack.setCurrentIndex(0)
        if "source" in params:
            idx = self.source.findData(params["source"])
            if idx >= 0:
                self.source.setCurrentIndex(idx)
        if "deck_id" in params:
            self._fill_decks()
            self.source.setCurrentIndex(self.source.findData("deck"))
            i = self.deck.findData(params["deck_id"])
            if i >= 0:
                self.deck.setCurrentIndex(i)
        if "mode" in params:
            self._select_mode(params["mode"])

    def on_show(self):
        if self.stack.currentIndex() == 0:
            self._source_changed()

    def _build_session(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        top = QHBoxLayout()
        self.progress_label = label("", "Muted")
        top.addWidget(self.progress_label)
        top.addStretch(1)
        self.score_label = label("", "Muted")
        top.addWidget(self.score_label)
        quit_btn = button("Oturumu bitir", "Ghost", self.finish_session)
        quit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        top.addWidget(quit_btn)
        lay.addLayout(top)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        lay.addWidget(self.progress)

        self.card = Card(margins=(30, 26, 30, 26), spacing=14)
        self.card.setMinimumHeight(330)
        self.card.lay.addStretch(1)
        self.prompt_hint = label("", "Muted", align=Qt.AlignmentFlag.AlignCenter)
        self.card.lay.addWidget(self.prompt_hint)
        self.word_view = WordView(self.ctx, show_example=True)
        self.card.lay.addWidget(self.word_view)
        self.prompt_big = label("", "BigWord", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.prompt_big.setStyleSheet(f"font-family: '{FONT_SERIF}'; font-size: 30px; color: {C['gold']};")
        self.card.lay.addWidget(self.prompt_big)
        self.listen_btn = button("Tekrar dinle", None, self._speak_current)
        self.listen_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.listen_btn.setMinimumHeight(48)
        lr = QHBoxLayout()
        lr.addStretch(1)
        lr.addWidget(self.listen_btn)
        lr.addStretch(1)
        self.card.lay.addLayout(lr)
        self.card.lay.addStretch(1)

        self.choices_box = QWidget()
        cg = QGridLayout(self.choices_box)
        cg.setContentsMargins(0, 0, 0, 0)
        cg.setSpacing(10)
        self.choice_buttons: list[QPushButton] = []
        for i in range(4):
            b = QPushButton()
            b.setObjectName("Choice")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(56)
            b.clicked.connect(lambda _=False, n=i: self._choose(n))
            self.choice_buttons.append(b)
            cg.addWidget(b, i // 2, i % 2)
        self.card.lay.addWidget(self.choices_box)

        self.answer = QLineEdit()
        self.answer.setObjectName("AnswerInput")
        self.answer.setPlaceholderText("İngilizcesini yaz ve Enter'a bas…")
        self.answer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card.lay.addWidget(self.answer)

        self.feedback = label("", None, wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.feedback.setStyleSheet("font-size: 16px;")
        self.card.lay.addWidget(self.feedback)
        lay.addWidget(self.card, 1)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(10)
        lay.addLayout(self.actions)
        self.stack.addWidget(page)

    def _action_buttons(self, specs):
        clear_layout(self.actions)
        self.actions.addStretch(1)
        for text, name, slot in specs:
            b = button(text, name, slot)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setMinimumHeight(44)
            b.setMinimumWidth(130)
            self.actions.addWidget(b)
        self.actions.addStretch(1)

    def _build_shortcuts(self):
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self)
            s.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            s.activated.connect(fn)
        sc(Qt.Key.Key_Space, self._key_space)
        sc(Qt.Key.Key_Return, self._key_enter)
        sc(Qt.Key.Key_Enter, self._key_enter)
        for n in range(4):
            sc(getattr(Qt.Key, f"Key_{n + 1}"), lambda n=n: self._key_number(n))

    def start_session(self, words: list[dict] | None = None):
        if words is None:
            levels = [lv for lv, cb in self.level_checks.items() if cb.isChecked()] or LEVELS
            src = self.source.currentData()
            deck_id = self.deck.currentData() if src == "deck" else None
            if src == "deck" and deck_id is None:
                self.feedback.setText("")
                self.info.setText("<span style='color:#EF4444'>Önce Card Draft sayfasında bir deste oluştur.</span>")
                return
            kinds = [k for k, cb in self.kind_checks.items() if cb.isChecked()] or list(KINDS)
            ids = self.db.session_word_ids(src, self.size.value(), levels, deck_id, kinds)
            words = self.db.get_words(ids)
        if not words:
            self.info.setText("<span style='color:#F59E0B'>Bu kaynakta çalışılacak kelime yok. "
                              "Başka bir kaynak seç.</span>")
            return
        self.words = words
        self.index = 0
        self.results = []
        self.started_at = time.time()
        self.stack.setCurrentIndex(1)
        self._show_word()

    def current(self) -> dict:
        return self.words[self.index]

    def _show_word(self):
        w = self.current()
        self.answered = False
        self.pending_quality = None
        n = len(self.words)
        self.progress.setMaximum(n)
        self.progress.setValue(self.index)
        self.progress_label.setText(f"{MODES[self.mode][1]}, {self.index + 1} / {n}")
        ok = sum(1 for _, c in self.results if c)
        self.score_label.setText(f"{ok} doğru, {len(self.results) - ok} yanlış")
        self.feedback.setText("")
        self.feedback.setStyleSheet("font-size: 16px;")
        self.word_view.set_word(w)
        self.choices_box.hide()
        self.answer.hide()
        self.listen_btn.hide()
        self.prompt_big.hide()
        self.word_view.show()

        if self.mode == "flash":
            self.prompt_hint.setText("Bu kelimenin anlamını hatırlıyor musun?")
            self.word_view.set_meaning_visible(False)
            self._action_buttons([("Cevabı göster  (Space)", "Primary", self._reveal_flash)])
        elif self.mode == "choice_en":
            self.prompt_hint.setText("Doğru Türkçe anlamı seç")
            self.word_view.set_meaning_visible(False)
            self._setup_choices(w, english_prompt=True)
        elif self.mode == "choice_tr":
            self.prompt_hint.setText(f"Bu anlama gelen İngilizce kelime hangisi?  ({pos_text(w.get('pos', ''))})")
            self.word_view.hide()
            self.prompt_big.setText(w["turkish"])
            self.prompt_big.show()
            self._setup_choices(w, english_prompt=False)
        elif self.mode == "typing":
            self.prompt_hint.setText(f"İngilizcesini yaz  ({pos_text(w.get('pos', ''))})")
            self.word_view.hide()
            self.prompt_big.setText(w["turkish"])
            self.prompt_big.show()
            self._setup_typing()
        elif self.mode == "listening":
            self.prompt_hint.setText("Dinle ve duyduğun kelimeyi yaz")
            self.word_view.hide()
            self.listen_btn.show()
            self._setup_typing()
            if not self.ctx.speaker.voices():
                self.feedback.setText("Bu bilgisayarda İngilizce ses bulunamadı (Ayarlar → Seslendirme).")
            QTimer.singleShot(250, self._speak_current)

    def _speak_current(self):
        if self.words:
            self.ctx.speak(self.current()["english"])

    def _reveal_flash(self):
        if self.answered:
            return
        self.answered = True
        self.word_view.set_meaning_visible(True)
        self.prompt_hint.setText("Ne kadar iyi hatırladın?")
        specs = [("Bilmiyorum  1", "Danger", lambda: self._grade(0)),
                 ("Zor  2", None, lambda: self._grade(3)),
                 ("İyi  3", "Primary", lambda: self._grade(4)),
                 ("Kolay  4", None, lambda: self._grade(5))]
        if self.current().get("status") == STATUS_NEW and self.current().get("reviews", 0) == 0:
            specs.append(("Zaten biliyorum", "Ghost", self._already_known))
        self._action_buttons(specs)

    def _grade(self, quality: int):
        w = self.current()
        res = self.db.record_answer(w["id"], quality, "flash")
        self.results.append((w, quality >= 3))
        if res.get("became_learned"):
            self.ctx.toast(f"{w['english']} artık öğrenildi")
        self._next()

    def _already_known(self):
        w = self.current()
        self.db.set_status(w["id"], STATUS_LEARNED)
        self.results.append((w, True))
        self.ctx.toast(f"{w['english']} öğrenildi olarak işaretlendi")
        self._next()

    def _setup_choices(self, w: dict, english_prompt: bool):
        pos = (w.get("pos") or "").split(",")[0].strip() or None
        exclude = {w["id"]}
        distractors = self.db.random_words(3, exclude, pos=pos)
        if len(distractors) < 3:
            distractors += self.db.random_words(3 - len(distractors), exclude | {d["id"] for d in distractors})
        seen_texts = {first_meaning(w["turkish"]).lower(), w["english"].lower()}
        options = [w]
        for d in distractors:
            key = (first_meaning(d["turkish"]) if english_prompt else d["english"]).lower()
            if key not in seen_texts:
                options.append(d)
                seen_texts.add(key)
        random.shuffle(options)
        self.options = options
        self.correct_index = options.index(w)
        for i, b in enumerate(self.choice_buttons):
            if i < len(options):
                o = options[i]
                text = first_meaning(o["turkish"]) if english_prompt else o["english"]
                b.setText(f"{i + 1}.  {text}")
                b.setProperty("state", "")
                b.setEnabled(True)
                b.show()
            else:
                b.hide()
            b.style().unpolish(b)
            b.style().polish(b)
        self.choices_box.show()
        self._action_buttons([("Bilmiyorum, geç", "Ghost", lambda: self._choose(-1))])

    def _choose(self, n: int):
        if self.answered or self.mode not in ("choice_en", "choice_tr"):
            return
        if n >= len(self.options):
            return
        self.answered = True
        w = self.current()
        correct = n == self.correct_index
        for i, b in enumerate(self.choice_buttons):
            if i == self.correct_index:
                b.setProperty("state", "correct")
            elif i == n:
                b.setProperty("state", "wrong")
            b.style().unpolish(b)
            b.style().polish(b)
        self.word_view.set_meaning_visible(True)
        if self.mode == "choice_tr":
            self.word_view.show()
            self.prompt_big.hide()
        self.db.record_answer(w["id"], 4 if correct else 0, self.mode,
                              answer="" if n < 0 else self.options[n]["english"])
        self.results.append((w, correct))
        if correct:
            self.feedback.setText(f"<span style='color:{C['success']}'>Doğru.</span>")
            self.ctx.speak(w["english"])
            QTimer.singleShot(1100, self._auto_next)
            self._action_buttons([("Devam  (Enter)", "Primary", self._next)])
        else:
            self.feedback.setText(f"<span style='color:{C['danger']}'>Doğrusu <b>{w['english']}</b> = "
                                  f"{w['turkish']}</span>")
            self._action_buttons([("Devam  (Enter)", "Primary", self._next)])

    def _auto_next(self):
        if self.stack.currentIndex() == 1 and self.answered and self.results and self.results[-1][1] \
                and self.words and self.results[-1][0] is self.current():
            self._next()

    def _setup_typing(self):
        self.answer.clear()
        self.answer.setEnabled(True)
        self.answer.setStyleSheet("")
        self.answer.show()
        self.answer.setFocus()
        self._action_buttons([("Bilmiyorum", "Ghost", self._give_up), ("Kontrol et", "Primary",
                                                                         self._check_typing)])

    def _check_typing(self):
        if self.answered:
            self._commit_typing()
            return
        w = self.current()
        given = normalize(self.answer.text())
        if not given:
            return
        target = normalize(w["english"])
        variants = {target, target.replace("-", " "), target.replace(" ", "")}
        self.answered = True
        self.answer.setEnabled(False)
        self.word_view.show()
        self.word_view.set_meaning_visible(True)
        self.prompt_big.hide()
        if given in variants:
            self.pending_quality = 4
            self._typing_feedback(True, "Doğru.")
            self.ctx.speak(w["english"])
        elif len(target) >= 4 and levenshtein(given, target) <= 1:
            self.pending_quality = 3
            self._typing_feedback(True, f"≈ Neredeyse! Doğru yazımı: <b>{w['english']}</b>")
        else:
            self.pending_quality = 0
            self._typing_feedback(False, f"Senin cevabın <s>{self.answer.text()}</s>, doğrusu <b>{w['english']}</b>.")
            self.ctx.speak(w["english"])

    def _typing_feedback(self, ok: bool, html: str):
        color = C["success"] if ok else C["danger"]
        self.feedback.setText(f"<span style='color:{color}'>{html}</span>")
        self.answer.setStyleSheet(f"border: 2px solid {color};")
        specs = [("Devam  (Enter)", "Primary", self._commit_typing)]
        if not ok:
            specs.insert(0, ("Aslında doğru say", "Ghost", self._override_correct))
        self._action_buttons(specs)

    def _override_correct(self):
        self.pending_quality = 3
        self._typing_feedback(True, f"Doğru sayıldı: <b>{self.current()['english']}</b>")

    def _give_up(self):
        if self.answered:
            return
        self.answer.setText("")
        self.answered = True
        self.pending_quality = 0
        self.answer.setEnabled(False)
        self.word_view.show()
        self.word_view.set_meaning_visible(True)
        self.prompt_big.hide()
        self._typing_feedback(False, f"Doğrusu: <b>{self.current()['english']}</b>")
        self.ctx.speak(self.current()["english"])

    def _commit_typing(self):
        if self.pending_quality is None:
            return
        w = self.current()
        q = self.pending_quality
        res = self.db.record_answer(w["id"], q, self.mode, answer=self.answer.text())
        self.results.append((w, q >= 3))
        if res.get("became_learned"):
            self.ctx.toast(f"{w['english']} artık öğrenildi")
        self.pending_quality = None
        self._next()

    def _key_space(self):
        if self.stack.currentIndex() == 1 and self.mode == "flash" and not self.answered:
            self._reveal_flash()
        elif self.stack.currentIndex() == 1 and self.mode == "listening" and not self.answered:
            self._speak_current()

    def _key_enter(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            self.start_session()
        elif idx == 1:
            if self.mode in ("typing", "listening"):
                self._check_typing()
            elif self.mode == "flash" and not self.answered:
                self._reveal_flash()
            elif self.mode in ("choice_en", "choice_tr") and self.answered:
                self._next()

    def _key_number(self, n: int):
        if self.stack.currentIndex() != 1:
            return
        if self.mode == "flash" and self.answered:
            self._grade([0, 3, 4, 5][n])
        elif self.mode in ("choice_en", "choice_tr") and not self.answered:
            self._choose(n)

    def _next(self):
        if self.stack.currentIndex() != 1:
            return
        self.ctx.progressChanged.emit()
        if self.index + 1 >= len(self.words):
            self.finish_session()
            return
        self.index += 1
        self._show_word()

    def finish_session(self):
        if self.started_at:
            self.db.add_study_seconds(int(time.time() - self.started_at))
            self.started_at = 0
        self.ctx.progressChanged.emit()
        self._show_summary()

    def _build_summary(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self.summary_card = Card(margins=(30, 26, 30, 26), spacing=12)
        lay.addWidget(self.summary_card)
        lay.addStretch(1)
        self.stack.addWidget(page)

    def _show_summary(self):
        clear_layout(self.summary_card.lay)
        total = len(self.results)
        ok = sum(1 for _, c in self.results if c)
        pct = 100 * ok / total if total else 0
        self.summary_card.lay.addWidget(label("Oturum tamamlandı", "PageTitle",
                                              align=Qt.AlignmentFlag.AlignCenter))
        self.summary_card.lay.addWidget(label(
            f"<span style='font-size:36px; font-weight:600'>{ok} / {total}</span><br>"
            f"<span style='color:{C['muted']}'>%{pct:.0f} başarı</span>", align=Qt.AlignmentFlag.AlignCenter))
        wrong = [w for w, c in self.results if not c]
        if wrong:
            self.summary_card.lay.addWidget(label("Tekrar bakman gerekenler:", "SectionTitle"))
            grid = QGridLayout()
            for i, w in enumerate(wrong[:24]):
                grid.addWidget(label(f"<b>{w['english']}</b>  <span style='color:{C['muted']}'>"
                                     f"{clean_ipa(w['phonetic'])}</span><br>{w['turkish']}", wrap=True),
                               i // 2, i % 2)
            self.summary_card.lay.addLayout(grid)
        row = QHBoxLayout()
        row.addStretch(1)
        if wrong:
            row.addWidget(button("Yanlışları tekrar çalış", None,
                                 lambda: self.start_session([self.db.get_word(w["id"]) for w in wrong])))
        row.addWidget(button("Yeni oturum", "Primary", lambda: self.start_session()))
        row.addWidget(button("Çalışma ayarları", None, lambda: self.stack.setCurrentIndex(0)))
        row.addWidget(button("Ana sayfa", None, lambda: self.ctx.navigate("home")))
        row.addStretch(1)
        self.summary_card.lay.addLayout(row)
        self.stack.setCurrentIndex(2)
