from __future__ import annotations

import html
import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QStackedWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)

from ..data.tenses import GROUP_TITLES, TENSES, all_quiz_questions, tense_by_key
from ..theme import C, FONT_SERIF, FONT_UI, FONT_WORD
from .common import Card, Page, button, clear_layout, label

OVERVIEW = "__overview__"
MIXED = "__mixed__"


def esc(t: str) -> str:
    return html.escape(t)


class TensesPage(Page):
    def __init__(self, ctx):
        super().__init__("Tenses", "İngilizce zamanları Türkçe açıklamalar, formüller ve örneklerle öğren; "
                                   "mini testlerle pekiştir.")
        self.ctx = ctx
        self.db = ctx.db
        body = QHBoxLayout()
        body.setSpacing(14)
        self.root.addLayout(body, 1)

        self.list = QListWidget()
        self.list.setFixedWidth(300)
        self.list.currentItemChanged.connect(self._item_changed)
        self.list.itemClicked.connect(self._item_clicked)
        body.addWidget(self.list)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        cl.addWidget(self.browser, 1)
        actions = QHBoxLayout()
        self.progress_label = label("", "Muted")
        actions.addWidget(self.progress_label)
        actions.addStretch(1)
        self.btn_speak = button("Örnekleri dinle", None, self._speak_examples)
        self.btn_read = button("Okudum", None, self._mark_read)
        self.btn_quiz = button("▶ Mini test", "Primary", self._start_quiz)
        for b in (self.btn_speak, self.btn_read, self.btn_quiz):
            actions.addWidget(b)
        cl.addLayout(actions)
        self.stack.addWidget(content)

        quiz = QWidget()
        ql = QVBoxLayout(quiz)
        ql.setContentsMargins(0, 0, 0, 0)
        self.quiz_card = Card(margins=(30, 26, 30, 26), spacing=14)
        self.q_progress = label("", "Muted")
        self.q_tense = label("", "Badge")
        top = QHBoxLayout()
        top.addWidget(self.q_progress)
        top.addStretch(1)
        top.addWidget(self.q_tense)
        self.quiz_card.lay.addLayout(top)
        self.q_text = label("", None, wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.q_text.setStyleSheet(f"font-family: '{FONT_SERIF}'; font-size: 26px; padding: 18px 0;")
        self.quiz_card.lay.addWidget(self.q_text)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.q_buttons: list[QPushButton] = []
        for i in range(4):
            b = QPushButton()
            b.setObjectName("Choice")
            b.setMinimumHeight(54)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=i: self._answer(n))
            self.q_buttons.append(b)
            grid.addWidget(b, i // 2, i % 2)
        self.quiz_card.lay.addLayout(grid)
        self.q_feedback = label("", None, wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.q_feedback.setStyleSheet("font-size: 15px;")
        self.quiz_card.lay.addWidget(self.q_feedback)
        nav = QHBoxLayout()
        nav.addWidget(button("Testi bitir", "Ghost", self._finish_quiz))
        nav.addStretch(1)
        self.q_next = button("Sonraki soru", "Primary", self._next_question)
        nav.addWidget(self.q_next)
        self.quiz_card.lay.addLayout(nav)
        self.quiz_card.lay.addStretch(1)
        ql.addWidget(self.quiz_card, 1)
        self.stack.addWidget(quiz)

        res = QWidget()
        rl = QVBoxLayout(res)
        rl.setContentsMargins(0, 0, 0, 0)
        self.result_card = Card(margins=(30, 26, 30, 26), spacing=12)
        rl.addWidget(self.result_card)
        rl.addStretch(1)
        self.stack.addWidget(res)

        self.current_key: str | None = None
        self._fill_list()
        self._item_changed(self.list.currentItem())

    def _fill_list(self):
        prog = self.db.tense_progress()
        current = self.current_key
        self.list.blockSignals(True)
        self.list.clear()
        for key, text in ((OVERVIEW, "Genel bakış"), (MIXED, "Karışık test (10 soru)")):
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(it)
        group = None
        for t in TENSES:
            if t["group"] != group:
                group = t["group"]
                h = QListWidgetItem(GROUP_TITLES.get(group, group))
                h.setFlags(Qt.ItemFlag.NoItemFlags)
                h.setForeground(Qt.GlobalColor.gray)
                f = h.font()
                f.setBold(True)
                f.setPointSizeF(9.5)
                h.setFont(f)
                self.list.addItem(h)
            p = prog.get(t["key"], {})
            mark = ""
            if p.get("best_score"):
                mark = f"   {p['best_score']}%"
            elif p.get("read_count"):
                mark = "   ✓"
            it = QListWidgetItem(f"{t['name']}{mark}\n{t['tr']}")
            it.setData(Qt.ItemDataRole.UserRole, t["key"])
            it.setToolTip(t["summary"])
            self.list.addItem(it)
        target = current or OVERVIEW
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == target:
                self.list.setCurrentRow(i)
                break
        self.list.blockSignals(False)

    def _item_clicked(self, item):
        key = item.data(Qt.ItemDataRole.UserRole)
        if key == self.current_key and key not in (None, MIXED) and self.stack.currentIndex() != 0:
            self.stack.setCurrentIndex(0)

    def _item_changed(self, item, _prev=None):
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if not key:
            return
        self.current_key = key
        if key == MIXED:
            self._start_quiz(mixed=True)
            return
        self.stack.setCurrentIndex(0)
        if key == OVERVIEW:
            self._render_overview()
        else:
            self._render_tense(tense_by_key(key))

    def _css(self) -> str:
        return (f"<style>body{{color:{C['text']}; font-family:'{FONT_UI}'; font-size:15px; line-height:150%;}}"
                f"h1{{font-family:'{FONT_WORD}'; font-size:34px; font-weight:600; margin:0;}}"
                f"h2{{font-size:17px; font-weight:600; margin-top:26px; margin-bottom:6px;}}"
                f".muted{{color:{C['muted']};}} .tr{{color:{C['gold']};}}"
                f".en{{font-family:'{FONT_SERIF}'; font-size:16px;}}"
                f"td{{padding:6px 14px 6px 0; vertical-align:top;}} .formula{{color:{C['text']}; font-weight:600;}}"
                f"</style>")

    def _render_overview(self):
        rows = []
        for t in TENSES:
            rows.append(
                f"<tr><td><b>{esc(t['name'])}</b><br><span class='muted'>{esc(t['tr'])}</span></td>"
                f"<td class='formula'>{esc(t['formula']['positive'])}</td>"
                f"<td><span class='en'>{esc(t['examples'][0][0])}</span><br>"
                f"<span class='tr'>{esc(t['examples'][0][1])}</span></td></tr>")
        self.browser.setHtml(
            self._css() +
            "<h1>Zamanlara genel bakış</h1>"
            "<p class='muted'>İngilizcede 3 ana zaman (Present, Past, Future) ve her birinin 4 görünüşü "
            "(Simple, Continuous, Perfect, Perfect Continuous) vardır: toplam 12 tense. "
            "Soldan bir konu seçip ayrıntılarını okuyabilir, mini testle kendini deneyebilirsin.</p>"
            "<h2>Akılda tutma şeması</h2>"
            "<table border='0' cellspacing='0' style='margin-top:4px'>"
            "<tr><td></td><td class='muted'>Simple</td><td class='muted'>Continuous</td>"
            "<td class='muted'>Perfect</td><td class='muted'>Perfect Continuous</td></tr>"
            "<tr><td><b>Present</b></td><td class='formula'>V1 / V1+s</td><td class='formula'>am/is/are + Ving</td>"
            "<td class='formula'>have/has + V3</td><td class='formula'>have/has been + Ving</td></tr>"
            "<tr><td><b>Past</b></td><td class='formula'>V2</td><td class='formula'>was/were + Ving</td>"
            "<td class='formula'>had + V3</td><td class='formula'>had been + Ving</td></tr>"
            "<tr><td><b>Future</b></td><td class='formula'>will + V1</td><td class='formula'>will be + Ving</td>"
            "<td class='formula'>will have + V3</td><td class='formula'>will have been + Ving</td></tr></table>"
            "<h2>Tüm konular</h2>"
            "<table border='0' cellspacing='0' width='100%'>" + "".join(rows) + "</table>")
        self.progress_label.setText("")
        for b in (self.btn_speak, self.btn_read, self.btn_quiz):
            b.setVisible(False)

    def _render_tense(self, t: dict):
        f, fx = t["formula"], t["formula_examples"]
        usage = "".join(
            f"<tr><td width='34%'><b>{esc(u)}</b></td><td><span class='en'>{esc(en)}</span><br>"
            f"<span class='tr'>{esc(tr)}</span></td></tr>" for u, en, tr in t["usage"])
        formula = "".join(
            f"<tr><td width='18%'><b>{lab}</b></td><td class='formula'>{esc(f[k])}</td>"
            f"<td><span class='en'>{esc(fx[k])}</span></td></tr>"
            for k, lab in (("positive", "Olumlu"), ("negative", "Olumsuz"), ("question", "Soru")))
        examples = "".join(f"<li><span class='en'>{esc(en)}</span><br><span class='tr'>{esc(tr)}</span></li>"
                           for en, tr in t["examples"])
        tips = "".join(f"<li>{esc(x)}</li>" for x in t["tips"])
        signals = ", ".join(f"<b>{esc(s)}</b>" for s in t["signals"])
        self.browser.setHtml(
            self._css() +
            f"<h1>{esc(t['name'])}</h1><p class='tr' style='font-size:17px; margin-top:4px'>{esc(t['tr'])}</p>"
            f"<p>{esc(t['summary'])}</p>"
            f"<h2>Formül</h2><table border='0' cellspacing='0' width='100%'>{formula}</table>"
            f"<h2>Ne zaman kullanılır?</h2><table border='0' cellspacing='0' width='100%'>{usage}</table>"
            f"<h2>İpucu kelimeler</h2><p>{signals}</p>"
            f"<h2>Örnek cümleler</h2><ul>{examples}</ul>"
            f"<h2>Dikkat / sık yapılan hatalar</h2><ul>{tips}</ul>")
        self.browser.verticalScrollBar().setValue(0)
        p = self.db.tense_progress().get(t["key"], {})
        total = p.get("correct", 0) + p.get("wrong", 0)
        self.progress_label.setText(
            f"{p.get('read_count', 0)} kez okundu. Testte {total} sorudan {p.get('correct', 0)} doğru, "
            f"en iyi skor %{p.get('best_score', 0)}.")
        for b in (self.btn_speak, self.btn_read, self.btn_quiz):
            b.setVisible(True)
        self.btn_quiz.setText(f"▶ Mini test ({len(t['quiz'])} soru)")

    def _speak_examples(self):
        t = tense_by_key(self.current_key or "")
        if t:
            self.ctx.speak(" ... ".join(en for en, _ in t["examples"]))

    def _mark_read(self):
        if self.current_key and tense_by_key(self.current_key):
            self.db.mark_tense_read(self.current_key)
            self.ctx.toast("Okundu olarak işaretlendi")
            self._fill_list()

    def _start_quiz(self, mixed: bool = False):
        if mixed:
            pool = all_quiz_questions()
            random.shuffle(pool)
            self.questions = pool[:10]
            self.quiz_key = MIXED
        else:
            t = tense_by_key(self.current_key or "")
            if not t:
                return
            qs = list(t["quiz"])
            random.shuffle(qs)
            self.questions = [(t, q) for q in qs]
            self.quiz_key = t["key"]
            self.db.mark_tense_read(t["key"])
        self.q_index = 0
        self.q_score = 0
        self.q_wrong: list[tuple[dict, dict]] = []
        self.stack.setCurrentIndex(1)
        self._show_question()

    def _show_question(self):
        t, q = self.questions[self.q_index]
        self.q_answered = False
        self.q_progress.setText(f"Soru {self.q_index + 1} / {len(self.questions)}, {self.q_score} doğru")
        self.q_tense.setText(t["name"] if self.quiz_key == MIXED else "Boşluğu doldur")
        self.q_text.setText(esc(q["q"]).replace("___", f"<span style='color:{C['accent2']}'>_____</span>"))
        order = list(range(len(q["options"])))
        random.shuffle(order)
        self.q_order = order
        for i, b in enumerate(self.q_buttons):
            if i < len(order):
                b.setText(f"{i + 1}.  {q['options'][order[i]]}")
                b.setProperty("state", "")
                b.show()
            else:
                b.hide()
            b.style().unpolish(b)
            b.style().polish(b)
        self.q_feedback.setText("")
        self.q_next.setEnabled(False)

    def _answer(self, n: int):
        if self.q_answered or n >= len(self.q_order):
            return
        self.q_answered = True
        t, q = self.questions[self.q_index]
        chosen = self.q_order[n]
        correct = chosen == q["answer"]
        for i, b in enumerate(self.q_buttons):
            if i < len(self.q_order) and self.q_order[i] == q["answer"]:
                b.setProperty("state", "correct")
            elif i == n:
                b.setProperty("state", "wrong")
            b.style().unpolish(b)
            b.style().polish(b)
        full = q["q"].replace("___", q["options"][q["answer"]])
        if correct:
            self.q_score += 1
            self.q_feedback.setText(f"<span style='color:{C['success']}'>Doğru.</span> {esc(q['explain'])}")
        else:
            self.q_wrong.append((t, q))
            self.q_feedback.setText(f"<span style='color:{C['danger']}'>Yanlış.</span> {esc(q['explain'])}"
                                    f"<br><span class='en'>Doğrusu: {esc(full)}</span>")
        self.db.record_tense_answer(t["key"], correct)
        self.ctx.speak(full)
        self.q_next.setEnabled(True)
        self.q_next.setText("Sonucu gör" if self.q_index + 1 >= len(self.questions) else "Sonraki soru")
        self.ctx.progressChanged.emit()

    def _next_question(self):
        if self.q_index + 1 >= len(self.questions):
            self._finish_quiz()
            return
        self.q_index += 1
        self._show_question()

    def _finish_quiz(self):
        total = self.q_index + (1 if getattr(self, "q_answered", False) else 0)
        total = max(total, 1)
        pct = round(100 * self.q_score / total)
        if self.quiz_key != MIXED and total == len(self.questions):
            self.db.record_tense_score(self.quiz_key, pct)
        clear_layout(self.result_card.lay)
        self.result_card.lay.addWidget(label(f"{self.q_score} / {total} doğru, %{pct}", "PageTitle",
                                             align=Qt.AlignmentFlag.AlignCenter))
        if self.q_wrong:
            self.result_card.lay.addWidget(label("Yanlış yaptıkların:", "SectionTitle"))
            for t, q in self.q_wrong:
                full = q["q"].replace("___", q["options"][q["answer"]])
                self.result_card.lay.addWidget(label(
                    f"<b>{esc(full)}</b><br><span style='color:{C['muted']}'>{esc(t['name'])}: "
                    f"{esc(q['explain'])}</span>", wrap=True))
        else:
            self.result_card.lay.addWidget(label("Hepsi doğru.", "Muted",
                                                 align=Qt.AlignmentFlag.AlignCenter))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Tekrar dene", "Primary",
                             lambda: self._start_quiz(mixed=self.quiz_key == MIXED)))
        if self.quiz_key != MIXED:
            row.addWidget(button("Konuya dön", None, lambda: self.stack.setCurrentIndex(0)))
        row.addStretch(1)
        self.result_card.lay.addLayout(row)
        self.stack.setCurrentIndex(2)
        QTimer.singleShot(0, self._fill_list)

    def on_show(self):
        if self.list.currentRow() < 0:
            self._fill_list()
