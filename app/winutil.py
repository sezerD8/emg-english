from __future__ import annotations

import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "EMGEnglish"

WM_NCCALCSIZE, WM_NCHITTEST, WM_NCACTIVATE = 0x0083, 0x0084, 0x0086
HTCLIENT, HTCAPTION = 1, 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 10, 11, 12, 13, 14, 15, 16, 17

FS_NONE, FS_WINDOWED, FS_EXCLUSIVE = "none", "fullscreen", "exclusive"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _shell32 = ctypes.windll.shell32
    try:
        _dwm = ctypes.windll.dwmapi
    except OSError:
        _dwm = None

    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.DefWindowProcW.restype = ctypes.c_ssize_t
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = wintypes.HMONITOR

    HWND_TOPMOST = wintypes.HWND(-1)
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0004, 0x0010
    SWP_FRAMECHANGED, SWP_NOOWNERZORDER = 0x0020, 0x0200
    GWL_STYLE = -16
    WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
    WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
    SM_CXSIZEFRAME, SM_CYSIZEFRAME, SM_CXPADDEDBORDER = 32, 33, 92
    MONITOR_DEFAULTTONEAREST = 2

    class MARGINS(ctypes.Structure):
        _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]

    class NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]


def force_topmost(win_id: int):
    if not IS_WINDOWS or not win_id:
        return
    try:
        _user32.SetWindowPos(wintypes.HWND(int(win_id)), HWND_TOPMOST, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
    except Exception:
        pass


_IGNORED_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def monitor_of(hwnd: int) -> int:
    if not IS_WINDOWS or not hwnd:
        return 0
    try:
        return int(_user32.MonitorFromWindow(wintypes.HWND(int(hwnd)), MONITOR_DEFAULTTONEAREST) or 0)
    except Exception:
        return 0


def fullscreen_state(own_hwnds: set[int] | None = None) -> tuple[str, int]:
    if not IS_WINDOWS:
        return FS_NONE, 0
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd or (own_hwnds and int(hwnd) in own_hwnds):
            return FS_NONE, 0
        monitor = int(_user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) or 0)
        state = ctypes.c_int(0)
        if _shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0 and state.value == 3:
            return FS_EXCLUSIVE, monitor
        buf = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(hwnd, buf, 64)
        if buf.value in _IGNORED_CLASSES:
            return FS_NONE, 0
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        _user32.GetMonitorInfoW(monitor, ctypes.byref(mi))
        m = mi.rcMonitor
        if rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom:
            return FS_WINDOWED, monitor
    except Exception:
        pass
    return FS_NONE, 0


_hooks: list = []


def install_foreground_hook(callback) -> bool:
    if not IS_WINDOWS:
        return False
    try:
        proc_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                       wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

        def _proc(_hook, _event, _hwnd, _obj, _child, _thread, _time):
            try:
                callback()
            except Exception:
                pass

        proc = proc_type(_proc)
        _user32.SetWinEventHook.restype = wintypes.HANDLE
        handle = _user32.SetWinEventHook(0x0003, 0x0003, None, proc, 0, 0, 0)
        if not handle:
            return False
        _hooks.append((handle, proc))
        return True
    except Exception:
        return False


def _dwm_set(hwnd: int, attr: int, value: int):
    if _dwm is None:
        return
    v = ctypes.c_int(value)
    try:
        _dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


def set_dark_titlebar(hwnd: int):
    if IS_WINDOWS and hwnd:
        _dwm_set(int(hwnd), 20, 1)
        _dwm_set(int(hwnd), 19, 1)


def enable_native_frame(hwnd: int):
    if not IS_WINDOWS or not hwnd:
        return
    h = wintypes.HWND(int(hwnd))
    style = _user32.GetWindowLongPtrW(h, GWL_STYLE)
    style |= WS_THICKFRAME | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
    _user32.SetWindowLongPtrW(h, GWL_STYLE, style)
    if _dwm is not None:
        try:
            _dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(MARGINS(0, 0, 0, 1)))
        except Exception:
            pass
    set_dark_titlebar(int(hwnd))
    _dwm_set(int(hwnd), 33, 2)
    _user32.SetWindowPos(h, None, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def _frame_thickness(hwnd) -> int:
    try:
        dpi = _user32.GetDpiForWindow(hwnd) or 96
        return (_user32.GetSystemMetricsForDpi(SM_CXSIZEFRAME, dpi)
                + _user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi))
    except Exception:
        return _user32.GetSystemMetrics(SM_CXSIZEFRAME) + _user32.GetSystemMetrics(SM_CXPADDEDBORDER)


def window_dpi_scale(hwnd: int) -> float:
    try:
        return (_user32.GetDpiForWindow(wintypes.HWND(int(hwnd))) or 96) / 96
    except Exception:
        return 1.0


def handle_frame_message(message, caption_test) -> tuple[bool, int]:
    if not IS_WINDOWS:
        return False, 0
    msg = wintypes.MSG.from_address(int(message))
    hwnd = msg.hWnd
    if msg.message == WM_NCCALCSIZE:
        if msg.wParam:
            if _user32.IsZoomed(hwnd):
                params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
                t = _frame_thickness(hwnd)
                r = params.rgrc[0]
                r.left += t
                r.top += t
                r.right -= t
                r.bottom -= t
            return True, 0
        return False, 0
    if msg.message == WM_NCACTIVATE:
        return True, _user32.DefWindowProcW(hwnd, msg.message, msg.wParam, -1)
    if msg.message == WM_NCHITTEST:
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if not _user32.IsZoomed(hwnd):
            b = max(4, round(6 * window_dpi_scale(hwnd)))
            left, right = x < rect.left + b, x >= rect.right - b
            top, bottom = y < rect.top + b, y >= rect.bottom - b
            if top and left:
                return True, HTTOPLEFT
            if top and right:
                return True, HTTOPRIGHT
            if bottom and left:
                return True, HTBOTTOMLEFT
            if bottom and right:
                return True, HTBOTTOMRIGHT
            if left:
                return True, HTLEFT
            if right:
                return True, HTRIGHT
            if top:
                return True, HTTOP
            if bottom:
                return True, HTBOTTOM
        origin = wintypes.POINT(0, 0)
        _user32.ClientToScreen(hwnd, ctypes.byref(origin))
        scale = window_dpi_scale(hwnd)
        if caption_test((x - origin.x) / scale, (y - origin.y) / scale):
            return True, HTCAPTION
        return True, HTCLIENT
    return False, 0


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{exe}" "{main}" --minimized'


def autostart_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    if not IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
