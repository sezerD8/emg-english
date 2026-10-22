from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import APP_ID, APP_NAME, USER_DIR
from app.context import AppContext
from app.database import open_database
from app.hotkeys import GlobalHotkeys
from app.main_window import MainWindow
from app.overlay import WordOverlay
from app.seed import seed_builtin
from app import theme
from app.tts import Speaker
from app.ui.common import make_app_icon
from app.winutil import set_dark_titlebar

SERVER_NAME = f"{APP_ID}-single-instance"


def _excepthook(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        with open(USER_DIR / "error.log", "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass
    sys.__excepthook__(exc_type, exc, tb)


def _already_running() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main() -> int:
    sys.excepthook = _excepthook
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(make_app_icon())
    app.setFont(QFont(theme.FONT_UI, 10))

    if _already_running():
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    db = open_database()
    theme.apply(db.get("app.theme"))
    app.setStyleSheet(theme.stylesheet())
    if theme.CURRENT == "dark":
        app.focusWindowChanged.connect(lambda w: set_dark_titlebar(int(w.winId())) if w is not None else None)

    try:
        seed_builtin(db)
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(None, APP_NAME, f"Kelime listesi yüklenemedi:\n{exc}")

    ctx = AppContext(db, Speaker())
    overlay = WordOverlay(ctx)
    ctx.overlay = overlay
    window = MainWindow(ctx, overlay)

    hotkeys = GlobalHotkeys(app)
    hotkeys.triggered.connect(overlay.handle_hotkey)

    def apply_hotkeys():
        failed = hotkeys.register_all() if ctx.get("widget.hotkeys") else (hotkeys.unregister_all() or [])
        window.pages["widget"].set_hotkey_status(failed)

    apply_hotkeys()
    ctx.settingsChanged.connect(lambda k: apply_hotkeys() if k == "widget.hotkeys" else None)

    def on_new_connection():
        conn = server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(window.show_window)
            conn.disconnected.connect(conn.deleteLater)
        window.show_window()

    server.newConnection.connect(on_new_connection)

    def restart_app():
        server.close()
        hotkeys.unregister_all()
        args = [a for a in sys.argv[1:] if a != "--minimized"]
        if not getattr(sys, "frozen", False):
            args.insert(0, str(Path(__file__).resolve()))
        QProcess.startDetached(sys.executable, args)
        window.quit_app()

    ctx.restart_app = restart_app

    overlay.start()
    if "--minimized" in sys.argv or ctx.get("app.start_minimized"):
        window.hide()
    else:
        window.show()

    code = app.exec()
    hotkeys.unregister_all()
    server.close()
    db.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
