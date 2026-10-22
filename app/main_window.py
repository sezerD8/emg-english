from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow, QMenu, QPushButton,
    QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from .config import APP_NAME
from .context import AppContext
from .theme import C
from .ui.ai_coach import AiCoachPage
from .ui.card_draft import CardDraftPage
from .ui.common import button, label, make_app_icon
from .ui.home import HomePage
from .ui.library import LibraryPage
from .ui.settings_page import SettingsPage
from .ui.tenses import TensesPage
from .ui.titlebar import TitleBar
from .ui.training import TrainingPage
from .ui.widget_settings import WidgetSettingsPage
from .winutil import IS_WINDOWS, enable_native_frame, handle_frame_message

NAV = [
    ("home", "Ana sayfa"),
    ("training", "Eğitim"),
    ("widget", "Widget"),
    ("library", "Kütüphane"),
    ("tenses", "Tenses"),
    ("draft", "Card Draft"),
    ("coach", "AI Koç"),
    ("settings", "Ayarlar"),
]
SIDEBAR_WIDTH = 196


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet(f"background: {C['text']}; color: {C['bg']}; border-radius: 6px;"
                           f" padding: 9px 16px; font-size: 14px;")
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, ms: int = 2600):
        self.setText(text)
        self.adjustSize()
        par = self.parentWidget()
        self.move((par.width() - SIDEBAR_WIDTH - self.width()) // 2, par.height() - self.height() - 28)
        self.raise_()
        self.show()
        self.anim.stop()
        self.anim.setDuration(180)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start(ms)

    def _fade_out(self):
        self.anim.stop()
        self.anim.setDuration(400)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()
        QTimer.singleShot(420, self.hide)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, overlay):
        super().__init__()
        self.ctx = ctx
        self.overlay = overlay
        self._really_quit = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon())
        self.setMinimumSize(1150, 680)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            g = screen.availableGeometry()
            self.resize(max(1150, min(1500, int(g.width() * 0.9))), max(680, min(940, int(g.height() * 0.9))))
            self.move(g.x() + (g.width() - self.width()) // 2, g.y() + (g.height() - self.height()) // 2)
        else:
            self.resize(1360, 860)

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        root = QWidget()
        root.setObjectName("Root")
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.title_bar = TitleBar(self)
        v.addWidget(self.title_bar)
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        h.addWidget(self._build_sidebar())
        v.addLayout(h, 1)
        self.setCentralWidget(root)
        self._frame_ready = False
        if IS_WINDOWS:
            enable_native_frame(int(self.winId()))
            self._frame_ready = True

        self.pages = {
            "home": HomePage(ctx),
            "training": TrainingPage(ctx),
            "widget": WidgetSettingsPage(ctx),
            "library": LibraryPage(ctx),
            "tenses": TensesPage(ctx),
            "draft": CardDraftPage(ctx),
            "coach": AiCoachPage(ctx),
            "settings": SettingsPage(ctx),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)

        self.toast = Toast(root)
        ctx.toastRequested.connect(self.toast.show_message)
        ctx.navigateRequested.connect(self.navigate)
        ctx.progressChanged.connect(self._update_sidebar_stats)
        ctx.settingsChanged.connect(self._on_setting)
        overlay.openMainRequested.connect(self.show_page)
        overlay.stateChanged.connect(self._update_widget_toggle)

        self._build_tray()
        self.navigate("home", {})
        self._update_sidebar_stats()
        self._update_widget_toggle()

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(SIDEBAR_WIDTH)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 28, 18, 18)
        lay.setSpacing(2)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, text in NAV:
            if key == "settings":
                lay.addStretch(1)
                lay.addWidget(self._build_widget_status())
                lay.addSpacing(14)
            b = QPushButton(text)
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.navigate(k, {}))
            self.nav_group.addButton(b)
            self.nav_buttons[key] = b
            lay.addWidget(b)
        return side

    def _build_widget_status(self) -> QWidget:
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 0, 0, 0)
        bl.setSpacing(8)
        self.side_stats = label("", "SideNote", wrap=True)
        bl.addWidget(self.side_stats)
        self.widget_toggle = button("", None,
                                    lambda: self.ctx.set("widget.enabled", not self.ctx.get("widget.enabled")))
        bl.addWidget(self.widget_toggle)
        return box

    def navigate(self, key: str, params: dict | None = None):
        page = self.pages.get(key)
        if page is None:
            return
        self.nav_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(page)
        self.title_bar.set_page(next((text for k, text in NAV if k == key), ""))
        if params and hasattr(page, "apply_params"):
            page.apply_params(params)
        page.on_show()

    def show_page(self, key: str):
        self.show_window()
        self.navigate(key, {})

    def _update_sidebar_stats(self):
        db = self.ctx.db
        today = db.today()
        goal = int(self.ctx.get("app.daily_goal"))
        streak = db.streak()
        lines = [f"Bugün {today['reviews']} / {goal} tekrar"]
        if streak >= 2:
            lines.append(f"{streak} gündür aralıksız")
        self._stats_text = "<br>".join(lines)
        self._update_widget_toggle()

    def _update_widget_toggle(self):
        on = bool(self.ctx.get("widget.enabled"))
        paused = self.overlay.paused
        state = "Widget duraklatıldı" if on and paused else "Widget açık" if on else "Widget kapalı"
        self.side_stats.setText(f"{state}<br>{getattr(self, '_stats_text', '')}")
        self.widget_toggle.setText("Widget'ı gizle" if on else "Widget'ı göster")
        if hasattr(self, "tray_toggle"):
            self.tray_toggle.setText("Widget'ı gizle" if on else "Widget'ı göster")
            self.tray_pause.setText("Devam et" if paused else "Duraklat")
            self.tray_click.setChecked(bool(self.ctx.get("widget.click_through")))

    def _on_setting(self, key: str):
        if key in ("widget.enabled", "widget.click_through"):
            self._update_widget_toggle()
        if key == "app.daily_goal":
            self._update_sidebar_stats()

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        act_open = QAction("Ana pencereyi aç", menu)
        act_open.triggered.connect(self.show_window)
        menu.addAction(act_open)
        menu.addSeparator()
        self.tray_toggle = QAction("", menu)
        self.tray_toggle.triggered.connect(lambda: self.ctx.set("widget.enabled", not self.ctx.get("widget.enabled")))
        menu.addAction(self.tray_toggle)
        self.tray_pause = QAction("", menu)
        self.tray_pause.triggered.connect(self.overlay.toggle_pause)
        menu.addAction(self.tray_pause)
        nxt = QAction("Sonraki kelime", menu)
        nxt.triggered.connect(self.overlay.manual_next)
        menu.addAction(nxt)
        self.tray_click = QAction("Oyun modu (tıklamaları geçir)", menu)
        self.tray_click.setCheckable(True)
        self.tray_click.triggered.connect(lambda v: self.ctx.set("widget.click_through", bool(v)))
        menu.addAction(self.tray_click)
        settings = QAction("Widget ayarları", menu)
        settings.triggered.connect(lambda: self.show_page("widget"))
        menu.addAction(settings)
        menu.addSeparator()
        quit_act = QAction("Çıkış", menu)
        quit_act.triggered.connect(self.quit_app)
        menu.addAction(quit_act)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        page = self.stack.currentWidget()
        if hasattr(page, "on_show"):
            page.on_show()

    def nativeEvent(self, event_type, message):
        if IS_WINDOWS and event_type == b"windows_generic_MSG":
            handled, result = handle_frame_message(message, self._is_caption)
            if handled:
                return True, result
        return super().nativeEvent(event_type, message)

    def _is_caption(self, x: float, y: float) -> bool:
        pos = self.title_bar.mapFrom(self, QPoint(int(x), int(y)))
        return self.title_bar.is_drag_area(pos)

    def showEvent(self, event):
        super().showEvent(event)
        if IS_WINDOWS and not self._frame_ready:
            enable_native_frame(int(self.winId()))
            self._frame_ready = True

    def closeEvent(self, event: QCloseEvent):
        if not self._really_quit and self.ctx.get("app.close_to_tray") and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            if not self.ctx.db.get("meta.tray_hint_shown", False):
                self.tray.showMessage(APP_NAME, "Uygulama sistem tepsisinde çalışmaya devam ediyor. "
                                                "Widget kelimeleri göstermeye devam edecek.",
                                      QSystemTrayIcon.MessageIcon.Information, 4000)
                self.ctx.db.set("meta.tray_hint_shown", True)
            return
        event.accept()
        self.quit_app()

    def quit_app(self):
        from PySide6.QtWidgets import QApplication
        self._really_quit = True
        self.tray.hide()
        self.overlay.stop()
        QApplication.instance().quit()
