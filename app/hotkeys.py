from __future__ import annotations

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

from .winutil import IS_WINDOWS

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
WM_HOTKEY = 0x0312

HOTKEYS = {
    "next": ("Ctrl+Alt+→", 0x27, "Sonraki kelime"),
    "prev": ("Ctrl+Alt+←", 0x25, "Önceki kelime"),
    "toggle": ("Ctrl+Alt+H", ord("H"), "Widget'ı gizle / göster"),
    "pause": ("Ctrl+Alt+P", ord("P"), "Duraklat / devam et"),
    "learned": ("Ctrl+Alt+L", ord("L"), "Bu kelimeyi öğrendim"),
    "favorite": ("Ctrl+Alt+F", ord("F"), "Favorilere ekle / çıkar"),
    "speak": ("Ctrl+Alt+S", ord("S"), "Kelimeyi seslendir"),
    "reveal": ("Ctrl+Alt+R", ord("R"), "Anlamı göster (aktif hatırlama)"),
    "clickthrough": ("Ctrl+Alt+C", ord("C"), "Tıklama geçirgenliğini aç / kapat"),
}


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: "GlobalHotkeys"):
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):
        ids = self._owner._ids
        if IS_WINDOWS and ids and event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
            except (TypeError, ValueError):
                return False, 0
            if msg.message == WM_HOTKEY and msg.wParam in ids:
                self._owner.triggered.emit(ids[msg.wParam])
                return True, 0
        return False, 0


class GlobalHotkeys(QObject):
    triggered = Signal(str)

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._ids: dict[int, str] = {}
        self._filter = _NativeFilter(self)
        self._installed = False

    def register_all(self) -> list[str]:
        if not IS_WINDOWS:
            return []
        if not self._installed:
            self._app.installNativeEventFilter(self._filter)
            self._installed = True
        self.unregister_all()
        failed = []
        for i, (action, (label, vk, _)) in enumerate(HOTKEYS.items(), start=1):
            hk_id = 0xB000 + i
            ok = _user32.RegisterHotKey(None, hk_id, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, vk)
            if ok:
                self._ids[hk_id] = action
            else:
                failed.append(label)
        return failed

    def unregister_all(self):
        if not IS_WINDOWS:
            return
        for hk_id in list(self._ids):
            _user32.UnregisterHotKey(None, hk_id)
        self._ids.clear()
