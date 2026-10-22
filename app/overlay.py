from __future__ import annotations

import random

from PySide6.QtCore import QEasingCurve, QPoint, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QAction, QGuiApplication, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from . import widget_render as wr
from .config import STATUS_LEARNED
from .context import AppContext
from .data.tenses import widget_snippets
from .winutil import (
    FS_EXCLUSIVE, FS_NONE, FS_WINDOWED, force_topmost, fullscreen_state, install_foreground_hook, monitor_of,
)

TOPMOST_NORMAL_MS = 2500
TOPMOST_FULLSCREEN_MS = 250

POSITIONS = {
    "top-left": ("top", "left"), "top-center": ("top", "center"), "top-right": ("top", "right"),
    "middle-left": ("middle", "left"), "center": ("middle", "center"), "middle-right": ("middle", "right"),
    "bottom-left": ("bottom", "left"), "bottom-center": ("bottom", "center"), "bottom-right": ("bottom", "right"),
}

POOL_KEYS = {"widget.source", "widget.order", "widget.levels", "widget.kinds", "widget.deck_id"}


class WordOverlay(QWidget):
    openMainRequested = Signal(str)
    stateChanged = Signal()
    itemChanged = Signal()
    fullscreenChanged = Signal(str)

    def __init__(self, ctx: AppContext):
        super().__init__(None)
        self.ctx = ctx
        self.db = ctx.db
        self._apply_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowTitle("EMG Widget")

        self.style_ = wr.WidgetStyle.from_settings(ctx.get)
        self.current: dict | None = None
        self.lines: list[wr.Line] = []
        self.revealed = True
        self.history: list[dict] = []
        self.hist_index = -1
        self.pool: list[int] = []
        self.pool_pos = 0
        self.pool_dirty = True
        self.paused = False
        self.hovering = False
        self.words_since_tense = 0
        self._tense_snippets = widget_snippets()
        self._content_opacity = 1.0
        self._drag_offset: QPoint | None = None
        self._press_pos = QPoint()
        self._dragging = False
        self._pending_item = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.reveal_timer = QTimer(self)
        self.reveal_timer.setSingleShot(True)
        self.reveal_timer.timeout.connect(self.reveal)
        self.top_timer = QTimer(self)
        self.top_timer.setInterval(TOPMOST_NORMAL_MS)
        self.top_timer.timeout.connect(self._keep_on_top)

        self.fs_state = FS_NONE
        self.fs_hidden = False
        self.voice_active = False
        self.fs_timer = QTimer(self)
        self.fs_timer.setInterval(1000)
        self.fs_timer.timeout.connect(self._check_fullscreen)
        self.voice_timer = QTimer(self)
        self.voice_timer.timeout.connect(self._voice_tick)
        install_foreground_hook(self._on_foreground_changed)

        self.fade_out = QVariantAnimation(self, startValue=1.0, endValue=0.0, duration=170)
        self.fade_out.setEasingCurve(QEasingCurve.Type.InQuad)
        self.fade_out.valueChanged.connect(self._set_opacity)
        self.fade_out.finished.connect(self._after_fade_out)
        self.fade_in = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=260)
        self.fade_in.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.fade_in.valueChanged.connect(self._set_opacity)

        ctx.settingsChanged.connect(self._on_setting)
        ctx.progressChanged.connect(self._mark_pool_dirty)
        ctx.wordsChanged.connect(self._mark_pool_dirty)
        ctx.decksChanged.connect(self._mark_pool_dirty)
        QGuiApplication.instance().screenAdded.connect(lambda *_: self.reposition())
        QGuiApplication.instance().screenRemoved.connect(lambda *_: self.reposition())

    def _apply_flags(self):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus |
                 Qt.WindowType.NoDropShadowWindowHint)
        if self.ctx.get("widget.click_through"):
            flags |= Qt.WindowType.WindowTransparentForInput
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    def start(self):
        if not self.ctx.get("widget.enabled"):
            self.hide()
            return
        if self.current is None:
            self.next_item(animate=False)
        if not self.fs_hidden:
            self.show()
        self._restart_timer()
        self.top_timer.start()
        self.fs_timer.start()
        self.stateChanged.emit()

    def stop(self):
        self.timer.stop()
        self.reveal_timer.stop()
        self.top_timer.stop()
        self.fs_timer.stop()
        self.voice_timer.stop()
        self.voice_active = False
        self.fs_hidden = False
        self.hide()
        self.stateChanged.emit()

    def set_enabled(self, enabled: bool):
        self.ctx.set("widget.enabled", enabled)

    def toggle_visible(self):
        self.set_enabled(not self.ctx.get("widget.enabled"))

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.timer.stop()
            self.voice_timer.stop()
        else:
            self._restart_timer()
        self.ctx.toast("Widget duraklatıldı" if self.paused else "Widget devam ediyor")
        self.stateChanged.emit()

    def _restart_timer(self):
        self.timer.stop()
        self.voice_timer.stop()
        if self.paused or not self.ctx.get("widget.enabled"):
            return
        if self.voice_active:
            self.voice_timer.start(max(5, int(self.ctx.get("widget.fs_voice_interval"))) * 1000)
        elif not self.fs_hidden:
            self.timer.start(max(1, int(self.ctx.get("widget.interval"))) * 1000)

    def showEvent(self, event):
        super().showEvent(event)
        force_topmost(int(self.winId()))

    def _keep_on_top(self):
        if self.isVisible():
            force_topmost(int(self.winId()))

    def _own_hwnds(self) -> set[int]:
        out = set()
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and w.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
                out.add(int(w.winId()))
        return out

    def _on_foreground_changed(self):
        if not self.fs_timer.isActive():
            return
        QTimer.singleShot(0, self._check_fullscreen)
        QTimer.singleShot(350, self._check_fullscreen)
        if self.isVisible():
            QTimer.singleShot(0, self._keep_on_top)

    def _check_fullscreen(self):
        state, monitor = fullscreen_state(self._own_hwnds())
        if state != FS_NONE and monitor and self.testAttribute(Qt.WidgetAttribute.WA_WState_Created) \
                and monitor != monitor_of(int(self.winId())):
            state = FS_NONE
        if state != self.fs_state:
            self.fs_state = state
            self._apply_fullscreen_behavior()
            self.fullscreenChanged.emit(state)

    def _apply_fullscreen_behavior(self):
        mode = self.ctx.get("widget.fs_mode")
        fs = self.fs_state
        hide = fs != FS_NONE and mode in ("voice", "hide")
        voice = (fs != FS_NONE and mode == "voice") or (fs == FS_EXCLUSIVE and mode == "show_voice")
        self.top_timer.setInterval(TOPMOST_FULLSCREEN_MS if fs == FS_WINDOWED and not hide else TOPMOST_NORMAL_MS)
        changed = hide != self.fs_hidden or voice != self.voice_active
        self.fs_hidden, self.voice_active = hide, voice
        if not self.ctx.get("widget.enabled"):
            return
        if hide and self.isVisible():
            self.hide()
        elif not hide and not self.isVisible():
            self.show()
        if fs == FS_WINDOWED and not hide:
            self._keep_on_top()
        if changed:
            self._restart_timer()
            self.stateChanged.emit()

    def _voice_tick(self):
        self.next_item(animate=False)
        item = self.current or {}
        if item.get("kind") == "tense":
            self.ctx.speaker.speak_pair(item.get("en", ""), item.get("tr", ""))
        else:
            meaning = (item.get("turkish") or "").split(";")[0].strip()
            self.ctx.speaker.speak_pair(item.get("english", ""), meaning)

    def _mark_pool_dirty(self):
        self.pool_dirty = True

    def _rebuild_pool(self):
        get = self.ctx.get
        self.pool = self.db.widget_pool(get("widget.source"), get("widget.order"), get("widget.levels"),
                                        get("widget.deck_id"), get("widget.kinds"))
        if get("widget.order") == "sequential" and get("widget.source") == "all":
            self.pool_pos = int(get("widget.seq_pos")) % max(1, len(self.pool))
        else:
            self.pool_pos = 0
        self.pool_dirty = False

    def _next_word(self) -> dict | None:
        for _ in range(3):
            if self.pool_dirty or self.pool_pos >= len(self.pool):
                self._rebuild_pool()
            if not self.pool:
                return None
            word_id = self.pool[self.pool_pos]
            self.pool_pos += 1
            if self.ctx.get("widget.order") == "sequential" and self.ctx.get("widget.source") == "all":
                self.db.set("widget.seq_pos", self.pool_pos)
            word = self.db.get_word(word_id)
            if word and (not self.current or word["id"] != self.current.get("id")):
                return word
        return None

    def _on_tick(self):
        if self.hovering and not self.ctx.get("widget.click_through"):
            return
        self.next_item()

    def next_item(self, animate: bool = True):
        if self.hist_index < len(self.history) - 1:
            self.hist_index += 1
            self._show(self.history[self.hist_index], animate, record=False)
            return
        tense_mix = int(self.ctx.get("widget.tense_mix") or 0)
        item = None
        if tense_mix > 0 and self.words_since_tense >= tense_mix and self._tense_snippets:
            item = dict(random.choice(self._tense_snippets))
            self.words_since_tense = 0
        else:
            item = self._next_word()
            self.words_since_tense += 1
        if item is None:
            return
        self.history.append(item)
        if len(self.history) > 60:
            self.history = self.history[-60:]
        self.hist_index = len(self.history) - 1
        self._show(item, animate, record=True)

    def prev_item(self):
        if self.hist_index > 0:
            self.hist_index -= 1
            self._show(self.history[self.hist_index], True, record=False)
            self._restart_timer()

    def manual_next(self):
        if self.voice_active:
            self._voice_tick()
        else:
            self.next_item()
        self._restart_timer()

    def _show(self, item: dict, animate: bool, record: bool):
        if record and item.get("kind") != "tense" and item.get("id"):
            self.db.record_widget_view(item["id"])
        if animate and self.ctx.get("widget.fade") and self.isVisible():
            self._pending_item = item
            self.fade_in.stop()
            self.fade_out.start()
        else:
            self._apply_item(item)

    def _after_fade_out(self):
        if self._pending_item is not None:
            self._apply_item(self._pending_item)
            self._pending_item = None
        self.fade_in.start()

    def _apply_item(self, item: dict):
        self.current = item
        quiz = bool(self.ctx.get("widget.quiz_mode"))
        self.revealed = not quiz
        self.reveal_timer.stop()
        if quiz:
            delay = min(int(self.ctx.get("widget.reveal_delay")), max(1, int(self.ctx.get("widget.interval")) - 1))
            self.reveal_timer.start(max(1, delay) * 1000)
        self._relayout()
        self.itemChanged.emit()
        if self.ctx.get("widget.auto_speak") and item.get("kind") != "tense":
            self.ctx.speak(item.get("english", ""))

    def reveal(self):
        if not self.revealed:
            self.revealed = True
            self._relayout()

    def _set_opacity(self, value):
        self._content_opacity = float(value)
        self.update()

    def _relayout(self):
        self.lines = wr.build_lines(self.current, self.style_, self.ctx.pron, self.revealed)
        size = wr.measure(self.lines, self.style_)
        if size != self.size():
            self.setFixedSize(size)
        self.reposition()
        self.update()

    def _screen(self):
        screens = QGuiApplication.screens()
        idx = int(self.ctx.get("widget.screen") or 0)
        return screens[idx] if 0 <= idx < len(screens) else QGuiApplication.primaryScreen()

    def reposition(self):
        pos = self.ctx.get("widget.position")
        if pos == "custom":
            x, y = int(self.ctx.get("widget.custom_x")), int(self.ctx.get("widget.custom_y"))
            target = QGuiApplication.screenAt(QPoint(x + 10, y + 10)) or self._screen()
            g = target.availableGeometry()
            x = max(g.left(), min(x, g.right() - self.width() + 1))
            y = max(g.top(), min(y, g.bottom() - self.height() + 1))
            self.move(x, y)
            return
        vert, horiz = POSITIONS.get(pos, ("top", "right"))
        g = self._screen().availableGeometry()
        m = int(self.ctx.get("widget.margin"))
        if horiz == "left":
            x = g.left() + m
        elif horiz == "right":
            x = g.right() - self.width() - m + 1
        else:
            x = g.left() + (g.width() - self.width()) // 2
        if vert == "top":
            y = g.top() + m
        elif vert == "bottom":
            y = g.bottom() - self.height() - m + 1
        else:
            y = g.top() + (g.height() - self.height()) // 2
        self.move(x, y)

    def paintEvent(self, event):
        p = QPainter(self)
        wr.paint(p, QRectF(self.rect()), self.lines, self.style_, self._content_opacity)
        p.end()

    def _on_setting(self, key: str):
        if not key.startswith(("widget.", "pron.")):
            return
        if key == "widget.enabled":
            self.start() if self.ctx.get("widget.enabled") else self.stop()
            return
        if key == "widget.click_through":
            self._apply_flags()
            self.stateChanged.emit()
            return
        if key in ("widget.interval", "widget.fs_voice_interval"):
            self._restart_timer()
            return
        if key == "widget.fs_mode":
            self._apply_fullscreen_behavior()
            return
        if key in POOL_KEYS:
            self.pool_dirty = True
            self.history = self.history[: self.hist_index + 1]
            return
        if key == "widget.quiz_mode":
            self.revealed = True
            self.reveal_timer.stop()
        self.style_ = wr.WidgetStyle.from_settings(self.ctx.get)
        if self.current is not None:
            self._relayout()
        else:
            self.reposition()

    def current_word(self) -> dict | None:
        if self.current and self.current.get("kind") != "tense":
            return self.current
        return None

    def speak_current(self):
        if not self.current:
            return
        if self.voice_active:
            meaning = (self.current.get("turkish") or self.current.get("tr") or "").split(";")[0].strip()
            self.ctx.speaker.speak_pair(self.current.get("english") or self.current.get("en", ""), meaning)
        else:
            self.ctx.speak(self.current.get("english") or self.current.get("en", ""))

    def mark_learned(self):
        w = self.current_word()
        if not w:
            return
        self.db.set_status(w["id"], STATUS_LEARNED)
        self.ctx.progressChanged.emit()
        self.ctx.toast(f"{w['english']} öğrenildi olarak işaretlendi")
        self.manual_next()

    def toggle_favorite(self):
        w = self.current_word()
        if not w:
            return
        fav = self.db.toggle_favorite(w["id"])
        w["favorite"] = int(fav)
        self.ctx.progressChanged.emit()
        self.ctx.toast(("Favorilere eklendi: " if fav else "Favorilerden çıkarıldı: ") + w["english"])

    def toggle_click_through(self):
        self.ctx.set("widget.click_through", not self.ctx.get("widget.click_through"))
        self.ctx.toast("Oyun modu (tıklama geçirgen) " + ("AÇIK" if self.ctx.get("widget.click_through") else "KAPALI"))

    def handle_hotkey(self, action: str):
        if action == "toggle":
            self.toggle_visible()
            return
        if not self.isVisible() and not self.voice_active:
            return
        {
            "next": self.manual_next,
            "prev": self.prev_item,
            "pause": self.toggle_pause,
            "learned": self.mark_learned,
            "favorite": self.toggle_favorite,
            "speak": self.speak_current,
            "reveal": self.reveal,
            "clickthrough": self.toggle_click_through,
        }.get(action, lambda: None)()

    def enterEvent(self, event):
        self.hovering = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovering = False
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            gp = event.globalPosition().toPoint()
            if not self._dragging and (gp - self._press_pos).manhattanLength() > 4:
                self._dragging = True
            if self._dragging:
                self.move(gp - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None and event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                pos = self.pos()
                self.ctx.db.set("widget.custom_x", pos.x())
                self.ctx.db.set("widget.custom_y", pos.y())
                if self.ctx.get("widget.position") != "custom":
                    self.ctx.set("widget.position", "custom")
                else:
                    self.ctx.settingsChanged.emit("widget.custom_x")
            elif not self.revealed:
                self.reveal()
            self._drag_offset = None
            self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.speak_current()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        w = self.current_word()

        def add(text, slot, enabled=True):
            act = QAction(text, menu)
            act.setEnabled(enabled)
            act.triggered.connect(slot)
            menu.addAction(act)
            return act

        add("Sonraki kelime", self.manual_next)
        add("Önceki kelime", self.prev_item, self.hist_index > 0)
        add("▶  Devam et" if self.paused else "Duraklat", self.toggle_pause)
        add("Seslendir", self.speak_current)
        if not self.revealed:
            add("Anlamı göster", self.reveal)
        menu.addSeparator()
        add("Öğrendim", self.mark_learned, w is not None)
        add("Favorilerden çıkar" if (w and w.get("favorite")) else "Favorilere ekle", self.toggle_favorite,
            w is not None)
        menu.addSeparator()
        add("Oyun modu (tıklamaları geçir)", self.toggle_click_through)
        add("Widget ayarları", lambda: self.openMainRequested.emit("widget"))
        add("Ana pencereyi aç", lambda: self.openMainRequested.emit("home"))
        add("Widget'ı gizle", lambda: self.set_enabled(False))
        menu.exec(event.globalPos())
