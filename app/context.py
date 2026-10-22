from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .database import Database
from .pronunciation import pronunciation_for
from .tts import Speaker


class AppContext(QObject):
    settingsChanged = Signal(str)
    progressChanged = Signal()
    wordsChanged = Signal()
    decksChanged = Signal()
    navigateRequested = Signal(str, dict)
    toastRequested = Signal(str)

    def __init__(self, db: Database, speaker: Speaker):
        super().__init__()
        self.db = db
        self.speaker = speaker
        self.overlay = None
        self.restart_app = None
        self.apply_tts_settings()

    def get(self, key: str, default=None):
        return self.db.get(key, default)

    def set(self, key: str, value):
        if self.db.get(key) == value:
            return
        self.db.set(key, value)
        self.settingsChanged.emit(key)

    def pron(self, word: dict) -> str:
        return pronunciation_for(word, self.db.get)

    def speak(self, text: str):
        self.speaker.speak(text)

    def apply_tts_settings(self):
        voice = self.get("app.tts_voice")
        if voice:
            self.speaker.set_voice(voice)
        self.speaker.set_rate(self.get("app.tts_rate"))

    def toast(self, message: str):
        self.toastRequested.emit(message)

    def navigate(self, page: str, **params):
        self.navigateRequested.emit(page, params)
