from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QPlainTextEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ..ai_coach import MODELS, CoachAgent, find_claude
from .common import Page, button, clear_layout, confirm, label

CONTENT_WIDTH = 820
HISTORY_LIMIT = 200
SUGGESTIONS = [
    "“I have went there yesterday” cümlesindeki hatayı açıkla",
    "Present perfect ile past simple farkını örneklerle anlat",
    "“Kafam çok karıştı” İngilizcede nasıl söylenir?",
    "Zorlandığım kelimelerle kısa bir hikâye yaz",
    "Restoranda sipariş verme üzerine benimle rol yap",
    "Let's chat in English about my day.",
]


class MessageView(QWidget):
    def __init__(self, role: str, text: str = ""):
        super().__init__()
        self.role = role
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.text = label("", "ChatError" if role == "error" else "ChatText", wrap=True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.text.setOpenExternalLinks(True)
        self.text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        if role == "user":
            self.text.setTextFormat(Qt.TextFormat.PlainText)
            bubble = QFrame()
            bubble.setObjectName("ChatBubble")
            bl = QVBoxLayout(bubble)
            bl.setContentsMargins(14, 10, 14, 10)
            bl.addWidget(self.text)
            bubble.setMaximumWidth(int(CONTENT_WIDTH * 0.8))
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            self.text.setTextFormat(Qt.TextFormat.MarkdownText)
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(label("Koç" if role == "assistant" else "Hata", "Dim"))
            col.addWidget(self.text)
            row.addLayout(col, 1)
        self.set_text(text)

    def set_text(self, text: str):
        self.text.setText(text)


class AiCoachPage(Page):
    def __init__(self, ctx):
        super().__init__("AI Koç", "Türkçe ve İngilizce bilen dil koçun. Çeviri, gramer, kelime ve telaffuz sor "
                                   "ya da İngilizce sohbet ederek pratik yap; hatalarını düzeltir.")
        self.ctx = ctx
        self.agent = CoachAgent(ctx, self)
        self.agent.delta.connect(self._on_delta)
        self.agent.finished.connect(self._on_finished)
        self.agent.failed.connect(self._on_failed)
        self.agent.busyChanged.connect(self._on_busy)
        QApplication.instance().aboutToQuit.connect(self.agent.shutdown)

        self.model = QComboBox()
        for key, name in MODELS.items():
            self.model.addItem(name, key)
        self.model.setCurrentIndex(max(0, self.model.findData(ctx.get("coach.model"))))
        self.model.setToolTip("Koçun kullanacağı Claude modeli")
        self.model.currentIndexChanged.connect(lambda: self.agent.set_model(self.model.currentData()))
        self.header_actions.addWidget(self.model)
        self.header_actions.addWidget(button("Yeni sohbet", None, self._new_chat))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        self.scroll.setWidget(holder)
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 4, 12, 12)
        column = QWidget()
        column.setMaximumWidth(CONTENT_WIDTH)
        h.addWidget(column, 1)
        h.addStretch(0)
        outer = QVBoxLayout(column)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.messages = QVBoxLayout()
        self.messages.setSpacing(18)
        outer.addLayout(self.messages)
        self.empty = self._build_empty()
        outer.addWidget(self.empty)
        outer.addStretch(1)
        self.root.addWidget(self.scroll, 1)
        self._stick = True
        sb = self.scroll.verticalScrollBar()
        sb.valueChanged.connect(lambda v: setattr(self, "_stick", v >= sb.maximum() - 40))
        sb.rangeChanged.connect(lambda _a, b: sb.setValue(b) if self._stick else None)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input = QPlainTextEdit()
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText("Koçuna bir şey sor… (Türkçe ya da İngilizce)")
        self.input.setTabChangesFocus(True)
        self.input.installEventFilter(self)
        self.input.document().contentsChanged.connect(self._fit_input)
        input_row.addWidget(self.input, 1)
        self.send_btn = button("Gönder", "Primary", self._send)
        self.stop_btn = button("Durdur", None, self.agent.stop)
        self.stop_btn.hide()
        input_row.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        input_row.addWidget(self.stop_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self.root.addLayout(input_row)
        self.hint = label("", "Dim", wrap=True)
        self.root.addWidget(self.hint)
        self._fit_input()

        self.current: MessageView | None = None
        self._pending = ""
        self._render_timer = QTimer(self, singleShot=True, interval=40)
        self._render_timer.timeout.connect(self._render_stream)
        self._load_history()

    def _build_empty(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(label("Şunlarla başlayabilirsin", "Dim"))
        for text in SUGGESTIONS:
            b = button(text, "Suggestion", lambda _=False, t=text: self._send(t))
            row = QHBoxLayout()
            row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
        return box

    def _fit_input(self):
        doc_h = self.input.document().size().height() * self.input.fontMetrics().lineSpacing()
        self.input.setFixedHeight(int(max(46, min(150, doc_h + 22))))

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.Type.KeyPress \
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._send()
            return True
        return super().eventFilter(obj, event)

    def on_show(self):
        self._update_hint()
        self.agent.warm_up()
        self.input.setFocus()

    def _update_hint(self):
        if find_claude():
            self.hint.setText("Enter gönderir, Shift+Enter yeni satır. Koç, bu bilgisayardaki Claude Code "
                              "oturumunla çalışır; ilerleme verilerine göre cevaplarını kişiselleştirir.")
        else:
            self.hint.setText("Claude Code bulunamadı. AI Koç için Claude Code'u kurup bir terminalde "
                              "<b>claude</b> yazarak giriş yap: claude.com/claude-code")

    def _add(self, role: str, text: str = "") -> MessageView:
        self.empty.hide()
        view = MessageView(role, text)
        self.messages.addWidget(view)
        self._stick = True
        return view

    def _load_history(self):
        for m in self.ctx.get("coach.history") or []:
            self._add(m["role"], m["text"])

    def _save(self, role: str, text: str):
        history = list(self.ctx.get("coach.history") or [])
        history.append({"role": role, "text": text})
        self.ctx.db.set("coach.history", history[-HISTORY_LIMIT:])

    def _send(self, text: str | None = None):
        if self.agent.busy:
            return
        text = (text if text is not None else self.input.toPlainText()).strip()
        if not text:
            return
        self.input.clear()
        self._add("user", text)
        self._save("user", text)
        self.current = self._add("assistant", "*düşünüyor…*")
        self._pending = ""
        self.agent.send(text)

    def _on_delta(self, chunk: str):
        self._pending += chunk
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _render_stream(self):
        if self.current is not None:
            self.current.set_text(self._pending)

    def _on_finished(self, text: str):
        self._render_timer.stop()
        if self.current is not None:
            self.current.set_text(text)
            self.current = None
        if text.strip():
            self._save("assistant", text)

    def _on_failed(self, message: str):
        self._render_timer.stop()
        if self.current is not None:
            self.current.setParent(None)
            self.current.deleteLater()
            self.current = None
        self._add("error", message)

    def _on_busy(self, busy: bool):
        self.send_btn.setVisible(not busy)
        self.stop_btn.setVisible(busy)
        self.model.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    def _new_chat(self):
        if self.messages.count() and not confirm(self, "Yeni sohbet", "Bu sohbet silinsin ve yenisi başlasın mı?",
                                                 "Yeni sohbet"):
            return
        self.agent.new_chat()
        self.current = None
        clear_layout(self.messages)
        self.ctx.db.set("coach.history", [])
        self.empty.show()
        self.input.setFocus()
