from __future__ import annotations

import datetime as dt

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QProgressBar, QScrollArea, QVBoxLayout, QWidget

from ..config import LEVELS
from .common import WordView, button, label, rule

MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
             "Kasım", "Aralık"]
WEEKDAYS_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
CONTENT_WIDTH = 760


def _num(n: int) -> str:
    return f"{n:,}".replace(",", ".")


class HomePage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("Page")
        self.ctx = ctx
        self.db = ctx.db

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        holder = QWidget()
        scroll.setWidget(holder)
        h = QHBoxLayout(holder)
        h.setContentsMargins(56, 36, 36, 36)
        column = QWidget()
        column.setMaximumWidth(CONTENT_WIDTH)
        h.addWidget(column, 1)
        h.addStretch(0)
        lay = QVBoxLayout(column)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.date = label("", "Muted")
        lay.addWidget(self.date)
        lay.addSpacing(28)
        lay.addWidget(label("Günün kelimesi", "Dim"))
        lay.addSpacing(4)
        self.word = WordView(ctx, centered=False)
        lay.addWidget(self.word)
        self.example = label("", "Example", wrap=True)
        lay.addSpacing(6)
        lay.addWidget(self.example)
        lay.addSpacing(14)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_fav = button("Favorilere ekle", None, self._fav)
        self.btn_known = button("Bunu biliyorum", "Ghost", self._known)
        actions.addWidget(self.btn_fav)
        actions.addWidget(self.btn_known)
        actions.addStretch(1)
        lay.addLayout(actions)

        lay.addSpacing(36)
        lay.addWidget(rule())
        lay.addSpacing(24)

        lay.addWidget(label("Bugün", "SectionTitle"))
        lay.addSpacing(12)
        due_row = QHBoxLayout()
        self.due_text = label("", "Lead", wrap=True)
        due_row.addWidget(self.due_text, 1)
        self.btn_study = button("", "Primary", self._study)
        due_row.addWidget(self.btn_study)
        lay.addLayout(due_row)
        lay.addSpacing(18)
        self.goal_text = label("", "Muted")
        lay.addWidget(self.goal_text)
        lay.addSpacing(6)
        self.goal_bar = QProgressBar()
        self.goal_bar.setFixedHeight(4)
        self.goal_bar.setTextVisible(False)
        lay.addWidget(self.goal_bar)
        lay.addSpacing(14)
        self.today_text = label("", "Muted", wrap=True)
        lay.addWidget(self.today_text)

        lay.addSpacing(36)
        lay.addWidget(rule())
        lay.addSpacing(24)

        lay.addWidget(label("İlerleme", "SectionTitle"))
        lay.addSpacing(12)
        self.progress_text = label("", "Lead", wrap=True)
        lay.addWidget(self.progress_text)
        lay.addSpacing(16)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        self.level_bars = {}
        for i, lv in enumerate(LEVELS):
            name = label(lv, "Muted")
            bar = QProgressBar()
            bar.setFixedHeight(4)
            bar.setTextVisible(False)
            pct = label("", "Dim")
            grid.addWidget(name, 0, i)
            grid.addWidget(bar, 1, i)
            grid.addWidget(pct, 2, i)
            self.level_bars[lv] = (bar, pct)
        lay.addLayout(grid)
        lay.addStretch(1)

        self.wotd = None
        ctx.progressChanged.connect(self._refresh_if_visible)

    def _refresh_if_visible(self):
        if self.isVisible():
            self.on_show()

    def on_show(self):
        now = dt.datetime.now()
        self.date.setText(f"{WEEKDAYS_TR[now.weekday()]}, {now.day} {MONTHS_TR[now.month - 1]}")

        self.wotd = self.db.word_of_the_day()
        self.word.set_word(self.wotd)
        ex = (self.wotd or {}).get("example") or ""
        ex_tr = (self.wotd or {}).get("example_tr") or ""
        self.example.setText(f"“{ex}”" + (f"<br>{ex_tr}" if ex_tr else "") if ex else "")
        self.example.setVisible(bool(ex))
        self._update_word_buttons()

        tot = self.db.totals()
        today = self.db.today()
        streak = self.db.streak()
        due = tot["due"]
        if due:
            self.due_text.setText(f"{_num(due)} kelimenin tekrar zamanı geldi.")
            self.btn_study.setText("Tekrara başla")
        else:
            self.due_text.setText("Tekrar bekleyen kelime yok. Yeni kelimelerle devam edebilirsin.")
            self.btn_study.setText("Yeni kelime çalış")

        goal = int(self.ctx.get("app.daily_goal"))
        done = today["reviews"]
        self.goal_bar.setMaximum(max(1, goal))
        self.goal_bar.setValue(min(done, goal))
        if done >= goal:
            self.goal_text.setText(f"Günlük hedef tamam: {done} tekrar.")
        else:
            self.goal_text.setText(f"Günlük hedef: {done} / {goal} tekrar.")

        parts = [f"Widget bugün {_num(today['widget_views'])} kelime gösterdi."]
        if today["reviews"]:
            acc = round(100 * today["correct"] / today["reviews"])
            parts.append(f"Cevaplarının %{acc}'i doğru.")
        if streak >= 2:
            parts.append(f"{streak} gündür aralıksız çalışıyorsun.")
        self.today_text.setText(" ".join(parts))

        self.progress_text.setText(
            f"{_num(tot['total'])} kelimeden {_num(tot['learned'])} tanesini öğrendin; "
            f"{_num(tot['learning'])} kelime tekrar döngüsünde.")
        levels = {r["level"]: r for r in self.db.level_breakdown()}
        for lv, (bar, pct) in self.level_bars.items():
            r = levels.get(lv, {"total": 0, "learned": 0})
            bar.setMaximum(max(1, r["total"]))
            bar.setValue(r["learned"])
            pct.setText(f"%{100 * r['learned'] / r['total']:.0f}" if r["total"] else "")

    def _update_word_buttons(self):
        w = self.wotd
        has = w is not None
        self.btn_fav.setEnabled(has)
        self.btn_known.setEnabled(has and w.get("status") != 2)
        self.btn_fav.setText("Favorilerden çıkar" if has and w.get("favorite") else "Favorilere ekle")

    def _fav(self):
        if self.wotd:
            self.wotd["favorite"] = int(self.db.toggle_favorite(self.wotd["id"]))
            self._update_word_buttons()
            self.ctx.progressChanged.emit()

    def _known(self):
        if self.wotd:
            self.db.set_status(self.wotd["id"], 2)
            self.ctx.toast(f"{self.wotd['english']} öğrenildi olarak işaretlendi")
            self.ctx.progressChanged.emit()

    def _study(self):
        self.ctx.navigate("training", source="due" if self.db.totals()["due"] else "new")
