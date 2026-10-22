# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["main.py"],
    datas=[("app/data/words", "app/data/words")],
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="EMG-English",
    icon="assets/emg.ico",
    console=False,
    upx=False,
)
